"""
管理路由: GET /admin/kb-status, POST /admin/kb-reload
"""

from fastapi import APIRouter
from customer_agent.knowledge import get_kb, reload_kb
from customer_agent.config import config

router = APIRouter()


@router.get("/admin/kb-status", summary="知识库状态")
def kb_status():
    kb = get_kb()
    return {
        "loaded": kb.is_loaded(),
        "chunks": len(kb.chunks),
        "faq_count": len(kb.faq_map),
        "doc_count": kb.doc_count,
        "knowledge_path": config.KNOWLEDGE_PATH,
    }


@router.post("/admin/kb-reload", summary="热加载知识库")
def kb_reload():
    kb = reload_kb()
    return {
        "code": 0,
        "message": "知识库已刷新",
        "chunks": len(kb.chunks),
        "faq_count": len(kb.faq_map),
    }
