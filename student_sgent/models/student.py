"""
学生智能助手模块 — 全部 9 张表 SQLAlchemy 模型定义

数据库：hambaki_3
学生ID 关联：test.students 表的 student_id

表清单：
    1.  ConversationSession    — 学生会话主表
    2.  ConversationMessage    — 消息明细表
    3.  EmotionProfileSnapshot — 心理画像表（一人一条当前快照）
    4.  RiskIntervention       — 心理预警表
    5.  FeedbackTicket         — 投诉工单表
    6.  AcademicSchedule       — 学业日程表
    7.  DeadlineReminder       — 考务提醒表
    8.  StudyIntention         — 升学意向表
    9.  StudentApplication     — 留学申请进度追踪表

设计原则：
    - 不使用 SQLAlchemy relationship（避免隐式 JOIN，业务关联在 Service 层做显式查询）
    - Python Enum 统一管理枚举值，同名类型跨表复用
    - 时间字段使用数据库侧 CURRENT_TIMESTAMP，保证多源写入一致性
    - 布尔字段使用 Boolean 而非 SmallInteger/Integer

注意：
    - 当前仅定义模型结构，不会自动建表
    - 所有表通过 student_id 与 test.students 表的 id 做业务关联
"""

from enum import Enum as PyEnum

from datetime import datetime

from sqlalchemy import (
    BigInteger, Column, Integer, String, Text,
    Date, DateTime, Enum as SAEnum, JSON, Index, Boolean,
    CheckConstraint, text,
)

from models import Base


# ============================================================
# 通用时间列工厂（基础设施代码，放在最前面）
# ============================================================

def _create_time_column():
    """
    创建 create_time 列。Python default + MySQL server_default 双重保障：
    Python 侧 flush 后立即可读（pymysql 不支持 RETURNING），
    MySQL 侧做直接 INSERT 时的兜底。
    """
    return Column(
        DateTime, nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="创建时间"
    )


def _update_time_column():
    """
    创建 update_time 列。Python default/onupdate + MySQL 双重保障。
    """
    return Column(
        DateTime, nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
        comment="更新时间"
    )


# ============================================================
# Python 枚举类定义（统一管理，跨表复用）
# ============================================================

class SessionStatusEnum(str, PyEnum):
    """会话状态"""
    ACTIVE = "active"
    CLOSED = "closed"
    TIMEOUT = "timeout"


class MessageRoleEnum(str, PyEnum):
    """消息角色"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class RiskLevelEnum(str, PyEnum):
    """风险等级（心理画像 + 心理预警 共用）"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InterventionStatusEnum(str, PyEnum):
    """心理预警处理状态"""
    PENDING = "pending"
    FOLLOWING = "following"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class TicketTypeEnum(str, PyEnum):
    """工单类型"""
    COMPLAINT = "complaint"
    SUGGESTION = "suggestion"
    CONSULT = "consult"


class TicketStatusEnum(str, PyEnum):
    """工单处理状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    CLOSED = "closed"


class PriorityEnum(str, PyEnum):
    """优先级（投诉工单 等共用）"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ScheduleTypeEnum(str, PyEnum):
    """学业日程类型"""
    COURSE = "course"
    EXAM = "exam"
    TASK = "task"
    PERSONAL = "personal"


class ScheduleStatusEnum(str, PyEnum):
    """学业日程状态"""
    PENDING = "pending"
    DONE = "done"
    CANCELLED = "cancelled"


class DeadlineTypeEnum(str, PyEnum):
    """DDL 类型"""
    PAPER = "paper"
    EXAM = "exam"
    APPLICATION = "application"
    VISA = "visa"
    OTHER = "other"


class DeadlineStatusEnum(str, PyEnum):
    """DDL 状态"""
    PENDING = "pending"
    REMINDED = "reminded"
    DONE = "done"
    MISSED = "missed"


