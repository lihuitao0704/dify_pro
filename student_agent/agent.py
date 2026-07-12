"""
Agent 主脑：对话入口 → 意图识别 → 多意图编排 → 7场景调度 → 回复生成
"""

import logging
from . import db as _db
from . import llm
from . import intent as _intent
from . import conversation as _conv
from .knowledge import get_kb
from .services import (
    leave_service, emotion_service, feedback_service,
    academic_service, upgrade_service, nl2sql_service,
)

logger = logging.getLogger(__name__)


def process_message(student_id: int, message: str, session_id: str = None) -> dict:
    if not session_id:
        session_id = _conv.new_session_id()

    context = _conv.get_history(session_id)
    raw_intents = llm.classify_intent(message, context)
    filtered = _intent.filter_low_confidence(raw_intents)
    sorted_intents = _intent.sort_by_priority(filtered)

    # 情绪分析：LLM + 关键词双引擎
    emotion_history = _conv.get_emotion_history(student_id, days=14)
    emotion_result = llm.analyze_emotion(message, emotion_history)
    kw_result = emotion_service.analyze_emotion_keywords(message)
    emotion_result = emotion_service.merge_emotion_results(emotion_result, kw_result)

    # 上下文意图纠正：短追问继承上一轮主意图
    follow_words = ["帮我", "预约", "联系", "怎么", "多少钱", "多久", "什么时候",
                    "能不能", "还要", "有没有", "处理", "进度", "状态"]
    if len(message) <= 20 and any(kw in message for kw in follow_words) and sorted_intents:
        current_intent = sorted_intents[0]["intent"]
        need_correct = current_intent in ("life_guide", "chat", "progress")
        if need_correct and session_id:
            sess = _db.query_one(
                "SELECT main_intents FROM conversation_session WHERE session_id = %s",
                (session_id,))
            if sess and sess.get("main_intents"):
                prev = sess["main_intents"].split(",")[0].strip()
                if prev and prev not in ("chat", "life_guide"):
                    sorted_intents[0]["intent"] = prev

    # 多意图编排
    actions = []
    partial_replies = []
    is_multi = _intent.is_multi_intent(sorted_intents)

    for item in sorted_intents:
        intent_name = item["intent"]
        params = item.get("params", {})
        try:
            handler = INTENT_HANDLERS.get(intent_name)
            if handler:
                result = handler(student_id, message, params, context)
                if result:
                    partial_replies.append(result)
                    actions.append({"intent": intent_name, "result": "ok", "detail": result[:200]})
            else:
                actions.append({"intent": intent_name, "result": "unknown"})
        except Exception as e:
            logger.error("Handler异常: intent=%s student=%d error=%s", intent_name, student_id, e, exc_info=True)
            actions.append({"intent": intent_name, "result": "error", "error": str(e)})

    # 情绪后处理
    emotion_alert = _handle_emotion_update(student_id, emotion_result, message)

    # 生成最终回复
    if not sorted_intents or sorted_intents[0]["intent"] == "chat":
        reply = llm.agent_chat(message, context)
    elif is_multi and len(partial_replies) > 1:
        reply = _merge_replies(message, partial_replies, sorted_intents, context)
    elif partial_replies:
        reply = partial_replies[0]
    else:
        reply = llm.agent_chat(message, context)

    has_mental = any(i["intent"] == "mental" for i in sorted_intents)
    if emotion_alert and has_mental:
        reply += emotion_alert

    # 记录对话日志
    intent_str = ",".join([i["intent"] for i in sorted_intents])
    _conv.save_turn(session_id, student_id, message, reply,
                    intent=intent_str, emotion=emotion_result.get("emotion", ""))

    return {
        "reply": reply, "intents": sorted_intents,
        "emotion": emotion_result, "session_id": session_id, "actions": actions,
    }


def _merge_replies(user_msg: str, partials: list[str], intents: list[dict],
                   context: list[dict]) -> str:
    instruction = (
        "学生的一句话包含了多个意图，你已经分别处理了每个意图。"
        "请把以下多个处理结果融合成一段自然流畅的回复。像正常对话一样，不要分点列举。\n\n"
        + "\n---\n".join(partials))
    return llm.agent_chat(user_msg, context, extra_instruction=instruction)


def _handle_emotion_update(student_id: int, emotion: dict, user_msg: str) -> str:
    return emotion_service.analyze_and_update(student_id, emotion, user_msg)


def _handle_life_guide(student_id: int, message: str, params: dict, context: list) -> str:
    activity_words = ["活动", "社团", "讲座", "分享会", "见面会", "迎新"]
    if any(kw in message for kw in activity_words):
        return "活动查询功能正在对接中，上线后可以直接帮你查最新的讲座、分享会、社团招新等活动信息～\n\n现在你可以问我海外生活、升学项目、学业日程等其他问题。"

    generic_words = ["海外生活", "生活指南", "海外指南", "生活支持"]
    if any(kw in message for kw in generic_words) and len(message) <= 15:
        return ("关于海外的学习生活，我了解以下信息～\n\n"
                "🏥 医疗就医\n🏠 租房住宿\n🚇 交通出行\n💳 银行卡与通讯\n"
                "🆘 紧急求助\n📚 留学政策\n🎓 升学项目\n\n"
                "直接告诉我想了解哪方面，我给你详细解答～")

    try:
        kb = get_kb()
        if kb and kb.is_loaded():
            faq_ans = kb.faq_match(message)
            if faq_ans:
                return faq_ans
            docs = kb.search(message, top_k=3)
            if docs:
                ctx = "\n\n".join(docs)
                instruction = f"基于以下知识库内容回答学生问题。如果信息不够，如实说。\n\n{ctx}"
                return llm.agent_chat(message, context, extra_instruction=instruction)
    except ImportError:
        pass

    topic_hints = {"医疗": "试试问:新加坡看病流程 或 怎么用医保",
                   "住房": "试试问:新加坡租房要注意什么",
                   "交通": "试试问:新加坡怎么坐地铁",
                   "银行": "试试问:新加坡怎么办银行卡",
                   "紧急": "试试问:新加坡紧急求助电话",
                   "签证": "试试问:学生签证怎么续签"}
    for kw, hint in topic_hints.items():
        if kw in message:
            return f"关于这方面，{hint}，我给你更详细的回答～"
    return "这方面我暂时了解不够全面，你可以换个方式问我，比如:新加坡怎么看病、德国有哪些专业~"


def _handle_chat(student_id: int, message: str, params: dict, context: list) -> str:
    return llm.agent_chat(message, context)


# 意图映射（委托给 services/ 模块）
INTENT_HANDLERS = {
    "leave":      leave_service.handle_leave,
    "mental":     emotion_service.handle_mental,
    "feedback":   feedback_service.handle_feedback,
    "academic":   academic_service.handle_academic,
    "progress":   academic_service.handle_progress,
    "life_guide": _handle_life_guide,
    "upgrade":    upgrade_service.handle_upgrade,
    "nl2sql":     nl2sql_service.handle_nl2sql,
    "chat":       _handle_chat,
}
