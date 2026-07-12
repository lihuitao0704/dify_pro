"""
学生心理健康周报服务。
"""

from typing import Any, Dict, List, Tuple

from summary_report.constants.report_context import MENTAL_REPORT_CONTEXT
from summary_report.services.nl2sql_service import build_mental_schema, run_nl2sql_pipeline

# 引导 LLM 从相关维度生成 SQL（仅供参考）
EXTRA_INSTRUCTION: str = """
以下维度供参考，请根据用户的具体问题选取相关维度，不要全部生成：
1. 整体情绪态势：按 record_date 统计每日平均 emotion_score，按 emotion_tag 分布统计
2. 风险学生识别：student_psych_profile 中 risk_level='high' 的学生清单
3. 预警统计：student_mental_alert 按 risk_level 分组统计数量，按 follow_up_status 统计处理情况
4. 告警处理：student_psych_alert 按 status 统计
5. 对话健康度：student_mental_profile 的 total_chat_count/negative_count/consecutive_negative 分布
6. 趋势分析：近4周 emotion_score 均值变化（按 record_date 周维度）

重要：如果 SELECT 列表中同时包含聚合函数（COUNT/SUM/AVG/MAX/MIN）和非聚合列，
必须使用 GROUP BY 子句列出所有非聚合列，以兼容 MySQL only_full_group_by 模式。
"""


def generate(question: str) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """生成学生心理健康周报。"""
    dynamic_schema = build_mental_schema()
    return run_nl2sql_pipeline(
        question=question,
        schema=dynamic_schema,
        report_context=MENTAL_REPORT_CONTEXT,
        extra_instruction=EXTRA_INSTRUCTION,
    )
