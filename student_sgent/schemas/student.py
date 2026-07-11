"""
学生模块 Pydantic 数据模型

定义请求体和响应体的数据结构，与 SQLAlchemy 模型一一对应。
所有 datetime 字段使用 ISO 8601 字符串格式。
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ============================================================
# 会话相关
# ============================================================

class SessionCreate(BaseModel):
    """创建会话"""
    student_id: int = Field(..., description="学生ID")
    session_id: Optional[str] = Field(None, description="自定义会话ID（不填则自动生成）")


class SessionResponse(BaseModel):
    """会话响应"""
    id: int
    session_id: str
    student_id: int
    status: str
    last_message_time: Optional[datetime] = None
    message_count: int = 0
    close_time: Optional[datetime] = None
    create_time: datetime

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    """创建消息"""
    session_id: str = Field(..., description="关联会话ID")
    role: str = Field(..., description="消息角色：user / assistant / system")
    content: str = Field(..., description="消息内容")
    intent: Optional[str] = Field(None, description="AI识别意图")
    emotion_tag: Optional[str] = Field(None, description="情绪标签")
    emotion_score: Optional[int] = Field(None, ge=0, le=100, description="情绪分值")
    trigger_keywords: Optional[list] = Field(None, description="触发关键词")
    tokens_used: Optional[int] = None
    response_time_ms: Optional[int] = None


class MessageResponse(BaseModel):
    """消息响应"""
    id: int
    session_id: str
    role: str
    content: str
    intent: Optional[str] = None
    emotion_tag: Optional[str] = None
    emotion_score: Optional[int] = None
    trigger_keywords: Optional[list] = None
    response_time_ms: Optional[int] = None
    create_time: datetime

    model_config = {"from_attributes": True}


# ============================================================
# 心理相关
# ============================================================

class EmotionProfileResponse(BaseModel):
    """心理画像响应"""
    id: int
    student_id: int
    latest_emotion_tag: Optional[str] = None
    emotion_score: Optional[int] = None
    risk_level: str
    emotion_history: Optional[list] = None
    last_interaction_time: Optional[datetime] = None
    update_time: datetime
    create_time: datetime

    model_config = {"from_attributes": True}


class RiskInterventionCreate(BaseModel):
    """创建预警"""
    student_id: int
    source_message_id: Optional[int] = None
    trigger_reason: str
    risk_level: str = "medium"
    risk_tags: Optional[list] = None


class RiskInterventionUpdate(BaseModel):
    """更新预警"""
    status: Optional[str] = None
    teacher_id: Optional[int] = None
    follow_record: Optional[str] = None
    risk_tags: Optional[list] = None


class RiskInterventionResponse(BaseModel):
    """预警响应"""
    id: int
    student_id: int
    source_message_id: Optional[int] = None
    trigger_reason: str
    risk_tags: Optional[list] = None
    risk_level: str
    status: str
    teacher_id: Optional[int] = None
    follow_record: Optional[str] = None
    resolved_time: Optional[datetime] = None
    update_time: datetime
    create_time: datetime

    model_config = {"from_attributes": True}


# ============================================================
# 工单相关
# ============================================================

class FeedbackTicketCreate(BaseModel):
    """创建工单"""
    student_id: int
    ticket_type: str = "complaint"
    category: Optional[str] = None
    title: Optional[str] = None
    content: str
    detail: Optional[str] = None
    priority: str = "medium"


class FeedbackTicketUpdate(BaseModel):
    """更新工单"""
    status: Optional[str] = None
    assignee_id: Optional[int] = None
    solution: Optional[str] = None
    satisfaction: Optional[int] = Field(None, ge=1, le=5)
    is_notified: Optional[bool] = None
    priority: Optional[str] = None


class FeedbackTicketResponse(BaseModel):
    """工单响应"""
    id: int
    student_id: int
    ticket_type: str
    category: Optional[str] = None
    title: Optional[str] = None
    content: str
    detail: Optional[str] = None
    status: str
    priority: str
    assignee_id: Optional[int] = None
    solution: Optional[str] = None
    satisfaction: Optional[int] = None
    is_notified: bool
    resolved_time: Optional[datetime] = None
    create_time: datetime
    update_time: datetime

    model_config = {"from_attributes": True}


# ============================================================
# 学业相关
# ============================================================

class AcademicScheduleCreate(BaseModel):
    """创建日程"""
    student_id: int
    schedule_type: str = "course"
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    is_recurring: bool = False
    reminder_enabled: bool = True
    reminder_minutes: Optional[int] = None


class AcademicScheduleResponse(BaseModel):
    """日程响应"""
    id: int
    student_id: int
    schedule_type: str
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    is_recurring: bool
    reminder_enabled: bool
    reminder_minutes: Optional[int] = None
    status: str
    create_time: datetime
    update_time: datetime

    model_config = {"from_attributes": True}


class DeadlineReminderCreate(BaseModel):
    """创建提醒"""
    student_id: Optional[int] = None
    deadline_type: str = "other"
    title: str
    description: Optional[str] = None
    deadline: datetime
    reminder_days: Optional[list] = None
    related_schedule_id: Optional[int] = None


class DeadlineReminderResponse(BaseModel):
    """提醒响应"""
    id: int
    student_id: Optional[int] = None
    deadline_type: str
    title: str
    description: Optional[str] = None
    deadline: datetime
    reminder_days: Optional[list] = None
    reminder_enabled: bool
    related_schedule_id: Optional[int] = None
    status: str
    create_time: datetime
    update_time: datetime

    model_config = {"from_attributes": True}


# ============================================================
# 留学相关
# ============================================================

class StudyIntentionCreate(BaseModel):
    """创建升学意向"""
    student_id: int
    target_country: Optional[str] = None
    target_school: Optional[str] = None
    target_major: Optional[str] = None
    education_level: Optional[str] = None
    expected_enroll_time: Optional[str] = None
    budget_range: Optional[str] = None
    language_score: Optional[str] = None
    priority: int = 0


class StudyIntentionResponse(BaseModel):
    """升学意向响应"""
    id: int
    student_id: int
    target_country: Optional[str] = None
    target_school: Optional[str] = None
    target_major: Optional[str] = None
    education_level: Optional[str] = None
    expected_enroll_time: Optional[str] = None
    budget_range: Optional[str] = None
    language_score: Optional[str] = None
    status: str
    priority: int
    create_time: datetime
    update_time: datetime

    model_config = {"from_attributes": True}


class StudentApplicationCreate(BaseModel):
    """创建申请进度"""
    student_id: int
    intention_id: Optional[int] = None
    target_school: str
    target_country: Optional[str] = None
    target_major: Optional[str] = None
    stage: str = "document_prep"
    progress_detail: Optional[str] = None
    deadline: Optional[datetime] = None
    next_action: Optional[str] = None
    handler_id: Optional[int] = None


class StudentApplicationResponse(BaseModel):
    """申请进度响应"""
    id: int
    student_id: int
    intention_id: Optional[int] = None
    target_country: Optional[str] = None
    target_school: str
    target_major: Optional[str] = None
    stage: str
    progress_detail: Optional[str] = None
    deadline: Optional[datetime] = None
    next_action: Optional[str] = None
    handler_id: Optional[int] = None
    status: str
    create_time: datetime
    update_time: datetime

    model_config = {"from_attributes": True}


# ============================================================
# NL2SQL 相关
# ============================================================

class NL2SQLRequest(BaseModel):
    """自然语言查询请求"""
    query: str = Field(..., description="自然语言查询，如 '查询我的最近对话' '查看申请进度'")
    student_id: Optional[int] = Field(None, description="当前学生ID（用于权限过滤）")
    use_template: bool = Field(True, description="优先使用预设模板匹配")


class NL2SQLResponse(BaseModel):
    """NL2SQL 查询响应"""
    natural_query: str = Field(..., description="原始自然语言查询")
    generated_sql: str = Field(..., description="生成的 SQL 语句")
    matched_template: Optional[str] = Field(None, description="匹配的预设模板名称（如果使用模板）")
    data: list = Field(default_factory=list, description="查询结果数据")
    row_count: int = Field(0, description="结果行数")
    elapsed_ms: float = Field(0, description="查询耗时（毫秒）")
