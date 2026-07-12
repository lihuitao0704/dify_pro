"""
客服Agent主脑
流程：消息入口 → 意图识别 → 7场景Handler调度 → 多轮参数收集 → 回复生成
支持：单意图/多意图/追问继承/多轮槽位填充
"""

import json
import re
from datetime import datetime
from customer_agent import llm, intent as intent_mod
from customer_agent.knowledge import get_kb
from customer_agent.bridge import (
    sa_recommend, sa_get_courses, sa_save_profile,
    event_query, event_register,
)
from customer_agent.persona import CUSTOMER_SERVICE_PERSONA, get_random


# ============================================================
# 会话管理（内存版，可后续替换为Redis/DB）
# ============================================================
_sessions: dict = {}  # session_id → {history, slots, intent_state}


def new_session_id() -> str:
    import uuid
    return uuid.uuid4().hex[:16]


def get_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "history": [],
            "slots": {},                 # 多轮收集的参数
            "last_intents": [],          # 上一轮意图，用于追问继承
            "last_topic": "",            # 上一轮主话题
            "followup_rounds": 0,        # 已追问轮次
            "created_at": datetime.now().isoformat(),
        }
    return _sessions[session_id]


def save_turn(session_id: str, user_msg: str, reply: str,
             intents: list = None):
    sess = get_session(session_id)
    sess["history"].append({
        "role": "user",
        "content": user_msg,
        "ts": datetime.now().isoformat(),
    })
    sess["history"].append({
        "role": "assistant",
        "content": reply,
        "ts": datetime.now().isoformat(),
    })
    if intents:
        sess["last_intents"] = [i["intent"] for i in intents]
        business = [i for i in intents if i["intent"] != "chat"]
        if business:
            sess["last_topic"] = business[0]["intent"]


def get_context(session_id: str) -> list:
    """返回最近 N 轮对话上下文"""
    sess = get_session(session_id)
    return sess["history"][-12:]


# ============================================================
# 主入口
# ============================================================
def process_message(message: str, session_id: str = None,
                    conversation_id: str = "0") -> dict:
    """
    处理一条访客消息

    参数:
        message: 自然语言
        session_id: 会话ID（None自动新建）
        conversation_id: Dify会话ID（用于关联用户画像）

    返回: {reply, intents, session_id, actions}
    """
    if not session_id:
        session_id = new_session_id()
    sess = get_session(session_id)
    context = get_context(session_id)

    # Step 1: 意图识别
    raw_intents = intent_mod.classify_intent(
        llm_chat_fn=llm.chat,
        llm_chat_json_fn=llm.chat_json,
        user_msg=message,
        context=context,
    )
    filtered = intent_mod.filter_low_confidence(raw_intents)
    sorted_intents = intent_mod.sort_by_priority(filtered)

    # Step 2: 追问短句继承上一轮主话题
    _maybe_inherit_intent(message, sorted_intents, sess)

    # Step 3: 调度各Handler
    actions = []
    partial_replies = []
    for item in sorted_intents:
        handler = INTENT_HANDLERS.get(item["intent"])
        if handler:
            try:
                result = handler(
                    message, item.get("params", {}),
                    context, sess, conversation_id,
                )
                if result:
                    partial_replies.append(result)
                    actions.append({"intent": item["intent"], "result": "ok"})
            except Exception as e:
                print(f"[Agent] Handler {item['intent']} 异常: {e}")
                actions.append({"intent": item["intent"], "result": "error",
                                "error": str(e)})

    # Step 4: 合成最终回复
    reply = _build_final_reply(
        message, sorted_intents, partial_replies, context, sess,
    )

    # 离线兜底：回复为空串时走规则话术
    if not reply or not reply.strip():
        from .persona import get_random
        reply = _offline_fallback(message, sorted_intents, sess)

    # Step 5: 记录
    save_turn(session_id, message, reply, sorted_intents)

    return {
        "reply": reply,
        "intents": sorted_intents,
        "session_id": session_id,
        "actions": actions,
    }


