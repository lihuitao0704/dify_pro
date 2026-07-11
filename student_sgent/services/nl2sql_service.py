"""
NL2SQL 服务 — 纯 Python 实现

双引擎架构：
    1. 预设模板匹配（快速、零成本、覆盖常见查询场景）
    2. AI 生成 SQL（灵活、通过 OpenAI 兼容 API，可选配置）

安全策略：
    - 仅允许单条 SELECT 语句
    - 多语句直接拒绝（不静默丢弃）
    - SQL 执行前关键字白名单校验
"""

import logging
import re
import time
from typing import Optional

import httpx
from sqlalchemy import text

from config import (
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL,
    NL2SQL_REQUEST_TIMEOUT,
)
from models import get_session

logger = logging.getLogger("nl2sql")


# ============================================================
# 数据库 Schema（注入 LLM Prompt）
# ============================================================

TABLE_SCHEMAS = {
    "conversation_sessions": {
        "name": "学生会话表",
        "columns": {
            "id": "主键 BIGINT", "session_id": "会话唯一标识 VARCHAR",
            "student_id": "学生ID BIGINT",
            "status": "状态 ENUM(active/closed/timeout)",
            "last_message_time": "最后消息时间 DATETIME",
            "message_count": "消息总数 INT",
            "create_time": "创建时间 DATETIME",
        },
    },
    "conversation_messages": {
        "name": "消息明细表",
        "columns": {
            "id": "主键 BIGINT", "session_id": "关联会话ID VARCHAR",
            "role": "角色 ENUM(user/assistant/system)",
            "content": "消息内容 TEXT", "intent": "AI识别意图 VARCHAR",
            "emotion_tag": "情绪标签 VARCHAR", "emotion_score": "情绪分值 INT(0-100)",
            "trigger_keywords": "触发关键词 JSON",
            "create_time": "创建时间 DATETIME",
        },
    },
    "emotion_profile_snapshots": {
        "name": "心理画像表（一人一条）",
        "columns": {
            "id": "主键 BIGINT", "student_id": "学生ID BIGINT UNIQUE",
            "latest_emotion_tag": "最新情绪标签 VARCHAR",
            "emotion_score": "情绪分值 INT(0-100)",
            "risk_level": "风险等级 ENUM(low/medium/high)",
            "emotion_history": "历史情绪数据 JSON",
            "update_time": "更新时间 DATETIME", "create_time": "创建时间 DATETIME",
        },
    },
    "risk_interventions": {
        "name": "心理预警表",
        "columns": {
            "id": "主键 BIGINT", "student_id": "学生ID BIGINT",
            "source_message_id": "触发消息ID BIGINT",
            "trigger_reason": "触发原因 TEXT",
            "risk_tags": "风险标签 JSON数组",
            "risk_level": "风险等级 ENUM(low/medium/high)",
            "status": "状态 ENUM(pending/following/resolved/dismissed)",
            "teacher_id": "老师ID BIGINT",
            "create_time": "创建时间 DATETIME",
        },
    },
    "feedback_tickets": {
        "name": "投诉工单表",
        "columns": {
            "id": "主键 BIGINT", "student_id": "学生ID BIGINT",
            "ticket_type": "类型 ENUM(complaint/suggestion/consult)",
            "category": "分类 VARCHAR", "title": "标题 VARCHAR",
            "content": "内容 TEXT", "status": "状态 ENUM(pending/processing/resolved/closed)",
            "priority": "优先级 ENUM(low/medium/high/urgent)",
            "satisfaction": "满意度 INT(1-5)",
            "resolved_time": "实际解决时间 DATETIME",
            "create_time": "创建时间 DATETIME",
        },
    },
    "academic_schedules": {
        "name": "学业日程表",
        "columns": {
            "id": "主键 BIGINT", "student_id": "学生ID BIGINT",
            "schedule_type": "类型 ENUM(course/exam/task/personal)",
            "title": "标题 VARCHAR", "start_time": "开始时间 DATETIME",
            "end_time": "结束时间 DATETIME", "location": "地点 VARCHAR",
            "status": "状态 ENUM(pending/done/cancelled)",
            "create_time": "创建时间 DATETIME",
        },
    },
    "deadline_reminders": {
        "name": "考务提醒表",
        "columns": {
            "id": "主键 BIGINT", "student_id": "学生ID BIGINT(可NULL=通用)",
            "deadline_type": "类型 ENUM(paper/exam/application/visa/other)",
            "title": "标题 VARCHAR", "deadline": "截止时间 DATETIME",
            "status": "状态 ENUM(pending/reminded/done/missed)",
            "create_time": "创建时间 DATETIME",
        },
    },
    "study_intentions": {
        "name": "升学意向表",
        "columns": {
            "id": "主键 BIGINT", "student_id": "学生ID BIGINT",
            "target_country": "目标国家 VARCHAR", "target_school": "目标院校 VARCHAR",
            "target_major": "目标专业 VARCHAR",
            "priority": "优先级 INT", "status": "状态 ENUM(active/frozen/completed/cancelled)",
            "create_time": "创建时间 DATETIME",
        },
    },
    "student_applications": {
        "name": "留学申请进度表",
        "columns": {
            "id": "主键 BIGINT", "student_id": "学生ID BIGINT",
            "target_school": "目标院校 VARCHAR", "target_major": "目标专业 VARCHAR",
            "stage": "阶段 ENUM(document_prep/submitted/under_review/offer_received/visa_processing/enrolled)",
            "deadline": "截止日期 DATE",
            "status": "状态 ENUM(ongoing/paused/completed/cancelled)",
            "create_time": "创建时间 DATETIME",
        },
    },
}

