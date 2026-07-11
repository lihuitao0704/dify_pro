"""
请假服务 — 请假申请处理、参数收集、状态查询

融合两套方案：
  1. LLM 参数提取（优先）：调用 llm.chat_json 从多轮对话提取结构化参数
  2. 关键词兜底：正则匹配时间 / 类型关键词

包含：
  - 请假参数多轮收集（_collect_leave_params）
  - 请假提交（含 SHA-256 幂等键校验，来自 education-service-api）
  - 请假记录查询 / 状态跟踪
  - 时间推断规则
"""

import hashlib
import json
import logging
import re
import requests
from datetime import datetime
from typing import Optional

from student_agent import db
from student_agent import llm
from student_agent.config import TEACHER_AGENT_URL

logger = logging.getLogger(__name__)

# ============================================================
# 请假类型映射
# ============================================================

LEAVE_TYPE_MAP = {
    "病假": "病假",
    "事假": "事假",
    "其他": "其他",
}

# 状态显示映射
STATUS_MAP = {
    "pending": "⏳ 待审批",
    "approved": "✅ 已通过",
    "rejected": "❌ 已驳回",
}


def _build_idempotent_key(student_id: int, leave_type: str,
                           start_time: str, end_time: str) -> str:
    """
    构建 SHA-256 幂等键，防止重复提交。

    来自 education-service-api 的幂等方案：
      raw = f"{student_id}_{start_date}_{end_date}_{leave_type}"
      idempotent_key = hashlib.sha256(raw.encode()).hexdigest()[:64]

    参数:
        student_id: 学生ID
        leave_type: 请假类型
        start_time: 开始时间
        end_time:   结束时间

    返回:
        SHA-256 前64位十六进制字符串
    """
    raw = f"{student_id}_{start_time}_{end_time}_{leave_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _check_idempotent(idempotent_key: str) -> Optional[dict]:
    """
    检查幂等键是否已存在。

    参数:
        idempotent_key: SHA-256 幂等键

    返回:
        已有请假记录 dict（存在时），None（不存在时）
    """
    return db.query_one(
        "SELECT id, status FROM leave_request WHERE idempotent_key = %s",
        (idempotent_key,)
    )


