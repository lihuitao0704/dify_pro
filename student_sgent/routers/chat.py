"""
会话与消息 API 路由
"""

from fastapi import APIRouter, HTTPException, Query

from schemas.student import SessionCreate, SessionResponse, MessageCreate, MessageResponse
from services import student_service as svc

router = APIRouter(prefix="/api/v1/chat", tags=["会话与消息"])


@router.post("/sessions", response_model=SessionResponse)
def create_session(body: SessionCreate):
    sess = svc.create_session(body.student_id, body.session_id)
    return SessionResponse.model_validate(sess)


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    student_id: int = Query(..., description="学生ID"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    sessions = svc.list_student_sessions(student_id, limit, offset)
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    sess = svc.get_session_by_id(session_id)
    if not sess:
        raise HTTPException(404, "会话不存在")
    return SessionResponse.model_validate(sess)


@router.post("/messages", response_model=MessageResponse)
def add_message(body: MessageCreate):
    # Service 层内部校验会话存在，Router 层不重复查询
    try:
        msg = svc.add_message(
            session_id=body.session_id,
            role=body.role,
            content=body.content,
            intent=body.intent,
            emotion_tag=body.emotion_tag,
            emotion_score=body.emotion_score,
            trigger_keywords=body.trigger_keywords,
            tokens_used=body.tokens_used,
            response_time_ms=body.response_time_ms,
        )
    except RuntimeError:
        raise HTTPException(404, "会话不存在")
    return MessageResponse.model_validate(msg)


@router.get("/messages", response_model=list[MessageResponse])
def list_messages(
    session_id: str = Query(..., description="会话ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    messages = svc.list_session_messages(session_id, limit, offset)
    return [MessageResponse.model_validate(m) for m in messages]
