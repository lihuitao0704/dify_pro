"""
画像评估 FastAPI 路由
========================
一个接口：
  POST /api/agent/assessment
  - 输入自然语言 → 大模型解析研判意图
  - 自动研判所有 project_id，单项目内规则得分和 >= 80 即通过
  - 结果写入 intention_diagnosis 表（不重复诊断）
  - 大模型润色为自然语言返回
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel, Field
from openai import OpenAI

from Assessment.assessment import (
    parse_intent,
    run_targeted_assessment,
    polish_error_message,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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
    3. 自动评估所有 project_id，单项目内规则得分和 >= 80 即通过
    4. 结果写入 intention_diagnosis 表
    5. 大模型润色为自然语言返回
    """
    try:
        # 1. 解析自然语言 → 目标用户筛选条件
        intent = parse_intent(req.query)
        logger.info(
            f"输入: {req.query} → 意图: {intent['intent_type']} | 目标: {intent.get('names', [])}"
        )

        if not intent["sql_filter"] and intent["intent_type"] == "evaluate_all":
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