class IntentionStatusEnum(str, PyEnum):
    """升学意向状态"""
    ACTIVE = "active"
    FROZEN = "frozen"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ApplicationStageEnum(str, PyEnum):
    """留学申请阶段"""
    DOCUMENT_PREP = "document_prep"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    OFFER_RECEIVED = "offer_received"
    VISA_PROCESSING = "visa_processing"
    ENROLLED = "enrolled"


class ApplicationStatusEnum(str, PyEnum):
    """留学申请状态"""
    ONGOING = "ongoing"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ============================================================
# 1. 学生会话主表
# ============================================================

class ConversationSession(Base):
    """
    学生会话主表

    记录学生会话的元信息，每个学生可有多条会话记录。
    通过 session_id（VARCHAR）与 ConversationMessage 做业务关联。
    """

    __tablename__ = "conversation_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # === 核心业务字段 ===
    session_id = Column(
        String(64), nullable=False, unique=True,
        comment="会话唯一标识"
    )
    student_id = Column(
        BigInteger, nullable=False,
        comment="学生ID（必填，仅记录学生）"
    )
    status = Column(
        SAEnum(SessionStatusEnum),
        nullable=False, default=SessionStatusEnum.ACTIVE,
        comment="会话状态：active=活跃 / closed=已关闭 / timeout=超时"
    )

    # === 时间字段 ===
    last_message_time = Column(DateTime, nullable=True, comment="最后消息时间")
    message_count = Column(Integer, nullable=False, default=0, comment="消息总数（冗余计数器，避免频繁COUNT）")
    close_time = Column(DateTime, nullable=True, comment="会话关闭时间")
    create_time = _create_time_column()

    # === 索引定义 ===
    __table_args__ = (
        Index("idx_session_student", "student_id"),
        Index("idx_session_status", "status"),
        {"comment": "学生会话主表"}
    )

    def __repr__(self):
        return (
            f"<ConversationSession("
            f"id={self.id}, student_id={self.student_id}, "
            f"status={self.status})>"
        )


# ============================================================
# 2. 消息明细表
# ============================================================

class ConversationMessage(Base):
    """
    消息明细表

    记录每条会话中的具体消息，包含 AI 意图识别和情绪分析结果。
    情绪字段（emotion_tag / emotion_score / trigger_keywords）是
    心理预警自动触发的数据来源。

    自动触发规则（在应用层实现）：
        emotion_score < 30 或 trigger_keywords 含高危词 → 自动创建 RiskIntervention
    """

    __tablename__ = "conversation_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # === 核心业务字段 ===
    session_id = Column(
        String(64), nullable=False,
        comment="关联会话ID（conversation_sessions.session_id）"
    )
    role = Column(
        SAEnum(MessageRoleEnum), nullable=False,
        comment="消息角色：user=学生 / assistant=AI / system=系统"
    )
    content = Column(Text, nullable=False, comment="消息内容")

    # === AI 分析结果 ===
    intent = Column(String(64), nullable=True, comment="AI识别意图（业务查询/政策咨询/闲聊等）")
    emotion_tag = Column(String(64), nullable=True, comment="情绪标签（焦虑/平稳/低落/愤怒等）")
    emotion_score = Column(Integer, nullable=True, comment="情绪分值 0-100，越高越积极")
    trigger_keywords = Column(JSON, nullable=True, comment="AI提取触发关键词（JSON数组）")

    # === 性能统计 ===
    tokens_used = Column(Integer, nullable=True, comment="消耗Token数")
    response_time_ms = Column(Integer, nullable=True, comment="响应耗时（毫秒）")

    # === 时间字段 ===
    create_time = _create_time_column()

    # === 索引与约束 ===
    __table_args__ = (
        Index("idx_msg_session", "session_id"),
        Index("idx_msg_intent", "intent"),
        Index("idx_msg_emotion", "emotion_tag"),
        Index("idx_msg_create_time", "create_time"),
        CheckConstraint(
            "emotion_score >= 0 AND emotion_score <= 100",
            name="ck_msg_emotion_score_range"
        ),
        {"comment": "消息明细表"}
    )

    def __repr__(self):
        return (
            f"<ConversationMessage("
            f"id={self.id}, session_id={self.session_id}, "
            f"role={self.role}, emotion_tag={self.emotion_tag})>"
        )


