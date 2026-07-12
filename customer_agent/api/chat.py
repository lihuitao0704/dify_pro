"""
主对话路由: POST /chat
兼容 Dify 调用习惯（UTF-8 编码 + 纯文本回复）
"""

import json
from fastapi import APIRouter, Request, Body
from typing import Optional
from pydantic import BaseModel, Field
from customer_agent.agent import process_message
from customer_agent.agent import get_context, new_session_id

router = APIRouter()


class ChatRequest(BaseModel):
    """Swagger 与调用方都会看到这个模型，输入框由此生成。"""
    message: str = Field(..., min_length=1, description="用户的自然语言问题")
    session_id: Optional[str] = Field(
        default=None,
        description="会话 ID（不传则自动创建新会话，下次传同一 ID 可续聊）",
    )
    conversation_id: str = Field(
        default="0",
        description="关联用户画像的会话标识（默认 '0'）",
    )


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


# 用 __init__ 占位让 Swagger 展示在线测试框；运行时仍走裸 Request 以兼容 Dify。
@router.post("/chat", summary="主对话")
async def chat_endpoint(
    body: Optional[ChatRequest] = Body(default=None),
    request: Request = None,
):
    """
    主对话入口。每次返回助手回复+识别到的意图。
    会话由 session_id 维护，不传则自动创建新会话。
    """
    if body is not None:
        message = body.message
        session_id = body.session_id
        conversation_id = body.conversation_id or "0"
    else:
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
    intents_out = [{"intent": i["intent"],
                    "confidence": i.get("confidence", 0)
                    } for i in result["intents"]]
    # 暴露当前锁定的多轮流程（供前端展示"正在完成 xxx"状态）
    flow = result.get("flow")
    if flow and flow.get("locked"):
        # 去重：若分类结果已含该意图，仅在第一条标记 _locked
        seen = False
        for it in intents_out:
            if it["intent"] == flow["intent"]:
                it["_locked"] = True
                it["confidence"] = 1.0
                seen = True
                break
        if not seen:
            intents_out.insert(0, {
                "intent": flow["intent"],
                "confidence": 1.0,
                "_locked": True,
            })
    out = {
        "reply": result["reply"],
        "intents": intents_out,
        "session_id": result["session_id"],
        "actions": result.get("actions", []),
    }
    if flow and flow.get("locked"):
        out["flow"] = flow
    return out


@router.get("/context/{session_id}", summary="查看会话历史")
def view_context(session_id: str):
    """调试用：查看某会话完整上下文"""
    return {"session_id": session_id, "context": get_context(session_id)}
