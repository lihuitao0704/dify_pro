"""
学生智能助手 Agent 启动入口
"""

import sys
import os
import logging
import traceback
import uvicorn

try:
    import bcrypt
except ImportError:
    bcrypt = None

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware

from .config import AGENT_HOST, AGENT_PORT, API_TOKEN, API_AUTH_ENABLED
from .db import init_database, query_one, query, insert, execute
from .agent import process_message
from .reminder import start_scheduler, stop_scheduler, scan_and_remind, get_pending_reminders, mark_read
from .knowledge import get_kb

logger = logging.getLogger(__name__)


# ============================================================
#  Bearer Token 中间件
# ============================================================
class AuthMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = {"/", "/health", "/docs", "/openapi.json", "/favicon.ico",
                  "/static", "/login", "/auth/login"}

    async def dispatch(self, request: Request, call_next):
        if not API_AUTH_ENABLED:
            return await call_next(request)
        path = request.path
        if any(path.startswith(p) for p in self.SKIP_PATHS):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing Bearer Token"})
        token = auth.split(" ", 1)[-1].strip()
        if token != API_TOKEN:
            return JSONResponse(status_code=403, content={"detail": "Invalid token"})
        return await call_next(request)


# ============================================================
#  生命周期
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("  学生智能助手 Agent 启动中...")
    print("=" * 50)
    init_database()
    get_kb()
    start_scheduler()
    print(f"  聊天页面: http://localhost:{AGENT_PORT}")
    print(f"  API文档:  http://localhost:{AGENT_PORT}/docs")
    print("=" * 50)
    yield
    stop_scheduler()
    print("[Agent] 已关闭")


