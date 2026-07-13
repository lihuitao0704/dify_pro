"""
分类路由模块（重构版）
负责将意图映射到对应的处理方式（RAG / API / DB / LLM）

改动要点:
 1. handle_activity 拆为"纯查询 + 引导报名"：不做一次性收集，
    展示活动列表后引导用户进入报名流程（通过 lock_intent）。
 2. 新增 handle_activity_register：独立 Handler，通过 ActivityRegisterState
    进行多轮参数收集（activity 选择 → 姓名 → 手机号），is_ready 齐全后调 API。
 3. handle_course_recommendation 对齐新的 state.py 命名（course_recommendation_state）。
 4. INTENT_HANDLERS 增加 activity_register 条目（供 _continue_flow 调用）。
"""

import re

from customer_agent import llm
from customer_agent.config import config
from customer_agent.knowledge import get_kb

# user_profiles 表实际存在的、画像流程可写的列（对齐 DB schema）
_USER_PROFILE_COLS = {
    "name", "phone", "education", "target_major", "language_score",
    "target_country", "gpa", "budget", "age", "major", "wechat", "email",
    "consultation_status", "assess", "development", "abilities",
    "is_Closed-loop",
}


def _coerce_profile_value(field, val):
    """
    把 CourseRecommendationState 里字符串形式的值转成 DB 列类型。
    gpa → float, budget（"30万"）→ int(元), age → int，其余保持字符串。
    返回 None 表示"无效值、应跳过"。
    """
    if val is None or val == "":
        return None
    if field == "gpa":
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    if field == "budget":
        m = re.search(r"(\d+(?:\.\d+)?)", str(val))
        if not m:
            return None
        num = float(m.group(1))
        return int(num * 10000) if "万" in str(val) else int(num)
    if field == "age":
        try:
            return int(val)
        except (ValueError, TypeError):
            return None
    return val
from customer_agent.services import (
    sa_recommend, sa_get_courses, sa_save_profile,
    event_query, event_register,
)
from customer_agent import persist
from customer_agent.persona import get_random
from customer_agent.state import SessionState, ActivityRegisterState


# ============================================================
# Handler 类型定义
# ============================================================
# 每个 handler 签名: (message, params, context, session_state, conversation_id) -> str | None
HandlerFn = None  # 类型标注用


