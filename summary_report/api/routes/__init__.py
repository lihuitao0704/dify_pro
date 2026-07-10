"""路由层：聚合所有 APIRouter，供 main.py 统一注册。"""

from fastapi import APIRouter

from summary_report.api.routes.complaint import router as complaint_router
from summary_report.api.routes.common_nl2sql import router as common_nl2sql_router
from summary_report.api.routes.customer import router as customer_router
from summary_report.api.routes.employee import router as employee_router
from summary_report.api.routes.mental import router as mental_router

# 统一聚合路由，方便 main.py 一键 include
all_routers: list[APIRouter] = [
    customer_router,
    employee_router,
    mental_router,
    complaint_router,
    common_nl2sql_router,
]
