"""
学生模块 ORM 模型
基于已建好的 test 数据库 10 张表，使用 SQLAlchemy 2.0 声明式映射
"""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    BigInteger, Integer, SmallInteger, String, Text, Date, DateTime,
    Numeric, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column
from utils.database import Base


# ============================================================
# 一、核心基础层
# ============================================================

class Student(Base):
    """学生主表 — 数据总线，关联所有外部系统 ID"""
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    union_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="全局唯一用户ID")
    crm_customer_id: Mapped[str | None] = mapped_column(String(64), comment="CRM系统客户ID")
    edu_system_id: Mapped[str | None] = mapped_column(String(64), comment="教务系统学生ID")
    name: Mapped[str | None] = mapped_column(String(32), comment="姓名（脱敏）")
    grade: Mapped[int | None] = mapped_column(SmallInteger, comment="当前年级")
    target_country: Mapped[str | None] = mapped_column(String(32), comment="意向国家")
    status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="0-正常 1-停用 2-流失")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, comment="软删除")


class ConversationSession(Base):
    """会话主表 — 会话级记忆与审计追溯"""
    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    session_token: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_type: Mapped[str | None] = mapped_column(String(32), comment="路由Agent")
    start_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class ConversationMessage(Base):
    """消息明细表 — 对话原文加密存储"""
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="1-用户 2-AI 3-系统")
    content: Mapped[str | None] = mapped_column(Text, comment="对话原文（加密）")
    emotion_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), comment="情绪打分")
    cost_token: Mapped[int | None] = mapped_column(Integer, comment="Token消耗")
    llm_model: Mapped[str | None] = mapped_column(String(16), comment="模型名")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ============================================================
# 二、业务事务层
# ============================================================

class LeaveApplication(Base):
    """请假申请表 — 学生提交-班主任审批闭环"""
    __tablename__ = "leave_applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotent_key: Mapped[str] = mapped_column(String(128), nullable=False, comment="幂等键")
    leave_type: Mapped[int] = mapped_column(SmallInteger, default=1, comment="1-病假 2-事假 3-其他")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    attachment_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="0-待审 1-通过 2-驳回 3-撤销")
    approver_id: Mapped[int | None] = mapped_column(BigInteger)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    notify_status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="0-未推送 1-推送中 2-已送达")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class FeedbackTicket(Base):
    """售后反馈工单表"""
    __tablename__ = "feedback_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="1-签证 2-文书 3-费用 4-生活 5-其他")
    priority: Mapped[int] = mapped_column(SmallInteger, default=2, comment="1-低 2-中 3-紧急")
    ai_summary: Mapped[str | None] = mapped_column(String(500))
    full_content: Mapped[str | None] = mapped_column(Text, comment="原始投诉（加密）")
    status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="0-待分配 1-处理中 2-待复核 3-已关闭")
    handler_id: Mapped[int | None] = mapped_column(BigInteger)
    sla_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    satisfaction_score: Mapped[int | None] = mapped_column(SmallInteger)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


# ============================================================
# 三、风险与分析层
# ============================================================

class EmotionProfileSnapshot(Base):
    """心理画像日快照表"""
    __tablename__ = "emotion_profile_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    avg_emotion_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    min_emotion_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    peak_negative_tags: Mapped[list | None] = mapped_column(JSON, comment="高频负向标签（JSON数组）")
    daily_chat_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class RiskIntervention(Base):
    """心理预警干预记录表"""
    __tablename__ = "risk_interventions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trigger_rule_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="触发规则ID")
    risk_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="1-黄 2-红")
    trigger_evidence: Mapped[str | None] = mapped_column(String(500), comment="AI摘要（不存完整对话）")
    ai_raw_output: Mapped[str | None] = mapped_column(Text, comment="模型原始输出JSON")
    human_confirmed_status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="0-待确认 1-已确认 2-误报")
    handler_id: Mapped[int | None] = mapped_column(BigInteger)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============================================================
# 四、辅助与配置层
# ============================================================

class DeadlineReminder(Base):
    """学业考务DDL提醒表"""
    __tablename__ = "deadline_reminders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment="1-论文 2-考试 3-选课")
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    deadline_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    push_status: Mapped[int] = mapped_column(SmallInteger, default=0, comment="0-待推送 1-已推送 2-已读")
    push_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class MarketingTouchLog(Base):
    """增值转化触达日志表"""
    __tablename__ = "marketing_touch_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    program_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ai_generated_text: Mapped[str | None] = mapped_column(Text, comment="AI推荐话术")
    user_clicked: Mapped[int] = mapped_column(SmallInteger, default=0, comment="0-未点击 1-已点击")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class SystemConfig(Base):
    """系统配置表 — 运维配置，无需改代码"""
    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(128), nullable=False)
    config_value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
