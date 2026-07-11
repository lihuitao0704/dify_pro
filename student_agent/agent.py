"""
Agent 主脑：对话入口 → 意图识别 → 多意图编排 → 7场景调度 → 回复生成

所有学生对话的中央处理器。每个场景对应一套处理逻辑：
  leave(请假) / mental(心理) / feedback(投诉) / academic(学业)
  / progress(进度) / life_guide(生活) / upgrade(转化) / nl2sql / chat
"""

import json
from datetime import datetime
from . import db as _db
from . import llm
from . import intent as _intent
from . import conversation as _conv
from .config import EMOTION_ALERT_THRESHOLD


# ============================================================
#  Agent 主入口
# ============================================================

def process_message(student_id: int, message: str, session_id: str = None) -> dict:
    """
    处理一条学生消息，返回 Agent 回复。

    参数:
        student_id: 学生ID
        message: 学生输入的自然语言
        session_id: 会话ID（None 则自动创建新会话）

    返回:
        {
            "reply": "Agent的回复文本",
            "intents": [...],      # 识别到的意图列表
            "emotion": {...},      # 情绪分析结果
            "session_id": "...",
            "actions": [...]       # 执行了哪些业务操作
        }
    """
    if not session_id:
        session_id = _conv.new_session_id()

    # ── Step 1: 加载上下文 ──
    context = _conv.get_history(session_id)

    # ── Step 2: 意图识别 ──
    raw_intents = llm.classify_intent(message, context)
    filtered = _intent.filter_low_confidence(raw_intents)
    sorted_intents = _intent.sort_by_priority(filtered)

    # ── Step 3: 情绪分析（旁路，不阻塞） ──
    emotion_history = _conv.get_emotion_history(student_id, days=14)
    emotion_result = llm.analyze_emotion(message, emotion_history)

    # ── 上下文意图纠正：短追问继承上一轮主意图 ──
    follow_words = ["帮我", "预约", "联系", "怎么", "多少钱", "多久", "什么时候", "能不能", "还要", "有没有", "处理"]
    if len(message) <= 20 and any(kw in message for kw in follow_words) and sorted_intents:
        current_intent = sorted_intents[0]["intent"]
        if current_intent in ("life_guide", "chat"):
            # LLM把追问判错了，从context推断真实意图
            # 简单策略：查conversation_session的main_intents
            # 直接从对话日志推断
            if session_id:
                sess = _db.query_one(
                    "SELECT main_intents FROM conversation_session WHERE session_id = %s",
                    (session_id,)
                )
                if sess and sess.get("main_intents"):
                    prev = sess["main_intents"].split(",")[0].strip()
                    if prev and prev not in ("chat", "life_guide"):
                        sorted_intents[0]["intent"] = prev

    # ── Step 4: 多意图编排 ──
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
            actions.append({"intent": intent_name, "result": "error", "error": str(e)})

    # ── Step 5: 情绪后处理 ──
    emotion_alert = _handle_emotion_update(student_id, emotion_result, message)

    # ── Step 6: 生成最终回复 ──
    if not sorted_intents or sorted_intents[0]["intent"] == "chat":
        reply = llm.agent_chat(message, context)
    elif is_multi and len(partial_replies) > 1:
        # 多意图：让 LLM 把多个回复融合成一段自然的回答
        reply = _merge_replies(message, partial_replies, sorted_intents, context)
    elif partial_replies:
        reply = partial_replies[0]
    else:
        reply = llm.agent_chat(message, context)

    # 只在心理意图时追加关怀话术，避免非心理场景出现不匹配的关怀
    has_mental = any(i["intent"] == "mental" for i in sorted_intents)
    if emotion_alert and has_mental:
        reply += emotion_alert

    # ── Step 7: 记录对话日志 ──
    intent_str = ",".join([i["intent"] for i in sorted_intents])
    _conv.save_turn(session_id, student_id, message, reply,
                    intent=intent_str, emotion=emotion_result.get("emotion", ""))

    return {
        "reply": reply,
        "intents": sorted_intents,
        "emotion": emotion_result,
        "session_id": session_id,
        "actions": actions,
    }


