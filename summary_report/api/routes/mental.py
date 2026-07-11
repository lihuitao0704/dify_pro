"""学生心理健康周报路由。"""

from fastapi import APIRouter, Form

from summary_report.api.routes._helpers import handle_report_request
from summary_report.api.schemas import ReportResponse
from summary_report.services.mental_report_service import generate

router = APIRouter(tags=["reports"])


@router.post("/student_mental", response_model=ReportResponse)
def report_student_mental(
    question: str = Form(..., min_length=1, description="用户的自然语言问题"),
) -> dict:
    """
    学生心理健康周报（表单提交）。

    表单字段：
    - question（必填）：用户的自然语言问题

    自动查询：
    - 本周/本月整体情绪态势（平均分、趋势）
    - 风险学生识别（低情绪、高焦虑、社交隔离）
    - 预警记录统计与处理情况
    - 情绪波动趋势（按日/周）
    - 重点关怀建议
    """
    return handle_report_request(
        question=question,
        report_name="心理健康",
        service_generate=generate,
    )
