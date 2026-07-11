"""
教育服务系统 — FastAPI 入口
学生智能助手模块

启动: uvicorn main:app --reload --host 0.0.0.0 --port 8008
文档: http://localhost:8008/docs
"""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from contextlib import asynccontextmanager

# 日志初始化放在入口文件，不在库模块里抢占调用方配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

from config import CORS_ORIGINS, API_TOKEN, API_AUTH_ENABLED, startup_check
from models import get_engine, get_session
from routers import chat, student, nl2sql

AUTH_WHITELIST = (
    "/docs", "/redoc", "/openapi.json", "/health", "/static",
)
AUTH_WHITELIST_EXACT = ("/api", "/api/")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    status = startup_check()
    if status["warnings"]:
        print("[lifespan] Warnings:", file=sys.stderr)
        for w in status["warnings"]:
            print(f"  - {w}", file=sys.stderr)
    try:
        get_engine()
    except Exception as e:
        print(f"[lifespan] Engine init failed: {e}", file=sys.stderr)
    yield


app = FastAPI(
    title="教育服务系统 - 学生智能助手 API",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# 认证中间件
# ============================================================

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    for prefix in AUTH_WHITELIST:
        if path.startswith(prefix):
            return await call_next(request)

    if path in AUTH_WHITELIST_EXACT:
        return await call_next(request)

    if request.method == "OPTIONS":
        return await call_next(request)

    if API_AUTH_ENABLED and path.startswith("/api"):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing token. Use: Authorization: Bearer <token>"},
            )
        # 取 Bearer 之后的部分并去掉首尾空白，容忍 "Bearer    token" 等多空格场景
        token = auth_header.split(" ", 1)[-1].strip() if " " in auth_header else ""
        if token != API_TOKEN:
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid token"},
            )

    return await call_next(request)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(chat.router)
app.include_router(student.router)
app.include_router(nl2sql.router)


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/api")
def api_info():
    return {"service": "教育服务系统 - 学生智能助手", "version": "1.0.0"}


@app.get("/health")
def health():
    try:
        from sqlalchemy import text
        with get_session() as s:
            s.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": str(e)},
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8008, reload=True)