# ============================================================
# 统一 LLM 改写层
# 所有检索结果(FAQ/Knowledge)都经此函数 LLM 改写后再输出
# ============================================================
def _rewrite_with_llm(message: str, context: list, docs: list,
                      intent: str, sess, conv_id: str,
                      *, fallback: str = "") -> str:
    """检索结果统一经 LLM 改写后再输出,避免机械直出原文。

    Args:
        message: 用户原始问题
        context: 对话历史 (agent_reply 需要)
        docs:   检索得到的原文片段列表
        intent: 改写风格, 决定 instruction 模板
                "company_info"   公司介绍, 融合为有温度的概览段
                "company_service" 业务咨询, 具体说明服务项目
                "study_policy"   政策解读, 按维度分点
                "faq"            FAQ, 直接准确回答
        sess / conv_id: 保留扩展用
        fallback: LLM 离线/失败时的降级文本

    Returns:
        LLM 改写后的自然语言; LLM 不可用返回 fallback
    """
    # 配置开关: 关闭则直接拼接旧文 (运营回退用)
    if not config.FORCE_REWRITE:
        return fallback if fallback else "\n\n".join(docs)

    if not docs:
        if fallback:
            return fallback
        return get_random("guide_menu")

    # 拼接检索材料作为 instruction 的上下文
    ctx_text = "\n\n".join(docs)

    # 按意图选择改写模板
    if intent == "company_info":
        style_rules = (
            "1. 理解用户想了解什么(规模/历史/口碑/校区/团队/联系...),只提取直接相关的内容\n"
            "2. 把分散的材料融合成一段有温度的公司介绍,像聊天一样自然\n"
            "3. 2 条以内直接说;3 条以上用「· 」分点,每点一行\n"
            "4. 不超过 280 字,不说空话套话,不编造材料中没有的信息\n"
            "5. 材料中没有用户想要的细节时,诚实说「更详细的资料可以联系顾问获取」\n"
            "6. 语气亲切温暖,称呼用户为「同学」或「小伙伴」"
        )
    elif intent == "company_service":
        style_rules = (
            "1. 具体说明提供什么服务(留学申请/语培/背景提升/文书/签证等)\n"
            "2. 如果材料区分了不同业务线,先做简洁分类再展开\n"
            "3. 用具体信息(业务名、适合人群、价格区间)增加说服力,不要只讲空话\n"
            "4. 材料不足时补充一句「更详细的课程大纲/服务清单可以联系顾问获取」\n"
            "5. 不超过 280 字,不编造,语气专业温暖"
        )
    elif intent == "study_policy":
        style_rules = (
            "1. 理解用户想了解哪方面(语言要求? GPA? 签证流程? 就业政策?)\n"
            "2. 从材料中提取直接相关信息,用自己的话重新组织\n"
            "3. 按维度分点(语言要求/院校门槛/签证流程/就业/移民),每个维度一行\n"
            "4. 材料中没有确切数字的绝不能编造;可以说「建议上官网确认最新要求」\n"
            "5. 政策容易过时,务必加一句「具体以官方最新公告为准」或建议查询渠道\n"
            "6. 不超过 280 字,语气专业、不瞎承诺"
        )
    else:  # faq
        style_rules = (
            "1. FAQ 要答得直接、准确,开头就回答结论\n"
            "2. 用材料中的信息回答,不要照搬原文,用自己的话说清楚\n"
            "3. 涉及金额、时间、材料清单等,必须精确到材料中的数字,没有就不写\n"
            "4. 材料不够覆盖问题时,诚实告知详细情况可联系顾问,不要编造流程/价格\n"
            "5. 不超过 280 字,语气简洁专业"
        )

    instruction = (
        f"以下是参考材料(多段,可能来自不同文件):\n\n{ctx_text}\n\n"
        f"用户问题:「{message}」\n\n"
        f"★★★ 回答要求 ★★★\n{style_rules}"
    )

    # 优先走轻量改写（无人设 prompt，快 3-4 倍）；失败再回退到带人设的 agent_reply。
    reply = llm.rewrite_retrieval(message, docs, style=intent)
    if not reply:
        reply = llm.agent_reply(message, context, extra_instruction=instruction)
    return reply if reply else fallback


# ============================================================
# Handler: 公司信息咨询 → RAG(公司信息)
# ============================================================
def handle_company_info(message: str, params: dict, context: list,
                        sess: SessionState, conv_id: str) -> str:
    kb = get_kb()
    docs = kb.search_by_intent(message, "company_info", top_k=4)
    if not docs:
        return get_random("guide_menu")
    return _rewrite_with_llm(message, context, docs, "company_info", sess, conv_id)


# ============================================================
# Handler: 公司业务咨询 → RAG(公司业务)
# ============================================================
def handle_company_service(message: str, params: dict, context: list,
                           sess: SessionState, conv_id: str) -> str:
    kb = get_kb()
    docs = kb.search_by_intent(message, "company_service", top_k=4)
    if not docs:
        return get_random("guide_menu")

    # 同时查课程表补充信息,作为追加检索材料一起送 LLM 改写
    country = _extract_country(message)
    if country:
        data = sa_get_courses(country=country, limit=5)
        if data.get("code") == 0 and data.get("data"):
            courses = data["data"]
            extra = "课程体系：\n" + "\n".join(
                f"· {c.get('course_name','')} ({c.get('category','')}) "
                f"- {c.get('target_education','')} | "
                f"{c.get('language_requirement','无语言要求')} | "
                f"¥{c.get('price',0):,.0f}"
                for c in courses[:5]
            )
            docs = list(docs) + [extra]

    return _rewrite_with_llm(message, context, docs, "company_service", sess, conv_id)


# ============================================================
# Handler: 留学政策咨询 → RAG(留学政策)
# ============================================================
def handle_study_policy(message: str, params: dict, context: list,
                        sess: SessionState, conv_id: str) -> str:
    kb = get_kb()
    docs = kb.search_by_intent(message, "study_policy", top_k=4)
    if not docs:
        return ("关于留学政策我会尽可能回答。目前信息库还没收录这个子话题，"
                "建议你把具体问题说得再细一些，我帮你定位答案～")

    return _rewrite_with_llm(message, context, docs, "study_policy", sess, conv_id)