# ============================================================
# 3. 心理画像表
# ============================================================

class EmotionProfileSnapshot(Base):
    """
    心理画像表（一人一条当前快照）

    记录学生当前心理状态，student_id 唯一。
    每次情绪交互后更新 latest_emotion_tag / emotion_score / risk_level。
    emotion_history 以 JSON 数组存储历史波动数据，用于周报分析。

    注意：
        这不是历史版本表！历史明细存在 ConversationMessage.emotion_* 字段。
        本表只保存「当前最新」快照，update_time 即最后刷新时间。
    """

    __tablename__ = "emotion_profile_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # === 核心业务字段 ===
    student_id = Column(
        BigInteger, nullable=False, unique=True,
        comment="学生ID（唯一，一人一条）"
    )
    latest_emotion_tag = Column(String(64), nullable=True, comment="最新情绪标签（焦虑/平稳/低落等）")
    emotion_score = Column(Integer, nullable=True, comment="情绪分值 0-100，越高越积极")
    risk_level = Column(
        SAEnum(RiskLevelEnum),
        nullable=False, default=RiskLevelEnum.LOW,
        comment="风险等级"
    )
    emotion_history = Column(
        JSON, nullable=True,
        comment="历史情绪波动数据（JSON数组，如 [{'tag':'焦虑','score':35,'date':'2026-07-01'}]）"
    )

    # === 时间字段 ===
    last_interaction_time = Column(DateTime, nullable=True, comment="最近一次交互时间")
    update_time = _update_time_column()
    create_time = _create_time_column()

    # === 索引定义 ===
    __table_args__ = (
        Index("idx_profile_risk", "risk_level"),
        {"comment": "心理画像表（一人一条当前快照）"}
    )

    def __repr__(self):
        return (
            f"<EmotionProfileSnapshot("
            f"student_id={self.student_id}, "
            f"tag={self.latest_emotion_tag}, "
            f"score={self.emotion_score}, risk={self.risk_level})>"
        )


# ============================================================
# 4. 心理预警表
# ============================================================

class RiskIntervention(Base):
    """
    心理预警表

    自动触发规则（在应用层实现）：
        - emotion_score < 30 或 trigger_keywords 含高危词（"绝望""轻生"等）
        → 自动创建一条预警记录，推送给班主任

    状态流转：
        pending → following（老师接手）→ resolved（已解除）/ dismissed（已忽略）
    """

    __tablename__ = "risk_interventions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # === 核心业务字段 ===
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    source_message_id = Column(
        BigInteger, nullable=True,
        comment="关联触发消息ID（conversation_messages.id）"
    )
    trigger_reason = Column(Text, nullable=False, comment="触发原因（AI提取关键词或原句）")
    risk_tags = Column(JSON, nullable=True, comment="风险标签数组，如 ['失眠','学业压力','人际关系']")
    risk_level = Column(
        SAEnum(RiskLevelEnum),
        nullable=False, default=RiskLevelEnum.MEDIUM,
        comment="风险等级"
    )
    status = Column(
        SAEnum(InterventionStatusEnum),
        nullable=False, default=InterventionStatusEnum.PENDING,
        comment="处理状态：pending=待处理 / following=跟进中 / resolved=已解除 / dismissed=已忽略"
    )

    # === 处理人信息 ===
    teacher_id = Column(BigInteger, nullable=True, comment="负责跟进老师ID")
    follow_record = Column(Text, nullable=True, comment="跟进记录")

    # === 时间字段 ===
    resolved_time = Column(DateTime, nullable=True, comment="解除时间")
    update_time = _update_time_column()
    create_time = _create_time_column()

    # === 索引定义 ===
    __table_args__ = (
        Index("idx_intervention_student", "student_id"),
        Index("idx_intervention_risk", "risk_level"),
        Index("idx_intervention_status", "status"),
        Index("idx_intervention_teacher", "teacher_id"),
        {"comment": "心理预警表"}
    )

    def __repr__(self):
        return (
            f"<RiskIntervention("
            f"id={self.id}, student_id={self.student_id}, "
            f"risk={self.risk_level}, status={self.status})>"
        )


