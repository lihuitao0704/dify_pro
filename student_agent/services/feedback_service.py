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
from datetime import datetime, timedelta
from typing import Optional

from student_agent import db
from student_agent import llm
from student_agent.config import TEACHER_AGENT_URL

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================

# 默认 SLA 时长（小时）
DEFAULT_SLA_HOURS = 24

# 紧急工单 SLA（小时）
URGENT_SLA_HOURS = 4

# 状态显示映射
STATUS_DISPLAY = {
    "open": "📭 待处理",
    "processing": "🔄 处理中",
    "resolved": "✅ 已解决",
    "closed": "📁 已关闭",
}

# 模糊反馈关键词（信息不足，需要追问）
VAGUE_KEYWORDS = [
    "我要反馈", "我想反馈", "我要投诉", "我想投诉",
    "我有问题", "有问题反馈", "我想提意见",
]


def _calculate_sla_deadline(urgency: str) -> str:
    """
    计算工单 SLA 截止时间。

    来自 education-service-api 的 SLA 模式：
      sla_deadline = datetime.now() + timedelta(hours=config.SLA_HOURS)

    紧急工单 4 小时内响应，普通工单 24 小时。

    参数:
        urgency: "urgent" 或 "normal"

    返回:
        SLA 截止时间字符串 "YYYY-MM-DD HH:MM:SS"
    """
    hours = URGENT_SLA_HOURS if urgency == "urgent" else DEFAULT_SLA_HOURS
    deadline = datetime.now() + timedelta(hours=hours)
    return deadline.strftime("%Y-%m-%d %H:%M:%S")


def create_ticket(
    student_id: int,
    message: str,
    title: str = None,
    category: str = None,
    summary: str = None,
    urgency: str = "normal",
) -> int:
    """
    创建反馈工单。

    参数说明：
      - title、category、summary 可由调用方传入，也可由 LLM 自动生成
      - urgency 可根据关键词自动判定

    参数:
        student_id: 学生ID
        message:    原始消息内容
        title:      工单标题（None 则自动截取前50字）
        category:   分类标签（None 则 LLM 自动分类）
        summary:    摘要（None 则 LLM 自动生成）
        urgency:    紧急度 "normal" / "urgent"（None 则自动判定）

    返回:
        新工单ID
    """
    # 自动生成摘要
    if summary is None:
        summary = llm.summarize(message)

    # 自动分类
    if category is None:
        category = llm.classify_category(message)

    # 自动判定紧急度
    if urgency is None:
        urgency = "urgent" if any(
            w in message for w in ["急", "严重", "马上", "立刻"]
        ) else "normal"

    # 自动生成标题
    if title is None:
        title = message[:50]

    priority = 10 if urgency == "urgent" else 5

    sla_deadline = _calculate_sla_deadline(urgency)

    ticket_id = db.insert("feedback_ticket", {
        "student_id": student_id,
        "title": title,
        "content": message,
        "summary": summary,
        "category": category,
        "urgency": urgency,
        "status": "open",
        "priority": priority,
        "sla_deadline": sla_deadline,
    })

    logger.info(
        "工单已创建: id=%s, student=%d, category=%s, urgency=%s, SLA=%s",
        ticket_id, student_id, category, urgency, sla_deadline,
    )
    return ticket_id


def query_tickets(
    student_id: int,
    status: str = None,
    category: str = None,
    limit: int = 5,
) -> list[dict]:
    """
    查询学生反馈工单列表。

    参数:
        student_id: 学生ID
        status:     筛选状态（None 表示全部）
        category:   筛选分类（None 表示全部）
        limit:      返回条数上限

    返回:
        工单记录列表
    """
    conditions = ["student_id = %s"]
    params = [student_id]

    if status:
        conditions.append("status = %s")
        params.append(status)
    if category:
        conditions.append("category = %s")
        params.append(category)

    where = " AND ".join(conditions)
    sql = f"""SELECT id, title, category, urgency, status, handler_name,
                     resolution, sla_deadline, created_at
              FROM feedback_ticket
              WHERE {where}
              ORDER BY created_at DESC
              LIMIT %s"""
    params.append(limit)

    return db.query(sql, tuple(params))


