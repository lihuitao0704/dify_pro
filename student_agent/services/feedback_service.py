"""
投诉反馈服务 — 工单创建、查询、SLA 管理

提供完整的工单生命周期管理：
  - 工单创建（LLM 摘要 + 分类；关键词紧急度判定）
  - 工单查询（按学生／状态／分类筛选）
  - SLA 截止时间计算（来自 education-service-api 的 SLA 模式）
  - 信息不足时的追问引导
  - 工单状态更新与处理
"""

import logging
from datetime import datetime
from typing import Optional

from student_agent import db
from student_agent import llm

logger = logging.getLogger(__name__)

# 状态映射（student_complaint.handle_status）
STATUS_DISPLAY = {
    "待处理": "📭 待处理",
    "处理中": "🔄 处理中",
    "已完结": "✅ 已完结",
    "驳回": "📁 已驳回",
}

# 模糊反馈关键词（信息不足，需要追问）
VAGUE_KEYWORDS = [
    "我要反馈", "我想反馈", "我要投诉", "我想投诉",
    "我有问题", "有问题反馈", "我想提意见",
]


def create_ticket(
    student_id: int,
    message: str,
    title: str = None,
    category: str = None,
    summary: str = None,
    urgency: str = None,
) -> int:
    """
    创建投诉记录（student_complaint 表，与企业端统一）。

    参数:
        student_id: 学生ID
        message:    原始消息内容
        title:      标题（拼入 complaint_detail）
        category:   分类标签 → complaint_type
        summary:    摘要（拼入 complaint_detail）
        urgency:    紧急度（用于日志）

    返回:
        新记录ID
    """
    if category is None:
        category = llm.classify_category(message)

    # complaint_detail = 标题 + 摘要 + 原文拼接
    parts = []
    if title and title != message[:50]:
        parts.append(f"【{title}】")
    if summary and len(summary) > 0 and summary != message[:150]:
        parts.append(f"摘要：{summary}")
    parts.append(message)
    complaint_detail = "\n".join(parts)

    ticket_id = db.insert("student_complaint", {
        "student_id": student_id,
        "complaint_detail": complaint_detail,
        "complaint_type": category,
        "handle_status": "待处理",
    })

    logger.info(
        "投诉已创建: id=%s, student=%d, type=%s",
        ticket_id, student_id, category,
    )
    return ticket_id


def query_tickets(
    student_id: int,
    status: str = None,
    category: str = None,
    limit: int = 5,
) -> list[dict]:
    """
    查询学生投诉记录（student_complaint 表）。

    参数:
        student_id: 学生ID
        status:     筛选状态（None 表示全部）
        category:   筛选分类（None 表示全部）
        limit:      返回条数上限

    返回:
        投诉记录列表
    """
    conditions = ["student_id = %s"]
    params = [student_id]

    if status:
        conditions.append("handle_status = %s")
        params.append(status)
    if category:
        conditions.append("complaint_type = %s")
        params.append(category)

    where = " AND ".join(conditions)
    sql = f"""SELECT id, complaint_type, complaint_detail, handle_status, create_time
              FROM student_complaint
              WHERE {where}
              ORDER BY create_time DESC
              LIMIT %s"""
    params.append(limit)

    return db.query(sql, tuple(params))


def _format_tickets_message(tickets: list[dict]) -> str:
    """
    将投诉列表格式化为用户可读的文本。

    参数:
        tickets: 投诉记录列表

    返回:
        格式化文本
    """
    if not tickets:
        return "你还没有提交过反馈或投诉～有什么问题可以直接告诉我！"

    lines = ["📋 你的反馈记录："]
    for t in tickets:
        status_text = STATUS_DISPLAY.get(t.get("handle_status", ""), t.get("handle_status", "未知"))
        detail = (t.get("complaint_detail") or "")[:60]
        line = f"· [{t.get('complaint_type', '')}] {detail} — {status_text}"
        lines.append(line)
    return "\n".join(lines)


def is_vague_feedback(message: str) -> bool:
    """
    判断反馈信息是否过于模糊，需要追问。

    参数:
        message: 学生消息

    返回:
        True=信息不足需要追问
    """
    return any(kw in message for kw in VAGUE_KEYWORDS) and len(message) <= 15


