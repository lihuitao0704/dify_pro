"""
跨模块 HTTP 桥接
- study_abroad_agent(:5000) → 课程/用户画像/推荐
- Event&Lecture(:8011)      → 讲座/活动/报名
- Assessment(:8002)         → 用户画像研判/产品匹配
"""

import requests
from customer_agent.config import config


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


# ============================================================
# study_abroad_agent :5000
# ============================================================
def sa_recommend(conversation_id: str, timeout: float = None) -> dict:
    """课程推荐: GET /api/v1/profiles/recommend (POST)"""
    t = timeout or config.BRIDGE_TIMEOUT
    try:
        r = requests.post(
            _url(config.STUDY_ABROAD_URL, "/api/v1/profiles/recommend"),
            json={"conversation_id": conversation_id},
            timeout=t,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Bridge] recommend失败: {e}")
        return {"code": -1, "message": str(e), "data": None}


def sa_get_courses(country: str = "", category: str = "",
                   keyword: str = "", limit: int = 10) -> dict:
    """查询课程列表: GET /api/v1/courses"""
    try:
        r = requests.get(
            _url(config.STUDY_ABROAD_URL, "/api/v1/courses"),
            params={"country": country, "category": category,
                    "keyword": keyword, "limit": limit},
            timeout=config.BRIDGE_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Bridge] get_courses失败: {e}")
        return {"code": -1, "message": str(e), "data": []}


def sa_save_profile(payload: dict) -> dict:
    """保存/更新用户画像: POST /api/v1/profiles/upsert"""
    try:
        r = requests.post(
            _url(config.STUDY_ABROAD_URL, "/api/v1/profiles/upsert"),
            json=payload,
            timeout=config.BRIDGE_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Bridge] save_profile失败: {e}")
        return {"code": -1, "message": str(e), "data": None}


# ============================================================
# Event&Lecture :8011
# ============================================================
def event_query(nl_query: str) -> dict:
    """通过NL2SQL查询活动/讲座"""
    try:
        r = requests.post(
            _url(config.EVENT_LECTURE_URL, "/nl2sql"),
            json={"query": nl_query},
            timeout=config.BRIDGE_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Bridge] event_query失败: {e}")
        return {"query": nl_query, "result": {"type": "error",
                "message": str(e)}, "polished": "暂时查不到活动信息，请稍后重试"}


def event_register(nl_query: str) -> dict:
    """通过NL2SQL报名活动/讲座"""
    return event_query(nl_query)  # 同一接口，NL2SQL自动识别INSERT意图


# ============================================================
# Assessment 研判桥接 (port 8002)
# ============================================================
def assessment_evaluate(query: str) -> dict:
    """
    调用研判服务进行用户画像评估与产品匹配
    输入: 自然语言查询（如"研判张三"或"评估所有用户"）
    返回: 研判结果 + 产品推荐
    """
    try:
        r = requests.post(
            _url(config.ASSESSMENT_URL, "/api/agent/assessment"),
            json={"query": query},
            timeout=config.BRIDGE_TIMEOUT + 10,  # 研判需要更长时间
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"code": -1, "msg": f"研判服务暂时不可用: {e}", "data": None}


def resume_submit(data: dict) -> dict:
    """
    提交用户信息/简历到研判服务
    输入: resume/profile data dict (name, education, major, target_country, gpa, language_score, etc.)
    """
    try:
        r = requests.post(
            _url(config.ASSESSMENT_URL, "/api/agent/resume/add"),
            json=data,
            timeout=config.BRIDGE_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"code": -1, "msg": f"简历提交失败: {e}", "data": None}
