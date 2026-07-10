"""投诉处理周报路由。"""

from fastapi import APIRouter

from summary_report.api.routes._helpers import handle_report_request
from summary_report.api.schemas import ReportRequest, ReportResponse
from summary_report.services.complaint_report_service import generate

router = APIRouter(tags=["reports"])


@router.post("/complaint_weekly", response_model=ReportResponse)
def report_complaint_weekly(request: ReportRequest) -> dict:
    """
    投诉处理周报。

    自动查询：
    - 本周投诉总量及同环比变化
    - 按类型/严重程度/AI分类的投诉分布
    - 处理状态统计
    - 超时工单清单及预警
    - 满意度评分分析、处理时效统计
    """
    return handle_report_request(
        question=request.question,
        report_name="投诉周报",
        service_generate=generate,
    )