# ============================================================
# Handler: 课程与项目推荐 → 多轮参数收集 + API
# ============================================================
def handle_course_recommendation(message: str, params: dict, context: list,
                                 sess: SessionState, conv_id: str) -> str:
    """推荐流程：逐步收集画像参数，全部齐全后再调推荐 API

    收集顺序（一次问一个字段，flow-first 锁定直至齐全）：
      必填三件套 → 国家 → GPA → 预算 → 入学时间 → 工作/实习 → 年龄 → 微信

    逐步写入策略：
      - diff_new_fields 提取这一步新增的字段 → 立即 profile_upsert 写库
      - 写库成功后记录到 _saved_profile_fields，给用户"已记住 ✅"反馈
      - DB 不可用时降级为不写库（try/except 兜底），不阻塞对话
    """
    from customer_agent.state import CourseRecommendationState

    rec = sess.course_recommendation_state
    if rec is None:
        rec = CourseRecommendationState()
        sess.course_recommendation_state = rec

    # 从当前消息提取参数，并 diff 出这一步新增的字段
    new_fields = rec.diff_new_fields(message)

    # 🆕 每提取一个新字段，立即写入画像（失败则降级为纯内存）
    # 字段名映射：state 内部名 → user_profiles 列名
    # state 内部字段名 → user_profiles 列名 映射
    _FIELD_MAP = {
        "education": "education",
        "target_major": "target_major",
        "language_score": "language_score",
        "country": "target_country",
        "gpa": "gpa",
        "budget": "budget",
        "intake": "intake",                   # 不在 user_profiles，仅保留内存
        "work_experience": "work_experience", # 不在 user_profiles，仅保留内存
        "age": "age",
        "wechat": "wechat",
    }
    if new_fields:
        mapped = {_FIELD_MAP.get(k, k): v for k, v in new_fields.items()}
        for k, v in mapped.items():
            # DB 列类型对齐：gpa → float, budget → int（元）
            v = _coerce_profile_value(k, v)
            if v is None:
                continue
            # 跳过 DB 中不存在的列（intake / work_experience 不在 user_profiles）
            if k not in _USER_PROFILE_COLS:
                continue
            if k not in sess.profile_slots:
                sess.profile_slots[k] = v
                sess._dirty_profile_fields.add(k)
                sess._saved_profile_fields.add(k)

    # ── Phase 1: 逐步追问，直到所有画像字段都收集齐 ────────────
    # 顺序：必填三件套 → 国家 → GPA → 预算 → 入学时间 → 工作/实习 → 年龄 → 微信
    # 每轮只追问一个字段，用户回复后回到这里继续下一个（flow-first 锁定）。
    missing = rec.next_missing_field()
    if missing:
        rec.phase = "required" if missing in rec._REQUIRED_FIELDS else "enrichment"
        sess.lock_intent("course_recommendation")
        feedback = sess.saved_profile_summary()
        question = rec.get_question(missing)
        # 首条引导语（无任何已收集信息时出现一次）
        head = (
            "好的！为了给你推荐最合适的留学项目，我需要了解几个信息：\n\n"
            if not feedback else ""
        )
        tail = "\n\n也可以直接告诉我你的完整背景哦～"
        return ((feedback + "\n\n" if feedback else "")
                + head + question + tail)

    # ── 所有字段齐全 → 调推荐 API（诉求 1）────────────────────
    # 已经展示过推荐结果（phase 已是 recommend）则不再重复调 API，
    # 直接把用户回复当作对推荐结果的回应（提取新参数 / 回答追问）。
    if rec.phase == "recommend":
        # 推荐已展示过，本轮只提取用户回复中的新参数写库，然后保持锁定。
        sess.lock_intent("course_recommendation")
        # 可以给一个简短确认 + 引导留联系方式（如果还没有）
        if not rec.name or not rec.phone:
            from customer_agent.persona import get_random
            return ("收到！已更新你的信息 ✅\n"
                    "有感兴趣的项目可以继续问我，或者留下[姓名 手机号]，"
                    "稍后专属顾问为你定制方案并回电 📞\n\n"
                    + get_random("after_recommend"))
        return "好的，已记住你的更新 ✅ 还有想了解的吗？"

    rec.phase = "recommend"
    # 注意：此处不解锁。推荐结果出来后若需要追问（≥3门课），
    # 必须保持 flow 锁定，否则下一轮用户回复无法路由回这里继续收集。

    # 最终把完整参数同步到会话级 profile_slots（统一由 agent.py sync 写库）
    # 注意：rec.gpa/rec.budget 是字符串形式，需转成 DB 列类型（gpa=decimal, budget=int元）
    _gpa = None
    if rec.gpa:
        try:
            _gpa = float(rec.gpa)
        except (ValueError, TypeError):
            _gpa = None
    _budget = None
    if rec.budget:
        m = re.search(r"(\d+(?:\.\d+)?)", rec.budget)
        if m:
            _budget = int(float(m.group(1)) * 10000) if "万" in rec.budget else int(float(m.group(1)))
    _final_map = {
        "education": rec.education,
        "target_major": rec.target_major,
        "language_score": rec.language_score,
        "target_country": rec.country,
        "gpa": _gpa,
        "budget": _budget,
        "age": rec.age,
        "wechat": rec.wechat,
    }
    for k, v in _final_map.items():
        if v is not None and k not in sess.profile_slots:
            # 跳过 DB 中不存在的列（intake / work_experience 不在 user_profiles）
            if k not in _USER_PROFILE_COLS:
                continue
            sess.profile_slots[k] = v
            sess._dirty_profile_fields.add(k)
    sess._saved_profile_fields.update(k for k, v in _final_map.items() if v is not None)

    # 兜底：同步画像到本地 study abroad 画像服务
    sa_save_profile({
        "conversation_id": conv_id,
        "education": rec.education,
        "target_major": rec.target_major,
        "language_score": rec.language_score,
        "target_country": rec.country,
        "gpa": rec.gpa,
        "budget": rec.budget,
        "age": rec.age,
        "wechat": rec.wechat,
    })

    rec_result = sa_recommend(conv_id)
    if rec_result.get("code") != 0 or not rec_result.get("data"):
        # API 失败/无数据 → 降级为直接查课程 → 流程结束，解锁
        sess.unlock_intent()
        courses = sa_get_courses(country=rec.country, limit=5)
        if courses.get("data"):
            lines = ["基于你的背景，目前匹配到的课程有：\n"]
            for c in courses["data"][:5]:
                lines.append(
                    f"· **{c.get('course_name','')}** ({c.get('category','')})\n"
                    f"  学历: {c.get('target_education','')} | "
                    f"语言: {c.get('language_requirement','无要求')} | "
                    f"¥{c.get('price',0):,.0f}"
                )
            lines.append("\n有感兴趣的可以免费试听或预约顾问一对一咨询～")
            return "\n".join(lines)
        return "目前暂未找到完全匹配的项目，建议直接联系顾问定制方案～"

    recs = rec_result["data"].get("recommendations", [])[:5]
    if not recs:
        # API 返回空推荐 → 流程结束，解锁
        sess.unlock_intent()
        return "目前没有完全匹配你背景的项目，建议直接咨询顾问定制～"

    lines = ["🎯 基于你的背景，为你推荐以下项目：\n"]
    for i, r in enumerate(recs, 1):
        lines.append(f"**{i}. {r.get('course_name','')}**")
        lines.append(f"   国家: {r.get('country','')} | "
                     f"方向: {r.get('sub_category','')}")
        lines.append(f"   适合: {r.get('target_education','')} | "
                     f"语言: {r.get('language_requirement', '无硬性要求')}")
        lines.append(f"   价格: ¥{r.get('price',0):,.0f}")
        if r.get("reasons"):
            lines.append(f"   匹配原因: {'、'.join(r['reasons'])}")
        lines.append("")

    # ── 推荐课程多时 → 主动追问细化 OR 收集联系方式（诉求 2）──
    has_followup = False  # 本轮是否抛出了追问（决定后续是否保持流锁定）
    if len(recs) >= 3:
        # 从当前消息里尝试提取姓名/手机
        if not rec.name:
            m = re.search(r"(?:我叫|姓名|名字|叫|名为)[：:\s]*([一-龥]{2,4})", message)
            if m:
                rec.name = m.group(1)
                sess.profile_slots["name"] = rec.name
                sess._dirty_profile_fields.add("name")
        if not rec.phone:
            m = re.search(r"(1[3-9]\d{9})", message)
            if m:
                rec.phone = m.group(0)
                sess.profile_slots["phone"] = rec.phone
                sess._dirty_profile_fields.add("phone")

        if rec.name or rec.phone:
            # 已拿到联系方式 → 提示专人服务 → 流程结束
            tip = "\n📞 稍后我们会有专属顾问根据您的背景为您定制方案"
            if rec.phone:
                tip += f"并回电 {rec.phone}"
            tip += "，请保持手机畅通～"
            lines.append(tip)
        else:
            # 没联系方式 → 追问 GPA/预算/联系方式 →【保持流锁定】
            has_followup = True
            lines.append(
                "\n项目比较多，为了给您精准推荐，可以补充一下：\n"
                "• GPA 或均分是多少？\n"
                "• 留学预算大概多少？\n"
                "或者直接告诉我「姓名 手机号」，稍后专属顾问为您定制方案并回电 📞"
            )
    else:
        # 少量课程时的普通转化尾巴
        lines.append("\n感兴趣的可以继续详细了解，或者预约留学顾问一对一深度咨询 🎓")

    # ── 流程收尾：有追问则保持锁定（等用户回复），否则解锁 ──────
    if has_followup:
        # 保持 course_recommendation 锁定 + state 存活，
        # agent.py flow-first 会把下一轮用户消息继续路由到这里。
        sess.lock_intent("course_recommendation")
    else:
        sess.unlock_intent()

    return "\n".join(lines)