def _offline_fallback(message: str, intents: list, sess: dict) -> str:
    """LLM离线时的规则兜底回复"""
    primary = intents[0]["intent"] if intents else "chat"

    # FAQ 直接走知识库答案（KB离线也能用）
    if primary == "faq":
        kb = get_kb()
        ans = kb.faq_match(message)
        if ans:
            return ans + "\n\n还有其他问题可以继续问我哈~"
        docs = kb.search(message, top_k=2)
        if docs:
            # 直接把知识库片段作为简洁回复
            return docs[0][:280]

    # 公司信息：给知识库片段
    if primary == "company_info":
        kb = get_kb()
        docs = kb.search(message, top_k=2)
        if docs:
            return docs[0][:280]

    # 政策：给知识库片段
    if primary == "policy":
        kb = get_kb()
        docs = kb.search(message, top_k=2)
        if docs:
            return docs[0][:280]

    # 活动服务未启动
    if primary == "event":
        return ("活动查询暂时不可用，建议关注我们的公众号第一时间获取活动通知~"
                "\n也可以拨打前台电话由人工协助查询和报名 🎓")

    # 闲聊/兜底
    from .persona import get_random
    return get_random("guide_menu") + ("\n(LLM离线模式，回复质量受限，"
                                    "请稍后再试或拨打热线，谢谢谅解 🙏)")


def _maybe_inherit_intent(message: str, intents: list, sess: dict):
    """短追问继承上一轮主话题"""
    if not intents or not sess.get("last_topic"):
        return
    short_followup = len(message) <= 15 and any(
        kw in message for kw in ["帮我", "预约", "联系", "怎么",
                                  "多少钱", "多久", "还有", "有没有"]
    )
    curr = intents[0]["intent"]
    if short_followup and curr == "chat":
        intents[0]["intent"] = sess["last_topic"]


def _build_final_reply(user_msg, intents, partials, context, sess) -> str:
    """合成最终回复文本"""
    is_multi = intent_mod.is_multi_intent(intents)
    primary = intents[0]["intent"] if intents else "chat"

    if not partials or primary == "chat":
        # 闲聊/兜底：走人设prompt
        hint = ""
        if sess.get("last_topic") != "chat":
            hint = f"\n学生可能对{sess['last_topic']}有兴趣，闲聊时可自然引导"
        return llm.agent_reply(user_msg, context,
                               extra_instruction=hint)

    if is_multi and len(partials) > 1:
        # 多意图融合
        instruction = (
            "用户一句话包含多个意图。请把以下多个结果融合成一段自然流畅的回复，"
            "像正常对话一样，不要分点列举，不超过280字。\n\n"
            + "\n---\n".join(partials)
        )
        return llm.agent_reply(user_msg, context,
                               extra_instruction=instruction)

    return partials[0]


# ============================================================
# Handler: 公司信息咨询
# ============================================================
def _handle_company_info(message, params, context, sess, conv_id):
    kb = get_kb()
    docs = kb.search(message, top_k=3)
    if not docs:
        return get_random("guide_menu")
    ctx_text = "\n\n".join(docs)
    instruction = (
        f"基于以下公司信息材料回答访客问题。\n\n{ctx_text}\n\n"
        "要求：简洁有力，不超过280字，官网语气但温暖。"
    )
    return llm.agent_reply(message, context, extra_instruction=instruction)


# ============================================================
# Handler: 业务查询
# ============================================================
def _handle_business_query(message, params, context, sess, conv_id):
    kb = get_kb()
    docs = kb.search(message, top_k=3)
    ctx_text = "\n\n".join(docs) if docs else ""

    # 同时查课程表补充信息
    country = _extract_country(message)
    extra = ""
    if country:
        data = sa_get_courses(country=country, limit=5)
        if data.get("code") == 0 and data.get("data"):
            courses = data["data"]
            extra = "\n\n课程体系：\n" + "\n".join(
                f"· {c.get('course_name','')} ({c.get('category','')}) "
                f"- {c.get('target_education','')} | "
                f"{c.get('language_requirement','无语言要求')} | "
                f"¥{c.get('price',0):,.0f}"
                for c in courses[:5]
            )

    instruction = (
        f"基于以下公司介绍和业务材料回答。\n\n{ctx_text}{extra}\n\n"
        "如涉及超出材料范围的内容，如实说'可以联系顾问详解'，不要编造。"
    )
    return llm.agent_reply(message, context, extra_instruction=instruction)


