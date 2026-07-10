"""
学生心理健康周报服务。
"""

from typing import Any, Dict, List, Tuple

from summary_report.constants.report_context import MENTAL_REPORT_CONTEXT
from summary_report.constants.schema_mental import MENTAL_SCHEMA
from summary_report.services.nl2sql_service import run_nl2sql_pipeline

EXTRA_INSTRUCTION: str = """
请生成多条 SELECT 查询，覆盖以下维度（字段名严格使用真实表字段）：
1. 整体情绪态势：按 record_date 统计每日平均 emotion_score，按 emotion_tag 分布统计
2. 风险学生识别：student_psych_profile 中 risk_level='high' 的学生清单
3. 预警统计：student_mental_alert 按 risk_level 分组统计数量，按 follow_up_status 统计处理情况
4. 告警处理：student_psych_alert 按 status ENUM('pending','following','resolved','dismissed') 统计
5. 对话健康度：student_mental_profile 的 total_chat_count/negative_count/consecutive_negative 分布
6. 趋势分析：近4周 emotion_score 均值变化（按 record_date 周维度）
每条 SQL 独立完整。
"""


def generate(question: str) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """生成学生心理健康周报。"""
    return run_nl2sql_pipeline(
        question=question,
        schema=MENTAL_SCHEMA,
        report_context=MENTAL_REPORT_CONTEXT,
        extra_instruction=EXTRA_INSTRUCTION,
    )
