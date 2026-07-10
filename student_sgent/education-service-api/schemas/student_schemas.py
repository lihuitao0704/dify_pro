"""
学生模块 Pydantic 请求/响应模型
用于 FastAPI 参数校验和 OpenAPI 文档自动生成
"""
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator


# ============================================================
# 学生基本信息
# ============================================================

class StudentProfile(BaseModel):
    """学生基本信息响应"""
    model_config = {"from_attributes": True}

    id: int
    union_id: str
    name: str | None = None
    grade: int | None = None
    target_country: str | None = None
    status: int


# ============================================================
# 请假申请
# ============================================================

class LeaveRequestCreate(BaseModel):
    """提交请假申请"""
    student_id: int = Field(..., description="学生ID")
    leave_type: int = Field(default=1, ge=1, le=3, description="1-病假 2-事假 3-其他")
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    reason: str | None = Field(None, max_length=255)
    attachment_url: str | None = Field(None, max_length=512)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class LeaveRequestApprove(BaseModel):
    """审批请假"""
    approver_id: int = Field(..., description="审批人ID")
    status: int = Field(..., ge=1, le=2, description="1-通过 2-驳回")
    approval_comment: str | None = Field(None, max_length=512)


class LeaveRequestResponse(BaseModel):
    """请假记录响应"""
    model_config = {"from_attributes": True}

    id: int
    student_id: int
    leave_type: int
    start_date: date
    end_date: date
    reason: str | None = None
    status: int
    approver_id: int | None = None
    approved_at: datetime | None = None
    created_at: datetime


# ============================================================
# 心理情绪记录
# ============================================================

class PsychRecordCreate(BaseModel):
    """记录情绪交互"""
    student_id: int = Field(..., description="学生ID")
    emotion_tag: str | None = Field(None, description="情绪标签，如：焦虑/平稳/低落")
    emotion_score: Decimal = Field(..., ge=-1.0, le=1.0, description="情绪分值 -1.0~1.0")
    interaction_content: str | None = Field(None, description="交互内容摘要")
    trigger_keywords: list[str] | None = Field(None, description="触发关键词")
    record_date: date = Field(..., description="记录日期")


class PsychAlertResponse(BaseModel):
    """心理预警响应"""
    model_config = {"from_attributes": True}

    id: int
    student_id: int
    trigger_rule_id: int
    risk_level: int
    trigger_evidence: str | None = None
    human_confirmed_status: int
    handler_id: int | None = None
    handled_at: datetime | None = None
    created_at: datetime


class PsychAlertUpdate(BaseModel):
    """处理预警"""
    handler_id: int = Field(..., description="老师ID")
    status: int = Field(..., ge=1, le=2, description="1-已确认 2-误报")
    follow_record: str | None = Field(None, description="跟进记录")


# ============================================================
# 售后反馈工单
# ============================================================

class FeedbackTicketCreate(BaseModel):
    """提交投诉/建议"""
    student_id: int = Field(..., description="学生ID")
    category: int = Field(..., ge=1, le=5, description="1-签证 2-文书 3-费用 4-生活 5-其他")
    priority: int = Field(default=2, ge=1, le=3, description="1-低 2-中 3-紧急")
    title: str | None = Field(None, max_length=255)
    content: str = Field(..., description="投诉/反馈内容")


class FeedbackTicketUpdate(BaseModel):
    """处理工单"""
    handler_id: int = Field(..., description="处理人ID")
    status: int = Field(..., ge=1, le=3, description="1-处理中 2-待复核 3-已关闭")
    solution: str | None = Field(None, description="解决方案")


class FeedbackTicketResponse(BaseModel):
    """工单响应"""
    model_config = {"from_attributes": True}

    id: int
    student_id: int
    category: int
    priority: int
    ai_summary: str | None = None
    status: int
    handler_id: int | None = None
    sla_deadline: datetime
    satisfaction_score: int | None = None
    closed_at: datetime | None = None
    created_at: datetime


# ============================================================
# DDL 提醒
# ============================================================

class DeadlineResponse(BaseModel):
    """DDL提醒响应"""
    model_config = {"from_attributes": True}

    id: int
    student_id: int
    event_type: int
    event_name: str
    deadline_time: datetime
    push_status: int
    push_at: datetime | None = None


# ============================================================
# 会话管理
# ============================================================

class SessionCreate(BaseModel):
    """创建会话"""
    student_id: int = Field(..., description="学生ID")
    agent_type: str | None = Field("student", description="Agent类型")


class SessionResponse(BaseModel):
    """会话响应"""
    model_config = {"from_attributes": True}

    id: int
    session_token: str
    student_id: int
    agent_type: str | None = None
    start_time: datetime
    message_count: int


# ============================================================
# 营销触达
# ============================================================

class MarketingTouchResponse(BaseModel):
    """营销触达记录"""
    model_config = {"from_attributes": True}

    id: int
    student_id: int
    program_id: str
    ai_generated_text: str | None = None
    user_clicked: int
    created_at: datetime


# ============================================================
# 通用响应
# ============================================================

class ApiResponse(BaseModel):
    """统一API响应"""
    code: int = 0
    msg: str = "success"
    data: object = None  # 使用 object 接受任意类型，不做限制


# ============================================================
# 学生更新
# ============================================================

class StudentUpdateRequest(BaseModel):
    """更新学生信息（JSON Body）"""
    name: str | None = None
    grade: int | None = None
    target_country: str | None = None
    status: int | None = None
    crm_customer_id: str | None = None
    edu_system_id: str | None = None


# ============================================================
# Dify 工具专用（JSON Body）
# ============================================================

class DifyLeaveSubmit(BaseModel):
    """Dify调用：提交请假"""
    student_id: int = Field(..., description="学生ID")
    leave_type: int = Field(default=1, ge=1, le=3, description="1-病假 2-事假 3-其他")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    reason: str = Field("", max_length=255)


class DifyEmotionRecord(BaseModel):
    """Dify调用：记录情绪"""
    student_id: int = Field(..., description="学生ID")
    emotion_score: float = Field(..., ge=-1.0, le=1.0, description="情绪分")
    emotion_tag: str = ""
    trigger_keywords: str = Field("", description="逗号分隔的关键词")
    interaction_content: str = ""
    record_date: str = Field("", description="YYYY-MM-DD，留空则今天")


class DifyFeedbackSubmit(BaseModel):
    """Dify调用：提交工单"""
    student_id: int = Field(..., description="学生ID")
    category: int = Field(..., ge=1, le=5, description="1-签证 2-文书 3-费用 4-生活 5-其他")
    title: str = ""
    content: str = Field(..., description="投诉/反馈内容")


class DifyInitSession(BaseModel):
    """Dify调用：初始化会话"""
    student_id: int = Field(..., description="学生ID")
    agent_type: str = Field("student", description="Agent类型")


class DifyTouchLog(BaseModel):
    """Dify调用：记录营销触达"""
    student_id: int = Field(..., description="学生ID")
    program_id: str = Field(..., description="推荐项目ID")
    text: str = Field("", description="推荐话术")


class DifyMessageLog(BaseModel):
    """Dify调用：记录消息"""
    session_id: int = Field(..., description="会话ID")
    role: int = Field(..., ge=1, le=3, description="1-用户 2-AI 3-系统")
    content: str = ""
    emotion_score: float | None = None
    cost_token: int | None = None
    llm_model: str = "deepseek"