# ============================================================
# Handler: 政策查询
# ============================================================
def _handle_policy(message, params, context, sess, conv_id):
    kb = get_kb()
    docs = kb.search(message, top_k=4)
    if not docs:
        return ("关于德/新留学政策我会尽可能回答。目前信息库还没收录这个子话题，"
                "建议你把具体问题说得再细一些，我帮你定位答案～")

    country = _extract_country(message)
    ctx_text = "\n\n".join(docs)
    hint = f"目标国家：{country}" if country else "目标国家未明确，做德新对比"
    instruction = (
        f"基于以下政策材料回答问题。{hint}\n\n{ctx_text}\n\n"
        "要求：分点清晰（如签证、院校门槛、语言要求、就业政策），"
        "不确定的务必标注官方查询渠道。"
    )
    return llm.agent_reply(message, context, extra_instruction=instruction)


# ============================================================
# Handler: 课程/项目推荐
# ============================================================
def _handle_recommend(message, params, context, sess, conv_id):
    slots = sess["slots"]

    # 从当前消息提取参数，累加到 slots
    _collect_recommend_slots(message, slots)

    # 必须齐全的核心字段（与推荐引擎评分维度对齐）
    # 学历(30) + 专业(35) + 语言(20) + 国家(10) = 95/100 分依赖这四个字段
    required = ["education", "target_major", "language_score", "target_country"]
    missing = [f for f in required if not slots.get(f)]

    # 追问轮次超限 → 走通用推荐（从3提升到5，保证4个必填字段+1次容错）
    MAX_REQUIRED_ROUNDS = 5
    if missing and sess.get("followup_rounds", 0) < MAX_REQUIRED_ROUNDS:
        sess["followup_rounds"] = sess.get("followup_rounds", 0) + 1
        q_map = {
            "education": "请问你目前是什么学历呢？（高中/本科/硕士）",
            "target_major": "想申请什么专业方向呢？（如计算机、商科、机械、金融等）",
            "language_score": '目前有雅思、托福或德语成绩吗？大概多少分呢？（没有的话可以说"暂无"）',
            "target_country": "想申请哪个国家的留学？（目前我们主要做德国和新加坡）",
        }
        ask = "\n".join(q_map.get(f, f"请补充：{f}") for f in missing[:1])
        return f"好的！为了给你推荐最合适的项目，我需要了解：\n\n{ask}\n也可以直接告诉我你的详细背景哦～"

    # 充足：调 study_abroad_agent 推荐
    sess["followup_rounds"] = 0
    # 先保存画像
    sa_save_profile({
        "conversation_id": conv_id,
        "education": slots.get("education", ""),
        "target_country": slots.get("target_country", ""),
        "target_major": slots.get("target_major", ""),
        "gpa": slots.get("gpa"),
        "language_score": slots.get("language_score", ""),
        "budget": slots.get("budget"),
        "name": slots.get("name", ""),
        "phone": slots.get("phone", ""),
    })

    rec_result = sa_recommend(conv_id)

    # 提取推荐结果；最高分低于阈值视为"无有效匹配"
    recs = []
    if rec_result.get("code") == 0 and rec_result.get("data"):
        all_recs = rec_result["data"].get("recommendations", [])[:5]
        recs = all_recs if (all_recs and all_recs[0].get("score", 0) >= 40) else []

    if not recs:
        # ══════════════════════════════════════════════════════════
        # 无有效匹配时不直接打发用户找顾问，
        # 而是继续追问缺失的可选信息，收集够了再重新推荐
        # ══════════════════════════════════════════════════════════
        enrichment = _ask_enrichment_field(sess)
        if enrichment:
            # 给出追问 + 当前已知的背景摘要，保持对话继续
            return (
                enrichment
                + "\n📌 当前已记住的背景："
                + _format_known_slots(slots)
            )

        # 所有可追问字段都齐了（或已达上限）：降级兜底展示
        courses = sa_get_courses(
            country=slots.get("target_country", ""),
            limit=5,
        )
        if courses.get("data"):
            lines = ["基于你的背景，这里有一些相近的项目供参考：\n"]
            for c in courses["data"][:5]:
                lines.append(
                    f"· **{c.get('course_name','')}** ({c.get('category','')})\n"
                    f"  学历: {c.get('target_education','')} | "
                    f"语言: {c.get('language_requirement','无要求')} | "
                    f"¥{c.get('price',0):,.0f}"
                )
            lines.append("\n以上可能不是100%匹配，如需更精准的推荐可以告诉我更多信息"
                         "（GPA / 预算 / 实习经验），或直接预约顾问定制方案 🎓")
            return "\n".join(lines)
        return ("暂时没有找到合适的匹配项目。建议直接拨打我们的顾问热线，"
                "让老师一对一帮你出方案，也可以留下手机号我让顾问回联系你 📞")

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

    lines.append("感兴趣的话可以继续详细了解，也可以告诉我更多偏好（GPA / 预算 / 入学时间），我帮你进一步缩小范围 🎓")
    # 推荐成功：清理追问标记，下次重新跑推荐流程时恢复干净状态
    sess.pop("enrichment_asked", None)
    return "\n".join(lines)


