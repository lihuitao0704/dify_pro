"""
FastAPI 应用入口
"""
import sys
from pathlib import Path

# 将项目根目录的父目录加入 sys.path，使 study_abroad_agent 包可被导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dify_pro.study_abroad_agent.api import ROUTERS
from dify_pro.study_abroad_agent.api.dify import router as dify_router
from dify_pro.study_abroad_agent.utils.logger import logger


def create_app() -> FastAPI:
    app = FastAPI(
        title="智能留学顾问系统 (NL2SQL + CRUD)",
        description=(
            "基于 FastAPI、MySQL 的留学课程推荐后端服务。\n\n"
            "- `/api/v1/*`：新版 CRUD + NL2SQL 接口\n"
            "- `/api/dify/*`：旧版 Dify 工作流兼容接口"
        ),
        version="3.0.0",
    )

    # ── CORS ──────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 新版 v1 路由 ──────────────────────────────────────
    for prefix, router in ROUTERS:
        app.include_router(router, prefix="/api/v1" + prefix)

    # ── 兼容旧版 /api/dify 路由 ────────────────────────────
    app.include_router(dify_router, prefix="/api/dify")

    # ── 全局错误处理 ──────────────────────────────────────
    @app.exception_handler(Exception)
    async def handle_all(_: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"code": 500, "data": None, "message": str(exc)},
        )

    @app.on_event("startup")
    async def on_startup():
        logger.info("✅ FastAPI 已就绪，Swagger 文档: /docs")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
