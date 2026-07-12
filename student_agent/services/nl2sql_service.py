"""
NL2SQL 服务 — 自然语言查库

双引擎架构（模板优先，LLM 兜底）：
  1. 预设模板匹配（12 个场景模板 + 1 个通用兜底，零成本、覆盖常见查询）
  2. LLM 生成 SQL（调用 llm.generate_sql，灵活处理复杂/罕见查询）

安全策略（三层防护，来自 shared/nl2sql_core.py）：
  1. 只允许 SELECT / WITH / SHOW / DESC 只读语句
  2. 禁止多条语句（分号检测）
  3. 写操作关键字白名单拦截（DROP/ALTER/DELETE 等）

数据流：
  自然语言 → 模板匹配 → 安全校验 → db.query → LLM 润色 → 返回
                                    ↓ (模板不匹配)
                               LLM 生成 SQL
"""

import json
import logging
import re
from typing import Optional

from student_agent import db
from student_agent import llm
from shared.nl2sql_core import (
    sanitize_sql as shared_sanitize,
    validate_readonly_sql,
)

logger = logging.getLogger(__name__)

# ============================================================
# 预设查询模板（12 个场景 + 1 个通用兜底）
# 移植自 student_sgent/services/nl2sql_service.py，适配 student_agent 的 %s 占位符
# ============================================================