def _merge_replies(user_msg: str, partials: list[str], intents: list[dict],
                   context: list[dict]) -> str:
    """多意图回复融合"""
    instruction = (
        "学生的一句话包含了多个意图，你已经分别处理了每个意图。"
        "请把以下多个处理结果融合成一段自然流畅的回复。像正常对话一样，不要分点列举。\n\n"
        + "\n---\n".join(partials)
    )
    return llm.agent_chat(user_msg, context, extra_instruction=instruction)


# ============================================================
#  情绪后处理
# ============================================================

def _handle_emotion_update(student_id: int, emotion: dict, user_msg: str) -> str:
    """更新心理画像，必要时触发预警。返回追加到回复的关怀文本"""
    risk_score = emotion.get("risk_score", 0)
    risk_level = emotion.get("risk_level", "low")

    # 更新心理画像
    profile = _db.query_one(
        "SELECT * FROM mental_health_profile WHERE student_id = %s",
        (student_id,)
    )

    # 计算连续负面天数
    if profile:
        new_neg_count = profile["negative_keywords_count"] + (1 if risk_level != "low" else 0)
        if risk_level != "low":
            new_cons = profile["consecutive_negative_days"] + 1
        else:
            new_cons = 0
        new_total = (profile.get("total_chat_count") or 0) + 1

        emotion_history = json.loads(profile.get("emotion_history", "[]") or "[]")
    else:
        new_neg_count = 1 if risk_level != "low" else 0
        new_cons = 1 if risk_level != "low" else 0
        new_total = 1
        emotion_history = []

    # 追加当前情绪到历史
    emotion_history.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "emotion": emotion.get("emotion", ""),
        "score": risk_score,
        "trigger": user_msg[:100],
    })
    # 保留最近30条
    emotion_history = emotion_history[-30:]

    upsert_data = {
        "current_emotion": emotion.get("emotion", "正常"),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "emotion_history": json.dumps(emotion_history, ensure_ascii=False),
        "negative_keywords_count": new_neg_count,
        "consecutive_negative_days": new_cons,
        "last_conversation": user_msg[:500],
        "last_assessment_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    if profile:
        _db.update("mental_health_profile", {"student_id": student_id}, upsert_data)
    else:
        upsert_data["student_id"] = student_id
        _db.insert("mental_health_profile", upsert_data)

    # 高危 → 触发预警
    if risk_score >= EMOTION_ALERT_THRESHOLD and emotion.get("needs_alert"):
        _create_alert(student_id, emotion, user_msg)

    # 返回关怀文本
    if risk_level == "high" or risk_level == "critical":
        return "\n\n💙 我有些担心你。如果你愿意，可以和老师聊聊，或者我帮你预约心理辅导？"
    elif risk_level == "medium":
        return "\n\n💪 听起来你最近压力不小，照顾好自己，需要的话我随时在～"
    return ""


def _create_alert(student_id: int, emotion: dict, user_msg: str):
    """创建心理预警"""
    existing = _db.query_one(
        """SELECT id FROM mental_health_alert
           WHERE student_id = %s AND follow_up_status = 'pending'
           AND DATE(created_at) = CURDATE()""",
        (student_id,)
    )
    if existing:
        return  # 今天已有预警，不重复

    _db.insert("mental_health_alert", {
        "student_id": student_id,
        "trigger_reason": emotion.get("alert_reason", f"风险评分{emotion.get('risk_score')}"),
        "risk_level": emotion.get("risk_level", "high"),
        "alert_content": user_msg[:500],
        "emotion_label": emotion.get("emotion", ""),
        "risk_score": emotion.get("risk_score", 0),
        "follow_up_status": "pending",
    })

    # 标记画像
    _db.update("mental_health_profile", {"student_id": student_id},
               {"teacher_notified": 1})


# ============================================================
#  场景① 行政服务 - 请假
# ============================================================

def _handle_leave(student_id: int, message: str, params: dict, context: list) -> str:
    """处理请假意图：缺参数时多轮追问，补全后确认提交"""
    student = _db.query_one("SELECT name, assigned_teacher_id FROM student WHERE id = %s", (student_id,))
    student_name = student["name"] if student else "同学"

    # 查询模式 → 调企业助手接口
    if any(kw in message for kw in ["查", "状态", "审核", "审批结果", "通过了吗", "记录"]):
        import requests
        from .config import TEACHER_AGENT_URL
        try:
            r = requests.get(
                f"{TEACHER_AGENT_URL}/api/v1/student/leave-requests",
                params={"student_id": student_id},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                records = data.get("data", data.get("records", []))
                if not records:
                    return "你还没有请假记录～"
                lines = ["📋 你最近的请假记录："]
                for i, rec in enumerate(records[:5], 1):
                    status_map = {"pending": "⏳ 待审批", "approved": "✅ 已通过", "rejected": "❌ 已驳回"}
                    st = rec.get("status", "")
                    lines.append(f"{i}. {rec.get('leave_type','')} | {str(rec.get('start_time',''))[:16]} ~ {str(rec.get('end_time',''))[:16]} | {status_map.get(st, st)}")
                    if rec.get("approval_remark"):
                        lines.append(f"   备注：{rec['approval_remark']}")
                return "\n".join(lines)
        except Exception:
            pass
        return "暂时查不到请假记录，请稍后重试～"

    # ── 提交模式：多轮收集参数 ──
    # 从当前消息 + 上下文提取已收集到的参数
    collected = _collect_leave_params(message, context)

    # 检查必填项
    missing = []
    if not collected.get("leave_type"):
        missing.append("请假类型（事假/病假）")
    if not collected.get("start_time"):
        missing.append("开始时间（比如:明天上午）")
    if not collected.get("end_time"):
        missing.append("结束时间（比如:后天下午）")
    if not collected.get("reason"):
        missing.append("请假原因（比如:感冒发烧需要休息）")

    if missing:
        # 有缺失 → 反问
        have = []
        if collected.get("leave_type"):
            have.append(f"类型：{collected['leave_type']}")
        if collected.get("start_time"):
            have.append(f"开始：{collected['start_time'][:16]}")
        if collected.get("end_time"):
            have.append(f"结束：{collected['end_time'][:16]}")
        if collected.get("reason"):
            have.append(f"原因：{collected['reason']}")

        have_text = "\n".join([f"  ✅ {h}" for h in have]) if have else "  还没有任何信息"
        missing_text = "\n".join([f"  ❓ {m}" for m in missing])

        return (
            f"好的，我来帮你提交请假申请 📝\n\n"
            f"目前已确认：\n{have_text}\n\n"
            f"还需要补充：\n{missing_text}\n\n"
            f"直接告诉我就行，比如'明天上午到后天下午，感冒了需要休息'~"
        )

    # 参数齐全 → 调企业助手API提交
    import requests
    from .config import TEACHER_AGENT_URL
    try:
        r = requests.post(
            f"{TEACHER_AGENT_URL}/api/v1/student/leave-requests",
            json={
                "student_id": student_id,
                "leave_type": collected["leave_type"],
                "start_time": collected["start_time"],
                "end_time": collected["end_time"],
                "reason": collected.get("reason", "未说明"),
            },
            timeout=5,
        )
        if r.status_code == 200:
            result = r.json()
            teacher_info = ""
            if student and student.get("assigned_teacher_id"):
                teacher_info = f"，已推送给班主任(ID:{student['assigned_teacher_id']})审批"
            return (
                f"请假申请已提交 ✅\n"
                f"📝 {collected['leave_type']} | {collected['start_time'][:16]} ~ {collected['end_time'][:16]}\n"
                f"📌 状态：等待审批中{teacher_info}\n"
                f"审批完成后我会第一时间通知你～"
            )
        else:
            return "请假提交失败，请稍后重试或联系班主任～"
    except Exception:
        return "请假系统暂时不可用，请稍后重试或直接联系班主任～"


def _collect_leave_params(message: str, context: list) -> dict:
    """从当前消息+多轮上下文提取请假参数（LLM优先，关键词兜底）"""
    from datetime import datetime as _dt
    now_str = _dt.now().strftime("%Y-%m-%d %H:%M:%S")

    if llm.is_online():
        # 把最近几轮对话一起发给 LLM
        ctx_lines = []
        for m in context[-6:]:
            ctx_lines.append(f"{m['role']}: {m['content'][:300]}")
        ctx_lines.append(f"user: {message}")
        full_text = "\n".join(ctx_lines)

        prompt = f"""从以下多轮对话中提取学生的请假参数。当前时间：{now_str}

返回 JSON：
{{
  "leave_type": "病假/事假/其他",
  "start_time": "YYYY-MM-DD HH:MM:SS",
  "end_time": "YYYY-MM-DD HH:MM:SS",
  "reason": "具体原因"
}}

时间推断规则：
- "明天上午" = 明天 08:00-12:00
- "后天下午" = 后天 14:00-18:00
- "明天全天" = 明天 08:00-18:00
- "请假两天"从明天起 = 明天起两个全天
- "下周一下午" = 下周一 14:00
- "这周五" = 本周五 08:00-18:00

如果某个参数在多轮对话中都没有出现，该字段填 null。只返回 JSON。"""

        try:
            result = llm.chat_json([{"role": "user", "content": full_text}], prompt)
            if isinstance(result, dict):
                # 去除 null 值
                return {k: v for k, v in result.items() if v is not None}
        except Exception:
            pass

    # ── 关键词兜底 ──
    result = {}
    if "病" in message:
        result["leave_type"] = "病假"
    elif "事" in message:
        result["leave_type"] = "事假"

    # 从上下文也搜一下
    all_text = message
    for m in context[-4:]:
        all_text += " " + m.get("content", "")

    import re
    # 简单的时间提取
    date_patterns = [
        (r"明天上午", lambda: f"{_dt.now().strftime('%Y-%m-%d')} 08:00:00"),
        (r"明天下午", lambda: f"{_dt.now().strftime('%Y-%m-%d')} 14:00:00"),
    ]
    for pattern, fn in date_patterns:
        if pattern in all_text and "start_time" not in result:
            result["start_time"] = fn()

    return result


# ============================================================
#  场景② 心理关怀
# ============================================================

def _handle_mental(student_id: int, message: str, params: dict, context: list) -> str:
    """处理心理关怀意图（情绪分析在 _handle_emotion_update 中统一完成）"""
    emotion_type = params.get("emotion", "")

    responses = {
        "压力大": "听你说压力很大……留学确实不容易，课程、论文、生活都压在肩上。你已经很努力了 💪 要不要聊聊具体是什么让你压力最大？",
        "焦虑": "焦虑的时候，试着深呼吸几次 🫁 你愿意和我说说是哪方面让你焦虑吗？学业？申请？还是生活上的事？",
        "孤独": "一个人在国外确实容易感到孤独……很多留学生都经历过这个阶段。你有没有想过参加一些社团活动，或者和班上的同学约个饭？我也可以帮你看看有什么学生活动～",
        "难过": "💙 我在听。有些时候不需要解决方案，只需要有个人愿意听。你想说什么都可以～",
        "想家": "想家是最正常不过的事了。有没有试过和家人视频？哪怕只是看看家里的猫🐱。",
    }

    for key, resp in responses.items():
        if key in emotion_type or key in message:
            return resp

    return "我听到了。留学路上有起有落，每一步都是在往前走。需要的话，随时可以找我聊聊 🌿"


# ============================================================
#  场景③ 售后反馈 - 投诉建议
# ============================================================

def _handle_feedback(student_id: int, message: str, params: dict, context: list) -> str:
    """处理投诉/反馈意图"""
    student = _db.query_one("SELECT name FROM student WHERE id = %s", (student_id,))
    student_name = student["name"] if student else "同学"

    # 判断是查询还是新建
    if any(kw in message for kw in ["查询", "进度", "状态", "处理", "怎么样"]):
        tickets = _db.query(
            """SELECT id, title, category, urgency, status, handler_name, resolution, created_at
               FROM feedback_ticket WHERE student_id = %s ORDER BY created_at DESC LIMIT 5""",
            (student_id,)
        )
        if not tickets:
            return "你还没有提交过反馈或投诉～有什么问题可以直接告诉我！"

        lines = ["📋 你的反馈工单："]
        for t in tickets:
            status_map = {"open": "📭 待处理", "processing": "🔄 处理中",
                          "resolved": "✅ 已解决", "closed": "📁 已关闭"}
            status_text = status_map.get(t["status"], t["status"])
            lines.append(f"· [{t['category']}] {t['title']} — {status_text}")
            if t.get("resolution"):
                lines.append(f"  处理：{t['resolution'][:80]}")
        return "\n".join(lines)

    # 检查是否信息不足 → 追问
    vague_keywords = ["我要反馈", "我想反馈", "我要投诉", "我想投诉", "我有问题", "有问题反馈"]
    is_vague = any(kw in message for kw in vague_keywords) and len(message) <= 15
    if is_vague:
        return (
            "好的，我来帮你提交反馈 📝\n\n"
            "请告诉我具体遇到了什么问题？\n"
            "比如：\n"
            "• \"宿舍空调坏了一周报修没人来\"\n"
            "• \"签证材料提交两周了没反馈\"\n"
            "• \"对课程安排有建议想说\"\n\n"
            "越详细越好，我会帮你整理成工单提交～"
        )

    # 新建工单
    title = params.get("title", message[:50])
    summary = llm.summarize(message)
    category = llm.classify_category(message)
    urgency = "urgent" if any(w in message for w in ["急", "严重", "马上", "立刻", "立刻"]) else "normal"
    priority = 10 if urgency == "urgent" else 5

    ticket_id = _db.insert("feedback_ticket", {
        "student_id": student_id,
        "title": title,
        "content": message,
        "summary": summary,
        "category": category,
        "urgency": urgency,
        "status": "open",
        "priority": priority,
    })

    urgency_text = "🚨 紧急工单" if urgency == "urgent" else "📝 普通工单"
    return (
        f"已收到你的反馈，工单已创建 ✅\n"
        f"{urgency_text} | 分类：{category}\n"
        f"📋 摘要：{summary}\n"
        f"我们会在24小时内跟进处理，处理完成后会通知你～"
    )


# ============================================================
#  场景④ 学业考务
# ============================================================

def _handle_academic(student_id: int, message: str, params: dict, context: list) -> str:
    """处理学业考务意图"""
    schedule = _db.query(
        """SELECT event_type, title, course_name, deadline, priority, status,
                  DATEDIFF(deadline, NOW()) AS days_left
           FROM academic_schedule
           WHERE student_id = %s AND status != 'completed'
           ORDER BY deadline ASC""",
        (student_id,)
    )

    if not schedule:
        return "你目前没有待完成的学业日程～继续保持！"

    # 过滤：如果问了特定类型（考试/论文），只返回匹配的
    if any(w in message for w in ["考试", "考", "exam"]):
        schedule = [s for s in schedule if s["event_type"] == "考试"]
    elif any(w in message for w in ["论文", "DDL", "deadline", "截止"]):
        schedule = [s for s in schedule if "论文" in s["event_type"] or "DDL" in s["event_type"]]

    if not schedule:
        return "没有找到相关的学业日程～"

    lines = ["📅 你的学业日程："]
    for s in schedule[:8]:
        days = s["days_left"]
        if days is not None and days < 0:
            days_text = f"⚠️ 已过期"
        elif days == 0:
            days_text = f"🔴 今天！"
        elif days <= 3:
            days_text = f"🔴 还剩{days}天"
        elif days <= 7:
            days_text = f"🟡 还剩{days}天"
        else:
            days_text = f"🟢 还剩{days}天"

        lines.append(
            f"· [{s['event_type']}] {s['title']} | {s['course_name'] or ''}\n"
            f"  截止：{str(s['deadline'])[:16]} | {days_text}"
        )

    return "\n".join(lines)


# ============================================================
#  场景⑤ 进度追踪
# ============================================================

def _handle_progress(student_id: int, message: str, params: dict, context: list) -> str:
    """处理申请进度查询"""
    apps = _db.query(
        """SELECT program_name, university, current_step, application_status,
                  submitted_date, estimated_completion
           FROM application_progress
           WHERE student_id = %s ORDER BY updated_at DESC""",
        (student_id,)
    )

    if not apps:
        return "你还没有留学申请记录～需要我帮你看看适合的项目吗？"

    lines = ["📊 你的留学申请进度："]
    for app in apps:
        steps_json = _db.query_one(
            "SELECT steps FROM application_progress WHERE id = %s",
            (app.get("id"),)
        )
        steps = []
        if steps_json and steps_json.get("steps"):
            try:
                steps = json.loads(steps_json["steps"]) if isinstance(steps_json["steps"], str) else steps_json["steps"]
            except (json.JSONDecodeError, TypeError):
                pass

        status_icon = {"in_progress": "🔄", "completed": "✅", "withdrawn": "❌"}.get(
            app["application_status"], "📋")

        lines.append(f"\n{status_icon} {app['program_name']} — {app['university']}")
        lines.append(f"   当前：{app['current_step']}")

        if steps:
            step_line = " → ".join([
                f"{'✅' if s.get('status') == 'completed' else '🔄' if s.get('status') == 'in_progress' else '⏳'} {s}"
                if isinstance(s, str) else
                f"{'✅' if s.get('status') == 'completed' else '🔄'} {s.get('step', '')}"
                for s in steps
            ])
            lines.append(f"   流程：{step_line}")

        if app.get("estimated_completion"):
            lines.append(f"   预计完成：{str(app['estimated_completion'])[:10]}")

    return "\n".join(lines)


# ============================================================
#  场景⑥ 生活支持 - RAG
# ============================================================

def _handle_life_guide(student_id: int, message: str, params: dict, context: list) -> str:
    """海外生活指南：FAQ优先 → RAG检索 → 智能降级"""
    # 泛问 → 展示菜单
    generic_words = ["海外生活", "生活指南", "海外指南", "生活支持"]
    if any(kw in message for kw in generic_words) and len(message) <= 15:
        return (
            "关于海外的学习生活，我了解以下信息～\n\n"
            "🏥 医疗就医\n"
            "🏠 租房住宿\n"
            "🚇 交通出行\n"
            "💳 银行卡与通讯\n"
            "🆘 紧急求助\n"
            "📚 留学政策\n"
            "🎓 升学项目\n\n"
            "直接告诉我想了解哪方面，我给你详细解答～"
        )

    # Step1: FAQ精确匹配
    try:
        from .knowledge import get_kb
        kb = get_kb()
        if kb and kb.is_loaded():
            faq_ans = kb.faq_match(message)
            if faq_ans:
                return faq_ans
            # Step2: RAG检索
            docs = kb.search(message, top_k=3)
            if docs:
                ctx = "\n\n".join(docs)
                instruction = f"基于以下知识库内容回答学生问题。如果信息不够，如实说。\n\n{ctx}"
                return llm.agent_chat(message, context, extra_instruction=instruction)
    except ImportError:
        pass

    # Step3: 智能降级——根据关键词引导到具体问题
    topic_hints = {
        "医疗": "试试问:新加坡看病流程 或 怎么用医保",
        "住房": "试试问:新加坡租房要注意什么",
        "交通": "试试问:新加坡怎么坐地铁",
        "银行": "试试问:新加坡怎么办银行卡",
        "紧急": "试试问:新加坡紧急求助电话",
        "签证": "试试问:学生签证怎么续签",
    }
    for kw, hint in topic_hints.items():
        if kw in message:
            return f"关于这方面，{hint}，我给你更详细的回答～"

    return "这方面我暂时了解不够全面，你可以换个方式问我，比如:新加坡怎么看病、德国有哪些专业~"


# ============================================================
#  场景⑦ 增值转化
# ============================================================

def _handle_upgrade(student_id: int, message: str, params: dict, context: list) -> str:
    """处理升学意向"""
    # 检查是继续聊还是新意向
    follow_keywords = ["预约", "联系", "报名", "怎么申请", "怎么报", "多少钱", "费用", "多久", "什么时候", "顾问", "一对一"]
    is_followup = any(kw in message for kw in follow_keywords) or len(message) <= 5

    if is_followup:
        prev_followup_count = sum(1 for m in context[-6:] if m.get("role") == "assistant" and ("预约留学顾问" in m.get("content", "") or "我可以帮你" in m.get("content", "")))
        if prev_followup_count > 0:
            # 学生确认了 → 更新意向状态为 interested（更新该学生最近一条identified）
            latest = _db.query_one("SELECT id FROM upgrade_interest WHERE student_id = %s AND conversion_status = 'identified' ORDER BY id DESC LIMIT 1", (student_id,))
            if latest:
                _db.update("upgrade_interest", {"id": latest["id"]}, {"conversion_status": "interested", "contacted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            return "好的！已经为你登记了顾问预约需求 📋\n\n顾问会在1-2个工作日内联系你，届时可以详细沟通你的升学方向、申请条件和时间规划。\n\n如果还有其他问题随时找我～"
        return (
            "好的！关于升学深造的具体事宜，我可以帮你：\n\n"
            "📞 预约留学顾问一对一免费咨询\n"
            "📋 获取详细的项目手册和申请条件\n"
            "📅 了解最新的申请截止日期\n\n"
            "告诉我你想了解的方向，我马上安排顾问联系你～"
        )

    # 检查是否已有意向 → 不重复插入
    existing = _db.query_one(
        "SELECT id FROM upgrade_interest WHERE student_id = %s AND DATE(created_at) = CURDATE()",
        (student_id,)
    )

    student = _db.query_one(
        """SELECT name, education, major, gpa, language_score,
                  target_country, target_degree, target_major
           FROM student WHERE id = %s""",
        (student_id,)
    )

    # 记录意向（当天不重复）
    if not existing:
        _db.insert("upgrade_interest", {
            "student_id": student_id,
            "interest_degree": params.get("degree", "硕士咨询"),
            "interest_country": params.get("country", ""),
            "interest_major": params.get("major", ""),
            "detected_source": "对话识别",
            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "conversation_snippet": message[:300],
            "conversion_status": "identified",
        })

    # 生成推荐
    profile = {
        "name": student["name"] if student else "同学",
        "education": student.get("education", ""),
        "major": student.get("major", ""),
        "gpa": student.get("gpa", ""),
        "language_score": student.get("language_score", ""),
        "target_country": student.get("target_country", ""),
    }
    recommendation = llm.generate_recommendation(profile)

    return (
        f"{recommendation}\n\n"
        f"💡 如果感兴趣，我可以帮你预约留学顾问做一对一咨询，为你定制专属升学方案～"
    )


# ============================================================
#  场景⑧ NL2SQL - 自然语言查库
# ============================================================

def _handle_nl2sql(student_id: int, message: str, params: dict, context: list) -> str:
    """NL2SQL：自然语言 → SQL → 执行 → 润色"""
    from .db import get_schema_description

    # 把 student_id 注入问题
    enriched = message.replace("我", f"学生ID={student_id}")

    schema = get_schema_description()
    sql = llm.generate_sql(enriched, schema)

    if sql.startswith("--"):
        return "抱歉，这个查询我暂时无法执行～"

    try:
        data = _db.query(sql)
    except Exception as e:
        return f"查询时遇到了一点问题，请换个方式问问看～"

    return llm.polish_answer(message, sql, data)


# ============================================================
#  场景⑨ 闲聊
# ============================================================

def _handle_chat(student_id: int, message: str, params: dict, context: list) -> str:
    """闲聊兜底"""
    return llm.agent_chat(message, context)


# ============================================================
#  意图 → 处理函数映射
# ============================================================

INTENT_HANDLERS = {
    "leave":      _handle_leave,
    "mental":     _handle_mental,
    "feedback":   _handle_feedback,
    "academic":   _handle_academic,
    "progress":   _handle_progress,
    "life_guide": _handle_life_guide,
    "upgrade":    _handle_upgrade,
    "nl2sql":     _handle_nl2sql,
    "chat":       _handle_chat,
}
