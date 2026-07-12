"""
学生智能助手 Agent 启动入口
"""

import sys
import os
import json
import logging
import traceback
import uvicorn

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware

from .config import AGENT_HOST, AGENT_PORT, API_TOKEN, API_AUTH_ENABLED
from .db import init_database, query_one, query, insert, execute
from .agent import process_message, process_message_stream
from .reminder import start_scheduler, stop_scheduler, scan_and_remind, get_pending_reminders, mark_read
from .knowledge import get_kb

logger = logging.getLogger(__name__)


# ============================================================
#  Bearer Token 中间件
# ============================================================
class AuthMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = {"/", "/health", "/docs", "/openapi.json", "/favicon.ico",
                  "/static", "/login", "/auth/login", "/portal"}

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
        # 将用户身份注入 request.state 供后续鉴权
        uid = request.headers.get("X-User-Id", "")
        if uid:
            try:
                request.state.auth_user_id = int(uid)
            except (ValueError, TypeError):
                pass
        return await call_next(request)


def _require_self_or_forbid(student_id: int, request: Request):
    """校验请求者身份：student_id 必须与 X-User-Id 一致"""
    if not API_AUTH_ENABLED:
        return
    auth_uid = getattr(request.state, "auth_user_id", None)
    if auth_uid and auth_uid != student_id:
        raise PermissionError(f"无权访问 student_id={student_id} 的数据")


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

# ── 统一门户前端（直连 student_agent:8000 时也可使用） ──
_unified_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "unified_frontend")

@app.get("/portal")
def portal_index():
    return FileResponse(os.path.join(_unified_dir, "index.html"))

@app.get("/portal/css/{filename}")
def portal_css(filename: str):
    filename = os.path.basename(filename)  # 防路径穿越
    return FileResponse(os.path.join(_unified_dir, "css", filename))

@app.get("/portal/js/{filename}")
def portal_js(filename: str):
    filename = os.path.basename(filename)  # 防路径穿越
    return FileResponse(os.path.join(_unified_dir, "js", filename))

@app.get("/portal/student-dashboard")
def portal_student_dashboard():
    return FileResponse(os.path.join(_unified_dir, "student-dashboard.html"))

@app.get("/portal/employee-dashboard")
def portal_employee_dashboard():
    return FileResponse(os.path.join(_unified_dir, "employee-dashboard.html"))


# ============================================================
#  数据模型
# ============================================================
class ChatRequest(BaseModel):
    student_id: int
    message: str
    session_id: str = ""

class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""
    student_id: int = 0
    name: str = ""

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
#  登录接口
# ============================================================
@app.post("/auth/login")
async def login(request: Request):
    """统一登录：account 表用户名+密码"""
    import json as _json
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()

    if username and password:
        user = query_one(
            """SELECT user_id, username, password, real_name, user_type,
                      student_id, phone, email
               FROM account WHERE username = %s AND status = 1""",
            (username,))
        if not user:
            return {"success": False, "message": "用户名或密码不正确"}
        if password != user["password"]:
            return {"success": False, "message": "用户名或密码不正确"}

        # 角色校验：学生端仅允许学员登录
        actual_type = (user.get("user_type") or "").strip()
        if actual_type != "学员":
            logger.warning("学生端拒绝非学员登录: username=%s user_type=%r", username, actual_type)
            return {"success": False, "message": f"该账号为{actual_type}账号，请使用员工登录入口"}

        sid = user.get("student_id") or user["user_id"]
        display_name = user["real_name"] or user["username"]
        if user.get("student_id"):
            stu = query_one("SELECT name FROM student WHERE id = %s", (user["student_id"],))
            if stu:
                display_name = stu["name"]
        return {"success": True, "student": {
            "id": sid, "name": display_name, "user_id": user["user_id"],
            "user_type": user["user_type"], "student_id": user.get("student_id"),
            "phone": user.get("phone", ""), "email": user.get("email", ""),
        }}

    return {"success": False, "message": "请提供用户名和密码"}


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
            reply="系统出了一点小问题，请稍后再试～", intents=[], emotion={},
            session_id="", actions=[{"intent": "error", "result": "error", "error": "internal_error"}],
        )


