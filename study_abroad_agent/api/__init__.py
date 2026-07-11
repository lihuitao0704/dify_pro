"""FastAPI 路由器聚合包。

返回 (prefix, router) 元组列表，由 app.py 在启动时显式注册。
在较新的 FastAPI/Starlette 版本 (0.139+) 中，这种方式比
`api_router.include_router(xxx.router)` 更稳定。ROUTERS 中的每个
条目都保持相对的 import 顺序，避免 lazy 导入带来的空路由问题。
"""
from study_abroad_agent.api import health, profiles, courses, consultations, nl2sql

ROUTERS = [
    ("", health.router),
    ("", profiles.router),
    ("", courses.router),
    ("", consultations.router),
    ("", nl2sql.router),
]
