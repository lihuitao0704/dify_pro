"""
customer_agent/services — 业务逻辑层

合并自 study_abroad_agent + Event & Lecture Registration：
  - courses.py        课程 CRUD (原 courses_service.py)
  - profiles.py       用户画像 CRUD + 完整性校验 (原 profile_service.py)
  - consultations.py 咨询记录 CRUD (原 consultation_service.py)
  - recommend.py      课程推荐打分引擎 (原 recommend_service.py)
  - nl2sql.py         统一 NL2SQL 引擎
                       覆盖 7 张表：user_profiles / courses / consultations
                                    lectures / activities /
                                    lecture_registrations / activity_registrations
"""

from customer_agent.services.recommend import RecommendService
from customer_agent.services.courses import CoursesService
from customer_agent.services.profiles import ProfileService
from customer_agent.services.consultations import ConsultationService
from customer_agent.services import nl2sql as NL2SQLService

__all__ = [
    "RecommendService",
    "CoursesService",
    "ProfileService",
    "ConsultationService",
    "NL2SQLService",
]


# ============================================================
# 本地业务调用适配器
# ============================================================
# 供 router.py / agent.py 使用，替代原来的 HTTP bridge 调用。
# 返回形状与旧 bridge.py 完全一致，Handler 代码无需修改。

def sa_get_courses(country: str = "", category: str = "",
                   keyword: str = "", limit: int = 10) -> dict:
    """查询课程列表 (本地版，替代 HTTP bridge)"""
    try:
        rows = CoursesService.list_courses(
            country=country, category=category, keyword=keyword, limit=limit,
        )
        return {"code": 0, "message": "success", "data": rows}
    except Exception as e:
        return {"code": -1, "message": str(e), "data": []}


def sa_save_profile(payload: dict) -> dict:
    """保存/更新用户画像 (本地版，替代 HTTP bridge)"""
    try:
        conversation_id = payload.get("conversation_id", "0")
        data = {k: v for k, v in payload.items() if k != "conversation_id"}
        profile = ProfileService.save_profile(conversation_id, data)
        return {"code": 0, "message": "success", "data": profile}
    except Exception as e:
        return {"code": -1, "message": str(e), "data": None}


def sa_recommend(conversation_id: str, timeout: float = None) -> dict:
    """基于画像的课程推荐 Top5 (本地版，替代 HTTP bridge)"""
    try:
        result = RecommendService.recommend(conversation_id)
        if result.get("success"):
            return {"code": 0, "message": "success", "data": result}
        return {"code": -1, "message": result.get("message", "推荐失败"), "data": None}
    except Exception as e:
        return {"code": -1, "message": str(e), "data": None}


def event_query(nl_query: str) -> dict:
    """通过直接 SQL + 可选 NL2SQL 增强 查询活动/讲座 (本地版，替代 HTTP bridge)。

    路径顺序（直查优先，LLM 增强）:
      1. 直接 SQL 查 lectures + activities（确定性最强，不依赖 LLM）
      2. LLM NL2SQL 仅作为增强路径（生成更精确的过滤 SQL，失败不影响主结果）
      3. 两者都无结果 → 返回 error 类型
    """
    import logging
    log = logging.getLogger(__name__)

    # ── 1. 主路径: 直接 SQL 查 lectures + activities（LLM 无关，最可靠）──
    rows = []
    try:
        rows = _fallback_event_list(nl_query)
    except Exception as e:
        log.error("[event_query] 主路径直查失败: %s", e)

    # ── 2. 增强路径: 尝试 LLM NL2SQL 做更精确的过滤/排序 ──
    # LLM 生成的 SQL 可能命中更精准的结果；失败时静默降级，不阻塞主路径。
    if not rows:
        try:
            result = NL2SQLService.run_nl2sql(
                question=nl_query, include_sql=True, polish=True,
            )
            if result.get("action") == "insert":
                return {
                    "query": nl_query,
                    "result": {"type": "dml", "message": "操作已执行"},
                    "polished": result.get("polished", "操作已执行"),
                }
            llm_rows = result.get("rows") or []
            if llm_rows:
                return {
                    "query": nl_query,
                    "result": {"type": "select", "data": llm_rows},
                    "polished": result.get("polished", ""),
                    "data": llm_rows,
                }
            log.info("[event_query] NL2SQL 无结果（多语句/解析失败等），保持主路径空结果")
        except Exception as e:
            # 真实报错打出来，方便排查；主路径已出结果，此处仅记录
            log.warning("[event_query] NL2SQL 增强路径失败（已降级）: %s", e)
            print(f"[event_query] NL2SQL 增强路径失败（已降级）: {e}")

    if rows:
        return {
            "query": nl_query,
            "result": {"type": "select", "data": rows},
            "polished": _format_events_readable(rows),
            "data": rows,
        }

    # ── 3. 两者都无结果 ──
    return {
        "query": nl_query,
        "result": {"type": "error", "message": "没有查询到相关记录"},
        "polished": "暂时查不到活动信息，请稍后重试",
    }


def event_register(nl_query: str) -> dict:
    """通过 NL2SQL 报名活动/讲座 (本地版，替代 HTTP bridge)。

    写操作必须走 LLM; LLM 失败则返回可操作的错误提示，不降级。
    """
    import logging
    log = logging.getLogger(__name__)
    try:
        result = NL2SQLService.run_nl2sql(
            question=nl_query, include_sql=True, polish=True,
        )
        return {
            "query": nl_query,
            "result": {"type": "dml", "message": "操作已执行"},
            "polished": result.get("polished", "操作已执行"),
        }
    except Exception as e:
        log.warning("[event_register] NL2SQL 报名失败: %s", e)
        return {
            "query": nl_query,
            "result": {"type": "error", "message": str(e)},
            "polished": f"报名失败：{e}\n建议直接电话微信联系顾问协助报名",
        }


# ── 降级用的直查函数 ──────────────────────────────────────────────────
def _fallback_event_list(nl_query: str) -> list:
    """LLM 失败时，把近期讲座+活动直接拉出来供展示。"""
    from customer_agent.db import get_db
    db = get_db()
    rows = []
    try:
        lectures = db.query(
            "SELECT 'lecture' AS kind, lecture_id AS id, title, "
            "event_time, location, speaker "
            "FROM lectures ORDER BY event_time DESC LIMIT 5"
        )
        rows.extend(lectures)
    except Exception:
        pass
    try:
        activities = db.query(
            "SELECT 'activity' AS kind, activity_id AS id, title, "
            "event_time, location, '' AS speaker "
            "FROM activities ORDER BY event_time DESC LIMIT 5"
        )
        rows.extend(activities)
    except Exception:
        pass
    return rows


def _format_events_readable(rows: list) -> str:
    if not rows:
        return "暂时查不到活动信息，请稍后重试"
    lines = ["为您找到以下活动和讲座：\n"]
    for i, r in enumerate(rows, 1):
        kind = "讲座" if r.get("kind") == "lecture" else "活动"
        lines.append(
            f"{i}. 【{kind}】{r.get('title', '')}\n"
            f"   时间: {r.get('event_time', '待定')} | 地点: {r.get('location', '待定')}"
            + (f" | 主讲: {r['speaker']}" if r.get("speaker") else "")
        )
    # 注意：CTA 由调用方 handle_activity 统一追加，避免重复
    return "\n".join(lines)
