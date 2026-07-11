"""
企业智能助手 - FastAPI 入口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from enterprise_agent.config import APP_CONFIG, logger
from enterprise_agent.database import test_connection

# ==================== 创建应用 ====================
app = FastAPI(
    title=APP_CONFIG["title"],
    description=APP_CONFIG["description"],
    version=APP_CONFIG["version"],
    docs_url="/docs",
    redoc_url="/redoc",
)

# ==================== CORS ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 全局异常 ====================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled: %s | %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "服务器内部错误，请稍后重试", "data": None},
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

# ==================== 登录接口 ====================
from pydantic import BaseModel as PydanticBaseModel

class LoginRequest(PydanticBaseModel):
    username: str
    password: str

@app.post("/auth/login", tags=["System"])
def auth_login(req: LoginRequest):
    """员工登录：查 account 表验证用户名密码"""
    from enterprise_agent.database import SessionLocal
    from enterprise_agent.models import Account
    import hashlib
    db = SessionLocal()
    try:
        user = db.query(Account).filter(
            Account.username == req.username,
            Account.status == 1,
        ).first()
        if not user:
            return {"success": False, "code": 401, "message": "用户名或密码错误"}
        # 密码验证（支持明文和哈希两种）
        hashed = hashlib.md5(req.password.encode()).hexdigest()
        if user.password == req.password or user.password == hashed:
            return {
                "success": True, "code": 0,
                "user_id": user.user_id,
                "username": user.username,
                "user_type": user.user_type,
                "real_name": user.real_name,
                "dept_id": user.dept_id,
            }
        return {"success": False, "code": 401, "message": "用户名或密码错误"}
    except Exception as e:
        logger.error(f"Login error: {e}")
        return {"success": False, "code": 500, "message": str(e)}
    finally:
        db.close()

# ==================== 前端页面（备用） ====================
_frontend_dir = os.path.dirname(os.path.abspath(__file__))

@app.get("/", include_in_schema=False)
async def index_page():
    return HTMLResponse(
        content="""<html><body style="font-family:sans-serif;padding:40px;background:#f0f2f5">
<h1>🤖 企业智能助手</h1>
<p>请使用 Streamlit 前端：<code>streamlit run enterprise_agent/frontend/app.py --server.port 8501</code></p>
<p>或查看 API 文档：<a href="/docs">/docs</a></p>
<p>或查看健康检查：<a href="/health">/health</a></p>
</body></html>""",
        status_code=200,
    )

# ==================== 注册路由 ====================
from enterprise_agent.routers import (
    customer, leave, report, organization, todo,
    complaint, score, knowledge, nl2sql,
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