# ============================================================
# 5. 投诉工单表
# ============================================================

class FeedbackTicket(Base):
    """
    投诉工单表

    学生提交投诉/建议/咨询工单，支持指派处理和满意度评价。

    状态流转：
        pending → processing（指派处理人）→ resolved（已解决）→ closed（学生确认关闭）

    升级机制（应用层实现）：
        超过 3 天未处理 → auto_escalate 提升 priority
    """

    __tablename__ = "feedback_tickets"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # === 核心业务字段 ===
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    ticket_type = Column(
        SAEnum(TicketTypeEnum),
        nullable=False, default=TicketTypeEnum.COMPLAINT,
        comment="工单类型：complaint=投诉 / suggestion=建议 / consult=咨询"
    )
    category = Column(String(64), nullable=True, comment="分类（签证办理/院校申请/生活服务/其他）")
    title = Column(String(255), nullable=True, comment="工单标题")
    content = Column(Text, nullable=False, comment="反馈内容摘要")
    detail = Column(Text, nullable=True, comment="详细描述")

    # === 流程控制字段 ===
    status = Column(
        SAEnum(TicketStatusEnum),
        nullable=False, default=TicketStatusEnum.PENDING,
        comment="处理状态"
    )
    priority = Column(
        SAEnum(PriorityEnum),
        nullable=False, default=PriorityEnum.MEDIUM,
        comment="优先级"
    )
    assignee_id = Column(BigInteger, nullable=True, comment="指派处理人ID")

    # === 处理结果 ===
    solution = Column(Text, nullable=True, comment="最终解决方案")
    satisfaction = Column(Integer, nullable=True, comment="满意度评分（1-5星）")
    is_notified = Column(Boolean, nullable=False, default=False, comment="是否已通知学生")

    # === 时间字段 ===
    resolved_time = Column(DateTime, nullable=True, comment="实际解决/关闭时间")
    update_time = _update_time_column()
    create_time = _create_time_column()

    # === 索引与约束 ===
    __table_args__ = (
        Index("idx_ticket_student", "student_id"),
        Index("idx_ticket_status", "status"),
        Index("idx_ticket_category", "category"),
        Index("idx_ticket_assignee", "assignee_id"),
        CheckConstraint(
            "satisfaction >= 1 AND satisfaction <= 5",
            name="ck_ticket_satisfaction_range"
        ),
        {"comment": "投诉工单表"}
    )

    def __repr__(self):
        return (
            f"<FeedbackTicket("
            f"id={self.id}, student_id={self.student_id}, "
            f"type={self.ticket_type}, status={self.status})>"
        )


# ============================================================
# 6. 学业日程表
# ============================================================

class AcademicSchedule(Base):
    """
    学业日程表

    学生个人日程管理，支持课程、考试、任务、个人事务四种类型。
    related_schedule_id 可被 deadline_reminders 反向引用。

    提醒粒度：分钟级（reminder_minutes），适合当天内的日程提醒。
    中长期截止日期预警请使用 DeadlineReminder（天数级）。
    """

    __tablename__ = "academic_schedules"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # === 核心业务字段 ===
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    schedule_type = Column(
        SAEnum(ScheduleTypeEnum),
        nullable=False, default=ScheduleTypeEnum.COURSE,
        comment="日程类型：course=课程 / exam=考试 / task=任务 / personal=个人"
    )
    title = Column(String(255), nullable=False, comment="日程标题")
    description = Column(Text, nullable=True, comment="日程描述")

    # === 时间相关 ===
    start_time = Column(DateTime, nullable=False, comment="开始时间")
    end_time = Column(DateTime, nullable=True, comment="结束时间")
    location = Column(String(255), nullable=True, comment="地点/线上链接")

    # === 周期与提醒 ===
    is_recurring = Column(Boolean, nullable=False, default=False, comment="是否周期性")
    reminder_enabled = Column(Boolean, nullable=False, default=True, comment="是否开启提醒")
    reminder_minutes = Column(
        Integer, nullable=True,
        comment="提前提醒分钟数（如 30 表示提前30分钟提醒）"
    )

    # === 状态与时间 ===
    status = Column(
        SAEnum(ScheduleStatusEnum),
        nullable=False, default=ScheduleStatusEnum.PENDING,
        comment="状态：pending=待办 / done=已完成 / cancelled=已取消"
    )
    update_time = _update_time_column()
    create_time = _create_time_column()

    # === 索引定义 ===
    __table_args__ = (
        Index("idx_schedule_student", "student_id"),
        Index("idx_schedule_start", "start_time"),
        Index("idx_schedule_status", "status"),
        Index("idx_schedule_type", "schedule_type"),
        {"comment": "学业日程表"}
    )

    def __repr__(self):
        return (
            f"<AcademicSchedule("
            f"id={self.id}, student_id={self.student_id}, "
            f"type={self.schedule_type}, title={self.title})>"
        )


