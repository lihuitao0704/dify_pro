"""
教育服务系统 — FastAPI 主入口
学生智能助手模块 API 服务
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import settings
from routers import student, tools

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    docs_url="/docs",       # Swagger UI
    redoc_url="/redoc",     # ReDoc
)

# CORS 跨域配置
# 注意：allow_origins=["*"] 与 allow_credentials=True 不能同时使用（CORS 规范禁止）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求体大小限制（纯 ASGI 协议层中间件，累计 body 大小防 chunked 绕过）
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Scope, Receive, Send, Message

MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB


class BodySizeLimitMiddleware:
    """纯 ASGI 中间件：拦截超大请求，支持 content-length 快速拒绝 + chunked 累计检查"""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Content-Length 快速拒绝
        content_length = 0
        for name, val in scope.get("headers", []):
            if name == b"content-length":
                content_length = int(val)
                break
        if content_length > self.max_bytes:
            response = JSONResponse(status_code=413, content={"detail": f"请求体超过 {self.max_bytes // 1024 // 1024}MB 限制"})
            await response(scope, receive, send)
            return

        # 无 Content-Length 或 chunked：累计 body 大小
        if content_length == 0:
            total_body = 0
            rejected = False

            async def tracked_receive() -> Message:
                nonlocal total_body, rejected
                message = await receive()
                if message["type"] == "http.request":
                    chunk = message.get("body", b"")
                    total_body += len(chunk)
                    if total_body > self.max_bytes and not rejected:
                        rejected = True
                        resp = JSONResponse(status_code=413, content={"detail": "请求体超过 5MB 限制"})
                        await resp(scope, receive, send)
                        # 消费剩余 body 块，但不再返回给 Starlette（避免 double-response）
                        return {"type": "http.request", "body": b"", "more_body": False}
                    if rejected:
                        # 已拒绝，静默消费后续所有 body 块
                        return {"type": "http.request", "body": b"", "more_body": message.get("more_body", False)}
                return message

            await self.app(scope, tracked_receive, send)
        else:
            await self.app(scope, receive, send)


app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_BODY_BYTES)

# 注册路由
app.include_router(student.router, tags=["学生智能助手"])
app.include_router(tools.router, tags=["Dify工具API"])


@app.get("/health", tags=["系统"])
def health_check():
    """健康检查（Dify 和负载均衡器探测用）"""
    api_key_ok = bool(settings.DEEPSEEK_API_KEY)
    # 数据库连接探测
    db_ok = False
    try:
        from utils.database import SessionLocal
        s = SessionLocal()
        s.execute(text("SELECT 1"))
        s.close()
        db_ok = True
    except Exception:
        pass

    all_ok = api_key_ok and db_ok
    return {
        "status": "ok" if all_ok else "degraded",
        "version": settings.APP_VERSION,
        "checks": {
            "deepseek_api": "configured" if api_key_ok else "missing",
            "database": "connected" if db_ok else "unreachable",
        },
    }


@app.get("/", tags=["系统"])
def index():
    """API 入口"""
    return {
        "service": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "student_business": "/api/v1/student/*",
            "dify_tools": "/api/v1/dify/tools/*",
        },
    }


# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,  # 开发模式热重载
    )
