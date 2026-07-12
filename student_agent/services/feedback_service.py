"""
投诉反馈服务 — student_complaint 表（与企业端统一）
"""

import logging
from datetime import datetime
from typing import Optional

from student_agent import db
from student_agent import llm

logger = logging.getLogger(__name__)

STATUS_DISPLAY = {"待处理": "📭 待处理", "处理中": "🔄 处理中", "已完结": "✅ 已完结", "驳回": "📁 已驳回"}

VAGUE_KEYWORDS = ["我要反馈", "我想反馈", "我要投诉", "我想投诉", "我有问题", "有问题反馈", "我想提意见"]


def create_ticket(student_id: int, message: str, title: str = None,
                  category: str = None, summary: str = None, urgency: str = None) -> int:
    if category is None:
        category = llm.classify_category(message)
    parts = []
    if title and title != message[:50]:
        parts.append(f"【{title}】")
    if summary and summary != message[:150]:
        parts.append(f"摘要：{summary}")
    parts.append(message)
    complaint_detail = "\n".join(parts)
    tid = db.insert("student_complaint", {
        "student_id": student_id, "complaint_detail": complaint_detail,
        "complaint_type": category, "handle_status": "待处理"})
    logger.info("投诉已创建: id=%s student=%d type=%s", tid, student_id, category)
    return tid


def query_tickets(student_id: int, status: str = None, category: str = None, limit: int = 5) -> list[dict]:
    conditions = ["student_id = %s"]
    params = [student_id]
    if status:
        conditions.append("handle_status = %s"); params.append(status)
    if category:
        conditions.append("complaint_type = %s"); params.append(category)
    where = " AND ".join(conditions)
    sql = f"""SELECT id, complaint_type, complaint_detail, handle_status, create_time
              FROM student_complaint WHERE {where} ORDER BY create_time DESC LIMIT %s"""
    params.append(limit)
    return db.query(sql, tuple(params))


def _format_tickets_message(tickets: list[dict]) -> str:
    if not tickets:
        return "你还没有提交过反馈或投诉～有什么问题可以直接告诉我！"
    lines = ["📋 你的反馈记录："]
    for t in tickets:
        status_text = STATUS_DISPLAY.get(t.get("handle_status", ""), t.get("handle_status", "未知"))
        detail = (t.get("complaint_detail") or "")[:60]
        lines.append(f"· [{t.get('complaint_type','')}] {detail} — {status_text}")
    return "\n".join(lines)


def is_vague_feedback(message: str) -> bool:
    return any(kw in message for kw in VAGUE_KEYWORDS) and len(message) <= 15


def get_vague_prompt() -> str:
    return ("好的，我来帮你提交反馈 📝\n\n请告诉我具体遇到了什么问题？\n比如：\n"
            "• \"宿舍空调坏了一周报修没人来\"\n• \"签证材料提交两周了没反馈\"\n"
            "• \"对课程安排有建议想说\"\n\n越详细越好，我会帮你整理成工单提交～")


def build_success_message(ticket_id: int, category: str, summary: str, urgency: str) -> str:
    return (f"已收到你的反馈，已记录 ✅\n分类：{category}\n📋 摘要：{summary}\n"
            f"我们会在24小时内跟进处理，你下次登录时可以在'我的'面板查看进度～")


def handle_feedback(student_id: int, message: str, params: dict, context: list) -> str:
    if any(kw in message for kw in ["查询", "进度", "状态", "处理", "怎么样"]):
        return _format_tickets_message(query_tickets(student_id))
    if is_vague_feedback(message):
        return get_vague_prompt()
    title = params.get("title", message[:50])
    category = llm.classify_category(message)
    summary = llm.summarize(message)
    urgency = "urgent" if any(w in message for w in ["急", "严重", "马上", "立刻"]) else "normal"
    ticket_id = create_ticket(student_id=student_id, message=message, title=title,
                               category=category, summary=summary, urgency=urgency)
    return build_success_message(ticket_id, category, summary, urgency)


def update_ticket_status(ticket_id: int, status: str, handler_user_id: int = None) -> bool:
    update_data = {"handle_status": status, "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if handler_user_id:
        update_data["handler_user_id"] = handler_user_id
    return db.update("student_complaint", {"id": ticket_id}, update_data) > 0


def get_ticket(ticket_id: int) -> Optional[dict]:
    return db.query_one("SELECT * FROM student_complaint WHERE id = %s", (ticket_id,))


def list_overdue_tickets() -> list[dict]:
    return db.query("""SELECT id, student_id, complaint_type, handle_status, create_time
                       FROM student_complaint WHERE handle_status IN ('待处理','处理中')
                         AND create_time < DATE_SUB(NOW(), INTERVAL 24 HOUR) ORDER BY create_time ASC""")


def count_student_tickets(student_id: int, status: str = None) -> int:
    if status:
        row = db.query_one("SELECT COUNT(*) AS cnt FROM student_complaint WHERE student_id=%s AND handle_status=%s",
                           (student_id, status))
    else:
        row = db.query_one("SELECT COUNT(*) AS cnt FROM student_complaint WHERE student_id=%s", (student_id,))
    return row["cnt"] if row else 0
