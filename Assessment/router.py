"""
画像评估 FastAPI 路由
========================
一个接口：
  POST /api/agent/assessment
  - 输入自然语言 → 大模型解析研判意图
  - 自动研判所有 project_id，单项目内规则得分和 >= 60 即通过
  - 结果写入 intention_diagnosis 表（不重复诊断）
  - 大模型润色为自然语言返回
"""

import logging
import re
from fastapi import APIRouter
from pydantic import BaseModel, Field
from openai import OpenAI

from Assessment.assessment import (
    parse_intent,
    run_targeted_assessment,
    polish_error_message,
    get_conn,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# evaluate_all 仅允许在这些关键词出现时使用（白名单，避免 LLM 误判为全量扫描）
_EVALUATE_ALL_KEYWORDS = ("全部", "所有", "所有用户", "全部用户", "所有人", "整体", "全员")


def _is_evaluate_all_query(query: str) -> bool:
    """输入是否明确表示要评估全部用户"""
    q = query.strip()
    return any(kw in q for kw in _EVALUATE_ALL_KEYWORDS)


def _filter_existing_users(names: list[str]) -> list[str]:
    """过滤出 user_profiles 中真实存在的用户名，去掉 LLM 幻觉"""
    if not names:
        return []
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            placeholders = ", ".join(["%s"] * len(names))
            cur.execute(
                f"SELECT name FROM user_profiles WHERE name IN ({placeholders})",
                names,
            )
            return [row["name"] for row in cur.fetchall()]
    finally:
        conn.close()


class AssessmentRequest(BaseModel):
    query: str = Field(
        ...,
        description="自然语言，如：'研判张三的用户信息'、'研判李四和王五'、'研判所有用户'",
        examples=["研判张三的用户信息", "研判所有用户"],
    )


@router.post("/assessment")
def assess(req: AssessmentRequest):
    """
    画像评估（自然语言输入）

    1. 大模型解析自然语言 → 确定要评估的目标用户
    2. 检查是否有重复诊断（有则返回"该用户已是意向客户"）
    3. 自动评估所有 project_id，单项目内规则得分和 >= 60 即通过
    4. 结果写入 intention_diagnosis 表
    5. 大模型润色为自然语言返回
    """
    try:
        # 1. 解析自然语言 → 目标用户筛选条件
        intent = parse_intent(req.query)
        logger.info(
            f"输入: {req.query!r} → 意图: {intent['intent_type']} | 目标: {intent.get('names', [])}"
        )

        # ── 安全拦截 A：evaluate_one 但没有识别出名字 ──
        if intent["intent_type"] == "evaluate_one" and not intent.get("names"):
            return {
                "code": 400,
                "msg": "invalid_request",
                "data": "未识别到具体的研判对象，请明确指定用户名，如「研判张三」",
            }

        # ── 安全拦截 B：evaluate_one 时，校验名字是否真正在数据库里 ──
        if intent["intent_type"] == "evaluate_one" and intent.get("names"):
            existing = _filter_existing_users(intent["names"])
            if not existing:
                return {
                    "code": 404,
                    "msg": "user_not_found",
                    "data": f"未找到用户 {intent['names']}，请检查姓名是否正确",
                }
            # 用真实存在的名字重建 sql_filter，丢弃 LLM 幻觉
            name_list = ", ".join(f"'{n}'" for n in existing)
            intent["sql_filter"] = f"`name` IN ({name_list})"
            intent["names"] = existing

        # ── 安全拦截 C：evaluate_all 仅允许白名单关键词触发 ──
        if intent["intent_type"] == "evaluate_all":
            if not _is_evaluate_all_query(req.query):
                # LLM 误判为全量，但输入里没有"全部/所有"等关键词 → 拒绝
                logger.warning(
                    f"LLM 误判 evaluate_all：输入={req.query!r} 无全量关键词，拒绝全量扫描"
                )
                return {
                    "code": 400,
                    "msg": "invalid_request",
                    "data": "未识别到具体的研判对象，请明确指定用户名，如「研判张三」；如需评估全部用户，请输入「研判所有用户」",
                }
            intent["sql_filter"] = ""  # 全部用户不限制

        # 2. 执行评估
        result = run_targeted_assessment(sql_filter=intent["sql_filter"])

        return {"code": 0, "msg": "success", "data": result}

    except ValueError as e:
        logger.warning(f"业务异常: {e}")
        return {"code": 409, "msg": "duplicate", "data": polish_error_message(str(e))}
    except Exception as e:
        logger.error(f"评估失败: {e}")
        return {"code": 500, "msg": "error", "data": polish_error_message(str(e))}
