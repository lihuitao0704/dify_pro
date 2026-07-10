"""
通用 NL2SQL 路由（兼容旧接口 + 全库查询）。

可跨模块查询全部 19 张表，内部使用全量 schema。
"""

from fastapi import APIRouter

from summary_report.api.routes._helpers import handle_report_request
from summary_report.api.schemas import ReportRequest, ReportResponse
from summary_report.constants.report_context import GENERAL_REPORT_CONTEXT
from summary_report.constants.schema_all import FULL_SCHEMA
from summary_report.services.nl2sql_service import run_nl2sql_pipeline

router = APIRouter(tags=["reports"])


def _general_generate(question: str):
    """使用全量 schema 跑通用 NL2SQL 流水线。"""
    return run_nl2sql_pipeline(
        question=question,
        schema=FULL_SCHEMA,
        report_context=GENERAL_REPORT_CONTEXT,
    )


@router.post("/nl2sql", response_model=ReportResponse)
def nl2sql_api(request: ReportRequest) -> dict:
    """
    通用自然语言查询接口，可查询全部 19 张表。

    支持跨模块的灵活查询，如：
    - 留学申请进度查询
    - 学生成绩分析
    - 行政审批统计
    - 跨模块联合分析
    """
    return handle_report_request(
        question=request.question,
        report_name="通用查询",
        service_generate=_general_generate,
    )