# ============================================================
#  FastAPI 应用
# ============================================================
app = FastAPI(
    title="学生智能助手 Agent",
    version="2.0.0",
    description="面向已签约学生的全生命周期智能助手",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ============================================================
#  数据模型
# ============================================================
class ChatRequest(BaseModel):
    student_id: int
    message: str
    session_id: str = ""

class LoginRequest(BaseModel):
    username: str
    password: str

class ChatResponse(BaseModel):
    reply: str
    intents: list = []
    emotion: dict = {}
    session_id: str = ""
    actions: list = []

class FeedbackSubmitRequest(BaseModel):
    student_id: int
    category: str = "生活服务"
    title: str = ""
    content: str = ""
    urgency: str = "normal"

class LeaveSubmitRequest(BaseModel):
    student_id: int
    leave_type: str = "事假"
    start_time: str = ""
    end_time: str = ""
    reason: str = ""
    attachment_url: str = ""


# ============================================================
#  密码工具
# ============================================================
def _verify_password(plain: str, stored: str) -> bool:
    if bcrypt is not None:
        try:
            return bcrypt.checkpw(plain.encode(), stored.encode())
        except (ValueError, AttributeError):
            pass
    return plain == stored

def _hash_password(plain: str) -> str:
    if bcrypt is not None:
        try:
            return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
        except (ValueError, AttributeError):
            pass
    return plain


# ============================================================
#  登录接口
# ============================================================
@app.post("/auth/login")
def login(req: LoginRequest):
    """统一账户密码登录，查 account 表，支持 bcrypt + 明文兼容"""
    user = query_one(
        """SELECT user_id, username, password, real_name, user_type,
                  student_id, phone, email
           FROM account WHERE username = %s AND status = 1""",
        (req.username,)
    )
    if not user:
        return {"success": False, "message": "用户名或密码不正确"}
    if not _verify_password(req.password, user["password"]):
        return {"success": False, "message": "用户名或密码不正确"}

    # 旧明文密码自动升级为 bcrypt
    if not user["password"].startswith("$2b$") and not user["password"].startswith("$2a$"):
        try:
            execute(
                "UPDATE account SET password = %s WHERE user_id = %s",
                (_hash_password(req.password), user["user_id"]),
            )
            logger.info("密码已升级为 bcrypt: user=%s", user["username"])
        except Exception:
            logger.warning("bcrypt 升级失败: user=%s", user["username"])

    sid = user.get("student_id") or user["user_id"]
    display_name = user["real_name"] or user["username"]
    if user.get("student_id"):
        stu = query_one("SELECT name, education, major FROM student WHERE id = %s", (user["student_id"],))
        if stu:
            display_name = stu["name"]

    return {
        "success": True,
        "student": {
            "id": sid,
            "name": display_name,
            "user_id": user["user_id"],
            "user_type": user["user_type"],
            "student_id": user.get("student_id"),
            "phone": user.get("phone", ""),
            "email": user.get("email", ""),
        }
    }


# ============================================================
#  根路径 + 聊天
# ============================================================
@app.get("/")
def root():
    chat_html = os.path.join(static_dir, "chat.html")
    if os.path.exists(chat_html):
        return FileResponse(chat_html)
    return {"service": "学生智能助手 Agent", "version": "2.0.0",
            "docs": "/docs", "chat": "POST /chat", "health": "GET /health"}

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    try:
        result = process_message(
            student_id=req.student_id,
            message=req.message,
            session_id=req.session_id or None,
        )
        return ChatResponse(**result)
    except Exception as e:
        logger.error("chat异常: sid=%s msg=%.100s", req.student_id, req.message, exc_info=True)
        return ChatResponse(
            reply=f"系统出错：{str(e)}", intents=[], emotion={},
            session_id="", actions=[{"intent": "error", "result": "error", "error": str(e)}],
        )


# ============================================================
#  "我的"面板
# ============================================================
@app.get("/my/profile/{student_id}")
def my_profile(student_id: int):
    mental = query_one(
        "SELECT current_emotion, risk_score, risk_level FROM mental_health_profile WHERE student_id = %s",
        (student_id,))
    upgrades = query(
        "SELECT interest_degree, interest_country, conversion_status, created_at FROM upgrade_interest WHERE student_id = %s ORDER BY created_at DESC LIMIT 5",
        (student_id,))
    return {
        "mental": {
            "emotion": mental["current_emotion"] if mental else "未知",
            "risk_score": mental["risk_score"] if mental else 0,
            "risk_level": mental["risk_level"] if mental else "low",
        },
        "upgrades": upgrades if upgrades else [],
    }

@app.get("/my/tickets/{student_id}")
def my_tickets(student_id: int):
    tickets = query(
        "SELECT id, complaint_type, complaint_detail, handle_status, create_time FROM student_complaint WHERE student_id = %s ORDER BY create_time DESC LIMIT 10",
        (student_id,))
    return {"tickets": tickets if tickets else []}

@app.get("/my/schedule/{student_id}")
def my_schedule(student_id: int):
    deadlines = query(
        "SELECT event_type, title, course_name, deadline, DATEDIFF(deadline, NOW()) AS days_left FROM academic_schedule WHERE student_id = %s AND status = 'upcoming' ORDER BY deadline ASC",
        (student_id,))
    apps = query(
        "SELECT program_name, university, current_step, application_status FROM application_progress WHERE student_id = %s ORDER BY updated_at DESC",
        (student_id,))
    reminders = query(
        "SELECT id, remind_type, message, sent_at, is_read FROM reminder_log WHERE student_id = %s AND is_read = 0 ORDER BY sent_at DESC LIMIT 10",
        (student_id,))
    return {"deadlines": deadlines if deadlines else [],
            "applications": apps if apps else [],
            "reminders": reminders if reminders else []}


# ============================================================
#  表单提交
# ============================================================
@app.post("/feedback/submit")
def feedback_submit(req: FeedbackSubmitRequest):
    tid = insert("student_complaint", {
        "student_id": req.student_id,
        "complaint_detail": f"【{req.title}】\n{req.content}",
        "complaint_type": req.category,
        "handle_status": "待处理",
    })
    return {"success": True, "ticket_id": tid, "message": "已记录"}

@app.post("/leave/submit")
def leave_submit(req: LeaveSubmitRequest):
    stu = query_one("SELECT name FROM student WHERE id = %s", (req.student_id,))
    tid = insert("leave_application", {
        "applicant_id": req.student_id,
        "applicant_type": "学生",
        "student_name": stu["name"] if stu else "同学",
        "leave_type": req.leave_type,
        "start_date": req.start_time[:10],
        "end_date": req.end_time[:10],
        "reason": req.reason,
        "status": 0,
    })
    logger.info("请假提交: student=%d ticket=%s type=%s", req.student_id, tid, req.leave_type)
    return {"success": True, "ticket_id": tid, "message": "请假申请已提交"}


# ============================================================
#  提醒
# ============================================================
@app.get("/reminders/{student_id}")
def get_reminders(student_id: int):
    reminders = get_pending_reminders(student_id)
    return {"student_id": student_id, "count": len(reminders), "reminders": reminders}

@app.post("/reminders/{reminder_id}/read")
def read_reminder(reminder_id: int):
    mark_read(reminder_id)
    return {"status": "ok"}

@app.post("/reminders/scan")
def trigger_reminder_scan():
    sent = scan_and_remind()
    return {"sent_count": len(sent), "sent": sent}

@app.get("/health")
def health():
    return {"status": "healthy"}


# ============================================================
#  启动
# ============================================================
if __name__ == "__main__":
    uvicorn.run(app, host=AGENT_HOST, port=AGENT_PORT)