def _format_tickets_message(tickets: list[dict]) -> str:
    """
    将工单列表格式化为用户可读的文本。

    参数:
        tickets: 工单列表

    返回:
        格式化文本
    """
    if not tickets:
        return "你还没有提交过反馈或投诉～有什么问题可以直接告诉我！"

    lines = ["📋 你的反馈工单："]
    for t in tickets:
        status_text = STATUS_DISPLAY.get(t["status"], t["status"])
        line = f"· [{t['category']}] {t['title']} — {status_text}"
        if t.get("resolution"):
            line += f"\n  处理：{t['resolution'][:80]}"
        if t.get("sla_deadline"):
            line += f"\n  SLA截止：{str(t['sla_deadline'])[:16]}"
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
    生成工单创建成功的回复消息。

    参数:
        ticket_id: 新工单ID
        category:  分类
        summary:   摘要
        urgency:   紧急度

    返回:
        回复文本
    """
    urgency_text = "🚨 紧急工单" if urgency == "urgent" else "📝 普通工单"
    sla_hours = URGENT_SLA_HOURS if urgency == "urgent" else DEFAULT_SLA_HOURS

    return (
        f"已收到你的反馈，工单已创建 ✅\n"
        f"{urgency_text} | 分类：{category}\n"
        f"📋 摘要：{summary}\n"
        f"我们会在 {sla_hours} 小时内跟进处理，你下次登录时可以在'我的'面板查看工单进度～"
    )


def handle_feedback(student_id: int, message: str, params: dict, context: list) -> str:
    """
    处理投诉/反馈意图完整 handler。

    流程：
      1. 检测查询模式 → 查工单列表
      2. 检测信息不足 → 追问
      3. 新建工单 → LLM 摘要 + 分类 + 紧急度判定

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

    # ── 新建工单 ──
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
# 工单管理（供管理后台 / 教师端使用）
# ============================================================

def update_ticket_status(
    ticket_id: int,
    status: str,
    handler_name: str = None,
    resolution: str = None,
) -> bool:
    """
    更新工单状态和处理信息。

    参数:
        ticket_id:    工单ID
        status:       新状态
        handler_name: 处理人姓名
        resolution:   处理方案

    返回:
        是否更新成功
    """
    update_data = {"status": status}

    if handler_name:
        update_data["handler_name"] = handler_name
    if resolution:
        update_data["resolution"] = resolution
    if status in ("resolved", "closed"):
        update_data["resolved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    affected = db.update(
        "feedback_ticket",
        {"id": ticket_id},
        update_data,
    )
    return affected > 0


def get_ticket(ticket_id: int) -> Optional[dict]:
    """
    查询单条工单详情。

    参数:
        ticket_id: 工单ID

    返回:
        工单 dict 或 None
    """
    return db.query_one(
        """SELECT * FROM feedback_ticket WHERE id = %s""",
        (ticket_id,)
    )


def list_overdue_tickets() -> list[dict]:
    """
    查询所有超过 SLA 截止时间仍未关闭的工单。

    来自 education-service-api 的超时工单查询模式：
      status IN (未关闭) AND sla_deadline < NOW()

    返回:
        超时工单列表，按 SLA 截止时间升序
    """
    return db.query(
        """SELECT id, student_id, title, category, urgency, status,
                  sla_deadline, created_at
           FROM feedback_ticket
           WHERE status IN ('open', 'processing')
             AND sla_deadline IS NOT NULL
             AND sla_deadline < NOW()
           ORDER BY sla_deadline ASC"""
    )


def count_student_tickets(student_id: int, status: str = None) -> int:
    """
    统计学生工单数量。

    参数:
        student_id: 学生ID
        status:     按状态筛选（None 表示全部）

    返回:
        工单数量
    """
    if status:
        row = db.query_one(
            "SELECT COUNT(*) AS cnt FROM feedback_ticket WHERE student_id = %s AND status = %s",
            (student_id, status)
        )
    else:
        row = db.query_one(
            "SELECT COUNT(*) AS cnt FROM feedback_ticket WHERE student_id = %s",
            (student_id,)
        )
    return row["cnt"] if row else 0
