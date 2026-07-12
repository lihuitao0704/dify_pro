"""
管理路由: GET /admin/kb-status, POST /admin/kb-reload, GET /admin/project-status
"""
import time
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


# ── ACT2026 项目进度（Phase 3: 性能调优 & 加固）──────────────────────
ACT2026_PROGRESS = {
    "project": "粤教留学 · 客服Agent (ACT2026)",
    "phase": "Phase 3",
    "phase_name": "性能调优 & 全链路加固",
    "version": "2.0.0",
    "overall_pct": 92,
    "milestones": [
        {"name": "基础架构（FastAPI + KB + 7意图）",   "pct": 100, "status": "done"},
        {"name": "三大外部服务桥接合并",               "pct": 100, "status": "done"},
        {"name": "多轮状态机 + 画像持久化 + 报名去重", "pct": 100, "status": "done"},
        {"name": "意图锁定 & 流程续写（flow-first）",  "pct": 100, "status": "done"},
        {"name": "管理后台 + 项目进度可视化",          "pct": 80,  "status": "doing"},
        {"name": "端到端压测 & 稳定性加固",           "pct": 70,  "status": "doing"},
    ],
    "kpis": {
        "intents_supported": 7,
        "kb_docs": 19,
        "kb_chunks": 112,
        "kb_faq_pairs": 86,
    },
    "health_checks": {
        "mysql": None,       # 延迟检测
        "llm": None,         # 延迟检测
    },
}

_health_cache = {"ts": 0.0, "data": None}


@router.get("/admin/project-status", summary="ACT2026 项目进度 + 健康状态")
def project_status():
    """返回项目里程碑进度和各依赖健康状态"""
    import time as _t
    now = _t.time()
    # 健康检测做简单缓存（10s），避免反复探测
    kb = get_kb()
    result = dict(ACT2026_PROGRESS)
    result["kpis"]["kb_chunks"] = len(kb.chunks)
    result["kpis"]["kb_faq_pairs"] = len(kb.faq_map)
    result["kpis"]["kb_docs"] = kb.doc_count

    cached = _health_cache["data"]
    if cached and (now - _health_cache["ts"]) < 10:
        result["health_checks"] = cached
        result["cached"] = True
        return result

    checks = {}
    # MySQL
    try:
        from customer_agent.db import get_db
        db = get_db()
        db.query("SELECT 1")
        checks["mysql"] = True
    except Exception:
        checks["mysql"] = False
    # LLM
    try:
        from customer_agent import llm as _llm
        checks["llm"] = _llm.is_online()
    except Exception:
        checks["llm"] = False

    _health_cache["ts"] = now
    _health_cache["data"] = checks
    result["health_checks"] = checks
    result["cached"] = False
    return result
