"""
客服Agent意图识别：7大业务场景 + 闲聊
LLM优先，API不可用时降级关键词规则
"""

import json
import re
import random
from .config import config


# ============================================================
# 7+1 意图体系
# ============================================================
CUSTOMER_INTENTS = {
    "company_info":   "公司信息咨询",       # 品牌、历程、案例、校区
    "business_query": "业务查询",          # 留学申请、语言培训、背景提升
    "policy":         "海外留学政策查询",   # 签证、院校门槛、移民就业
    "recommend":      "课程与项目推荐",     # 基于画像智能推荐
    "event":          "活动与讲座报名",     # 查询+预约+报名
    "faq":            "常见问题自助解答",   # 申请流程、费用、退费
    "chat":           "日常闲聊互动",       # 情感维系
}

# 意图优先级（数字越小越先处理）
INTENT_PRIORITY = {
    "company_info":   1,
    "business_query": 2,
    "policy":         3,
    "recommend":      4,
    "event":          5,
    "faq":            6,
    "chat":           9,   # 闲聊永远兜底
}


# ============================================================
# LLM 意图分类 Prompt
# ============================================================
INTENT_SYSTEM_PROMPT = """你是粤教留学客服Agent的意图识别模块。分析访客消息，从以下7+1种意图中识别所有匹配的意图。

7大业务场景：
1. company_info   - 公司信息咨询：问公司背景、发展历程、品牌实力、校区分布、成功客户案例、机构口碑
2. business_query - 业务查询：问留学申请服务、语言培训、背景提升项目、具体课程内容
3. policy         - 海外留学政策查询：问签证要求、院校申请门槛、语言成绩要求、移民政策、留学生就业政策
4. recommend      - 课程与项目推荐：希望基于自身情况获得推荐、寻问适合自己的留学方案、问有哪些课程/项目
5. event          - 活动与讲座报名：查询留学讲座/分享会/招生官见面会、报名活动。
    ★ 关键识别规则：只要消息同时含有"报名/预约/参加"等动作词 + 活动指向（如"第一个""第1个""讲座""活动""这个活动"），
      一律归为 event（即使句子很短/像闲聊）。"报名第一个""报名第2个""预约讲座"都是典型的 event 意图。、问近期有什么活动
6. faq            - 常见问题自助解答：问申请流程、服务费用、退费政策、材料准备等纯事实性问题
7. chat           - 日常闲聊互动：打招呼、道谢、天气、与业务无关的闲聊、无明确诉求

⚠️ 关键分流规则（必须遵守）：
- 凡是问到「课程」「项目」「有什么课」「课程内容」「课程费用」「某个专业有什么课」等与具体课程/项目相关的内容 → 必须分类为 recommend（走课程推荐接口），绝对不能分类为 faq。
- 凡是问到「活动」「讲座」「分享会」「招生官见面会」「近期活动」「线下活动」等活动/讲座内容 → 必须分类为 event（走活动查询接口），绝对不能分类为 faq。
- faq 只适用于不涉及课程/活动的纯事实性问题，例如申请流程、退费政策、签证材料、APS流程等。

要求：
- 一条消息可能包含多个意图。例如 "你们有什么德国留学项目，顺便帮我报名下周讲座" → [recommend, event]
- 提取关键参数（如国家、学历、专业、姓名、手机号等）
- 置信度范围 0.0~1.0

返回格式（纯JSON数组）：
[
  {"intent": "company_info", "confidence": 0.95, "params": {"topic": "发展历程"}},
  {"intent": "event", "confidence": 0.8, "params": {"action": "register"}}
]

只返回 JSON 数组。如果只有一个意图，数组长度就是1。"""


# ============================================================
# 关键词规则（离线降级）
# ============================================================
KEYWORD_RULES = [
    # (关键词列表, 意图名, 额外params提取函数)
    (["公司", "你们是谁", "你们家", "机构", "品牌", "背景", "成立", "多久",
      "历程", "发展", "校区", "分布", "地址", "成功案例", "口碑", "获奖",
      "简介", "介绍下你们", "实力", "靠谱吗", "正规吗", "资质"],
     "company_info"),

    (["留学申请", "申请留学", "背景提升", "语言培训", "语培", "雅思班",
      "托福班", "德语班", "gre", "gmat", "培训项目", "有什么业务",
      "服务", "业务范围", "能做什么", "有什么课", "课程内容"],
     "business_query"),

    (["签证", "政策", "申请门槛", "分数要求", "gpa要求", "语言要求",
      "ielts", "雅思多少", "托福多少", "德语要求", "testdaf", "dsh",
      "移民", "就业", "打工", "居留", "永居", "pr", "入学条件",
      "录取条件", "aps"],
     "policy"),

    (["推荐", "适合我", "有什么方案", "我能申什么", "帮我选择", "选哪个",
      "我的背景", "我这种情况", "匹配", "哪个项目", "方案推荐",
      "有什么适合", "适合什么", "我能去哪", "有哪些课程", "课程有哪些",
      "有什么课", "课程内容", "课程费用", "有什么项目", "有哪些项目",
      "项目费用", "某个专业有什么课", "有哪些方向", "有什么方向"],
     "recommend"),

    (["讲座", "分享会", "招生官", "见面会", "活动", "报名", "预约活动",
      "线下", "线上直播", "宣讲", "说明会", "报名活动", "参加活动",
      "听讲座", "参加讲座", "近期活动", "有什么活动", "近期讲座",
      "报名第", "报名一", "报名二", "报名三", "第几个"],
     "event"),

    (["流程", "申请流程", "退费", "退款",
      "学制", "几年", "多久毕业", "认证", "回国认证",
      "中留服", "材料准备", "需要什么材料", "时间规划", "什么时候申请",
      "截止日期", "deadline", "step by step", "怎么办签证"],
     "faq"),

    (["你好", "哈喽", "hi", "hello", "嗨", "在吗", "你是谁", "谢谢",
      "thanks", "感谢", "拜拜", "bye", "好的", "嗯", "哈哈",
      "天气", "吃饭", "周末", "无聊"],
     "chat"),
]