@app.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """流式 SSE 聊天端点"""
    import json as _json

    async def generate():
        try:
            for event in process_message_stream(
                student_id=req.student_id,
                message=req.message,
                session_id=req.session_id or None,
            ):
                yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("Stream异常: %s", e, exc_info=True)
            yield f"data: {_json.dumps({'type': 'token', 'text': f'[出错] {e}'}, ensure_ascii=False)}\n\n"
            yield f"data: {_json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
#  "我的"面板
# ============================================================
@app.get("/my/profile/{student_id}")
def my_profile(student_id: int, request: Request):
    try: _require_self_or_forbid(student_id, request)
    except PermissionError: return JSONResponse(status_code=403, content={"detail": "无权访问"})
    mental = query_one(
        "SELECT current_emotion, risk_score, risk_level, emotion_history, "
        "negative_keywords_count, consecutive_negative_days, last_assessment_at "
        "FROM mental_health_profile WHERE student_id = %s",
        (student_id,))
    # 最近一条待处理预警
    recent_alert = query_one(
        "SELECT trigger_reason, risk_level, alert_content, emotion_label, risk_score, "
        "follow_up_status, created_at FROM mental_health_alert "
        "WHERE student_id = %s AND follow_up_status = 'pending' "
        "ORDER BY created_at DESC LIMIT 1",
        (student_id,))
    upgrades = query(
        "SELECT interest_degree, interest_country, conversion_status, created_at FROM upgrade_interest WHERE student_id = %s ORDER BY created_at DESC LIMIT 5",
        (student_id,))
    return {
        "mental": {
            "emotion": mental["current_emotion"] if mental else "未知",
            "risk_score": mental["risk_score"] if mental else 0,
            "risk_level": mental["risk_level"] if mental else "low",
            "emotion_history": json.loads(mental["emotion_history"]) if (mental and mental.get("emotion_history")) else [],
            "negative_keywords_count": mental["negative_keywords_count"] if mental else 0,
            "consecutive_negative_days": mental["consecutive_negative_days"] if mental else 0,
            "last_assessment_at": str(mental["last_assessment_at"]) if (mental and mental.get("last_assessment_at")) else None,
            "recent_alert": {
                "trigger_reason": recent_alert.get("trigger_reason", ""),
                "risk_level": recent_alert.get("risk_level", "low"),
                "follow_up_status": recent_alert.get("follow_up_status", "pending"),
                "created_at": str(recent_alert["created_at"]) if recent_alert.get("created_at") else None,
            } if recent_alert else None,
        },
        "upgrades": upgrades if upgrades else [],
    }

@app.get("/my/tickets/{student_id}")
def my_tickets(student_id: int, request: Request):
    try: _require_self_or_forbid(student_id, request)
    except PermissionError: return JSONResponse(status_code=403, content={"detail": "无权访问"})
    tickets = query(
        "SELECT id, complaint_type, complaint_detail, handle_status, create_time FROM student_complaint WHERE student_id = %s ORDER BY create_time DESC LIMIT 10",
        (student_id,))
    return {"tickets": tickets if tickets else []}

@app.get("/my/schedule/{student_id}")
def my_schedule(student_id: int, request: Request):
    try: _require_self_or_forbid(student_id, request)
    except PermissionError: return JSONResponse(status_code=403, content={"detail": "无权访问"})
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
def feedback_submit(req: FeedbackSubmitRequest, request: Request):
    try: _require_self_or_forbid(req.student_id, request)
    except PermissionError: return JSONResponse(status_code=403, content={"detail": "无权访问"})
    tid = insert("student_complaint", {
        "student_id": req.student_id,
        "complaint_detail": f"【{req.title}】\n{req.content}",
        "complaint_type": req.category,
        "handle_status": "待处理",
    })
    return {"success": True, "ticket_id": tid, "message": "已记录"}

@app.post("/leave/submit")
def leave_submit(req: LeaveSubmitRequest, request: Request):
    try: _require_self_or_forbid(req.student_id, request)
    except PermissionError: return JSONResponse(status_code=403, content={"detail": "无权访问"})
    stu = query_one("SELECT name FROM student WHERE id = %s", (req.student_id,))
    tid = insert("leave_request", {
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
def get_reminders(student_id: int, request: Request):
    try: _require_self_or_forbid(student_id, request)
    except PermissionError: return JSONResponse(status_code=403, content={"detail": "无权访问"})
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
