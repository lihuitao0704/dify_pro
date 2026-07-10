"""
全域客户经营分析报告服务。

覆盖签约/跟进中/已流失三大客群，封装专属的表结构、报告上下文与
SQL 生成维度建议，对外暴露单一的 ``generate(question)`` 入口。
"""

from typing import Any, Dict, List, Tuple

from summary_report.constants.report_context import CUSTOMER_REPORT_CONTEXT
from summary_report.constants.schema_customer import CUSTOMER_SCHEMA
from summary_report.services.nl2sql_service import run_nl2sql_pipeline

# 引导 LLM 生成覆盖完整业务维度的 SQL（字段名与真实表一致）
EXTRA_INSTRUCTION: str = """
请生成多条 SELECT 查询，覆盖以下维度（字段名严格使用真实表字段）：
1. 客户状态分布：按 current_status ENUM('已签约','跟进中','已流失') 统计数量与占比
2. 渠道分析：按 customer_source 统计各渠道客户数、签约率
3. 顾问业绩：按 sales_user_id 分组统计各顾问负责客户数与签约数（可 JOIN account 获取 real_name）
4. 客户画像：按 target_country / budget / language_score 分析高价值特征（来自 user_profiles）
5. 流失分析：已流失客户的渠道分布、流失时间趋势（按 create_time 月份）
6. 咨询转化：consultations 表中各 status 的咨询量与推荐课程
每条 SQL 独立完整，能单独执行。
"""


def generate(question: str) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """
    生成全域客户经营分析报告。

    Returns:
        (sql_list, results, answer) 三元组。
    """
    return run_nl2sql_pipeline(
        question=question,
        schema=CUSTOMER_SCHEMA,
        report_context=CUSTOMER_REPORT_CONTEXT,
        extra_instruction=EXTRA_INSTRUCTION,
    )
