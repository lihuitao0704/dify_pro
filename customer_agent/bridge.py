"""
跨模块 HTTP 桥接

当前仅桥接研判服务 Assessment(:8002)。
课程推荐、活动讲座报名的桥接已于 v2.0 合并到 customer_agent/services/，
直接本地调用 study abroad 与 Event&Lecture 的业务逻辑，
不再走 HTTP 桥接。
"""

import requests

from customer_agent.config import config


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


# ============================================================
# Assessment 研判桥接 (port 8002) — 仍保持 HTTP 桥接
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