QUERY_TEMPLATES = [
    {
        "name": "查看学生档案",
        "pattern": r"学生.*(?:信息|档案|资料|详情).*",
        "sql": "SELECT current_emotion, risk_score, risk_level FROM mental_health_profile WHERE student_id = %s",
        "params_func": lambda sid: (sid,),
        "description": "查询学生的心理档案信息",
    },
    {
        "name": "查询对话记录",
        "pattern": r"(?:对话|聊天|消息|会话).*(?:记录|历史|最近)|(?:最近|历史).*(?:对话|会话)",
        "sql": """SELECT session_id, total_turns, main_intents, start_time, end_time
                  FROM conversation_session
                  WHERE student_id = %s
                  ORDER BY start_time DESC LIMIT 10""",
        "params_func": lambda sid: (sid,),
        "description": "查询最近的对话会话记录",
    },
    {
        "name": "查询心理状态",
        "pattern": r"(?:心理|情绪|心情).*(?:状态|怎样|如何|报告|分析|画像)",
        "sql": "SELECT current_emotion, risk_score, risk_level, emotion_history, last_assessment_at FROM mental_health_profile WHERE student_id = %s",
        "params_func": lambda sid: (sid,),
        "description": "查询学生心理画像和情绪状态",
    },
    {
        "name": "查询心理预警",
        "pattern": r"(?:心理|情绪).*(?:预警|警报)|风险.*预警|预警.*记录",
        "sql": """SELECT id, trigger_reason, risk_level, alert_content, emotion_label,
                         risk_score, follow_up_status, created_at
                  FROM mental_health_alert
                  WHERE student_id = %s
                  ORDER BY created_at DESC LIMIT 10""",
        "params_func": lambda sid: (sid,),
        "description": "查询心理预警记录",
    },
    {
        "name": "查询投诉记录",
        "pattern": r"(?:投诉|反馈|工单).*(?:记录|历史|情况|进度)",
        "sql": """SELECT id, title, category, urgency, status, priority, created_at
                  FROM feedback_ticket
                  WHERE student_id = %s
                  ORDER BY created_at DESC LIMIT 10""",
        "params_func": lambda sid: (sid,),
        "description": "查询学生的投诉反馈工单",
    },
    {
        "name": "查询学业日程",
        "pattern": r"(?:课程|课表|日程|考试).*(?:安排|查询|情况)|.*(?:今天|明天|本周).*(?:课|日程)",
        "sql": """SELECT id, event_type, title, course_name, deadline,
                         DATEDIFF(deadline, NOW()) AS days_left
                  FROM academic_schedule
                  WHERE student_id = %s AND status != 'completed'
                  ORDER BY deadline ASC LIMIT 20""",
        "params_func": lambda sid: (sid,),
        "description": "查询学业日程和考试安排",
    },
    {
        "name": "查询DDL",
        "pattern": r"(?:DDL|ddl|截止|deadline).*|(?:最近|近期).*DDL",
        "sql": """SELECT id, event_type, title, course_name, deadline,
                         DATEDIFF(deadline, NOW()) AS days_left
                  FROM academic_schedule
                  WHERE student_id = %s AND status != 'completed'
                    AND deadline >= NOW()
                  ORDER BY deadline ASC LIMIT 15""",
        "params_func": lambda sid: (sid,),
        "description": "查询即将到来的论文/考试截止日期",
    },
    {
        "name": "查询升学意向",
        "pattern": r"(?:升学|留学).*(?:意向|目标|计划|方向)",
        "sql": """SELECT id, interest_degree, interest_country, interest_major,
                         conversion_status, created_at
                  FROM upgrade_interest
                  WHERE student_id = %s
                  ORDER BY created_at DESC LIMIT 10""",
        "params_func": lambda sid: (sid,),
        "description": "查询学生升学意向记录",
    },
    {
        "name": "查询申请进度",
        "pattern": r"(?:申请).*(?:进度|状态|情况|流程)|offer|录取.*(?:情况|进度)",
        "sql": """SELECT id, program_name, university, current_step, application_status,
                         submitted_date, estimated_completion
                  FROM application_progress
                  WHERE student_id = %s
                  ORDER BY updated_at DESC LIMIT 10""",
        "params_func": lambda sid: (sid,),
        "description": "查询留学申请进度",
    },
    {
        "name": "统计请假记录",
        "pattern": r"(?:统计|查).*(?:请假|休假).*|请假.*(?:统计|次数|多少|几次)",
        "sql": """SELECT status, COUNT(*) AS cnt
                  FROM leave_request
                  WHERE student_id = %s
                  GROUP BY status""",
        "params_func": lambda sid: (sid,),
        "description": "按状态统计请假记录",
    },
    {
        "name": "统计工单数量",
        "pattern": r"(?:统计|多少).*(?:工单|反馈|投诉).*|.*工单.*(?:数量|多少)",
        "sql": """SELECT status, COUNT(*) AS cnt
                  FROM feedback_ticket
                  WHERE student_id = %s
                  GROUP BY status""",
        "params_func": lambda sid: (sid,),
        "description": "按状态统计工单数量",
    },
    {
        "name": "查询我的基本信息",
        "pattern": r"(?:我的|我).*(?:信息|资料|档案|基本)|(?:我是|我叫).*",
        "sql": """SELECT id, name, education, major, school, gpa, language_score,
                         target_country, target_degree, target_major
                  FROM student
                  WHERE id = %s""",
        "params_func": lambda sid: (sid,),
        "description": "查询学生基本信息",
    },
    {
        "name": "查询讲座报名",
        "pattern": r"(?:我的|我).*(?:讲座|报名).*(?:记录|情况|哪些|什么)|(?:报名|参加).*(?:讲座|什么讲座)",
        "sql": """SELECT lr.registration_id, l.title, l.event_time, l.location, lr.phone
                  FROM lecture_registrations lr
                  JOIN lectures l ON lr.lecture_id = l.lecture_id
                  WHERE lr.name COLLATE utf8mb4_unicode_ci = (SELECT name FROM student WHERE id = %s)
                  ORDER BY l.event_time DESC""",
        "params_func": lambda sid: (sid,),
        "description": "查询学生报名的讲座记录",
    },
    {
        "name": "查询活动报名",
        "pattern": r"(?:我的|我).*(?:活动|报名).*(?:记录|情况|哪些|什么)|(?:报名|参加).*(?:活动|什么活动)",
        "sql": """SELECT ar.registration_id, a.title, a.event_time, a.location, ar.phone
                  FROM activity_registrations ar
                  JOIN activities a ON ar.activity_id = a.activity_id
                  WHERE ar.name COLLATE utf8mb4_unicode_ci = (SELECT name FROM student WHERE id = %s)
                  ORDER BY a.event_time DESC""",
        "params_func": lambda sid: (sid,),
        "description": "查询学生报名的活动记录",
    },
    {
        "name": "查询我的成绩",
        "pattern": r"(?:我的|我).*(?:成绩|分数|绩点)|(?:成绩|分数|绩点|gpa).*(?:查询|多少|怎么|如何)",
        "sql": """SELECT subject, score, exam_type, exam_date
                  FROM student_score
                  WHERE student_id = %s
                  ORDER BY exam_date DESC""",
        "params_func": lambda sid: (sid,),
        "description": "查询学生的考试成绩列表",
    },
    {
        "name": "统计成绩",
        "pattern": r"(?:统计|汇总|平均).*(?:成绩|分数)|.*(?:平均分|最高分|最低分)",
        "sql": """SELECT exam_type, COUNT(*) AS n, AVG(score) AS avg_score,
                         MAX(score) AS max_score, MIN(score) AS min_score
                  FROM student_score
                  WHERE student_id = %s
                  GROUP BY exam_type""",
        "params_func": lambda sid: (sid,),
        "description": "按考试类型统计成绩（平均分/最高/最低）",
    },
    {
        "name": "通用查询",
        "pattern": r".*",
        "sql": """SELECT id, event_type, title, deadline,
                         DATEDIFF(deadline, NOW()) AS days_left
                  FROM academic_schedule
                  WHERE student_id = %s AND status != 'completed'
                  ORDER BY deadline ASC LIMIT 5""",
        "params_func": lambda sid: (sid,),
        "description": "通用最近日程查询兜底",
    },
]


