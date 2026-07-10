"""全域客户经营分析报告路由。"""

from fastapi import APIRouter

from summary_report.api.routes._helpers import handle_report_request
from summary_report.api.schemas import ReportRequest, ReportResponse
from summary_report.services.customer_report_service import generate

router = APIRouter(tags=["reports"])


@router.post("/customer_operation", response_model=ReportResponse)
def report_customer_operation(request: ReportRequest) -> dict:
    """
    全域客户经营分析报告。

    覆盖意向、成交、流失三大客群，自动查询：
    - 意向客户新增趋势及聚类画像
    - 成交客户转化路径与高价值特征
    - 流失客户归因与风险预警
    """
    return handle_report_request(
        question=request.question,
        report_name="客户经营",
        service_generate=generate,
    )