# ============================================================
# Handler: 活动与讲座查询 → API（原 handle_activity，拆分为纯查询）
# ============================================================
def handle_activity(message: str, params: dict, context: list,
                    sess: SessionState, conv_id: str) -> str:
    """
    活动/讲座查询 — 重构版：
    - 只负责查询和展示
    - 不再尝试在当前 handler 内完成报名
    - 结果缓存到 session.last_activity_results，供后续 activity_register 使用
    - 展示后引导用户表达报名意愿
    """
    # 判断是查询还是有报名意愿
    is_register_intent = any(kw in message for kw in
                              ["报名", "预约", "我要", "register"])

    if is_register_intent and sess.last_activity_results:
        # 有缓存结果 + 用户想报名 + 已指定具体活动 → 直接转入报名流程
        if _resolve_activity(message, sess.last_activity_results):
            return _enter_activity_register_from_cached(message, sess)
        # 有缓存 + 想报名但没指定哪条 → 展示缓存列表引导选择
        return (_format_cached_activities(sess.last_activity_results) +
                "\n\n想报名哪条呢？告诉我序号（如「第一个」）或活动名就行～")

    # ── 查询模式 ──
    result = event_query(f"查询 {_build_event_filter(message)} 活动和讲座")
    if result.get("result", {}).get("type") == "error":
        return ("活动查询暂时不可用，建议关注我们的公众号第一时间获取活动通知～"
                "\n也可以拨打前台电话由人工协助查询和报名 🎓")

    polished = result.get("polished", "")

    # 缓存结构化数据，方便后续报名选序号
    raw_data = result.get("data", [])
    if isinstance(raw_data, list) and raw_data:
        sess.last_activity_results = raw_data
    elif isinstance(raw_data, dict):
        sess.last_activity_results = raw_data.get("items",
                                         raw_data.get("activities",
                                                     raw_data.get("list", [])))
    else:
        sess.last_activity_results = []

    # 查到结果 + 用户想报名：仅当消息中已指定具体活动时才一步进入报名，
    # 否则先展示列表让用户选（避免把下一句姓名误当活动）
    if sess.last_activity_results and is_register_intent:
        if _resolve_activity(message, sess.last_activity_results):
            return _enter_activity_register_from_cached(message, sess)
        return (polished +
                "\n\n想报名哪条呢？告诉我序号（如「第一个」）或活动名就行～")

    if polished:
        return (polished +
                "\n\n感兴趣的话告诉我就行，比如「报名第一个 姓名 手机号」📅")
    return get_random("guide_menu")


