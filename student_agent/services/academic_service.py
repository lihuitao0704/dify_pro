"""
学业考务服务 — 学术日程查询、申请进度追踪

包含两大部分：
  1. 学业日程（academic_schedule）：考试、论文DDL、选课截止等
  2. 申请进度（application_progress）：留学申请各阶段状态追踪

功能：
  - 按类型筛选（考试/论文/DDL）
  - 剩余天数计算与可视化
  - 步骤进度展示与状态面板
"""

import json
import logging
from datetime import datetime
from typing import Optional

from student_agent import db

logger = logging.getLogger(__name__)


# ============================================================
# 学业日程
# ============================================================

def query_schedule(
    student_id: int,
    event_type: str = None,
    status: str = "upcoming",
    limit: int = 8,
) -> list[dict]:
    """
    查询学生学业日程。

    参数:
        student_id: 学生ID
        event_type: 按类型筛选（"考试"/"论文DDL"等，None=全部）
        status:     按状态筛选（默认 "upcoming" 未完成）
        limit:      返回上限

    返回:
        日程记录列表
    """
    if status:
        conditions = ["student_id = %s", "status != 'completed'"]
        params = [student_id]
    else:
        conditions = ["student_id = %s"]
        params = [student_id]

    if event_type:
        conditions.append("event_type = %s")
        params.append(event_type)

    where = " AND ".join(conditions)
    sql = f"""SELECT event_type, title, course_name, deadline, priority, status,
                     DATEDIFF(deadline, NOW()) AS days_left
              FROM academic_schedule
              WHERE {where}
              ORDER BY deadline ASC
              LIMIT %s"""
    params.append(limit)

    return db.query(sql, tuple(params))


def filter_schedule_by_keyword(schedule: list[dict], message: str) -> list[dict]:
    """
    根据消息关键词过滤日程列表。

    参数:
        schedule: 原始日程列表
        message:  学生消息（用于关键词匹配）

    返回:
        过滤后的日程列表
    """
    if any(w in message for w in ["考试", "考", "exam"]):
        return [s for s in schedule if s["event_type"] == "考试"]
    elif any(w in message for w in ["论文", "DDL", "deadline", "截止"]):
        return [s for s in schedule if "论文" in s["event_type"] or "DDL" in s["event_type"]]
    return schedule


def _format_schedule(schedule: list[dict]) -> str:
    """
    将学业日程格式化为用户可读的文本。

    参数:
        schedule: 日程记录列表

    返回:
        格式化文本
    """
    if not schedule:
        return "你目前没有待完成的学业日程～继续保持！"

    lines = ["📅 你的学业日程："]
    for s in schedule:
        days = s["days_left"]
        if days is not None and days < 0:
            days_text = "⚠️ 已过期"
        elif days == 0:
            days_text = "🔴 今天！"
        elif days <= 3:
            days_text = f"🔴 还剩{days}天"
        elif days <= 7:
            days_text = f"🟡 还剩{days}天"
        else:
            days_text = f"🟢 还剩{days}天"

        lines.append(
            f"· [{s['event_type']}] {s['title']} | {s.get('course_name', '') or ''}\n"
            f"  截止：{str(s['deadline'])[:16]} | {days_text}"
        )

    return "\n".join(lines)


def query_scores(student_id: int) -> list[dict]:
    """
    查询学生成绩（student_score 表）。

    参数:
        student_id: 学生ID

    返回:
        成绩记录列表，按 exam_date 降序
    """
    return db.query(
        """SELECT subject, score, exam_type, exam_date
           FROM student_score
           WHERE student_id = %s
           ORDER BY exam_date DESC""",
        (student_id,)
    )


def _format_scores(scores: list[dict]) -> str:
    """将成绩列表格式化为用户可读文本"""
    if not scores:
        return "还没有你的成绩记录～"

    lines = ["📊 你的成绩："]
    for s in scores:
        lines.append(
            f"· {s['subject']} — {s['score']}分 "
            f"({s.get('exam_type', '')}, {str(s.get('exam_date', ''))})"
        )
    return "\n".join(lines)


def is_score_query(message: str) -> bool:
    """判断是否为成绩查询"""
    score_words = ["成绩", "分数", "绩点", "gpa", "GPA", "考了多少", "多少分"]
    return any(kw in message for kw in score_words)


