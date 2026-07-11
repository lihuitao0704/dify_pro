"""
企业智能助手 API - 主入口
============================
"""

import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from Assessment.router import router as assessment_router

# ────────────────────────────────────────────────────────────
# 创建 FastAPI 应用
# ────────────────────────────────────────────────────────────
app = FastAPI(
    title="企业智能助手 API",
    description="教育服务系统 - 画像评估接口（NL2SQL）",
    version="2.0.0",
)

# CORS 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ────────────────────────────────────────────────────────────
# 注册路由（统一前缀 /api/agent）
# ────────────────────────────────────────────────────────────
app.include_router(assessment_router, prefix="/api/agent")


# ────────────────────────────────────────────────────────────
# 根路径
# ────────────────────────────────────────────────────────────
@app.get("/")
def root():
    """健康检查"""
    return {"code": 0, "msg": "企业智能助手 API 运行中", "data": {"version": "2.0.0"}}


# ────────────────────────────────────────────────────────────
# 启动入口
# ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