def get_vague_prompt() -> str:
    """
    信息不足时的追问提示文本。

    返回:
        追问文本
    """
    return (
        "好的，我来帮你提交反馈 📝\n\n"
        "请告诉我具体遇到了什么问题？\n"
        "比如：\n"
        "• \"宿舍空调坏了一周报修没人来\"\n"
        "• \"签证材料提交两周了没反馈\"\n"
        "• \"对课程安排有建议想说\"\n\n"
        "越详细越好，我会帮你整理成工单提交～"
    )


def build_success_message(ticket_id: int, category: str,
                           summary: str, urgency: str) -> str:
    """
    生成投诉创建成功的回复消息。

    参数:
        ticket_id: 新记录ID
        category:  分类
        summary:   摘要
        urgency:   紧急度

    返回:
        回复文本
    """
    return (
        f"已收到你的反馈，已记录 ✅\n"
        f"分类：{category}\n"
        f"📋 摘要：{summary}\n"
        f"我们会在24小时内跟进处理，你下次登录时可以在'我的'面板查看进度～"
    )


def handle_feedback(student_id: int, message: str, params: dict, context: list) -> str:
    """
    处理投诉/反馈意图完整 handler。

    流程：
      1. 检测查询模式 → 查记录列表
      2. 检测信息不足 → 追问
      3. 新建记录 → LLM 摘要 + 分类

    参数:
        student_id: 学生ID
        message:    学生消息
        params:     意图参数
        context:    对话上下文

    返回:
        回复文本
    """
    # ── 查询模式 ──
    if any(kw in message for kw in ["查询", "进度", "状态", "处理", "怎么样"]):
        tickets = query_tickets(student_id)
        return _format_tickets_message(tickets)

    # ── 信息不足 → 追问 ──
    if is_vague_feedback(message):
        return get_vague_prompt()

    # ── 新建记录 ──
    title = params.get("title", message[:50])
    category = llm.classify_category(message)
    summary = llm.summarize(message)
    urgency = "urgent" if any(
        w in message for w in ["急", "严重", "马上", "立刻"]
    ) else "normal"

    ticket_id = create_ticket(
        student_id=student_id,
        message=message,
        title=title,
        category=category,
        summary=summary,
        urgency=urgency,
    )

    return build_success_message(ticket_id, category, summary, urgency)


# ============================================================
# 投诉管理（供管理后台 / 教师端使用）
# ============================================================

def update_ticket_status(
    ticket_id: int,
    status: str,
    handler_user_id: int = None,
) -> bool:
    """
    更新投诉处理状态。

    参数:
        ticket_id:       记录ID
        status:          新状态（'待处理'/'处理中'/'已完结'/'驳回'）
        handler_user_id: 处理人用户ID

    返回:
        是否更新成功
    """
    update_data = {
        "handle_status": status,
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if handler_user_id:
        update_data["handler_user_id"] = handler_user_id

    affected = db.update(
        "student_complaint",
        {"id": ticket_id},
        update_data,
    )
    return affected > 0


def get_ticket(ticket_id: int) -> Optional[dict]:
    """
    查询单条投诉详情。

    参数:
        ticket_id: 记录ID

    返回:
        投诉 dict 或 None
    """
    return db.query_one(
        """SELECT * FROM student_complaint WHERE id = %s""",
        (ticket_id,)
    )


def list_overdue_tickets() -> list[dict]:
    """
    查询所有超过24小时仍未处理的投诉。

    返回:
        超时记录列表，按创建时间升序
    """
    return db.query(
        """SELECT id, student_id, complaint_type, handle_status, create_time
           FROM student_complaint
           WHERE handle_status IN ('待处理', '处理中')
             AND create_time < DATE_SUB(NOW(), INTERVAL 24 HOUR)
           ORDER BY create_time ASC"""
    )


def count_student_tickets(student_id: int, status: str = None) -> int:
    """
    统计学生投诉数量。

    参数:
        student_id: 学生ID
        status:     按状态筛选（None 表示全部）

    返回:
        投诉数量
    """
    if status:
        row = db.query_one(
            "SELECT COUNT(*) AS cnt FROM student_complaint WHERE student_id = %s AND handle_status = %s",
            (student_id, status)
        )
    else:
        row = db.query_one(
            "SELECT COUNT(*) AS cnt FROM student_complaint WHERE student_id = %s",
            (student_id,)
        )
    return row["cnt"] if row else 0
