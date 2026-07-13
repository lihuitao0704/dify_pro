"""
员工日报智能汇总报告服务。
"""

from typing import Any, Dict, List, Tuple

from summary_report.constants.report_context import EMPLOYEE_REPORT_CONTEXT
from summary_report.constants.schema_employee import EMPLOYEE_SCHEMA
from summary_report.services.nl2sql_service import run_nl2sql_pipeline

# 引导 LLM 从相关维度生成 SQL（仅供参考）
EXTRA_INSTRUCTION: str = """
以下维度供参考，请根据用户的具体问题选取相关维度，不要全部生成：
1. 日报提交情况：按 report_date 统计每日提交人数，按 dept_id 分组统计各部门提交率
   （employee_daily_report 关联 account 获取 real_name，关联 department 获取 dept_name）
2. 部门产出汇总：按 department.dept_name 统计各部门日报数量与提交及时性
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
