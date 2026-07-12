"""
投诉处理周报服务。
"""

from typing import Any, Dict, List, Tuple

from summary_report.constants.report_context import COMPLAINT_REPORT_CONTEXT
from summary_report.services.nl2sql_service import build_complaint_schema, run_nl2sql_pipeline

# 引导 LLM 从相关维度生成 SQL（仅供参考）
EXTRA_INSTRUCTION: str = """
以下维度供参考，请根据用户的具体问题选取相关维度，不要全部生成：
1. 投诉总量：student_feedback_ticket 中 ticket_type='complaint' 按 create_time 统计本周数量，与上周对比
2. 分类分布：按 category / priority 统计数量与占比
3. 处理状态：按 status 统计各状态工单数
4. 满意度分析：按 category 统计平均 satisfaction 评分
5. 积压预警：status 为 'pending'/'processing' 且超过 create_time 3天以上的工单
6. 投诉主表维度：student_complaint 按 complaint_type 分布、按 handle_status 统计

重要：如果 SELECT 列表中同时包含聚合函数（COUNT/SUM/AVG/MAX/MIN）和非聚合列，
必须使用 GROUP BY 子句列出所有非聚合列，以兼容 MySQL only_full_group_by 模式。
"""


def generate(question: str) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """生成投诉处理周报。"""
    # 使用基于真实库结构的动态 schema（按投诉相关表过滤）
    dynamic_schema = build_complaint_schema()
    return run_nl2sql_pipeline(
        question=question,
        schema=dynamic_schema,
        report_context=COMPLAINT_REPORT_CONTEXT,
        extra_instruction=EXTRA_INSTRUCTION,
    )
