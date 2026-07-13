"""
请假服务 — leave_request 表（与企业端统一）
"""

import logging
import re
import requests
from datetime import datetime, timedelta
from typing import Optional

from student_agent import db
from student_agent import llm
from student_agent.config import TEACHER_AGENT_URL

logger = logging.getLogger(__name__)

STATUS_MAP = {0: "⏳ 待审批", 1: "✅ 已通过", 2: "❌ 已驳回"}


def collect_leave_params(message: str, context: list) -> dict:
    """LLM优先 + 关键词兜底提取请假参数"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if llm.is_online():
        ctx_lines = []
        for m in context[-6:]:
            ctx_lines.append(f"{m.get('role','?')}: {(m.get('content','') or '')[:300]}")
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
                return {k: v for k, v in result.items() if v is not None}
        except Exception as e:
            logger.warning("LLM 请假参数提取失败，降级至关键词: %s", e)

    # 关键词兜底
    result = {}
    if "病" in message:
        result["leave_type"] = "病假"
    elif "事" in message:
        result["leave_type"] = "事假"

    all_text = message
    for m in context[-4:]:
        all_text += " " + m.get("content", "")

    today = datetime.now()
    tom = today + timedelta(days=1)
    dat = today + timedelta(days=2)

    date_patterns = [
        (r"今天上午|今天早上", lambda: today.strftime("%Y-%m-%d 08:00:00")),
        (r"今天下午",           lambda: today.strftime("%Y-%m-%d 14:00:00")),
        (r"今天全天|今天",       lambda: today.strftime("%Y-%m-%d 08:00:00")),
        (r"明天上午|明天早上",   lambda: tom.strftime("%Y-%m-%d 08:00:00")),
        (r"明天下午",           lambda: tom.strftime("%Y-%m-%d 14:00:00")),
        (r"明天全天|明天",       lambda: tom.strftime("%Y-%m-%d 08:00:00")),
        (r"后天上午|后天早上",   lambda: dat.strftime("%Y-%m-%d 08:00:00")),
        (r"后天下午",           lambda: dat.strftime("%Y-%m-%d 14:00:00")),
        (r"后天全天|后天",       lambda: dat.strftime("%Y-%m-%d 08:00:00")),
    ]
    for pattern, fn in date_patterns:
        if re.search(pattern, all_text):
            if "start_time" not in result:
                result["start_time"] = fn()
            break

    if "start_time" in result and "end_time" not in result:
        base_date = result["start_time"][:10]
        if "上午" in all_text and "下午" not in all_text:
            result["end_time"] = f"{base_date} 12:00:00"
        elif "下午" in all_text:
            result["end_time"] = f"{base_date} 18:00:00"
        elif "全天" in all_text:
            result["end_time"] = f"{base_date} 18:00:00"

    reason_match = re.search(r"(?:因为|由于|需要|要)(.{2,30})(?:休息|看病|处理|回家|办事|调整)", all_text)
    if reason_match and "reason" not in result:
        result["reason"] = reason_match.group(0)[:100]

    return result


def query_leave_records(student_id: int) -> list[dict]:
    return db.query(
        """SELECT id, leave_type, start_date, end_date, reason, status, approval_user, create_time
           FROM leave_application
           WHERE applicant_id = %s AND applicant_type = '学生'
           ORDER BY create_time DESC""",
        (student_id,)) or []


def _format_records_message(records: list[dict]) -> str:
    if not records:
        return "你还没有请假记录～"
    lines = ["📋 你最近的请假记录："]
    for i, rec in enumerate(records[:5], 1):
        st = rec.get("status", 0)
        lines.append(
            f"{i}. {rec.get('leave_type','')} | "
            f"{rec.get('start_date','')} ~ {rec.get('end_date','')} | "
            f"{STATUS_MAP.get(st, str(st))}")
        if rec.get("approval_user"):
            lines.append(f"   审批人：{rec['approval_user']}")
    return "\n".join(lines)


def fetch_remote_records(student_id: int) -> Optional[str]:
    try:
        r = requests.get(f"{TEACHER_AGENT_URL}/api/v1/student/leave-requests",
                         params={"student_id": student_id}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            records = data.get("data", data.get("records", []))
            return _format_records_message(records)
    except requests.RequestException as e:
        logger.warning("远程请假记录查询失败: %s", e)
    return None


def query_records(student_id: int) -> str:
    remote_result = fetch_remote_records(student_id)
    if remote_result:
        return remote_result
    return _format_records_message(query_leave_records(student_id))


def _check_fields(collected: dict) -> tuple[list[str], list[str]]:
    missing, have = [], []
    if collected.get("leave_type"): have.append(f"类型：{collected['leave_type']}")
    else: missing.append("请假类型（事假/病假）")
    if collected.get("start_time"): have.append(f"开始：{collected['start_time'][:16]}")
    else: missing.append("开始时间（比如：明天上午）")
    if collected.get("end_time"): have.append(f"结束：{collected['end_time'][:16]}")
    else: missing.append("结束时间（比如：后天下午）")
    if collected.get("reason"): have.append(f"原因：{collected['reason']}")
    else: missing.append("请假原因（比如：感冒发烧需要休息）")
    return have, missing


def build_missing_prompt(collected: dict) -> str:
    have, missing = _check_fields(collected)
    have_text = "\n".join([f"  ✅ {h}" for h in have]) if have else "  还没有任何信息"
    missing_text = "\n".join([f"  ❓ {m}" for m in missing])
    return (f"好的，我来帮你提交请假申请 📝\n\n目前已确认：\n{have_text}\n\n"
            f"还需要补充：\n{missing_text}\n\n"
            f"直接告诉我就行，比如'明天上午到后天下午，感冒了需要休息'～")


def submit_leave(student_id: int, collected: dict) -> str:
    leave_type = collected.get("leave_type", "其他")
    start_time = collected.get("start_time", "")
    end_time = collected.get("end_time", "")
    reason = collected.get("reason", "未说明")
    start_date = start_time[:10] if start_time else ""
    end_date = end_time[:10] if end_time else ""

    # 重复检测
    dup = db.query_one(
        """SELECT id, status FROM leave_application
           WHERE applicant_id = %s AND applicant_type = '学生'
             AND leave_type = %s AND start_date = %s AND end_date = %s
             AND DATE(create_time) = CURDATE() LIMIT 1""",
        (student_id, leave_type, start_date, end_date))
    if dup:
        return f"你今天已经提交过相同的请假申请了，无需重复提交～"

    student = db.query_one("SELECT name, assigned_teacher_id FROM student WHERE id = %s", (student_id,))
    student_name = (student["name"] if student else "同学") if student else "同学"

    r = None
    try:
        r = requests.post(f"{TEACHER_AGENT_URL}/api/v1/student/leave-requests",
                          json={"student_id": student_id, "leave_type": leave_type,
                                "start_time": start_time, "end_time": end_time, "reason": reason},
                          timeout=5)
        if r.status_code == 200:
            teacher_info = ""
            if student and student.get("assigned_teacher_id"):
                teacher_info = f"，已推送给班主任(ID:{student['assigned_teacher_id']})审批"
            return (f"请假申请已提交 ✅\n📝 {leave_type} | {start_date} ~ {end_date}\n"
                    f"📌 状态：等待审批中{teacher_info}\n审批完成后，下次登录时可以查看审批结果～")
        logger.warning("请假提交远程API返回非200: %s，降级至本地落库", r.status_code)
    except requests.RequestException as e:
        logger.warning("请假提交远程API不可用: %s，降级至本地落库", e)

    if r is None or r.status_code != 200:
        try:
            tid = db.insert("leave_application", {
                "applicant_id": student_id, "applicant_type": "学生",
                "student_name": student_name, "leave_type": leave_type,
                "start_date": start_date, "end_date": end_date,
                "reason": reason, "status": 0})
            logger.info("请假本地落库成功: id=%s", tid)
            return (f"请假申请已提交 ✅\n📝 {leave_type} | {start_date} ~ {end_date}\n"
                    f"📌 状态：等待审批中\n系统已完成记录，稍后同步给审批老师～")
        except Exception as db_err:
            logger.error("请假本地落库失败: %s", db_err)
            return "请假系统暂时不可用，请稍后重试或直接联系班主任～"


def handle_leave(student_id: int, message: str, params: dict, context: list) -> str:
    if any(kw in message for kw in ["查", "状态", "审核", "审批结果", "通过了吗", "记录", "进度", "审批",
                                      "批了", "怎么样", "如何", "了吗", "好了吗", "结果"]):
        return query_records(student_id)
    collected = collect_leave_params(message, context)
    have, missing = _check_fields(collected)
    if missing:
        return build_missing_prompt(collected)
    return submit_leave(student_id, collected)


def update_approval_status(leave_id: int, status: int, approval_user: str = None) -> bool:
    update_data = {"status": status, "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if approval_user:
        update_data["approval_user"] = approval_user
    return db.update("leave_application", {"id": leave_id}, update_data) > 0
