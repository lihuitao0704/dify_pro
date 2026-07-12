"""
客服Agent FastAPI 入口
运行: python -m customer_agent.main  →  http://localhost:9000
Swagger: /docs
"""

import os
import sys
from pathlib import Path

# 确保能 import customer_agent 包（当直接运行 main.py 时需加上级目录到 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles

from customer_agent.api import chat as chat_api, admin as admin_api
from customer_agent.knowledge import get_kb
from customer_agent.config import config


# ============================================================
# UTF-8 编码中间件（防止Dify调用时出现 ASCII 编码错误）
# ============================================================
class UTF8JSONResponse(JSONResponse):
    """强制 Content-Type 带 charset=utf-8 的 JSON 响应"""
    media_type = "application/json; charset=utf-8"


class UTF8Middleware(BaseHTTPMiddleware):
    """兜底：给所有响应补上 charset=utf-8"""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if "charset" not in ct:
            if ct.startswith("application/json") or ct.startswith("text/"):
                response.headers["content-type"] = ct + "; charset=utf-8"
        return response


# ============================================================
# 生命周期
# ============================================================
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 55)
    print("  客服Agent 启动中... 端口:", config.AGENT_PORT)
    print("=" * 55)

    # 初始化知识库
    kb = get_kb()

    print(f"  知识库: {len(kb.chunks)} chunks, {len(kb.faq_map)} FAQ")
    print(f"  文档: http://localhost:{config.AGENT_PORT}/docs")
    print(f"  知识库状态: http://localhost:{config.AGENT_PORT}/admin/kb-status")
    print(f"  LLM模型: {config.LLM_MODEL}")
    print(f"  桥接 study_abroad_agent: {config.STUDY_ABROAD_URL}")
    print(f"  桥接 Event&Lecture: {config.EVENT_LECTURE_URL}")
    print("=" * 55)

    yield


# ============================================================
# FastAPI 应用
# ============================================================
app = FastAPI(
    title="粤教留学客服Agent",
    description=(
        "面向潜在客户的智能客服系统，覆盖七大场景：\n"
        "- 公司信息咨询\n"
        "- 业务查询\n"
        "- 海外留学政策\n"
        "- 课程与项目推荐\n"
        "- 活动与讲座报名\n"
        "- 常见问题自助解答\n"
        "- 日常闲聊互动\n\n"
        "底层桥接 study_abroad_agent(:5000) + Event&Lecture(:8011)"
    ),
    version="1.0.0",
    default_response_class=UTF8JSONResponse,
    lifespan=lifespan,
)

# 中间件（后添加的先执行）
app.add_middleware(UTF8Middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(chat_api.router)
app.include_router(admin_api.router)

# 静态文件服务（前端页面）
_static_dir = str(Path(__file__).resolve().parent / "static")
import os as _os
_os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# 统一门户前端（显式路由方式，避免 Windows 上 mount 的缓存问题）
from customer_agent import portal_routes
portal_routes.register_portal_routes(app)


# ============================================================
# 根路径 → 重定向到工作台
# ============================================================
@app.get("/")
def root():
    """根路径 → 重定向到工作台（如已登录）或登录页"""
    return FileResponse(os.path.join(_static_dir, "login.html"))


# ============================================================
# 前端页面快捷路由（类 SeaShell 的友好路径）
# ============================================================
@app.get("/login")
def login_page():
    return FileResponse(os.path.join(_static_dir, "login.html"))


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(os.path.join(_static_dir, "dashboard.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


# ============================================================
# 统一登录（account表，与student_agent共享）
# ============================================================
@app.post("/auth/login")
async def auth_login(request: Request):
    """统一登录：支持 account表(用户名+密码，bcrypt/明文兼容) 和 student表(学号+姓名)"""
    import pymysql, json as _json
    from student_agent.config import DB_CONFIG

    body = await request.json()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    sid = body.get("student_id") or 0
    sname = (body.get("name") or "").strip()

    def check_pw(plain, stored):
        try:
            import bcrypt
            return bcrypt.checkpw(plain.encode(), stored.encode())
        except Exception:
            return plain == stored

    conn = pymysql.connect(**DB_CONFIG)
    conn.autocommit(True)
    try:
        with conn.cursor() as cur:
            if username and password:
                cur.execute(
                    """SELECT user_id, username, password, real_name, user_type, student_id, phone, email
                       FROM account WHERE username = %s AND status = 1""", (username,))
                row = cur.fetchone()
                if not row:
                    return {"success": False, "message": "用户名或密码不正确"}
                cols = [c[0] for c in cur.description]
                user = dict(zip(cols, row))
                if not check_pw(password, user["password"]):
                    return {"success": False, "message": "用户名或密码不正确"}
                uid = user.get("student_id") or user["user_id"]
                dname = user["real_name"] or user["username"]
                if user.get("student_id"):
                    cur.execute("SELECT name FROM student WHERE id = %s", (user["student_id"],))
                    sr = cur.fetchone()
                    if sr: dname = sr[0]
                return {"success": True, "student": {
                    "id": uid, "name": dname, "user_id": user["user_id"],
                    "user_type": user["user_type"], "student_id": user.get("student_id"),
                    "phone": user.get("phone",""), "email": user.get("email","")}}
            if sid and sname:
                cur.execute("SELECT id, name, education, major FROM student WHERE id=%s AND name=%s", (sid, sname))
                row = cur.fetchone()
                if row:
                    cols = [c[0] for c in cur.description]
                    stu = dict(zip(cols, row))
                    return {"success": True, "student": {
                        "id": stu["id"], "name": stu["name"],
                        "education": stu.get("education",""), "major": stu.get("major","")}}
                return {"success": False, "message": "学号或姓名不正确"}
            return {"success": False, "message": "请提供用户名+密码 或 学号+姓名"}
    finally:
        conn.close()


# ============================================================
# 直接运行入口
# ============================================================
if __name__ == "__main__":
    uvicorn.run("customer_agent.main:app", host=config.AGENT_HOST,
                port=config.AGENT_PORT, reload=True)
