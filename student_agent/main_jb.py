"""
学生智能助手 Agent 启动入口
通过根目录 main.py 启动：python main.py → http://localhost:8000
"""

import sys
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from starlette.middleware.base import BaseHTTPMiddleware

from .config import AGENT_HOST, AGENT_PORT, API_TOKEN, API_AUTH_ENABLED
from .db import init_database, query_one
from .agent import process_message
from .reminder import start_scheduler, stop_scheduler, scan_and_remind, get_pending_reminders, mark_read
from .knowledge import get_kb


# ============================================================
#  Bearer <REDACTED> 中间件（复用 student_sgent 的鉴权方案）
# ============================================================
class AuthMiddleware(BaseHTTPMiddleware):
    """验证 Bearer <REDACTED>（可通过 .env 的 API_AUTH_ENABLED=false 关闭）"""

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
            return JSONResponse(status_code=401,
                                content={"detail": "Missing Bearer <REDACTED>"})
        token = auth.split(" ", 1)[-1].strip()
        if token != API_TOKEN:
            return JSONResponse(status_code=403,
                                content={"detail": "Invalid token"})
        return await call_next(request)


# ============================================================
#  生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务启动/关闭"""
    print("=" * 50)
    print("  学生智能助手 Agent 启动中...")
    print("=" * 50)

    # 初始化数据库（建库建表种子数据）
    init_database()

    # 加载知识库
    kb = get_kb()

    # 启动定时提醒
    start_scheduler()

    print(f"  聊天页面: http://localhost:{AGENT_PORT}")
    print(f"  API文档:  http://localhost:{AGENT_PORT}/docs")
    print("=" * 50)

    yield

    # 关闭
    stop_scheduler()
    print("[Agent] 已关闭")


# ============================================================
#  FastAPI 应用
# ============================================================