# 用于"收集更多信息"阶段的可选字段（按追问优先级排序）
_ENRICHMENT_FIELDS = [
    ("gpa",         "方便说一下你的 GPA 或均分吗？（例如 3.2/4.0 或 82/100）"),
    ("budget",      "你的留学预算大概在什么范围？（例如 15 万/年、总预算 30 万）"),
    ("intake",      "计划什么时间入学呢？（如 2027 秋季）"),
    ("work_experience", "有没有相关的工作或实习经验？"),
]
# 用于和用户确认"已记住"的字段顺序与可读标签
_KNOWN_FIELD_LABELS = [
    ("education",       "学历"),
    ("target_major",    "专业"),
    ("language_score",  "语言"),
    ("target_country",  "国家"),
    ("gpa",             "GPA"),
    ("budget",          "预算"),
    ("intake",          "入学时间"),
    ("work_experience", "经验"),
]


def _ask_enrichment_field(sess: dict) -> str:
    """
    当推荐无有效匹配时，从可选字段中挑一个还没收集、还没追问过的字段来问。
    返回追问话术（str），若所有可选字段都已问过则返回空串。
    """
    slots = sess["slots"]
    asked = sess.setdefault("enrichment_asked", [])
    # 总共追问上限（含必填 + 额外），防止无限循环
    if sess.get("followup_rounds", 0) >= 8:
        return ""
    for field, question in _ENRICHMENT_FIELDS:
        if field in asked:
            continue
        if slots.get(field):
            # 已有值但还没记为 asked，反正不会重复问
            asked.append(field)
            continue
        # 找到缺失也未追问过的 → 追问
        asked.append(field)
        sess["followup_rounds"] = sess.get("followup_rounds", 0) + 1
        return (
            "为了给你更精准的推荐，再了解一下：\n\n"
            + question
            + "\n（边聊边记住你的信息，回答越详细推荐越准哦～）"
        )
    return ""


def _format_known_slots(slots: dict) -> str:
    """拼出"已记住的背景"短摘要，供追问时展示"""
    parts = []
    for field, label in _KNOWN_FIELD_LABELS:
        val = slots.get(field)
        if val:
            parts.append(f" {label}={val}")
    return ("".join(parts)) if parts else "（暂无）"


