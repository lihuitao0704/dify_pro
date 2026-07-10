"""
Pydantic 请求 / 响应模型。

集中管理所有路由层的输入输出契约，方便前端对接与 FastAPI
自动生成 OpenAPI 文档。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    """报告请求体：自然语言问题（用于灵活查询）。"""

    question: str = Field(..., min_length=1, description="用户的自然语言问题")


class ReportResponse(BaseModel):
    """报告响应体：包含 SQL、原始结果与润色后的回答。"""

    question: str
    sql_list: List[str]
    results: List[Dict[str, Any]]
    answer: str


class HealthResponse(BaseModel):
    """健康检查响应体。"""

    status: str
    reports: List[str]


class RootResponse(BaseModel):
    """根路径响应体。"""

    service: str
    version: str
    docs: str
    health: str


class MessageResponse(BaseModel):
    """通用消息响应（如校验结果）。"""

    message: str
    detail: Optional[Dict[str, Any]] = None
