"""
主对话路由: POST /chat
兼容 Dify 调用习惯（UTF-8 编码 + 纯文本回复）
"""

import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from typing import Optional
from customer_agent.agent import process_message
from customer_agent.agent import get_context, new_session_id

router = APIRouter()


async def _parse_chat_body(request: Request) -> dict:
    """健壮地解析请求体：支持 JSON / form / urlencoded"""
    body = await request.body()
    ctype = request.headers.get("content-type", "")
    if "json" in ctype:
        try:
            return json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            pass
    # form / urlencoded / multipart
    try:
        form = await request.form()
        if form:
            return {k: v for k, v in form.items()}
    except Exception:
        pass
    # 最后尝试 JSON fallback
    try:
        return json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        return {}


@router.post("/chat", summary="主对话")
async def chat_endpoint(request: Request):
    """
    主对话入口。每次返回助手回复+识别到的意图。
    会话由 session_id 维护，不传则自动创建新会话。
    需要 Bearer Token 鉴权。
    """
    # 鉴权：已登录 → 校验学员身份；未登录 → 公开体验模式
    user_id = getattr(request.state, "auth_user_id", None)
    if user_id:
        user_type = getattr(request.state, "auth_user_type", "")
        if user_type != "学员":
            return JSONResponse({"error": "仅学生账号可使用客服聊天"}, status_code=403)
    # 无 auth_user_id = 公开体验（首页未登录用户），不做角色限制

    data = await _parse_chat_body(request)
    message = data.get("message", "")
    session_id = data.get("session_id", None)
    if session_id == "":
        session_id = None
    conversation_id = data.get("conversation_id", "0") or "0"

    result = process_message(
        message=message,
        session_id=session_id,
        conversation_id=conversation_id,
    )
    return {
        "reply": result["reply"],
        "intents": [{"intent": i["intent"],
                     "confidence": i.get("confidence", 0)
                     } for i in result["intents"]],
        "session_id": result["session_id"],
        "actions": result.get("actions", []),
    }


@router.get("/context/{session_id}", summary="查看会话历史")
def view_context(session_id: str):
    """调试用：查看某会话完整上下文"""
    return {"session_id": session_id, "context": get_context(session_id)}
