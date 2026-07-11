"""
学生业务 API 路由

涵盖：心理画像、预警干预、投诉工单、学业日程、DDL提醒、升学意向、申请进度
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from schemas.student import (
    EmotionProfileResponse,
    RiskInterventionCreate, RiskInterventionUpdate, RiskInterventionResponse,
    FeedbackTicketCreate, FeedbackTicketUpdate, FeedbackTicketResponse,
    AcademicScheduleCreate, AcademicScheduleResponse,
    DeadlineReminderCreate, DeadlineReminderResponse,
    StudyIntentionCreate, StudyIntentionResponse,
    StudentApplicationCreate, StudentApplicationResponse,
)
from services import student_service as svc

router = APIRouter(prefix="/api/v1/student", tags=["学生业务"])


# ============================================================
# 心理画像
# ============================================================

@router.get("/psych/profile", response_model=EmotionProfileResponse)
def get_emotion_profile(student_id: int = Query(..., description="学生ID")):
    """获取学生心理画像（不存在时返回默认空画像 + 200）"""
    profile = svc.get_or_create_emotion_profile(student_id)
    return EmotionProfileResponse.model_validate(profile)


# ============================================================
# 心理预警
# ============================================================

@router.post("/psych/alerts", response_model=RiskInterventionResponse)
def create_alert(body: RiskInterventionCreate):
    """创建心理预警"""
    alert = svc.create_risk_intervention(
        student_id=body.student_id,
        trigger_reason=body.trigger_reason,
        risk_level=body.risk_level,
        source_message_id=body.source_message_id,
        risk_tags=body.risk_tags,
    )
    return RiskInterventionResponse.model_validate(alert)


@router.get("/psych/alerts", response_model=list[RiskInterventionResponse])
def list_alerts(
    student_id: Optional[int] = Query(None),
    risk_level: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """查询心理预警列表"""
    alerts = svc.list_risk_interventions(student_id, risk_level, status, limit, offset)
    return [RiskInterventionResponse.model_validate(a) for a in alerts]


@router.put("/psych/alerts/{alert_id}", response_model=RiskInterventionResponse)
def update_alert(alert_id: int, body: RiskInterventionUpdate):
    """处理心理预警"""
    alert = svc.update_risk_intervention(
        alert_id=alert_id,
        status=body.status,
        teacher_id=body.teacher_id,
        follow_record=body.follow_record,
        risk_tags=body.risk_tags,
    )
    if not alert:
        raise HTTPException(404, "预警记录不存在")
    return RiskInterventionResponse.model_validate(alert)


# ============================================================
# 投诉工单
# ============================================================

@router.post("/feedback-tickets", response_model=FeedbackTicketResponse)
def create_ticket(body: FeedbackTicketCreate):
    """提交投诉/反馈工单"""
    ticket = svc.create_feedback_ticket(
        student_id=body.student_id,
        content=body.content,
        ticket_type=body.ticket_type,
        category=body.category,
        title=body.title,
        detail=body.detail,
        priority=body.priority,
    )
    return FeedbackTicketResponse.model_validate(ticket)


@router.get("/feedback-tickets", response_model=list[FeedbackTicketResponse])
def list_tickets(
    student_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """查询工单列表"""
    tickets = svc.list_feedback_tickets(student_id, status, category, limit, offset)
    return [FeedbackTicketResponse.model_validate(t) for t in tickets]


@router.put("/feedback-tickets/{ticket_id}", response_model=FeedbackTicketResponse)
def update_ticket(ticket_id: int, body: FeedbackTicketUpdate):
    """处理工单"""
    ticket = svc.update_feedback_ticket(
        ticket_id=ticket_id,
        status=body.status,
        assignee_id=body.assignee_id,
        solution=body.solution,
        satisfaction=body.satisfaction,
        is_notified=body.is_notified,
        priority=body.priority,
    )
    if not ticket:
        raise HTTPException(404, "工单不存在")
    return FeedbackTicketResponse.model_validate(ticket)


# ============================================================
# 学业日程
# ============================================================

@router.post("/schedules", response_model=AcademicScheduleResponse)
def create_schedule(body: AcademicScheduleCreate):
    """创建学业日程"""
    schedule = svc.create_academic_schedule(
        student_id=body.student_id,
        title=body.title,
        start_time=body.start_time,
        schedule_type=body.schedule_type,
        description=body.description,
        end_time=body.end_time,
        location=body.location,
        is_recurring=body.is_recurring,
        reminder_enabled=body.reminder_enabled,
        reminder_minutes=body.reminder_minutes,
    )
    return AcademicScheduleResponse.model_validate(schedule)


@router.get("/schedules", response_model=list[AcademicScheduleResponse])
def list_schedules(
    student_id: int = Query(..., description="学生ID"),
    schedule_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """查询学业日程"""
    schedules = svc.list_academic_schedules(student_id, schedule_type, status, limit, offset)
    return [AcademicScheduleResponse.model_validate(s) for s in schedules]


# ============================================================
# DDL 提醒
# ============================================================

@router.post("/deadlines", response_model=DeadlineReminderResponse)
def create_deadline(body: DeadlineReminderCreate):
    """创建DDL提醒"""
    reminder = svc.create_deadline_reminder(
        title=body.title,
        deadline=body.deadline,
        deadline_type=body.deadline_type,
        student_id=body.student_id,
        description=body.description,
        reminder_days=body.reminder_days,
        related_schedule_id=body.related_schedule_id,
    )
    return DeadlineReminderResponse.model_validate(reminder)


@router.get("/deadlines", response_model=list[DeadlineReminderResponse])
def list_deadlines(
    student_id: Optional[int] = Query(None),
    upcoming_days: int = Query(7, ge=1, le=365),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """查询未来到期的DDL"""
    deadlines = svc.list_upcoming_deadlines(student_id, upcoming_days, limit, offset)
    return [DeadlineReminderResponse.model_validate(d) for d in deadlines]


# ============================================================
# 升学意向
# ============================================================

@router.post("/intentions", response_model=StudyIntentionResponse)
def create_intention(body: StudyIntentionCreate):
    """创建升学意向"""
    intention = svc.create_study_intention(
        student_id=body.student_id,
        target_country=body.target_country,
        target_school=body.target_school,
        target_major=body.target_major,
        education_level=body.education_level,
        expected_enroll_time=body.expected_enroll_time,
        budget_range=body.budget_range,
        language_score=body.language_score,
        priority=body.priority,
    )
    return StudyIntentionResponse.model_validate(intention)


@router.get("/intentions", response_model=list[StudyIntentionResponse])
def list_intentions(
    student_id: int = Query(..., description="学生ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """查询升学意向"""
    intentions = svc.list_study_intentions(student_id, limit, offset)
    return [StudyIntentionResponse.model_validate(i) for i in intentions]


# ============================================================
# 申请进度
# ============================================================

@router.post("/applications", response_model=StudentApplicationResponse)
def create_application(body: StudentApplicationCreate):
    """创建申请进度"""
    app = svc.create_student_application(
        student_id=body.student_id,
        target_school=body.target_school,
        target_country=body.target_country,
        target_major=body.target_major,
        stage=body.stage,
        progress_detail=body.progress_detail,
        deadline=body.deadline,
        next_action=body.next_action,
        handler_id=body.handler_id,
        intention_id=body.intention_id,
    )
    return StudentApplicationResponse.model_validate(app)


@router.get("/applications", response_model=list[StudentApplicationResponse])
def list_applications(
    student_id: Optional[int] = Query(None),
    stage: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """查询申请进度"""
    apps = svc.list_student_applications(student_id, stage, status, limit, offset)
    return [StudentApplicationResponse.model_validate(a) for a in apps]
