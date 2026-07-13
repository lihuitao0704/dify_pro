"""
客服Agent主脑
流程：消息入口 → 意图识别 → 多轮流程续写优先 → Handler调度 → 回复生成

架构（v2.0）:
  - 会话状态由 state.SessionState 管理（替代旧 dict，支持意图锁定/子流程）
  - Handler 实现在 router.py（单一职责），本文件只做 orchestration
  - 记忆：对话历史 + 多轮收集参数(slots) + 用户画像(persist) 三层
"""
import json
import re
from customer_agent import llm, intent as intent_mod
from customer_agent.knowledge import get_kb
from customer_agent.persona import get_random

# ── 会话状态（委托 state.py）──────────────────────────────────────
from customer_agent.state import (
    new_session_id,
    derive_conversation_id,
    get_session,
)

# ── Handler 映射（委托 router.py）─────────────────────────────────
from customer_agent.router import INTENT_HANDLERS


def get_context(session_id: str) -> list:
    """返回最近 N 轮对话上下文（兼容旧 API 接口）"""
    sess = get_session(session_id)
    return sess.get_context()


def save_turn(session_id: str, user_msg: str, reply: str,
             intents: list = None):
    """记录一轮对话到 SessionState（兼容旧接口，保留以备外部调用）"""
    sess = get_session(session_id)
    sess.add_turn("user", user_msg)
    sess.add_turn("assistant", reply)


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
        conversation_id: 关联用户画像的会话标识（默认 '0'）

    返回: {reply, intents, session_id, actions}
    """
    if not session_id:
        session_id = new_session_id()
    sess = get_session(session_id)
    # 外部传入非默认 conversation_id 时覆盖（用于关联真实用户画像）
    if conversation_id and conversation_id != "0":
        sess.conversation_id = conversation_id
    context = sess.get_context()

    actions = []
    partial_replies = []
    sorted_intents = []

    # ── Step 1: 优先续写未完成的多轮流程（flow-first）────────────
    if sess.has_active_flow():
        locked = sess.current_intent
        handler = INTENT_HANDLERS.get(locked)
        if handler:
            try:
                result = handler(
                    message, {}, context, sess, sess.conversation_id,
                )
                if result:
                    partial_replies.append(result)
                actions.append({"intent": locked, "result": "ok"})
                sorted_intents = [{"intent": locked,
                                   "confidence": 1.0, "params": {}}]
            except Exception as e:
                print(f"[Agent] 续写流程 {locked} 异常: {e}")
                actions.append({"intent": locked, "result": "error",
                                "error": str(e)})
                sess.unlock_intent()  # 出错时解锁，避免死锁
                # 解锁后继续走正常分类流程（不 return）
                return _classify_and_dispatch(
                    message, session_id, context, sess, conversation_id,
                )

        if partial_replies:
            reply = _build_final_reply(
                message, sorted_intents, partial_replies, context, sess,
            )
            if not reply or not reply.strip():
                reply = _offline_fallback(message, sorted_intents, sess)
            sess.add_turn("user", message)
            sess.add_turn("assistant", reply)
            # ── 每轮结束：提取用户参数 → 增量写库 ─────────────────────
            sess.extract_profile(message)
            sess.sync_profile_to_db()
            still_locked = sess.has_active_flow()
            out = {
                "reply": reply,
                "intents": sorted_intents,
                "session_id": session_id,
                "actions": actions,
            }
            if still_locked:
                out["flow"] = {"locked": True, "intent": locked}
            return out

    # ── Step 2: 正常分类 + 调度 ────────────────────────────────
    return _classify_and_dispatch(
        message, session_id, context, sess, conversation_id,
    )


def _classify_and_dispatch(message, session_id, context, sess, conversation_id):
    """意图分类 + Handler 调度（抽取为函数供 flow-first 复用）"""
    actions = []
    partial_replies = []

    # Step 2a: 意图识别
    raw_intents = intent_mod.classify_intent(
        llm_chat_fn=llm.chat,
        llm_chat_json_fn=llm.chat_json,
        user_msg=message,
        context=context,
    )
    filtered = intent_mod.filter_low_confidence(raw_intents)
    sorted_intents = intent_mod.sort_by_priority(filtered)

    # Step 2b: 追问短句继承上一轮主话题
    _maybe_inherit_intent(message, sorted_intents, sess)

    # Step 2c: 调度各 Handler
    for item in sorted_intents:
        handler = INTENT_HANDLERS.get(item["intent"])
        if handler:
            try:
                result = handler(
                    message, item.get("params", {}),
                    context, sess, sess.conversation_id,
                )
                if result:
                    partial_replies.append(result)
                actions.append({"intent": item["intent"], "result": "ok"})
            except Exception as e:
                print(f"[Agent] Handler {item['intent']} 异常: {e}")
                actions.append({"intent": item["intent"], "result": "error",
                                "error": str(e)})

    # Step 2d: 合成最终回复
    reply = _build_final_reply(
        message, sorted_intents, partial_replies, context, sess,
    )

    # 离线兜底：回复为空串时走规则话术
    if not reply or not reply.strip():
        reply = _offline_fallback(message, sorted_intents, sess)

    # Step 2e: 记录对话 + 更新话题
    sess.add_turn("user", message)
    sess.add_turn("assistant", reply)
    if sorted_intents:
        sess.last_intents = [i["intent"] for i in sorted_intents]
        business = [i for i in sorted_intents if i["intent"] != "chat"]
        if business:
            sess.last_topic = business[0]["intent"]

    # ── 每轮结束：提取用户参数 → 增量写库 ─────────────────────
    # 推荐流程也会走这里：extract_profile 不会覆盖 profile_slots 已有值，
    # 仅补充姓名/电话等推荐流程没抓的字段；sync 只写 dirty 字段不重复写。
    sess.extract_profile(message)
    sess.sync_profile_to_db()

    return {
        "reply": reply,
        "intents": sorted_intents,
        "session_id": session_id,
        "actions": actions,
    }


def _offline_fallback(message: str, intents: list, sess) -> str:
    """LLM 离线时的规则兜底回复。

    优先尝试 LLM 改写(若 LLM 实际可用); LLM 真不可用时降级为知识库原文片段 + 标记。
    """
    primary = intents[0]["intent"] if intents else "chat"

    kb = get_kb()

    # FAQ 优先精确匹配 → 尝试 LLM 改写, 失败则降级原文
    if primary == "faq":
        ans = kb.faq_match(message)
        if ans:
            from customer_agent.router import _rewrite_with_llm
            return _rewrite_with_llm(
                message, [], [ans], "faq", sess, "",
                fallback=ans + "\n\n还有其他问题可以继续问我哈~"
            )

    # 业务类意图：LLM 可用时改写, 不可用时才降级原文片段
    if primary in ("company_info", "company_service", "study_policy", "faq"):
        docs = kb.search(message, top_k=2)
        if docs:
            from customer_agent.router import _rewrite_with_llm
            return _rewrite_with_llm(
                message, [], docs, primary, sess, "",
                fallback=(docs[0][:280]
                          + "\n\n（当前为知识库原文参考，如需更详细解答可稍后重试在线模式）")
            )

    # 活动服务未启动
    if primary in ("activity", "activity_register"):
        return ("活动查询暂时不可用，建议关注我们的公众号第一时间获取活动通知~"
                "\n也可以拨打前台电话由人工协助查询和报名 🎓")

    # 闲聊/兜底
    return get_random("guide_menu") + ("\n(LLM离线模式，回复质量受限，"
                                    "请稍后再试或拨打热线，谢谢谅解 🙏)")


def _maybe_inherit_intent(message: str, intents: list, sess):
    """短追问继承上一轮主话题"""
    if not intents or not sess.last_topic:
        return
    short_followup = len(message) <= 15 and any(
        kw in message for kw in ["帮我", "预约", "联系", "怎么",
                                  "多少钱", "多久", "还有", "有没有"]
    )
    curr = intents[0]["intent"]
    if short_followup and curr == "chat":
        intents[0]["intent"] = sess.last_topic


def _build_final_reply(user_msg, intents, partials, context, sess) -> str:
    """合成最终回复文本"""
    is_multi = intent_mod.is_multi_intent(intents)
    primary = intents[0]["intent"] if intents else "chat"

    if not partials or primary == "chat":
        # 闲聊/兜底：走人设 prompt
        hint = ""
        if sess.last_topic and sess.last_topic != "chat":
            hint = f"\n学生可能对{sess.last_topic}有兴趣，闲聊时可自然引导"
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