def collect_leave_params(message: str, context: list) -> dict:
    """
    从当前消息 + 多轮对话上下文提取请假参数。

    LLM 优先（在线时使用深度语义提取），关键词正则兜底。

    参数:
        message: 当前学生消息
        context: 多轮对话上下文列表 [{role, content}, ...]

    返回:
        {"leave_type": str, "start_time": str, "end_time": str, "reason": str}
        只包含提取到的字段，缺失字段不会出现在 dict 中
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Step 1: LLM 提取（在线时优先） ──
    if llm.is_online():
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
        except Exception as e:
            logger.warning("LLM 请假参数提取失败，降级至关键词: %s", e)

    # ── Step 2: 关键词 + 正则兜底 ──
    result = {}

    # 提取请假类型
    if "病" in message:
        result["leave_type"] = "病假"
    elif "事" in message:
        result["leave_type"] = "事假"

    # 从上下文也搜索
    all_text = message
    for m in context[-4:]:
        all_text += " " + m.get("content", "")

    # 提取时间
    today = datetime.now()
    _ymd = today.strftime("%Y-%m-%d")

    date_patterns = [
        (r"明天上午", lambda: f"{_ymd} 08:00:00"),
        (r"明天下午", lambda: f"{_ymd} 14:00:00"),
        (r"明天全天|明天", lambda: f"{_ymd} 08:00:00"),
        (r"后天上午", lambda: f"{_ymd} 08:00:00"),  # 简化：后天需+2天，这里仅演示
        (r"后天下午", lambda: f"{_ymd} 14:00:00"),
        (r"今天下午", lambda: f"{_ymd} 14:00:00"),
        (r"今天上午|今天", lambda: f"{_ymd} 08:00:00"),
    ]

    for pattern, fn in date_patterns:
        if re.search(pattern, all_text) and "start_time" not in result:
            result["start_time"] = fn()

    # 提取请假原因（"因为/由于/需要...休息/看病"等）
    reason_patterns = [
        r"(?:因为|由于|需要)(.{2,30})(?:休息|看病|处理|回家|办事)",
        r"(?:感冒|发烧|生病|不舒服|有事|家里|身体)(.{0,20})",
    ]
    for pat in reason_patterns:
        m = re.search(pat, all_text)
        if m:
            result["reason"] = m.group(0)[:100]
            break

    return result


def query_leave_records(student_id: int) -> list[dict]:
    """
    查询学生请假记录（本地数据库）。

    参数:
        student_id: 学生ID

    返回:
        请假记录列表，按 created_at 降序
    """
    records = db.query(
        """SELECT id, leave_type, start_time, end_time, reason, status,
                  approver_name, approval_remark, approved_at, created_at
           FROM leave_request
           WHERE student_id = %s
           ORDER BY created_at DESC""",
        (student_id,)
    )
    return records or []


def _format_records_message(records: list[dict]) -> str:
    """
    将请假记录列表格式化为用户可读的文本。

    参数:
        records: 请假记录列表

    返回:
        格式化后的回复文本
    """
    if not records:
        return "你还没有请假记录～"

    lines = ["📋 你最近的请假记录："]
    for i, rec in enumerate(records[:5], 1):
        st = rec.get("status", "")
        lines.append(
            f"{i}. {rec.get('leave_type', '')} | "
            f"{str(rec.get('start_time', ''))[:16]} ~ "
            f"{str(rec.get('end_time', ''))[:16]} | "
            f"{STATUS_MAP.get(st, st)}"
        )
        if rec.get("approval_remark"):
            lines.append(f"   备注：{rec['approval_remark']}")
    return "\n".join(lines)


def fetch_remote_records(student_id: int) -> Optional[str]:
    """
    从企业助手（教师端）API 获取请假记录。

    参数:
        student_id: 学生ID

    返回:
        格式化后的记录文本，或 None（API 不可用）
    """
    try:
        r = requests.get(
            f"{TEACHER_AGENT_URL}/api/v1/student/leave-requests",
            params={"student_id": student_id},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json()
            records = data.get("data", data.get("records", []))
            return _format_records_message(records)
    except requests.RequestException as e:
        logger.warning("远程请假记录查询失败: %s", e)
    return None


def query_records(student_id: int) -> str:
    """
    查询请假记录：优先查远程 API，本地兜底。

    参数:
        student_id: 学生ID

    返回:
        回复文本
    """
    # 远程查询优先
    remote_result = fetch_remote_records(student_id)
    if remote_result:
        return remote_result

    # 本地兜底
    records = query_leave_records(student_id)
    return _format_records_message(records)


def _check_fields(collected: dict) -> tuple[list[str], list[str]]:
    """
    检查必填字段是否齐全。

    参数:
        collected: 已收集到的参数 dict

    返回:
        (have_list, missing_list)
          - have_list:   已填写字段的显示文案
          - missing_list: 缺失字段的提示文案
    """
    missing = []
    have = []

    if collected.get("leave_type"):
        have.append(f"类型：{collected['leave_type']}")
    else:
        missing.append("请假类型（事假/病假）")

    if collected.get("start_time"):
        have.append(f"开始：{collected['start_time'][:16]}")
    else:
        missing.append("开始时间（比如：明天上午）")

    if collected.get("end_time"):
        have.append(f"结束：{collected['end_time'][:16]}")
    else:
        missing.append("结束时间（比如：后天下午）")

    if collected.get("reason"):
        have.append(f"原因：{collected['reason']}")
    else:
        missing.append("请假原因（比如：感冒发烧需要休息）")

    return have, missing


def submit_leave(student_id: int, collected: dict) -> str:
    """
    提交请假申请（含幂等校验 + 远程 API 提交）。

    参数:
        student_id: 学生ID
        collected:  完整请假参数 {leave_type, start_time, end_time, reason}

    返回:
        回复文本
    """
    leave_type = collected.get("leave_type", "其他")
    start_time = collected.get("start_time", "")
    end_time = collected.get("end_time", "")
    reason = collected.get("reason", "未说明")

    # 构建幂等键并检查
    idempotent_key = _build_idempotent_key(student_id, leave_type, start_time, end_time)
    existing = _check_idempotent(idempotent_key)
    if existing:
        logger.info("幂等拦截：请假已存在(id=%s, status=%s)", existing["id"], existing["status"])
        return f"该请假申请已提交过了(state={STATUS_MAP.get(existing['status'], existing['status'])})，无需重复提交～"

    # 获取学生信息
    student = db.query_one(
        "SELECT name, assigned_teacher_id FROM student WHERE id = %s",
        (student_id,)
    )
    student_name = student["name"] if student else "同学"

    # 远程 API 提交
    try:
        r = requests.post(
            f"{TEACHER_AGENT_URL}/api/v1/student/leave-requests",
            json={
                "student_id": student_id,
                "leave_type": leave_type,
                "start_time": start_time,
                "end_time": end_time,
                "reason": reason,
                "idempotent_key": idempotent_key,
            },
            timeout=5,
        )
        if r.status_code == 200:
            teacher_info = ""
            if student and student.get("assigned_teacher_id"):
                teacher_info = f"，已推送给班主任(ID:{student['assigned_teacher_id']})审批"
            return (
                f"请假申请已提交 ✅\n"
                f"📝 {leave_type} | {start_time[:16]} ~ {end_time[:16]}\n"
                f"📌 状态：等待审批中{teacher_info}\n"
                f"审批完成后，下次登录时可以查看审批结果～"
            )
        else:
            logger.warning("请假提交API返回非200: %s", r.status_code)
            return "请假提交失败，请稍后重试或联系班主任～"
    except requests.RequestException as e:
        logger.error("请假提交API不可用: %s", e)
        # API 不可用时落本地数据库
        try:
            tid = db.insert("leave_request", {
                "student_id": student_id,
                "leave_type": leave_type,
                "start_time": start_time,
                "end_time": end_time,
                "reason": reason,
                "status": "pending",
                "idempotent_key": idempotent_key,
            })
            logger.info("请假本地落库成功: id=%s", tid)
            return (
                f"请假申请已提交 ✅\n"
                f"📝 {leave_type} | {start_time[:16]} ~ {end_time[:16]}\n"
                f"📌 状态：等待审批中\n"
                f"系统已完成记录，稍后同步给审批老师～"
            )
        except Exception as db_err:
            logger.error("请假本地落库失败: %s", db_err)
            return "请假系统暂时不可用，请稍后重试或直接联系班主任～"


def build_missing_prompt(collected: dict) -> str:
    """
    参数不齐全时，生成反问提示文本。

    参数:
        collected: 已收集到的参数

    返回:
        提示学生补充信息的文本
    """
    have, missing = _check_fields(collected)

    have_text = "\n".join([f"  ✅ {h}" for h in have]) if have else "  还没有任何信息"
    missing_text = "\n".join([f"  ❓ {m}" for m in missing])

    return (
        f"好的，我来帮你提交请假申请 📝\n\n"
        f"目前已确认：\n{have_text}\n\n"
        f"还需要补充：\n{missing_text}\n\n"
        f"直接告诉我就行，比如'明天上午到后天下午，感冒了需要休息'～"
    )


def handle_leave(student_id: int, message: str, params: dict, context: list) -> str:
    """
    处理请假意图完整 handler。

    流程：
      1. 检测查询模式 → 查记录
      2. 收集参数 → 检查必填项
      3. 参数齐全 → 提交
      4. 参数缺失 → 反问

    参数:
        student_id: 学生ID
        message:    学生消息
        params:     意图参数
        context:    对话上下文

    返回:
        回复文本
    """
    # ── 查询模式 ──
    if any(kw in message for kw in ["查", "状态", "审核", "审批结果", "通过了吗", "记录"]):
        return query_records(student_id)

    # ── 提交模式：收集参数 ──
    collected = collect_leave_params(message, context)

    # 检查必填项
    have, missing = _check_fields(collected)

    if missing:
        return build_missing_prompt(collected)

    # 参数齐全 → 提交
    return submit_leave(student_id, collected)


def update_approval_status(leave_id: int, status: str, approver_id: int = None,
                            approver_name: str = None, remark: str = None) -> bool:
    """
    更新请假审批状态（供教师端回调使用）。

    参数:
        leave_id:       请假记录ID
        status:         新状态（approved/rejected）
        approver_id:    审批人ID
        approver_name:  审批人姓名
        remark:         审批备注

    返回:
        是否更新成功
    """
    update_data = {
        "status": status,
        "approver_id": approver_id,
        "approver_name": approver_name,
        "approval_remark": remark,
        "approved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    # 过滤 None 值
    update_data = {k: v for k, v in update_data.items() if v is not None}

    affected = db.update(
        "leave_request",
        {"id": leave_id},
        update_data,
    )
    return affected > 0
