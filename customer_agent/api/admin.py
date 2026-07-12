"""
管理路由: GET /admin/kb-status, POST /admin/kb-reload
需 Bearer Token 鉴权，仅员工/管理者可访问
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from customer_agent.knowledge import get_kb, reload_kb
from customer_agent.config import config

router = APIRouter()

OPERATOR_ROLES = ("员工", "管理者")


def _require_employee(request: Request) -> bool:
    """校验是否为员工角色"""
    user_type = getattr(request.state, "auth_user_type", "")
    return user_type in OPERATOR_ROLES


@router.get("/admin/kb-status", summary="知识库状态")
def kb_status(request: Request):
    if not _require_employee(request):
        return JSONResponse({"error": "仅员工可访问管理功能"}, status_code=403)
    kb = get_kb()
    return {
        "loaded": kb.is_loaded(),
        "chunks": len(kb.chunks),
        "faq_count": len(kb.faq_map),
        "doc_count": kb.doc_count,
        "knowledge_path": config.KNOWLEDGE_PATH,
    }


@router.post("/admin/kb-reload", summary="热加载知识库")
def kb_reload(request: Request):
    if not _require_employee(request):
        return JSONResponse({"error": "仅员工可访问管理功能"}, status_code=403)
    kb = reload_kb()
    return {
        "code": 0,
        "message": "知识库已刷新",
        "chunks": len(kb.chunks),
        "faq_count": len(kb.faq_map),
    }
