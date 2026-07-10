"""
投诉处理周报服务。
"""

from typing import Any, Dict, List, Tuple

from summary_report.constants.report_context import COMPLAINT_REPORT_CONTEXT
from summary_report.constants.schema_complaint import COMPLAINT_SCHEMA
from summary_report.services.nl2sql_service import run_nl2sql_pipeline

EXTRA_INSTRUCTION: str = """
请生成多条 SELECT 查询，覆盖以下维度（字段名严格使用真实表字段）：
1. 投诉总量：student_feedback_ticket 中 ticket_type='complaint' 按 create_time 统计本周数量，与上周对比
2. 分类分布：按 category / priority 统计数量与占比
3. 处理状态：按 status ENUM('pending','processing','resolved','closed') 统计各状态工单数
4. 满意度分析：按 category 统计平均 satisfaction 评分
5. 积压预警：status 为 'pending'/'processing' 且超过 create_time 3天以上的工单
6. 投诉主表维度：student_complaint 按 complaint_type 分布、按 handle_status 统计
每条 SQL 独立完整。
"""


def generate(question: str) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """生成投诉处理周报。"""
    return run_nl2sql_pipeline(
        question=question,
        schema=COMPLAINT_SCHEMA,
        report_context=COMPLAINT_REPORT_CONTEXT,
        extra_instruction=EXTRA_INSTRUCTION,
    )