# ============================================================
# 预设查询模板（共 12 个）
# ============================================================

QUERY_TEMPLATES = {
    "查看学生档案": {
        "pattern": r"学生.*(信息|档案|资料|详情).*",
        "sql": "SELECT e.student_id, e.latest_emotion_tag, e.emotion_score, e.risk_level, e.last_interaction_time FROM emotion_profile_snapshots e WHERE e.student_id = :student_id",
    },
    "查询对话记录": {
        "pattern": r"(对话|聊天|消息|会话).*(记录|历史|最近)|(最近|历史).*(对话|会话)",
        "sql": "SELECT s.session_id, s.status, s.message_count, s.last_message_time, s.create_time FROM conversation_sessions s WHERE s.student_id = :student_id ORDER BY s.last_message_time DESC LIMIT 20",
    },
    "查询心理状态": {
        "pattern": r"(心理|情绪|心情).*(状态|怎样|如何|报告|分析|画像)",
        "sql": "SELECT latest_emotion_tag, emotion_score, risk_level, emotion_history, last_interaction_time FROM emotion_profile_snapshots WHERE student_id = :student_id",
    },
    "查询心理预警": {
        "pattern": r"(心理|情绪).*(预警|警报)|风险.*预警|预警.*记录",
        "sql": "SELECT id, trigger_reason, risk_tags, risk_level, status, follow_record, create_time FROM risk_interventions WHERE student_id = :student_id ORDER BY create_time DESC LIMIT 20",
    },
    "查询投诉记录": {
        "pattern": r"(投诉|反馈|工单).*(记录|历史|情况|进度)",
        "sql": "SELECT id, ticket_type, category, title, status, priority, satisfaction, create_time FROM feedback_tickets WHERE student_id = :student_id ORDER BY create_time DESC LIMIT 20",
    },
    "查询学业日程": {
        "pattern": r"(课程|课表|日程|考试).*(安排|查询|情况)|.*(今天|明天|本周).*(课|日程)",
        "sql": "SELECT id, schedule_type, title, start_time, end_time, location, status FROM academic_schedules WHERE student_id = :student_id ORDER BY start_time LIMIT 30",
    },
    "查询DDL": {
        "pattern": r"(DDL|ddl|截止|deadline).*|(最近|近期).*DDL",
        "sql": "SELECT id, deadline_type, title, deadline, reminder_days, status FROM deadline_reminders WHERE (student_id = :student_id OR student_id IS NULL) AND status IN ('pending','reminded') ORDER BY deadline ASC LIMIT 30",
    },
    "查询升学意向": {
        "pattern": r"(升学|留学).*(意向|目标|计划|方向)",
        "sql": "SELECT id, target_country, target_school, target_major, education_level, expected_enroll_time, priority, status FROM study_intentions WHERE student_id = :student_id ORDER BY priority ASC",
    },
    "查询申请进度": {
        "pattern": r"(申请).*(进度|状态|情况|流程)|\\boffer\\b|(录取).*(情况)",
        "sql": "SELECT id, target_country, target_school, target_major, stage, progress_detail, deadline, next_action, status, update_time FROM student_applications WHERE student_id = :student_id ORDER BY update_time DESC LIMIT 20",
    },
    "统计情绪趋势": {
        "pattern": r"(统计|汇总|趋势).*(情绪|心理).*",
        "sql": "SELECT DATE(m.create_time) AS dt, AVG(m.emotion_score) AS avg_score, COUNT(*) AS cnt FROM conversation_messages m JOIN conversation_sessions s ON s.session_id = m.session_id WHERE s.student_id = :student_id AND m.emotion_score IS NOT NULL GROUP BY DATE(m.create_time) ORDER BY dt DESC LIMIT 30",
    },
    "统计申请数量": {
        "pattern": r"(统计|多少).*(申请|offer).*|.*申请.*数量",
        "sql": "SELECT stage, COUNT(*) AS cnt, GROUP_CONCAT(target_school) AS schools FROM student_applications WHERE student_id = :student_id GROUP BY stage ORDER BY cnt DESC",
    },
    "通用查询": {
        "pattern": r".*",
        "sql": "SELECT s.session_id, m.content, m.intent, m.emotion_tag, m.emotion_score, m.create_time FROM conversation_messages m JOIN conversation_sessions s ON s.session_id = m.session_id WHERE s.student_id = :student_id ORDER BY m.create_time DESC LIMIT 10",
    },
}


# ============================================================
# LLM 调用
# ============================================================

