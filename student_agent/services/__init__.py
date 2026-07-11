"""
学生智能助手 — 业务逻辑层服务包

包含 7 个服务模块，从 agent.py 中提取的业务逻辑：
  - emotion_service:   情绪分析、心理画像管理、心理预警
  - leave_service:     请假处理（参数收集、提交、状态查询）
  - feedback_service:  投诉/反馈工单（创建、查询、SLA管理）
  - academic_service:  学业考务（日程查询、申请进度追踪）
  - upgrade_service:   增值转化意向（识别、冷却检查、推荐生成）
  - nl2sql_service:    自然语言查库（模板引擎优先 + LLM 兜底 + 安全校验）

使用方式：
  from student_agent.services import emotion_service
  result = emotion_service.analyze_and_update(student_id, emotion_result, message)
"""

from . import emotion_service
from . import leave_service
from . import feedback_service
from . import academic_service
from . import upgrade_service
from . import nl2sql_service

__all__ = [
    "emotion_service",
    "leave_service",
    "feedback_service",
    "academic_service",
    "upgrade_service",
    "nl2sql_service",
]