def _collect_recommend_slots(message: str, slots: dict):
    """从用户语句提取学历/国家/专业/GPA/语言"""
    import re
    # 学历
    for pat, val in [
        (r"(高中|职高|中专)", "高中"),
        (r"(本科|大学|在读本科)", "本科"),
        (r"(硕士|研究生|在读硕士)", "硕士"),
        (r"(博士|在读博士)", "博士"),
        (r"(大专|专科)", "大专"),
    ]:
        if re.search(pat, message) and not slots.get("education"):
            slots["education"] = val

    # 国家
    if ("德国" in message or "german" in message.lower()) and not slots.get("target_country"):
        slots["target_country"] = "德国"
    elif ("新加坡" in message or "singapore" in message.lower()) and not slots.get("target_country"):
        slots["target_country"] = "新加坡"

    # GPA
    m = re.search(r"(?:gpa|绩点|成绩)[^\d]*(\d+(?:\.\d+)?)", message, re.I)
    if m:
        slots["gpa"] = float(m.group(1))

    # 语言成绩
    m = re.search(r"(ielts|雅思)[^\d]*(\d+(?:\.\d+)?)", message, re.I)
    if m:
        slots["language_score"] = f"IELTS {m.group(2)}"
    m = re.search(r"(toefl|托福)[^\d]*(\d+)", message, re.I)
    if m:
        slots["language_score"] = f"TOEFL {m.group(1)}"
    if "德语" in message and not slots.get("language_score"):
        m2 = re.search(r"德语([a-zA-Z0-9]+)", message)
        slots["language_score"] = f"德语{m2.group(1)}" if m2 else "德语"

    # 专业/方向
    m = re.search(r"(?:想读|申请|专业|方向)[是为]?[：:\s]*([一-龥A-Za-z]{2,20})", message)
    if m:
        slots["target_major"] = m.group(1)
    # 兜底：用户直接回答专业名时也能识别
    if not slots.get("target_major"):
        for kw in ["计算机", "商科", "金融", "会计", "管理", "工程", "机械",
                   "电子", "土木", "医学", "法学", "艺术", "生物", "化学",
                   "物理", "数学", "传媒", "教育", "心理", "人工智能", "数据"]:
            if kw in msg:
                slots["target_major"] = kw
                break

    # 姓名+手机
    m = re.search(r"(?:我叫|姓名|名字)[：:\s]*([一-龥]{2,4})", message)
    if m:
        slots["name"] = m.group(1)
    m = re.search(r"1[3-9]\d{9}", message)
    if m:
        slots["phone"] = m.group(0)


def _extract_country(message: str) -> str:
    if "德国" in message or "german" in message.lower():
        return "德国"
    if "新加坡" in message or "singapore" in message.lower():
        return "新加坡"
    return ""


# ============================================================
# Handler: 活动/讲座报名
# ============================================================
def _handle_event(message, params, context, sess, conv_id):
    slots = sess["slots"]
    # 提取报名参数
    m = re_name(message)
    if m:
        slots["name"] = m
    m = re_phone(message)
    if m:
        slots["phone"] = m

    # 判断是查询还是报名
    is_register = any(kw in message for kw in
                      ["报名", "预约", "参加", "我要", "register"])
    is_query = any(kw in message for kw in
                   ["有哪些", "有没有", "查询", "查一下", "最近", "即将",
                    "讲座", "分享会", "招生官", "见面会"])

    if is_query or (not is_register):
        # 通过 bridge 查活动
        result = event_query(f"查询 {_build_event_filter(message)} 活动和讲座")
        if result.get("result", {}).get("type") == "error":
            return ("活动查询暂时不可试，建议关注我们的公众号第一时间获取活动通知～")
        polished = result.get("polished", "")
        if polished:
            return polished + "\n\n感兴趣的话可以直接告诉我「报名讲座XX 姓名 手机号」，我帮你一键预约 📅"
        return get_random("guide_menu")

    # 报名模式：需要 姓名+手机+活动ID或标题关键词
    if not slots.get("name") or not slots.get("phone"):
        sess["followup_rounds"] = sess.get("followup_rounds", 0) + 1
        missing = []
        if not slots.get("name"):
            missing.append("姓名")
        if not slots.get("phone"):
            missing.append("手机号")
        return f"好的！报名还需要补充：{'、'.join(missing)}\n直接告诉我就行，比如'张三 13800138000'"

    # 调 bridge 报名
    if not _has_event_keyword(message):
        # 没提具体活动 → 先展示列表
        result = event_query(f"查询所有近期活动和讲座")
        polished = result.get("polished", "")
        return (f"{polished}\n\n想报名哪条？告诉我序号或标题就行，"
                f"姓名：{slots['name']} 手机：{slots['phone']}")

    # 生成报名NL2SQL
    nl = f"报名活动或讲座，姓名{slots['name']}，手机号{slots['phone']}"
    if "讲座" in message:
        nl += "，预约讲座"
    if "活动" in message:
        nl += "，预约活动"
    result = event_register(nl)
    polished = result.get("polished", "")
    if result.get("result", {}).get("type") == "error":
        return f"报名遇到了点问题：{result['result'].get('message', '未知错误')}\n建议直接电话微信联系顾问协助报名"
    return f"报名成功！✅\n{polished}\n\n期待你的参与～有任何变动随时联系我哦😊"


