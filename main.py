import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import customer, leave, report, organization, chat

# 创建 FastAPI 应用
app = FastAPI(
    title="企业智能助手 API",
    description="教育服务系统 - 企业智能助手后端接口",
    version="1.0.0",
)

# CORS 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由 — 所有路径已带 /api/agent 前缀
app.include_router(customer.router, prefix="/api/agent")
app.include_router(report.router, prefix="/api/agent")
app.include_router(leave.router, prefix="/api/agent")
app.include_router(organization.router, prefix="/api/agent")
app.include_router(chat.router, prefix="/api/agent")


@app.get("/")
def root():
    """健康检查"""
    return {"code": 0, "msg": "企业智能助手 API 运行中", "data": None}


if __name__ == "__main__":
    # 启动服务：python main.py
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