# ============================================================
# 7. 考务提醒表
# ============================================================

class DeadlineReminder(Base):
    """
    考务提醒表

    记录学生关键学业节点（论文DDL、考试时间、申请截止、签证到期等）。
    支持通用提醒（student_id=NULL，适用于全量学生）和个人提醒。

    提醒粒度：天数级（reminder_days），适合中长期的截止日期预警。
    当天内的即时提醒请使用 AcademicSchedule（分钟级）。

    查询示例（未来7天到期）：
        WHERE deadline BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 7 DAY)
        AND status = 'pending'
        ORDER BY deadline ASC
    """

    __tablename__ = "deadline_reminders"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # === 核心业务字段 ===
    student_id = Column(
        BigInteger, nullable=True,
        comment="学生ID（NULL=通用提醒，适用于所有学生）"
    )
    related_schedule_id = Column(
        BigInteger, nullable=True,
        comment="关联学业日程ID（academic_schedules.id）"
    )
    deadline_type = Column(
        SAEnum(DeadlineTypeEnum),
        nullable=False, default=DeadlineTypeEnum.OTHER,
        comment="DDL类型：paper=论文 / exam=考试 / application=申请 / visa=签证 / other=其他"
    )
    title = Column(String(255), nullable=False, comment="节点名称")
    description = Column(Text, nullable=True, comment="描述")

    # === 时间与提醒 ===
    deadline = Column(DateTime, nullable=False, comment="截止时间")
    reminder_days = Column(
        JSON, nullable=True,
        comment="提前提醒天数配置，如 [7, 3, 1] 表示提前7天/3天/1天各提醒一次"
    )
    reminder_enabled = Column(Boolean, nullable=False, default=True, comment="是否开启提醒")

    # === 状态与时间 ===
    status = Column(
        SAEnum(DeadlineStatusEnum),
        nullable=False, default=DeadlineStatusEnum.PENDING,
        comment="状态：pending=待提醒 / reminded=已提醒 / done=已完成 / missed=已错过"
    )
    update_time = _update_time_column()
    create_time = _create_time_column()

    # === 索引定义 ===
    __table_args__ = (
        Index("idx_deadline_student", "student_id"),
        Index("idx_deadline_time", "deadline"),
        Index("idx_deadline_status", "status"),
        Index("idx_deadline_type", "deadline_type"),
        {"comment": "考务提醒表"}
    )

    def __repr__(self):
        return (
            f"<DeadlineReminder("
            f"id={self.id}, student_id={self.student_id}, "
            f"type={self.deadline_type}, deadline={self.deadline})>"
        )


# ============================================================
# 8. 升学意向表
# ============================================================

