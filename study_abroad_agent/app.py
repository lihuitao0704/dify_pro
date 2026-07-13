"""
FastAPI 应用入口
"""
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使 study_abroad_agent / shared 包可被导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from study_abroad_agent.api import ROUTERS
from study_abroad_agent.api.dify import router as dify_router
from study_abroad_agent.utils.logger import logger
from shared.auth import verify_jwt, bearer_token

# ── 免鉴权路径 ──
_AUTH_SKIP_PATHS = {"/health", "/ready", "/docs", "/openapi.json", "/favicon.ico"}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """验证 Bearer Token"""

    async def dispatch(self, request: Request, call_next):
        path = request.scope.get("path", "") if hasattr(request, "scope") else str(request.url.path)

        if any(path.startswith(p) for p in _AUTH_SKIP_PATHS):
            return await call_next(request)

        token = bearer_token(dict(request.headers))
        if not token:
            return JSONResponse(status_code=401, content={"detail": "缺少认证令牌"})

        payload = verify_jwt(token)
        if payload is None:
            return JSONResponse(status_code=401, content={"detail": "令牌无效或已过期"})

        request.state.auth_user_id = payload.get("user_id")
        request.state.auth_user_type = payload.get("user_type")
        return await call_next(request)


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

    # ── 鉴权中间件 ──────────────────────────────────────
    app.add_middleware(BearerAuthMiddleware)

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

    # ── 全局错误处理（不泄露内部异常详情）──────────────
    @app.exception_handler(Exception)
    async def handle_all(_: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"code": 500, "data": None, "message": "服务器内部错误，请稍后重试"},
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