def _enter_activity_register_from_cached(message: str, sess: SessionState) -> str:
    """从已缓存的活动列表 + 用户报名意愿，转入报名流程"""
    from customer_agent.router import handle_activity_register
    # 初始化报名状态 + 锁定意图
    sess.lock_intent("activity_register")
    reg = sess.activity_register_state
    # 注入 register_kind（根据缓存结果的 key 区分 lecture / activity）
    sess.register_kind = _detect_register_kind(sess.last_activity_results)
    # 关键：先把缓存结果注入 reg，否则 resolve_index / resolve_name 无从映射
    reg.last_query_results = sess.last_activity_results
    # 尝试解析"第N个"
    reg.resolve_index(message)
    if not reg.activity_id and not reg.activity_name:
        # 尝试用活动名匹配
        reg.resolve_name(message)

    # 把报名意愿也带入后续收集（conv_id 从会话状态取，不再写死 "0"）
    return handle_activity_register(message, {}, sess.get_context(),
                                     sess, sess.conversation_id)


def _resolve_activity(message: str, last_results: list) -> bool:
    """试探消息是否能在 last_results 中匹配到具体活动（序号或活动名）。"""
    if not last_results:
        return False
    probe = ActivityRegisterState()
    probe.last_query_results = last_results
    probe.resolve_index(message)
    if probe.activity_id or probe.activity_name:
        return True
    probe.resolve_name(message)
    return bool(probe.activity_id or probe.activity_name)


