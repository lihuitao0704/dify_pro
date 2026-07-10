"""员工日报智能汇总报告路由。"""

from fastapi import APIRouter

from summary_report.api.routes._helpers import handle_report_request
from summary_report.api.schemas import ReportRequest, ReportResponse
from summary_report.services.employee_report_service import generate

router = APIRouter(tags=["reports"])


@router.post("/employee_daily", response_model=ReportResponse)
def report_employee_daily(request: ReportRequest) -> dict:
    """
    员工日报智能汇总报告。

    自动查询：
    - 指定日期/周的日报提交情况（提交率）
    - 各部门工作产出统计（任务数、工作产出摘要）
    - 风险/阻塞项汇总
    - 员工工作状态分析
    """
    return handle_report_request(
        question=request.question,
        report_name="员工日报",
        service_generate=generate,
    )
