"""
员工日报智能汇总报告服务。
"""

from typing import Any, Dict, List, Tuple

from summary_report.constants.report_context import EMPLOYEE_REPORT_CONTEXT
from summary_report.constants.schema_employee import EMPLOYEE_SCHEMA
from summary_report.services.nl2sql_service import run_nl2sql_pipeline

# 引导 LLM 从相关维度生成 SQL（仅供参考）
# 重要：department 表没有编制/人数字段，禁止引用不存在的字段计算提交率。
# "各部门提交人数/提交量"必须通过聚合 employee_daily_report 得到，
# 分子 = COUNT(DISTINCT employee_daily_report.user_id)，
# 分母 = COUNT(DISTINCT account.user_id WHERE account.dept_id = department.dept_id)，
# 必须在 SQL 中通过 GROUP BY department.dept_id 同时算出分子分母，不得凭空估算。
EXTRA_INSTRUCTION: str = """
以下维度供参考，请根据用户的具体问题选取相关维度，不要全部生成：
1. 日报提交情况：按 report_date 统计每日提交人数；按 department.dept_name 分组统计
   各部门"实际提交人数"（分子，来自 employee_daily_report）和"部门在册人数"（分母，
   来自 account 表同一 dept_id 的 COUNT），用 JOIN + GROUP BY 一次算出，
   严禁引用 department 表上不存在的编制字段或凭空推算提交率
2. 部门产出汇总：按 department.dept_name 统计各部门日报数量与提交及时性，
   未提交日报的部门也必须出现在结果中以 0 计（从 department 表 LEFT JOIN employee_daily_report）
3. 内容关键词提取：使用 report_content LIKE '%关键词%' 检索"风险""阻塞""协助"等关键信息
4. 提交时间分析：按 submit_time 的小时分布判断提交是否及时
5. 趋势分析：按 report_date 周维度统计提交量变化趋势
"""


def generate(question: str) -> Tuple[List[str], List[Dict[str, Any]], str]:
    """生成员工日报智能汇总报告。"""
    return run_nl2sql_pipeline(
        question=question,
        schema=EMPLOYEE_SCHEMA,
        report_context=EMPLOYEE_REPORT_CONTEXT,
        extra_instruction=EXTRA_INSTRUCTION,
    )