def _build_event_filter(message: str) -> str:
    """根据关键词生成查询条件"""
    filters = []
    country = _extract_country(message)
    if country:
        filters.append(country)
    for kw in ["留学", "讲座", "分享会", "招生官", "说明会", "见面会", "答疑"]:
        if kw in message:
            filters.append(kw)
    return " ".join(filters) if filters else "所有"


def _has_event_keyword(message: str) -> bool:
    return any(kw in message for kw in
               ["讲座", "分享会", "招生官", "见面会", "说明会", "活动"])


def re_name(text):
    import re
    m = re.search(r"(?:我叫|姓名|名字|叫|名为)[：:\s]*([一-龥]{2,4})", text)
    return m.group(1) if m else None


def re_phone(text):
    import re
    m = re.search(r"1[3-9]\d{9}", text)
    return m.group(0) if m else None


# ============================================================
# Handler: FAQ 常见问题
# ============================================================
def _handle_faq(message, params, context, sess, conv_id):
    kb = get_kb()
    # FAQ 精确匹配
    ans = kb.faq_match(message)
    if ans:
        return ans + "\n\n还有疑问可以继续问我哈 💪"
    # FAQ 材料搜
    docs = kb.search(message, top_k=3)
    if docs:
        instruction = (
            f"基于以下FAQ材料直接给出简明的答案。如材料不够，"
            f"如实说「可以联系顾问详解」。\n\n" + "\n\n".join(docs)
        )
        return llm.agent_reply(message, context, extra_instruction=instruction)
    # 兜底
    return ("这个问题我不太确定最准确的答案。建议你：\n"
            "1. 直接告诉我更多细节，我再帮你定位答案\n"
            "2. 或预约专属顾问一对一解答 🎓")


# ============================================================
# Handler: 闲聊
# ============================================================
def _handle_chat(message, params, context, sess, conv_id):
    session_rounds = len(sess["history"]) // 2

    # 情感维系：多轮无转化 → 自然引导
    if session_rounds >= 5 and not sess.get("slots"):
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

    # 其他人设prompt下的闲聊
    hint = ""
    if sess.get("last_topic") and session_rounds >= 3:
        hint = f"\n用户之前聊过{sess['last_topic']}，闲聊自然引导话题回来"

    return llm.agent_reply(
        message, context,
        extra_instruction=f"闲聊回复。不超过200字。{hint}",
    )


# ============================================================
# 意图 → Handler 映射表
# ============================================================

INTENT_HANDLERS = {
    "company_info":   _handle_company_info,
    "business_query": _handle_business_query,
    "policy":         _handle_policy,
    "recommend":      _handle_recommend,
    "event":          _handle_event,
    "faq":            _handle_faq,
    "chat":           _handle_chat,
}
