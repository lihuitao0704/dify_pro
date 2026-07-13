"""
企业智能助手 API - 主入口
============================
"""

import os
import sys
from pathlib import Path

# 兼容两种运行方式：
#   python -m Assessment.main_ass      （模块方式）
#   python Assessment/main_ass.py      （直接运行文件）
# 后者会把 Assessment/ 加进 sys.path，导致 `from Assessment.xxx` 找不到顶层包；
# 这里统一把项目根目录加入 sys.path，让顶层包 Assessment 可被正确导入。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from Assessment.router import router as assessment_router
# resume_api 同时以 standalone(8007) 与挂载到 main_ass(8002) 两种方式运行；
# 这里挂载其 router，使 /evaluation/detail、/resume/add、/resume/upload 统一由 8002 对外。
from Assessment.resume_api import router as resume_router

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
app.include_router(resume_router, prefix="/api/agent")


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
    uvicorn.run("Assessment.main_ass:app", host=host, port=port, reload=False)
