"""
通用 NL2SQL 路由（兼容旧接口 + 全库查询）。
"""

from fastapi import APIRouter, Form

from summary_report.api.routes._helpers import handle_report_request
from summary_report.api.schemas import ReportResponse
from summary_report.constants.report_context import GENERAL_REPORT_CONTEXT
from summary_report.constants.schema_all import FULL_SCHEMA
from summary_report.services.nl2sql_service import run_nl2sql_pipeline

router = APIRouter(tags=["reports"])


@router.post("/nl2sql", response_model=ReportResponse)
def nl2sql_api(
    question: str = Form(..., min_length=1, description="用户的自然语言问题"),
) -> dict:
    """
    通用自然语言查询接口（表单提交），使用全量 schema 跨模块联合查询。

    表单字段：
    - question（必填）：用户的自然语言问题

    示例：
    - 留学申请进度查询
    - 学生成绩分析
    - 意向客户渠道分布
    - 跨模块联合分析
    """
    def _generate(q: str):
        return run_nl2sql_pipeline(
            question=q,
            schema=FULL_SCHEMA,
            report_context=GENERAL_REPORT_CONTEXT,
        )

    return handle_report_request(
        question=question,
        report_name="通用查询",
        service_generate=_generate,
    )