def sort_by_priority(intents: list) -> list:
    """按优先级排序"""
    return sorted(intents, key=lambda x: INTENT_PRIORITY.get(x["intent"], 99))


# 用于判断一条消息是否明确与课程/活动相关
_COURSE_KW = [
    "课程", "项目", "专业", "方向", "选课", "课堂", "班上", "班上",
    "培训", "语培", "雅思", "托福", "德语", "gre", "gmat",
]
_ACTIVITY_KW = [
    "活动", "讲座", "分享会", "招生官", "见面会", "宣讲", "说明会",
    "线下", "线上直播", "听讲座", "参加活动", "近期活动", "近期讲座",
]


def _override_faq_for_business(intents: list, user_msg: str) -> list:
    """安全兜底：当消息明确涉及课程/活动时，移除 faq 意图，
    避免课程/活动类问题被错误路由到 FAQ 知识库（知识库中没有课程/活动数据）。
    """
    has_course = any(kw in user_msg for kw in _COURSE_KW)
    has_activity = any(kw in user_msg for kw in _ACTIVITY_KW)

    if not has_course and not has_activity:
        return intents  # 不涉及课程/活动，不做干预

    # 检查是否有业务类意图（recommend / event）也在结果中
    business_intents = [
        i for i in intents
        if i["intent"] in ("recommend", "event", "activity_register",
                           "course_recommendation")
    ]
    faq_intents = [i for i in intents if i["intent"] == "faq"]

    if business_intents and faq_intents:
        # 两者都有 → 去掉 faq，只保留业务类（具体接口能查到真实数据）
        return [i for i in intents if i["intent"] != "faq"]

    return intents


def filter_low_confidence(intents: list) -> list:
    """低于阈值的低置信意图降级为 chat"""
    result = []
    has_high = False
    for item in intents:
        if item["confidence"] >= config.INTENT_CONFIDENCE_THRESHOLD:
            result.append(item)
            has_high = True

    if not has_high and intents:
        best = max(intents, key=lambda x: x.get("confidence", 0))
        best["intent"] = "chat"
        result = [best]

    return result


# ============================================================
# LLM 调用（传入 get_client 回调，避免循环导入）
# ============================================================
def classify_intent(
    llm_chat_fn,
    llm_chat_json_fn,
    user_msg: str,
    context: list = None,
) -> list:
    """
    意图分类入口
    - llm_chat_fn:    (messages, system_prompt, temperature) -> str
    - llm_chat_json_fn: (messages, system_prompt, temperature) -> dict
    """
    messages = []
    if context:
        recent = [m for m in context[-6:] if m.get("role") in ("user", "assistant")]
        if recent:
            ctx_text = "\n".join(
                [f"{m['role']}: {m['content'][:200]}" for m in recent]
            )
            messages.append({
                "role": "system",
                "content": (
                    f"最近对话上下文。重要规则：如果当前消息看起来像是对上一轮的追问/延续，"
                    f"且上一轮聊的是XX话题，当前意图应保持一致。\n{ctx_text}"
                ),
            })
    messages.append({"role": "user", "content": user_msg})

    try:
        result = llm_chat_json_fn(messages, INTENT_SYSTEM_PROMPT, 0.3)
        if isinstance(result, dict):
            result = [result]
        if not isinstance(result, list):
            return _override_faq_for_business(_fallback(user_msg), user_msg)
        result.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        return _override_faq_for_business(result, user_msg)
    except Exception as e:
        print(f"[Intent] LLM意图识别降级关键词: {e}")
        return _override_faq_for_business(_keyword_intent(user_msg), user_msg)


def _keyword_intent(user_msg: str) -> list:
    """关键词意图匹配（离线兜底）"""
    msg_lower = user_msg.lower()
    matched = []
    for keywords, intent in KEYWORD_RULES:
        for kw in keywords:
            if kw in msg_lower:
                matched.append({"intent": intent, "confidence": 0.8, "params": {}})
                break
    if not matched:
        matched.append({"intent": "chat", "confidence": 0.6, "params": {}})
    return matched


# 快捷引用
_fallback = _keyword_intent


def is_multi_intent(intents: list) -> bool:
    """是否多业务意图（chat不算）"""
    business = [i for i in intents if i["intent"] != "chat"]
    return len(business) > 1


def format_intent_summary(intents: list) -> str:
    """调试/日志用"""
    parts = []
    for item in intents:
        name = CUSTOMER_INTENTS.get(item["intent"], item["intent"])
        conf = item.get("confidence", 0)
        parts.append(f"{name}({conf:.0%})")
    return " → ".join(parts)
