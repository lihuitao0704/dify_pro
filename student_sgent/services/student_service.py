"""
学生模块业务逻辑层
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import desc, func, or_

from models import get_session
from models.student import (
    ConversationSession,
    ConversationMessage,
    EmotionProfileSnapshot,
    RiskIntervention,
    FeedbackTicket,
    AcademicSchedule,
    DeadlineReminder,
    StudyIntention,
    StudentApplication,
)

logger = logging.getLogger("student_service")

_MAX_EMOTION_HISTORY = 100

# 情绪关键词库（服务端分析用，后续可由 LLM 替代）
_POSITIVE_WORDS = [
    '开心','高兴','喜欢','棒','好','不错','顺利','感谢','谢谢','期待',
    '兴奋','成功','通过','录取','offer','优秀','加油','恭喜','太棒了','nice',
    'great','awesome','happy','love','wonderful','fantastic',
]
_NEGATIVE_WORDS = [
    '焦虑','担心','害怕','压力','烦','累','难过','伤心','生气','讨厌',
    '无聊','失望','痛苦','崩溃','失眠','睡不着','紧张','烦躁','无助','孤独',
    '迷茫','恐惧','疲惫','委屈','后悔','愤怒','沮丧',
]
_CRITICAL_WORDS = [
    '绝望','轻生','自杀','不想活','死了算了','自残','伤害自己','不想活了',
    '活不下去','生无可恋','活着没意思',
]


def _utcnow_naive():
    """返回 naive UTC datetime，与 MySQL CURRENT_TIMESTAMP 对齐"""
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


def _analyze_emotion(content: str) -> dict:
    """
    服务端基础情绪分析。检测关键词并返回情绪标签、分值、触发词。
    后续接入 LLM/Dify 后可替换为 AI 分析。
    """
    keywords = []
    tag = '平稳'
    score = 75  # 默认中性偏积极

    # 高危词优先检测
    for w in _CRITICAL_WORDS:
        if w in content:
            keywords.append(w)
            score = 15
            tag = '高危'
            break

    if tag != '高危':
        neg_found = [w for w in _NEGATIVE_WORDS if w in content]
        pos_found = [w for w in _POSITIVE_WORDS if w in content]

        if neg_found:
            keywords = neg_found
            score = 35
            tag = '焦虑'
        if pos_found and tag == '平稳':
            # 仅在无负面情绪时标记为积极
            keywords.extend(pos_found)
            score = 80
            tag = '积极'
        elif pos_found and tag == '焦虑':
            # 混杂情绪：记录正面词但不改变主情绪
            keywords.extend(pos_found)
            score = 45  # 中和一点

    return {
        'tag': tag,
        'score': score,
        'keywords': keywords[:5],
    }


def _build_emotion_history_entry(
    emotion_tag: Optional[str],
    emotion_score: Optional[int],
    risk_level: str,
) -> dict:
    return {
        "tag": emotion_tag,
        "score": emotion_score,
        "risk": risk_level,
        "date": _utcnow_naive().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ============================================================
# 会话与消息
# ============================================================

def create_session(student_id: int, session_id: Optional[str] = None) -> ConversationSession:
    with get_session() as session:
        sess = ConversationSession(
            session_id=session_id or f"sess_{uuid.uuid4().hex[:16]}",
            student_id=student_id,
        )
        session.add(sess)
        session.flush()
        logger.info("Session created: sid=%s, student=%d", sess.session_id, student_id)
        return sess


def get_session_by_id(session_id: str) -> Optional[ConversationSession]:
    with get_session() as session:
        return session.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()


def list_student_sessions(
    student_id: int, limit: int = 20, offset: int = 0,
) -> list:
    with get_session() as session:
        return (
            session.query(ConversationSession)
            .filter(ConversationSession.student_id == student_id)
            .order_by(desc(ConversationSession.last_message_time))
            .offset(offset).limit(limit).all()
        )


def add_message(
    session_id: str,
    role: str,
    content: str,
    intent: Optional[str] = None,
    emotion_tag: Optional[str] = None,
    emotion_score: Optional[int] = None,
    trigger_keywords: Optional[list] = None,
    tokens_used: Optional[int] = None,
    response_time_ms: Optional[int] = None,
) -> ConversationMessage:
    with get_session() as session:
        sess = session.query(ConversationSession).filter(
            ConversationSession.session_id == session_id
        ).first()
        if not sess:
            raise RuntimeError(f"Session not found: {session_id}")

        msg = ConversationMessage(
            session_id=session_id,
            role=role,
            content=content,
            intent=intent,
            emotion_tag=emotion_tag,
            emotion_score=emotion_score,
            trigger_keywords=trigger_keywords,
            tokens_used=tokens_used,
            response_time_ms=response_time_ms,
        )
        session.add(msg)

        # user 消息无情绪数据时，服务端自动分析
        if role == "user" and emotion_tag is None and emotion_score is None:
            analyzed = _analyze_emotion(content)
            emotion_tag = analyzed['tag']
            emotion_score = analyzed['score']
            trigger_keywords = trigger_keywords or analyzed['keywords']
            # 回填到已创建的 msg 对象，flush 时一起写入
            msg.emotion_tag = emotion_tag
            msg.emotion_score = emotion_score
            msg.trigger_keywords = trigger_keywords

        # 原子更新计数器 + 最后消息时间
        now = _utcnow_naive()
        session.query(ConversationSession).filter(
            ConversationSession.id == sess.id
        ).update(
            {
                "message_count": func.coalesce(ConversationSession.message_count, 0) + 1,
                "last_message_time": now,
            },
            synchronize_session="fetch",
        )

        # 情绪画像同步（user 消息携带情绪数据时触发）
        if role == "user" and emotion_tag is not None:
            profile = session.query(EmotionProfileSnapshot).filter(
                EmotionProfileSnapshot.student_id == sess.student_id
            ).first()
            if not profile:
                profile = EmotionProfileSnapshot(
                    student_id=sess.student_id, risk_level="low"
                )
                session.add(profile)
                session.flush()

            new_risk_level = profile.risk_level
            if emotion_score is not None:
                if emotion_score < 30:
                    new_risk_level = "high"
                elif emotion_score < 60:
                    new_risk_level = "medium"
                else:
                    new_risk_level = "low"

            # 构建新历史数组。注意：极端并发下同学生两条消息的
            # emotion_history 可能互相覆盖（read-modify-write），此场景
            # 发生率极低且非金融数据，接受最终一致性。
            history_entry = _build_emotion_history_entry(
                emotion_tag, emotion_score, new_risk_level,
            )
            current_history = profile.emotion_history or []
            current_history.append(history_entry)
            profile.emotion_history = current_history[-_MAX_EMOTION_HISTORY:]

            if emotion_tag is not None:
                profile.latest_emotion_tag = emotion_tag
            if emotion_score is not None:
                profile.emotion_score = emotion_score
            profile.risk_level = new_risk_level
            profile.last_interaction_time = _utcnow_naive()

        session.flush()
        return msg


def list_session_messages(
    session_id: str, limit: int = 50, offset: int = 0,
) -> list:
    with get_session() as session:
        return (
            session.query(ConversationMessage)
            .filter(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.create_time)
            .offset(offset).limit(limit).all()
        )


# ============================================================
# 心理画像与预警
# ============================================================

def get_emotion_profile(student_id: int) -> Optional[EmotionProfileSnapshot]:
    with get_session() as session:
        return session.query(EmotionProfileSnapshot).filter(
            EmotionProfileSnapshot.student_id == student_id
        ).first()


def get_or_create_emotion_profile(student_id: int) -> EmotionProfileSnapshot:
    with get_session() as session:
        profile = session.query(EmotionProfileSnapshot).filter(
            EmotionProfileSnapshot.student_id == student_id
        ).first()
        if not profile:
            profile = EmotionProfileSnapshot(student_id=student_id)
            session.add(profile)
            session.flush()
        return profile


def update_emotion_profile(
    student_id: int,
    emotion_tag: Optional[str] = None,
    emotion_score: Optional[int] = None,
    risk_level: Optional[str] = None,
) -> EmotionProfileSnapshot:
    with get_session() as session:
        profile = session.query(EmotionProfileSnapshot).filter(
            EmotionProfileSnapshot.student_id == student_id
        ).first()
        if not profile:
            profile = EmotionProfileSnapshot(student_id=student_id, risk_level="low")
            session.add(profile)
        if emotion_tag is not None:
            profile.latest_emotion_tag = emotion_tag
        if emotion_score is not None:
            profile.emotion_score = emotion_score
        if risk_level is not None:
            profile.risk_level = risk_level
        profile.last_interaction_time = _utcnow_naive()
        session.flush()
        return profile


def create_risk_intervention(
    student_id: int,
    trigger_reason: str,
    risk_level: str = "medium",
    source_message_id: Optional[int] = None,
    risk_tags: Optional[list] = None,
) -> RiskIntervention:
    with get_session() as session:
        alert = RiskIntervention(
            student_id=student_id,
            trigger_reason=trigger_reason,
            risk_level=risk_level,
            source_message_id=source_message_id,
            risk_tags=risk_tags,
        )
        session.add(alert)
        session.flush()
        logger.warning(
            "Risk alert created: student=%d, level=%s, tags=%s",
            student_id, risk_level, risk_tags,
        )
        return alert


def list_risk_interventions(
    student_id: Optional[int] = None,
    risk_level: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    with get_session() as session:
        query = session.query(RiskIntervention)
        if student_id is not None:
            query = query.filter(RiskIntervention.student_id == student_id)
        if risk_level:
            query = query.filter(RiskIntervention.risk_level == risk_level)
        if status:
            query = query.filter(RiskIntervention.status == status)
        return (
            query.order_by(desc(RiskIntervention.create_time))
            .offset(offset).limit(limit).all()
        )


def update_risk_intervention(
    alert_id: int,
    status: Optional[str] = None,
    teacher_id: Optional[int] = None,
    follow_record: Optional[str] = None,
    risk_tags: Optional[list] = None,
) -> Optional[RiskIntervention]:
    with get_session() as session:
        alert = session.get(RiskIntervention, alert_id)
        if not alert:
            return None
        if status is not None:
            alert.status = status
            if status in ("resolved", "dismissed"):
                alert.resolved_time = _utcnow_naive()
        if teacher_id is not None:
            alert.teacher_id = teacher_id
        if follow_record is not None:
            alert.follow_record = follow_record
        if risk_tags is not None:
            alert.risk_tags = risk_tags
        session.flush()
        logger.info("Alert updated: id=%d, status=%s, teacher=%s",
                     alert_id, alert.status, alert.teacher_id)
        return alert


# ============================================================
# 投诉工单
# ============================================================

def create_feedback_ticket(
    student_id: int,
    content: str,
    ticket_type: str = "complaint",
    category: Optional[str] = None,
    title: Optional[str] = None,
    detail: Optional[str] = None,
    priority: str = "medium",
) -> FeedbackTicket:
    with get_session() as session:
        ticket = FeedbackTicket(
            student_id=student_id,
            ticket_type=ticket_type,
            category=category,
            title=title or f"Student {student_id} {ticket_type}",
            content=content,
            detail=detail,
            priority=priority,
        )
        session.add(ticket)
        session.flush()
        logger.info("Ticket created: student=%d, type=%s, priority=%s",
                     student_id, ticket_type, priority)
        return ticket


def list_feedback_tickets(
    student_id: Optional[int] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    with get_session() as session:
        query = session.query(FeedbackTicket)
        if student_id is not None:
            query = query.filter(FeedbackTicket.student_id == student_id)
        if status:
            query = query.filter(FeedbackTicket.status == status)
        if category:
            query = query.filter(FeedbackTicket.category == category)
        return (
            query.order_by(desc(FeedbackTicket.create_time))
            .offset(offset).limit(limit).all()
        )


def update_feedback_ticket(
    ticket_id: int,
    status: Optional[str] = None,
    assignee_id: Optional[int] = None,
    solution: Optional[str] = None,
    satisfaction: Optional[int] = None,
    is_notified: Optional[bool] = None,
    priority: Optional[str] = None,
) -> Optional[FeedbackTicket]:
    with get_session() as session:
        ticket = session.get(FeedbackTicket, ticket_id)
        if not ticket:
            return None
        if status is not None:
            ticket.status = status
            if status in ("resolved", "closed"):
                ticket.resolved_time = _utcnow_naive()
        if assignee_id is not None:
            ticket.assignee_id = assignee_id
        if solution is not None:
            ticket.solution = solution
        if satisfaction is not None:
            ticket.satisfaction = satisfaction
        if is_notified is not None:
            ticket.is_notified = is_notified
        if priority is not None:
            ticket.priority = priority
        session.flush()
        logger.info("Ticket updated: id=%d, status=%s, priority=%s",
                     ticket_id, ticket.status, ticket.priority)
        return ticket


# ============================================================
# 学业日程
# ============================================================

def create_academic_schedule(
    student_id: int,
    title: str,
    start_time: datetime,
    schedule_type: str = "course",
    description: Optional[str] = None,
    end_time: Optional[datetime] = None,
    location: Optional[str] = None,
    is_recurring: bool = False,
    reminder_enabled: bool = True,
    reminder_minutes: Optional[int] = None,
) -> AcademicSchedule:
    with get_session() as session:
        schedule = AcademicSchedule(
            student_id=student_id,
            schedule_type=schedule_type,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            location=location,
            is_recurring=is_recurring,
            reminder_enabled=reminder_enabled,
            reminder_minutes=reminder_minutes,
        )
        session.add(schedule)
        session.flush()
        return schedule


def list_academic_schedules(
    student_id: int,
    schedule_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    with get_session() as session:
        query = session.query(AcademicSchedule).filter(
            AcademicSchedule.student_id == student_id
        )
        if schedule_type:
            query = query.filter(AcademicSchedule.schedule_type == schedule_type)
        if status:
            query = query.filter(AcademicSchedule.status == status)
        return (
            query.order_by(AcademicSchedule.start_time)
            .offset(offset).limit(limit).all()
        )


# ============================================================
# DDL 提醒
# ============================================================

def create_deadline_reminder(
    title: str,
    deadline: datetime,
    deadline_type: str = "other",
    student_id: Optional[int] = None,
    description: Optional[str] = None,
    reminder_days: Optional[list] = None,
    related_schedule_id: Optional[int] = None,
) -> DeadlineReminder:
    with get_session() as session:
        # 明确区分 None（未传）和 []（不需要提醒）
        days = reminder_days if reminder_days is not None else [7, 3, 1]
        reminder = DeadlineReminder(
            student_id=student_id,
            deadline_type=deadline_type,
            title=title,
            description=description,
            deadline=deadline,
            reminder_days=days,
            related_schedule_id=related_schedule_id,
        )
        session.add(reminder)
        session.flush()
        return reminder


def list_upcoming_deadlines(
    student_id: Optional[int] = None,
    upcoming_days: int = 7,
    limit: int = 30,
    offset: int = 0,
) -> list:
    with get_session() as session:
        now = _utcnow_naive()
        future = now + timedelta(days=upcoming_days)
        query = session.query(DeadlineReminder).filter(
            DeadlineReminder.deadline.between(now, future),
            DeadlineReminder.status == "pending",
        )
        if student_id is not None:
            query = query.filter(
                or_(
                    DeadlineReminder.student_id == student_id,
                    DeadlineReminder.student_id.is_(None),
                )
            )
        return (
            query.order_by(DeadlineReminder.deadline)
            .offset(offset).limit(limit).all()
        )


# ============================================================
# 升学意向
# ============================================================

def create_study_intention(
    student_id: int,
    target_country: Optional[str] = None,
    target_school: Optional[str] = None,
    target_major: Optional[str] = None,
    education_level: Optional[str] = None,
    expected_enroll_time: Optional[str] = None,
    budget_range: Optional[str] = None,
    language_score: Optional[str] = None,
    priority: int = 0,
) -> StudyIntention:
    with get_session() as session:
        intention = StudyIntention(
            student_id=student_id,
            target_country=target_country,
            target_school=target_school,
            target_major=target_major,
            education_level=education_level,
            expected_enroll_time=expected_enroll_time,
            budget_range=budget_range,
            language_score=language_score,
            priority=priority,
        )
        session.add(intention)
        session.flush()
        return intention


def list_study_intentions(
    student_id: int, limit: int = 50, offset: int = 0,
) -> list:
    with get_session() as session:
        return (
            session.query(StudyIntention)
            .filter(StudyIntention.student_id == student_id)
            .order_by(StudyIntention.priority)
            .offset(offset).limit(limit).all()
        )


# ============================================================
# 申请进度
# ============================================================

def create_student_application(
    student_id: int,
    target_school: str,
    target_country: Optional[str] = None,
    target_major: Optional[str] = None,
    stage: str = "document_prep",
    progress_detail: Optional[str] = None,
    deadline: Optional[datetime] = None,
    next_action: Optional[str] = None,
    handler_id: Optional[int] = None,
    intention_id: Optional[int] = None,
) -> StudentApplication:
    with get_session() as session:
        app = StudentApplication(
            student_id=student_id,
            intention_id=intention_id,
            target_country=target_country,
            target_school=target_school,
            target_major=target_major,
            stage=stage,
            progress_detail=progress_detail,
            deadline=deadline,
            next_action=next_action,
            handler_id=handler_id,
        )
        session.add(app)
        session.flush()
        return app


def list_student_applications(
    student_id: Optional[int] = None,
    stage: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
) -> list:
    with get_session() as session:
        query = session.query(StudentApplication)
        if student_id is not None:
            query = query.filter(StudentApplication.student_id == student_id)
        if stage:
            query = query.filter(StudentApplication.stage == stage)
        if status:
            query = query.filter(StudentApplication.status == status)
        return (
            query.order_by(desc(StudentApplication.update_time))
            .offset(offset).limit(limit).all()
        )
