"""
企业智能助手 - FastAPI 入口（修复版）
- bcrypt 密码哈希（替代 MD5）
- JWT Token 签发
- CORS 安全配置修复
- 全局异常处理
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Optional

from enterprise_agent.config import APP_CONFIG, logger
from enterprise_agent.database import test_connection
from enterprise_agent.security import (
    verify_password_compat, migrate_hash, create_jwt, verify_jwt, bearer_token,
)

# ==================== 创建应用 ====================
app = FastAPI(
    title=APP_CONFIG["title"],
    description=APP_CONFIG["description"],
    version=APP_CONFIG["version"],
    docs_url="/docs",
    redoc_url="/redoc",
)

# ==================== CORS（修复：明确指定域名或使用安全通配） ====================
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(",") if CORS_ORIGINS != "*" else ["*"],
    allow_credentials=False if CORS_ORIGINS == "*" else True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ==================== JWT 依赖注入（兼容旧版 Query Param） ====================

def get_current_user(
    request: Request,
    current_user_id: Optional[int] = None,
    current_user_type: Optional[str] = None,
) -> dict:
    """
    获取当前用户信息。
    优先从 JWT 解析（Authorization: Bearer <token>），
    回退到 Query Param（兼容前端旧版调用）。
    """
    # 尝试从 JWT 获取
    token = bearer_token(dict(request.headers))
    if token:
        payload = verify_jwt(token)
        if payload:
            return {
                "user_id": payload.get("user_id"),
                "user_type": payload.get("user_type"),
                "real_name": payload.get("real_name", ""),
                "username": payload.get("username", ""),
            }

    # 回退到 Query Param（兼容模式）
    if current_user_id is not None and current_user_type is not None:
        return {
            "user_id": current_user_id,
            "user_type": current_user_type,
            "real_name": "",
            "username": "",
        }

    raise HTTPException(status_code=401, detail="未登录或 Token 已过期")


# ==================== 全局异常 ====================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled: %s | %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "服务器内部错误，请稍后重试", "data": None},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("HTTP %s: %s", exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": exc.detail, "data": None},
    )

# ==================== 启动事件 ====================
@app.on_event("startup")
async def startup():
    ok = test_connection()
    logger.info("DB status: %s", "connected" if ok else "FAILED")
    if not ok:
        logger.warning("Check DB_HOST/DB_PORT/DB_USER/DB_PASSWORD in .env")
    # 启动主动待办推送调度器
    try:
        from enterprise_agent.todo_scheduler import start_scheduler as start_todo_scheduler
        start_todo_scheduler(interval=300)
        logger.info("待办推送调度器已启动")
    except Exception as e:
        logger.warning("待办推送调度器启动失败: %s", e)

# ==================== 健康检查 ====================
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "enterprise_agent", "version": APP_CONFIG["version"]}

# ==================== 登录接口（修复：bcrypt + JWT） ====================
from pydantic import BaseModel as PydanticBaseModel

class LoginRequest(PydanticBaseModel):
    username: str
    password: str

@app.post("/auth/login", tags=["System"])
def auth_login(req: LoginRequest):
    """员工登录：bcrypt验证 → 返回JWT Token"""
    from enterprise_agent.database import SessionLocal
    from enterprise_agent.models import Account
    db = SessionLocal()
    try:
        user = db.query(Account).filter(
            Account.username == req.username,
            Account.status == 1,
        ).first()
        if not user:
            return {"success": False, "code": 401, "message": "用户名或密码错误"}

        # bcrypt 验证（兼容旧版SHA256哈希，返回是否需迁移）
        is_valid, needs_migrate = verify_password_compat(req.password, user.password)
        if not is_valid:
            return {"success": False, "code": 401, "message": "用户名或密码错误"}

        # 旧版哈希 → 自动升级为 bcrypt（强制迁移，不留长期双哈希）
        if needs_migrate:
            logger.warning(
                "密码哈希迁移: user_id=%s, username=%s, 旧SHA256→bcrypt",
                user.user_id, user.username,
            )
            user.password = migrate_hash(req.password)
            db.commit()

        # 签发 JWT
        token = create_jwt({
            "user_id": user.user_id,
            "username": user.username,
            "user_type": user.user_type,
            "real_name": user.real_name,
        })

        return {
            "success": True, "code": 0,
            "token": token,
            "token_type": "Bearer",
            "expire_hours": int(os.getenv("JWT_EXPIRE_HOURS", "24")),
            "user_id": user.user_id,
            "username": user.username,
            "user_type": user.user_type,
            "real_name": user.real_name,
            "dept_id": user.dept_id,
        }
    except Exception as e:
        logger.error("Login error: %s", e)
        return {"success": False, "code": 500, "message": "服务器错误"}
    finally:
        db.close()

# ==================== 前端页面 ====================
_frontend_dir = os.path.dirname(os.path.abspath(__file__))
_frontend_file = os.path.join(_frontend_dir, "test_dashboard.html")

@app.get("/", include_in_schema=False)
async def index_page():
    if os.path.exists(_frontend_file):
        with open(_frontend_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Frontend not found</h1>", status_code=404)

# ==================== 注册路由 ====================
from enterprise_agent.routers import (
    customer, leave, report, organization, todo,
    complaint, score, knowledge, nl2sql, mental_health,
)

app.include_router(customer.router, prefix="/api/agent", tags=["意向客户管理"])
app.include_router(leave.router, prefix="/api/agent", tags=["请假管理"])
app.include_router(report.router, prefix="/api/agent", tags=["日报管理"])
app.include_router(organization.router, prefix="/api/agent", tags=["组织架构"])
app.include_router(todo.router, prefix="/api/agent", tags=["待办汇总"])
app.include_router(complaint.router, prefix="/api/agent", tags=["投诉反馈"])
app.include_router(score.router, prefix="/api/agent", tags=["成绩管理"])
app.include_router(knowledge.router, prefix="/api/agent", tags=["知识库问答"])
app.include_router(nl2sql.router, prefix="/api/agent", tags=["NL2SQL自然语言查询"])
app.include_router(mental_health.router, prefix="/api/agent", tags=["心理健康管理"])

logger.info(
    "Routes registered: /api/agent/* (%d modules)",
    len(app.routes),
)

# ==================== 启动 ====================
if __name__ == "__main__":
    uvicorn.run(
        "enterprise_agent.main:app",
        host=APP_CONFIG["host"],
        port=APP_CONFIG["port"],
        reload=APP_CONFIG["debug"],
        log_level="info",
    )