class StudyIntention(Base):
    """
    升学意向表

    学生留学目标清单，记录意向国家、院校、专业、学历层次、预算等信息。
    与 StudentApplication 的关联通过 intention_id 在应用层做显式 JOIN 查询。

    优先级规则：
        priority 越小越优先，0 为最高优先级
    """

    __tablename__ = "study_intentions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # === 核心业务字段 ===
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    target_country = Column(
        String(128), nullable=True,
        comment="目标国家（多值逗号分隔，如 英国,澳大利亚）"
    )
    target_school = Column(String(128), nullable=True, comment="目标院校")
    target_major = Column(String(128), nullable=True, comment="目标专业")

    # === 背景要求 ===
    education_level = Column(String(64), nullable=True, comment="目标学历（本科/硕士/博士等）")
    expected_enroll_time = Column(String(32), nullable=True, comment="预期入学时间（如 2027-09）")
    budget_range = Column(String(64), nullable=True, comment="预算范围（如 30-50万）")
    language_score = Column(String(64), nullable=True, comment="语言成绩要求（如 雅思6.5/托福90）")

    # === 排序与状态 ===
    priority = Column(Integer, nullable=False, default=0, comment="优先级（越小越优先）")
    status = Column(
        SAEnum(IntentionStatusEnum),
        nullable=False, default=IntentionStatusEnum.ACTIVE,
        comment="状态：active=进行中 / frozen=冻结 / completed=已完成 / cancelled=已取消"
    )

    # === 时间字段 ===
    update_time = _update_time_column()
    create_time = _create_time_column()

    # === 索引定义 ===
    __table_args__ = (
        Index("idx_intention_student", "student_id"),
        Index("idx_intention_status", "status"),
        Index("idx_intention_priority", "priority"),
        {"comment": "升学意向表"}
    )

    def __repr__(self):
        return (
            f"<StudyIntention("
            f"id={self.id}, student_id={self.student_id}, "
            f"school={self.target_school}, status={self.status})>"
        )


# ============================================================
# 9. 留学申请进度追踪表
# ============================================================

class StudentApplication(Base):
    """
    留学申请进度追踪表

    记录学生实际的留学申请执行进度。
    与 StudyIntention 的关联通过 intention_id 在应用层做显式 JOIN 查询。

    阶段流转：
        document_prep（材料准备）
        → submitted（已提交）
        → under_review（审核中）
        → offer_received（收到offer）
        → visa_processing（签证中）
        → enrolled（已入学）
    """

    __tablename__ = "student_applications"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")

    # === 核心业务字段 ===
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    intention_id = Column(
        BigInteger, nullable=True,
        comment="关联升学意向ID（study_intentions.id，可选追溯目标）"
    )
    target_country = Column(String(64), nullable=True, comment="目标国家")
    target_school = Column(String(128), nullable=False, comment="目标院校")
    target_major = Column(String(128), nullable=True, comment="目标专业")

    # === 流程控制 ===
    stage = Column(
        SAEnum(ApplicationStageEnum),
        nullable=False, default=ApplicationStageEnum.DOCUMENT_PREP,
        comment="申请阶段"
    )
    progress_detail = Column(Text, nullable=True, comment="进度详情描述")
    deadline = Column(Date, nullable=True, comment="关键截止日期")
    next_action = Column(String(255), nullable=True, comment="下一步操作（如 准备补充材料）")

    # === 负责人与状态 ===
    handler_id = Column(BigInteger, nullable=True, comment="负责顾问ID")
    status = Column(
        SAEnum(ApplicationStatusEnum),
        nullable=False, default=ApplicationStatusEnum.ONGOING,
        comment="状态：ongoing=进行中 / paused=暂停 / completed=已完成 / cancelled=已取消"
    )

    # === 时间字段 ===
    update_time = _update_time_column()
    create_time = _create_time_column()

    # === 索引定义 ===
    __table_args__ = (
        Index("idx_application_student", "student_id"),
        Index("idx_application_stage", "stage"),
        Index("idx_application_deadline", "deadline"),
        Index("idx_application_handler", "handler_id"),
        Index("idx_application_intention", "intention_id"),
        {"comment": "留学申请进度追踪表"}
    )

    def __repr__(self):
        return (
            f"<StudentApplication("
            f"id={self.id}, student_id={self.student_id}, "
            f"school={self.target_school}, stage={self.stage})>"
        )