def _format_cached_activities(last_results: list) -> str:
    """把缓存的活动/讲座列表拼成可读文本（复用直查结果的展示格式）。"""
    if not last_results:
        return "暂时查不到活动信息，请稍后重试"
    lines = ["为您找到以下活动和讲座：\n"]
    for i, r in enumerate(last_results, 1):
        kind = "讲座" if r.get("kind") == "lecture" else "活动"
        lines.append(
            f"{i}. 【{kind}】{r.get('title', '')}\n"
            f"   时间: {r.get('event_time', '待定')} | 地点: {r.get('location', '待定')}"
            + (f" | 主讲: {r['speaker']}" if r.get("speaker") else "")
        )
    return "\n".join(lines)


def _detect_register_kind(last_results: list) -> str:
    """根据缓存结果的首条 item 的 key 判断本次报名是 lecture 还是 activity。"""
    if not last_results:
        return "activity"
    first = last_results[0]
    if "lecture_id" in first:
        return "lecture"
    return "activity"


# ============================================================
# 🆕 Handler: 活动报名信息收集（多轮）
# ============================================================
def handle_activity_register(message: str, params: dict, context: list,
                             sess: SessionState, conv_id: str) -> str:
    """
    活动/讲座报名 — 独立多轮收集 Handler（逐步写库版）

    流程（对齐方案 a：先选活动 → 再收人 → 写表）:
      1. 选活动：diff_new_activity → 反馈"已锁定活动 XXX ✅"
      2. 收姓名/手机：diff_new_person → 每收一个就 profile_upsert 写入画像 → 反馈"已记住：姓名=xxx ✅"
      3. is_ready → 写 lecture/activity_registrations（去重预检）→ 解锁
      DB 不可用时降级为原 NL2SQL 路径（try/except 兜底，不阻塞对话）
    """
    reg = sess.activity_register_state
    if reg is None:
        reg = ActivityRegisterState()
        sess.activity_register_state = reg
        # 首次进入：尝试从缓存结果推断 register_kind
        if sess.register_kind is None:
            sess.register_kind = _detect_register_kind(sess.last_activity_results)

    # 注入最近查询结果缓存（resolve_index/resolve_name 使用）
    if not reg.last_query_results and sess.last_activity_results:
        reg.last_query_results = sess.last_activity_results

    # ── 反馈文案拼接（收集到新信息时回显给用户）──
    feedback_parts = []

    # ── 第一步：选活动（仅当活动未定时才解析）──
    has_activity = bool(reg.activity_id or reg.activity_name or reg.activity_index >= 0)
    new_activity = None
    if not has_activity:
        new_activity = reg.diff_new_activity(message)
        if new_activity:
            activity_name = (
                persist.activity_get_name(new_activity["activity_id"])
                if sess.register_kind == "activity"
                else persist.lecture_get_name(new_activity["activity_id"])
            )
            activity_name = activity_name or new_activity["activity_name"]
            feedback_parts.append(f"已为你锁定活动 **{activity_name}** ✅")

    # ── 第二步：收集姓名/手机 → 每收一个就存画像 ──
    new_person = reg.diff_new_person(message)
    if new_person:
        try:
            persist.profile_upsert(conv_id, new_person)
            sess._saved_profile_fields.update(new_person.keys())
        except Exception as e:
            print(f"[Router] profile_upsert 失败（降级内存模式）: {e}")
        for k, v in new_person.items():
            label = "姓名" if k == "name" else "手机"
            feedback_parts.append(f"{label}={v}")
        # 给一个聚合的"已记住"小尾巴（仅当没有活动锁定时，避免重复）
        if not new_activity:
            pass  # 由下方 saved_profile_summary 展示

    # ── 第三步：全部齐全 → 写 *_registrations + 去重 ──
    if reg.is_ready():
        sess.unlock_intent()
        ref_id = reg.activity_id
        is_lecture = sess.register_kind == "lecture"
        table = "lecture_registrations" if is_lecture else "activity_registrations"
        try:
            if persist.has_registered(table, ref_id, reg.name, reg.phone):
                return ("你已报名过这项活动啦，无需重复报名～\n"
                        f"（{reg.name} / {reg.phone}）")
            result = (persist.lecture_register if is_lecture
                      else persist.activity_register)(ref_id, reg.name, reg.phone)
        except Exception as e:
            # DB 不可用 → 降级回原 NL2SQL 路径
            print(f"[Router] 报名写库失败，降级 NL2SQL: {e}")
            return _fallback_nl2sql_register(reg, sess)

        if result["ok"]:
            return _build_register_success(reg)
        if result.get("reason") == "duplicate":
            return (f"你已报名过这项活动啦，无需重复报名～\n"
                    f"（{reg.name} / {reg.phone}）")
        return (f"报名失败：{result.get('msg', '未知错误')}\n"
                f"建议直接电话微信联系顾问协助报名")

    # ── 中间态：缺字段 → 追问（顶部展示"已记住"反馈）──
    sess.lock_intent("activity_register")
    missing = reg.next_missing_field()
    question = reg.get_question(missing)

    # 组合：活动锁定 + 个人信息追记（如有），都在追问之前
    head_parts = list(feedback_parts)
    # 补充一个"已记住："聚合（当用户已提供部分个人信息时）
    if sess._saved_profile_fields and not new_activity:
        summary = sess.saved_profile_summary()
        if summary:
            head_parts.insert(0, summary)

    head = ("\n\n".join(head_parts) + "\n\n") if head_parts else ""
    return head + question