app = FastAPI(
    title="学生智能助手 Agent",
    version="1.0.0",
    description="面向已签约学生的全生命周期智能助手，覆盖7大留学服务场景",
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

# 静态文件（聊天页面）
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ============================================================
#  接口
# ============================================================

class ChatRequest(BaseModel):
    student_id: int
    message: str
    session_id: str = ""


class LoginRequest(BaseModel):
    student_id: int
    name: str


class ChatResponse(BaseModel):
    reply: str
    intents: list = []
    emotion: dict = {}
    session_id: str = ""
    actions: list = []


# ============================================================
#  登录接口
# ============================================================

@app.post("/auth/login")
def login(req: LoginRequest):
    """验证学生身份，查本地student表"""
    student = query_one(
        "SELECT id, name, education, major, gpa, assigned_teacher_id FROM student WHERE id = %s AND name = %s",
        (req.student_id, req.name)
    )
    if student:
        return {
            "success": True,
            "student": {
                "id": student["id"],
                "name": student["name"],
                "education": student.get("education", ""),
                "major": student.get("major", ""),
            }
        }
    return {"success": False, "message": "学号或姓名不正确"}


@app.get("/")
def root():
    """根路径 → 返回聊天页面"""
    chat_html = os.path.join(static_dir, "chat.html")
    if os.path.exists(chat_html):
        return FileResponse(chat_html)
    return {
        "service": "学生智能助手 Agent",
        "version": "1.0.0",
        "chat_page": "请访问 /static/chat.html",
        "docs": "/docs",
        "endpoints": {
            "chat": "POST /chat",
            "reminders": "GET /reminders/{student_id}",
            "health": "GET /health",
        }
    }


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """
    主对话接口：学生发送消息，Agent 返回回复。

    参数：
    - student_id: 学生ID（1001-1005 为种子数据）
    - message: 自然语言消息
    - session_id: 可选，会话ID（用于多轮对话上下文）
    """
    import traceback
    try:
        result = process_message(
            student_id=req.student_id,
            message=req.message,
            session_id=req.session_id or None,
        )
        return ChatResponse(**result)
    except Exception as e:
        traceback.print_exc()
        return ChatResponse(
            reply=f"系统出错：{str(e)}",
            intents=[],
            emotion={},
            session_id="",
            actions=[{"intent": "error", "result": "error", "error": str(e)}],
        )


# ============================================================
#  "我的"面板接口
# ============================================================

@app.get("/my/profile/{student_id}")
def my_profile(student_id: int):
    """我的：心理状态 + 升学意向"""
    from .db import query_one, query
    mental = query_one(
        "SELECT current_emotion, risk_score, risk_level FROM mental_health_profile WHERE student_id = %s",
        (student_id,)
    )
    upgrades = query(
        "SELECT interest_degree, interest_country, conversion_status, created_at FROM upgrade_interest WHERE student_id = %s ORDER BY created_at DESC LIMIT 5",
        (student_id,)
    )
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
    """我的：反馈工单"""
    from .db import query
    tickets = query(
        "SELECT id, title, category, urgency, status, created_at FROM feedback_ticket WHERE student_id = %s ORDER BY created_at DESC LIMIT 10",
        (student_id,)
    )
    return {"tickets": tickets if tickets else []}


@app.get("/my/schedule/{student_id}")
def my_schedule(student_id: int):
    """我的：日程 + 申请进度 + 未读提醒"""
    from .db import query
    deadlines = query(
        "SELECT event_type, title, course_name, deadline, DATEDIFF(deadline, NOW()) AS days_left FROM academic_schedule WHERE student_id = %s AND status = 'upcoming' ORDER BY deadline ASC",
        (student_id,)
    )
    apps = query(
        "SELECT program_name, university, current_step, application_status FROM application_progress WHERE student_id = %s ORDER BY updated_at DESC",
        (student_id,)
    )
    reminders = query(
        "SELECT id, remind_type, message, sent_at, is_read FROM reminder_log WHERE student_id = %s AND is_read = 0 ORDER BY sent_at DESC LIMIT 10",
        (student_id,)
    )
    return {
        "deadlines": deadlines if deadlines else [],
        "applications": apps if apps else [],
        "reminders": reminders if reminders else [],
    }


# ============================================================
#  投诉反馈表单提交
# ============================================================

class FeedbackSubmitRequest(BaseModel):
    student_id: int
    category: str = "生活服务"
    title: str = ""
    content: str = ""
    urgency: str = "normal"

@app.post("/feedback/submit")
def feedback_submit(req: FeedbackSubmitRequest):
    """表单提交投诉建议，写入 feedback_ticket"""
    from .db import insert
    tid = insert("feedback_ticket", {
        "student_id": req.student_id,
        "title": req.title,
        "content": req.content,
        "category": req.category,
        "urgency": req.urgency,
        "priority": 10 if req.urgency == "urgent" else 5,
        "status": "open",
    })
    return {"success": True, "ticket_id": tid, "message": "工单已创建"}


# ============================================================
#  请假表单提交
# ============================================================

class LeaveSubmitRequest(BaseModel):
    student_id: int
    leave_type: str = "事假"
    start_time: str = ""
    end_time: str = ""
    reason: str = ""
    attachment_url: str = ""

@app.post("/leave/submit")
def leave_submit(req: LeaveSubmitRequest):
    """表单提交请假"""
    from .db import insert
    insert("reminder_log", {
        "student_id": req.student_id,
        "remind_type": "请假申请",
        "remind_channel": "agent",
        "message": f"请假: {req.leave_type} | {req.start_time[:16]}~{req.end_time[:16]} | {req.reason}",
    })
    return {"success": True, "message": "请假申请已提交"}


@app.get("/reminders/{student_id}")
def get_reminders(student_id: int):
    """获取学生的未读提醒"""
    reminders = get_pending_reminders(student_id)
    return {
        "student_id": student_id,
        "count": len(reminders),
        "reminders": reminders,
    }


@app.post("/reminders/{reminder_id}/read")
def read_reminder(reminder_id: int):
    """标记提醒为已读"""
    mark_read(reminder_id)
    return {"status": "ok"}


@app.post("/reminders/scan")
def trigger_reminder_scan():
    """手动触发提醒扫描（测试用）"""
    sent = scan_and_remind()
    return {"sent_count": len(sent), "sent": sent}


@app.get("/health")
def health():
    return {"status": "healthy"}


# ============================================================
#  直接运行入口
# ============================================================

if __name__ == "__main__":
    uvicorn.run("student_agent.main:app", host=AGENT_HOST, port=AGENT_PORT)