def handle_academic(student_id: int, message: str, params: dict, context: list) -> str:
    """
    处理学业考务查询意图完整 handler。

    流程：
      1. 成绩查询 → 返回成绩列表
      2. 日程查询 → 按类型过滤展示

    参数:
        student_id: 学生ID
        message:    学生消息
        params:     意图参数
        context:    对话上下文

    返回:
        回复文本
    """
    # ── 成绩查询 ──
    if is_score_query(message):
        scores = query_scores(student_id)
        return _format_scores(scores)

    # ── 日程查询 ──
    schedule = query_schedule(student_id)

    if not schedule:
        return "你目前没有待完成的学业日程～继续保持！"

    # 关键词过滤
    filtered = filter_schedule_by_keyword(schedule, message)

    if not filtered:
        if any(w in message for w in ["考试", "考", "exam"]):
            return "没有找到相关考试日程～"
        elif any(w in message for w in ["论文", "DDL", "deadline", "截止"]):
            return "没有找到相关的论文或DDL日程～"
        return "没有找到相关的学业日程～"

    return _format_schedule(filtered)


# ============================================================
# 申请进度
# ============================================================

def query_application_progress(student_id: int) -> list[dict]:
    """
    查询学生留学申请进度。

    参数:
        student_id: 学生ID

    返回:
        申请记录列表，按 updated_at 降序
    """
    return db.query(
        """SELECT id, program_name, university, current_step, application_status,
                  submitted_date, estimated_completion
           FROM application_progress
           WHERE student_id = %s
           ORDER BY updated_at DESC""",
        (student_id,)
    )


def _parse_steps(app: dict) -> list:
    """
    解析申请记录的步骤 JSON。

    参数:
        app: 申请记录 dict（含 steps 字段）

    返回:
        步骤列表（可迭代元素）
    """
    steps = []
    steps_raw = db.query_one(
        "SELECT steps FROM application_progress WHERE id = %s",
        (app.get("id"),)
    )
    if steps_raw and steps_raw.get("steps"):
        try:
            raw = steps_raw["steps"]
            steps = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            pass
    return steps


def _format_step(steps: list) -> str:
    """
    将步骤列表格式化为箭头连接的进度展示字符串。

    参数:
        steps: 步骤列表（字符串或 dict）

    返回:
        格式化步骤字符串
    """
    parts = []
    for s in steps:
        if isinstance(s, str):
            parts.append(s)
        elif isinstance(s, dict):
            parts.append(s.get("step", str(s)))
    return " → ".join(parts)


def _format_progress(apps: list[dict]) -> str:
    """
    将申请进度记录格式化为用户可读的文本。

    参数:
        apps: 申请记录列表

    返回:
        格式化文本
    """
    if not apps:
        return "你还没有留学申请记录～需要我帮你看看适合的项目吗？"

    lines = ["📊 你的留学申请进度："]

    for app in apps:
        status_icon = {
            "in_progress": "🔄",
            "completed": "✅",
            "withdrawn": "❌",
        }.get(app.get("application_status", ""), "📋")

        lines.append(f"\n{status_icon} {app['program_name']} — {app['university']}")
        lines.append(f"   当前：{app.get('current_step', '')}")

        # 步骤详情
        steps = _parse_steps(app)
        if steps:
            step_str = _format_step(steps)
            lines.append(f"   流程：{step_str}")

        # 预计完成时间
        if app.get("estimated_completion"):
            lines.append(f"   预计完成：{str(app['estimated_completion'])[:10]}")

    return "\n".join(lines)


def handle_progress(student_id: int, message: str, params: dict, context: list) -> str:
    """
    处理申请进度查询意图完整 handler。

    参数:
        student_id: 学生ID
        message:    学生消息
        params:     意图参数
        context:    对话上下文

    返回:
        回复文本
    """
    apps = query_application_progress(student_id)
    return _format_progress(apps)


# ============================================================
# 额外辅助方法
# ============================================================

def get_upcoming_deadlines(student_id: int, days: int = 7) -> list[dict]:
    """
    查询最近 N 天内即将到期的学业日程。

    参数:
        student_id: 学生ID
        days:       未来天数（默认7天）

    返回:
        即将到期的日程列表
    """
    return db.query(
        """SELECT event_type, title, course_name, deadline,
                  DATEDIFF(deadline, NOW()) AS days_left
           FROM academic_schedule
           WHERE student_id = %s
             AND status != 'completed'
             AND deadline BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL %s DAY)
           ORDER BY deadline ASC""",
        (student_id, days)
    )


def count_upcoming_events(student_id: int) -> dict:
    """
    统计各类型未完成学业事件数量。

    参数:
        student_id: 学生ID

    返回:
        {"考试": N, "论文DDL": N, "答辩": N, "total": N}
    """
    rows = db.query(
        """SELECT event_type, COUNT(*) AS cnt
           FROM academic_schedule
           WHERE student_id = %s AND status != 'completed'
           GROUP BY event_type""",
        (student_id,)
    )
    result = {"total": 0}
    for row in rows:
        result[row["event_type"]] = row["cnt"]
        result["total"] += row["cnt"]
    return result