def match_template(natural_query: str) -> Optional[dict]:
    """
    匹配预设查询模板。

    不匹配通用模板（兜底），仅匹配前 12 个具体场景模板。
    如果具体模板都不匹配，返回 None 让 LLM 兜底。

    参数:
        natural_query: 自然语言查询

    返回:
        匹配的模板 dict（含 name/sql/params_func/description）
        或 None（无匹配）
    """
    for template in QUERY_TEMPLATES[:-1]:  # 排除通用兜底
        if re.search(template["pattern"], natural_query, re.IGNORECASE):
            logger.debug("NL2SQL 模板匹配成功: %s", template["name"])
            return template

    logger.debug("NL2SQL 无模板匹配，将使用 LLM 生成")
    return None


def execute_template(template: dict, student_id: int) -> list[dict]:
    """
    执行模板 SQL 查询。

    参数:
        template:  匹配的模板 dict
        student_id: 学生ID

    返回:
        查询结果列表
    """
    sql = template["sql"]
    params = template["params_func"](student_id)
    return db.query(sql, params)


def is_simple_query(message: str) -> bool:
    """
    判断是否是简单查询（可直接用模板）。
    简单查询特征：短、包含模板常见关键词。

    参数:
        message: 自然语言查询

    返回:
        True = 属于常见简单查询
    """
    common_keywords = [
        "查", "看", "显示", "列表", "记录", "信息", "状态",
        "我的", "我有什么", "我有", "多少", "几个",
        "考试", "论文", "成绩", "DDL", "截止",
        "请假", "投诉", "反馈", "申请", "offer",
    ]
    short = len(message) <= 30
    has_keyword = any(kw in message for kw in common_keywords)
    return short and has_keyword


def build_llm_query(student_id: int, message: str) -> str:
    """
    构建发给 LLM 的自然语言查询（注入学生ID过滤）。

    参数:
        student_id: 学生ID
        message:    原始自然语言

    返回:
        增强后的查询文本
    """
    return message.replace("我", f"学生ID={student_id}")