def _fallback_nl2sql_register(reg: ActivityRegisterState,
                              sess: SessionState) -> str:
    """DB 不可用时的降级路径：沿用原 NL2SQL 调用 Event&Lecture 服务。"""
    is_lecture = getattr(sess, "register_kind", "activity") == "lecture"
    nl = f"报名{'讲座' if is_lecture else '活动'}，姓名{reg.name}，手机号{reg.phone}"
    if reg.activity_name:
        nl += f"，{'讲座' if is_lecture else '活动'}名称{reg.activity_name}"
    if reg.activity_id:
        nl += f"，{'讲座' if is_lecture else '活动'}ID{reg.activity_id}"
    result = event_register(nl)
    if result.get("result", {}).get("type") == "error":
        return (f"报名遇到了点问题：{result['result'].get('message', '未知错误')}\n"
                f"建议直接电话微信联系顾问协助报名")
    return (f"报名成功！✅\n{result.get('polished', '')}\n\n"
            f"期待你的参与～有任何变动随时联系我哦 😊")


def _build_register_success(reg: ActivityRegisterState) -> str:
    """拼接报名成功页：活动详情 + 报名人信息，给用户一个完整结果。"""
    kind_label = "讲座" if reg.kind == "lecture" else "活动"
    lines = [
        f"🎉 报名成功！✅\n",
        f"📌 {kind_label}：{reg.activity_name}",
    ]
    if reg.event_time:
        lines.append(f"🕒 时间：{reg.event_time}")
    if reg.location:
        lines.append(f"📍 地点：{reg.location}")
    if reg.speaker:
        lines.append(f"🎤 主讲：{reg.speaker}")
    lines.append(f"\n👤 姓名：{reg.name}")
    lines.append(f"📱 手机：{reg.phone}")
    lines.append(f"\n期待你的参与～有任何变动随时联系我 😊")
    return "\n".join(lines)