def _build_llm_prompt(student_id: Optional[int]) -> str:
    """构建 LLM system prompt，正确处理 student_id 为 None 的情况"""
    schema_lines = ["# 数据库表结构（数据库：hambaki_3）\n"]
    for tname, info in TABLE_SCHEMAS.items():
        schema_lines.append(f"## 表: {tname} ({info['name']})")
        for col, desc in info["columns"].items():
            schema_lines.append(f"  {col}: {desc}")
        schema_lines.append("")

    schema_text = "\n".join(schema_lines)

    student_clause = (
        f"使用 student_id = {student_id}"
        if student_id is not None
        else "不要添加 student_id 过滤条件"
    )

    return f"""你是 MySQL 专家。根据用户自然语言查询和以下数据库结构，生成一条安全的 SELECT SQL 语句。

{schema_text}
# 严格规则
1. 只生成单条 SELECT 语句，禁止 INSERT/UPDATE/DELETE/DROP/ALTER
2. {student_clause}
3. 必须返回完整可执行的 SQL，末尾可带分号也可不带
4. MySQL 中 NULL 判断必须使用 IS NULL / IS NOT NULL，不能用 = NULL
5. 只输出 SQL 语句本身，不要加任何解释、不要 markdown 代码块、不要输出多条语句"""


async def generate_sql_via_llm(natural_query: str, student_id: Optional[int] = None) -> str:
    if not LLM_API_KEY:
        raise ValueError("LLM_API_KEY not configured")

    system_prompt = _build_llm_prompt(student_id)

    async with httpx.AsyncClient(timeout=NL2SQL_REQUEST_TIMEOUT) as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": natural_query},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    raw = data["choices"][0]["message"]["content"].strip()
    # 去掉 markdown 代码块包裹
    raw = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)

    # 检测多语句：忽略字符串字面量里的分号（含 MySQL '' 转义）
    _no_strings = re.sub(r"'(?:[^']|'')*'", "", raw)
    _no_strings = re.sub(r'"(?:[^"]|"")*"', "", _no_strings)
    if _no_strings.count(";") > 1:
        raise ValueError("LLM generated multi-statement SQL, rejected.")
    # 取第一条有效 SQL（不含末尾分号，调用方自行处理）
    sql = raw.split(";")[0].strip()
    if not sql.upper().startswith("SELECT"):
        raise ValueError(
            "LLM did not generate a SELECT statement. "
            f"Response preview: {raw[:200]}"
        )
    return sql


# ============================================================
# 模板匹配
# ============================================================

def match_template(natural_query: str) -> dict:
    """匹配预设模板，始终返回有效模板（兜底为通用查询）"""
    for name, config in QUERY_TEMPLATES.items():
        if name == "通用查询":
            continue
        if re.search(config["pattern"], natural_query, re.IGNORECASE):
            return {"name": name, "sql": config["sql"]}
    return {"name": "通用查询", "sql": QUERY_TEMPLATES["通用查询"]["sql"]}


# ============================================================
# SQL 安全校验
# ============================================================

def sanitize_sql(sql: str) -> bool:
    sql_stripped = sql.strip().rstrip(";").strip()
    sql_upper = sql_stripped.upper()
    if not sql_upper.startswith("SELECT"):
        return False
    if ";" in sql_stripped:
        return False
    dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
                 "CREATE", "TRUNCATE", "GRANT", "REVOKE", "EXEC",
                 "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
                 "SLEEP", "BENCHMARK", "WAITFOR"]
    for word in dangerous:
        if re.search(rf"\b{word}\b", sql_upper):
            return False
    return True


# ============================================================
# 主入口
# ============================================================

async def execute_nl2sql(
    natural_query: str,
    student_id: Optional[int] = None,
    use_template: bool = True,
) -> dict:
    start_time = time.perf_counter()
    matched_template = None
    generated_sql = ""

    if use_template:
        template = match_template(natural_query)
        if template:
            matched_template = template["name"]
            generated_sql = template["sql"]

    if not generated_sql:
        try:
            generated_sql = await generate_sql_via_llm(natural_query, student_id)
        except Exception as e:
            logger.warning("LLM failed, fallback to default template: %s", e)
            generated_sql = QUERY_TEMPLATES["通用查询"]["sql"]
            matched_template = matched_template or "通用查询（LLM不可用，已回退）"

    generated_sql = generated_sql.strip().rstrip(";").strip()
    if not sanitize_sql(generated_sql):
        raise ValueError(f"SQL rejected by safety check.\n{generated_sql[:200]}")

    params = {"student_id": student_id} if ":student_id" in generated_sql else {}
    with get_session() as session:
        result = session.execute(text(generated_sql), params)
        rows = result.fetchmany(1000)
        columns = list(result.keys())
        data = [dict(zip(columns, row)) for row in rows]

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    return {
        "natural_query": natural_query,
        "generated_sql": generated_sql,
        "matched_template": matched_template,
        "data": data,
        "row_count": len(data),
        "elapsed_ms": round(elapsed_ms, 1),
    }