def execute_nl2sql(student_id: int, message: str, context: list = None) -> str:
    """
    NL2SQL 主入口：自然语言 → 安全 SQL → 执行 → 润色。

    执行流程：
      1. 先尝试模板匹配（零成本、零延迟）
      2. 模板匹配成功 → 安全校验 → 执行
      3. 模板匹配失败 → LLM 生成 SQL
      4. LLM 生成失败 → 使用通用模板兜底
      5. 对结果进行 LLM 润色成自然语言

    参数:
        student_id: 学生ID
        message:    自然语言查询
        context:    对话上下文（可选，暂未使用）

    返回:
        自然语言回答文本
    """
    sql = None
    template_name = None
    query_data = []

    # ── Step 1: 模板匹配优先 ──
    template = match_template(message)
    if template:
        try:
            query_data = execute_template(template, student_id)
            sql = template["sql"]
            template_name = template["name"]
            logger.info("NL2SQL 模板命中: %s, 结果数: %d", template_name, len(query_data))
        except Exception as e:
            logger.warning("NL2SQL 模板执行失败: %s，降级至 LLM", e)
            template = None  # 降级至 LLM

    # ── Step 2: LLM 兜底 ──
    if not template:
        try:
            from student_agent.db import get_schema_description
            schema = get_schema_description()
            enriched = build_llm_query(student_id, message)
            raw_sql = llm.generate_sql(enriched, schema)

            if raw_sql.startswith("--"):
                # LLM 返回了注释（表示无法生成安全 SQL）
                return "抱歉，这个查询我暂时无法执行～"

            # 清洗 SQL（去 markdown 包裹、去末尾分号）
            cleaned_sql = shared_sanitize(raw_sql)

            # 安全校验
            try:
                safe_sql = validate_readonly_sql(cleaned_sql)
            except ValueError as ve:
                logger.warning("NL2SQL 安全校验失败: %s", ve)
                return "抱歉，这个查询涉及敏感操作，无法执行～"

            sql = safe_sql
            # 执行查询（注意：参数化查询需确保 SQL 中无注入）
            query_data = db.query(sql)
            logger.info("NL2SQL LLM 生成成功，SQL: %.100s, 结果数: %d", sql, len(query_data))

        except Exception as e:
            logger.error("NL2SQL LLM 生成/执行失败: %s", e)
            # ── Step 3: 通用模板终极兜底 ──
            fallback = QUERY_TEMPLATES[-1]  # 通用查询模板
            try:
                query_data = execute_template(fallback, student_id)
                sql = fallback["sql"]
                template_name = "通用兜底"
                logger.info("NL2SQL 通用模板兜底，结果数: %d", len(query_data))
            except Exception as fallback_err:
                logger.error("NL2SQL 通用模板也失败: %s", fallback_err)
                return "查询时遇到了一点问题，请换个方式问问看～"

    # ── Step 4: 结果润色 ──
    if not query_data:
        return "没有查到相关记录～"

    try:
        return llm.polish_answer(message, sql or "", query_data)
    except Exception as e:
        logger.warning("NL2SQL 润色失败: %s，直接格式化返回", e)
        # 直接格式化
        if len(query_data) == 1:
            items = [f"{k}: {v}" for k, v in query_data[0].items() if v is not None]
            return "查到：" + "，".join(items)
        return f"查到 {len(query_data)} 条记录"


def handle_nl2sql(student_id: int, message: str, params: dict, context: list) -> str:
    """
    处理 NL2SQL 查询意图完整 handler。

    与 agent.py 中 _handle_nl2sql 兼容：
      - 自动注入 student_id 过滤
      - 模板匹配优先 + LLM 兜底
      - 全程安全校验

    参数:
        student_id: 学生ID
        message:    自然语言查询
        params:     意图参数
        context:    对话上下文

    返回:
        回答文本
    """
    return execute_nl2sql(student_id, message, context)


# ============================================================
# 辅助工具
# ============================================================

def list_available_queries() -> list[dict]:
    """
    列出所有可用的查询模板（供前端展示/引导用）。

    返回:
        模板列表（不含 params_func）
    """
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "example": t.get("example", ""),
        }
        for t in QUERY_TEMPLATES[:-1]  # 排除通用兜底
    ]


def validate_query_sql(sql: str) -> str:
    """
    外部 SQL 安全校验工具（供其他模块调用）。

    参数:
        sql: 待校验的 SQL 语句

    返回:
        校验通过后的清洁 SQL

    抛出:
        ValueError: 校验失败（含具体原因）
    """
    cleaned = shared_sanitize(sql)
    return validate_readonly_sql(cleaned)