# ============================================================
# Handler: FAQ → RAG(高频问题FAQ)
# ============================================================
def handle_faq(message: str, params: dict, context: list,
               sess: SessionState, conv_id: str) -> str:
    # 安全兜底：如果消息明确问的是课程/活动，FAQ 知识库里没有这些实时数据，
    # 直接转到对应接口处理，避免检索 FAQ 得到无关内容。
    from customer_agent.intent import _COURSE_KW, _ACTIVITY_KW
    _msg = message
    if any(kw in _msg for kw in _COURSE_KW):
        return handle_course_recommendation(message, params, context, sess, conv_id)
    if any(kw in _msg for kw in _ACTIVITY_KW):
        return handle_activity(message, params, context, sess, conv_id)

    kb = get_kb()
    # FAQ 精确匹配（优先）→ 统一走 LLM 改写, 不再原样输出
    ans = kb.faq_match(message)
    if ans:
        return _rewrite_with_llm(
            message, context, [ans], "faq", sess, conv_id,
            fallback=ans + "\n\n还有疑问可以继续问我哈 💪"
        )

    # FAQ 语义搜 → 统一走 LLM 改写
    docs = kb.search_by_intent(message, "faq", top_k=3)
    if docs:
        return _rewrite_with_llm(message, context, docs, "faq", sess, conv_id)

    # 材料搜索也没命中
    return ("这个问题我不太确定最准确的答案。建议你：\n"
            "1. 把问题说得再细一些（比如具体国家、阶段），我再帮你定位\n"
            "2. 或预约专属顾问一对一解答 🎓")


# ============================================================
# Handler: 闲聊 → LLM
# ============================================================
def handle_chat(message: str, params: dict, context: list,
                sess: SessionState, conv_id: str) -> str:
    rounds = sess.round_count()

    # 情感维系：多轮无转化 → 自然引导
    if rounds >= 5:
        import random
        if random.random() < 0.4:
            return get_random("conversion_pivot")

    # 道别场景
    if any(kw in message for kw in ["再见", "拜拜", "bye", "好的谢谢",
                                      "谢谢了", "没问题了"]):
        return get_random("goodbye")

    # 无菜单引导
    if any(kw in message for kw in ["不确定", "不知道", "没想好", "随便"]):
        return get_random("guide_menu")

    hint = ""
    if sess.last_topic and rounds >= 3:
        hint = f"\n用户之前聊过{sess.last_topic}，闲聊自然引导话题回来"

    instruction = (
        f"闲聊回复，像朋友聊天一样自然。\n"
        f"要求：\n"
        f"1. 开头先热情回应对方（道谢/打招呼/道别的回复）\n"
        f"2. 中间可以自然承接，但不要生硬推销业务\n"
        f"3. 结尾可以用开放式问题把对话延续回来（如问想了解哪个方向）\n"
        f"4. 不超过 150 字，不要超过 3 行\n"
        f"5. 禁止使用模板套话（如'有什么可以帮您的'式的客服腔）\n"
        f"{hint}"
    )

    return llm.agent_reply(
        message, context,
        extra_instruction=instruction,
    )


# ============================================================
# 辅助函数
# ============================================================
def _extract_country(message: str) -> str:
    if "德国" in message or "german" in message.lower():
        return "德国"
    if "新加坡" in message or "singapore" in message.lower():
        return "新加坡"
    return ""


def _build_event_filter(message: str) -> str:
    filters = []
    country = _extract_country(message)
    if country:
        filters.append(country)
    for kw in ["留学", "讲座", "分享会", "招生官", "说明会", "见面会", "答疑"]:
        if kw in message:
            filters.append(kw)
    return " ".join(filters) if filters else "所有"


# ============================================================
# 意图 → Handler 映射表
# ============================================================
INTENT_HANDLERS = {
    "company_info":          handle_company_info,
    "company_service":       handle_company_service,
    "business_query":        handle_company_service,    # 兼容旧名称
    "study_policy":          handle_study_policy,
    "policy":                handle_study_policy,       # 兼容旧名称
    "course_recommendation": handle_course_recommendation,
    "recommend":             handle_course_recommendation,  # 兼容旧名称
    "activity":              handle_activity,
    "event":                 handle_activity,           # 兼容旧名称
    "activity_register":     handle_activity_register,  # 🆕 供 _continue_flow 调用
    "faq":                   handle_faq,
    "chat":                  handle_chat,
}


# ============================================================
# 意图 → 处理方式类型
# ============================================================
# RAG 型：需要检索知识库后 LLM 生成
# API 型：直接调用外部接口
# DB 型：需要多轮收集后写入数据库
# LLM 型：纯 LLM 对话
INTENT_PROCESSING_TYPE = {
    "company_info":          "rag",
    "company_service":       "rag",
    "business_query":        "rag",
    "study_policy":          "rag",
    "policy":                "rag",
    "course_recommendation": "api",
    "recommend":             "api",
    "activity":              "api",
    "event":                 "api",
    "activity_register":     "db",   # 🆕
    "faq":                   "rag",
    "chat":                  "llm",
}
