"""
学生智能助手 — 业务 API 路由（22个端点）
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from utils.database import get_db
from services.student_service import student_service
from utils.config_manager import config_manager
from schemas.student_schemas import (
    ApiResponse,
    LeaveRequestCreate, LeaveRequestApprove, LeaveRequestResponse,
    PsychRecordCreate, PsychAlertResponse, PsychAlertUpdate,
    FeedbackTicketCreate, FeedbackTicketUpdate, FeedbackTicketResponse,
    DeadlineResponse, SessionCreate, StudentProfile, StudentUpdateRequest,
    MarketingTouchResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/student", tags=["学生智能助手"])


def _check_student_exists(db: Session, student_id: int):
    try:
        student_service.require_student(db, student_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 学生信息 ──

@router.get("/profile/{student_id}", response_model=ApiResponse)
def get_student_profile(student_id: int, db: Session = Depends(get_db)):
    student = student_service.get_student(db, student_id)
    if not student:
        raise HTTPException(status_code=404, detail=f"学生 {student_id} 不存在")
    return ApiResponse(data={
        "id": student.id, "union_id": student.union_id, "name": student.name,
        "grade": student.grade, "target_country": student.target_country,
        "status": student.status, "crm_customer_id": student.crm_customer_id,
        "edu_system_id": student.edu_system_id,
    })


@router.get("/students", response_model=ApiResponse)
def list_students(
    keyword: str | None = Query(None), status: int | None = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    result = student_service.list_students(db, keyword=keyword, status=status, page=page, page_size=page_size)
    return ApiResponse(data={
        "total": result["total"], "page": result["page"], "page_size": result["page_size"],
        "items": [StudentProfile.model_validate(s).model_dump() for s in result["items"]],
    })


@router.put("/profile/{student_id}", response_model=ApiResponse)
def update_student(student_id: int, req: StudentUpdateRequest, db: Session = Depends(get_db)):
    student = student_service.update_student(
        db, student_id,
        name=req.name, grade=req.grade, target_country=req.target_country,
        status=req.status, crm_customer_id=req.crm_customer_id, edu_system_id=req.edu_system_id,
    )
    if not student:
        raise HTTPException(status_code=404, detail=f"学生 {student_id} 不存在")
    return ApiResponse(msg="更新成功", data={"id": student.id})


# ── 请假管理 ──

@router.post("/leave-requests", response_model=ApiResponse)
def submit_leave(req: LeaveRequestCreate, db: Session = Depends(get_db)):
    _check_student_exists(db, req.student_id)
    logger.info(f"学生 {req.student_id} 提交请假: {req.start_date} ~ {req.end_date}")
    try:
        leave = student_service.create_leave(db, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ApiResponse(msg="请假申请已提交", data={
        "id": leave.id, "status": leave.status, "idempotent_key": leave.idempotent_key,
    })


@router.get("/leave-requests", response_model=ApiResponse)
def list_leaves(
    student_id: int = Query(...), status: int | None = Query(None),
    db: Session = Depends(get_db),
):
    _check_student_exists(db, student_id)
    leaves = student_service.list_leaves(db, student_id, status)
    return ApiResponse(data={
        "count": len(leaves),
        "items": [LeaveRequestResponse.model_validate(l).model_dump() for l in leaves],
    })


@router.put("/leave-requests/{request_id}/approve", response_model=ApiResponse)
def approve_leave(request_id: int, req: LeaveRequestApprove, db: Session = Depends(get_db)):
    logger.info(f"审批请假 {request_id}: status={req.status}, approver={req.approver_id}")
    try:
        leave = student_service.approve_leave(db, request_id, req)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return ApiResponse(msg="审批完成", data={"id": leave.id, "status": leave.status})


# ── 心理健康 ──

@router.post("/psych/record", response_model=ApiResponse)
def record_emotion(req: PsychRecordCreate, db: Session = Depends(get_db)):
    _check_student_exists(db, req.student_id)
    logger.info(f"学生 {req.student_id} 情绪: score={req.emotion_score}, tags={req.trigger_keywords}")
    result = student_service.record_emotion(db, req)
    has_alert = result["alert"] is not None
    return ApiResponse(
        msg="情绪已记录" + ("，已触发预警" if has_alert else ""),
        data={
            "snapshot_id": result["snapshot"].id, "alert_triggered": has_alert,
            "alert_id": result["alert"].id if has_alert else None,
            "risk_level": result["alert"].risk_level if has_alert else None,
        },
    )


@router.get("/psych/alerts", response_model=ApiResponse)
def list_psych_alerts(
    student_id: int | None = Query(None), risk_level: int | None = Query(None),
    status: int | None = Query(None), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    result = student_service.list_psych_alerts(
        db, student_id=student_id, risk_level=risk_level, status=status, page=page, page_size=page_size,
    )
    return ApiResponse(data={
        "total": result["total"], "page": result["page"], "page_size": result["page_size"],
        "items": [PsychAlertResponse.model_validate(a).model_dump() for a in result["items"]],
    })


@router.get("/psych/alerts/actionable", response_model=ApiResponse)
def list_actionable_alerts(
    student_id: int | None = Query(None), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    result = student_service.list_actionable_alerts(db, student_id=student_id, page=page, page_size=page_size)
    return ApiResponse(data={
        "total": result["total"],
        "items": [PsychAlertResponse.model_validate(a).model_dump() for a in result["items"]],
    })


@router.put("/psych/alerts/{alert_id}", response_model=ApiResponse)
def handle_alert(alert_id: int, req: PsychAlertUpdate, db: Session = Depends(get_db)):
    logger.info(f"处理预警 {alert_id}: status={req.status}, handler={req.handler_id}")
    alert = student_service.handle_alert(db, alert_id, req)
    if not alert:
        raise HTTPException(status_code=404, detail="预警不存在")
    return ApiResponse(msg="预警已处理", data={"id": alert.id, "human_confirmed_status": alert.human_confirmed_status})


# ── 售后反馈 ──

@router.post("/feedback-tickets", response_model=ApiResponse)
def submit_feedback(req: FeedbackTicketCreate, db: Session = Depends(get_db)):
    _check_student_exists(db, req.student_id)
    logger.info(f"学生 {req.student_id} 提交反馈: category={req.category}")
    ticket = student_service.create_feedback(db, req)
    return ApiResponse(msg="工单已创建", data={
        "id": ticket.id, "status": ticket.status, "sla_deadline": str(ticket.sla_deadline),
    })


@router.get("/feedback-tickets", response_model=ApiResponse)
def list_feedbacks(
    student_id: int = Query(...), status: int | None = Query(None),
    db: Session = Depends(get_db),
):
    _check_student_exists(db, student_id)
    tickets = student_service.list_feedbacks(db, student_id, status)
    return ApiResponse(data={
        "count": len(tickets),
        "items": [FeedbackTicketResponse.model_validate(t).model_dump() for t in tickets],
    })


@router.put("/feedback-tickets/{ticket_id}", response_model=ApiResponse)
def handle_feedback(ticket_id: int, req: FeedbackTicketUpdate, db: Session = Depends(get_db)):
    logger.info(f"处理工单 {ticket_id}: status={req.status}")
    ticket = student_service.handle_feedback(db, ticket_id, req)
    if not ticket:
        raise HTTPException(status_code=404, detail="工单不存在")
    return ApiResponse(msg="工单已更新", data={"id": ticket.id, "status": ticket.status})


@router.get("/tickets/overdue", response_model=ApiResponse)
def list_overdue_tickets(db: Session = Depends(get_db)):
    tickets = student_service.list_overdue_tickets(db)
    return ApiResponse(data={
        "count": len(tickets),
        "items": [FeedbackTicketResponse.model_validate(t).model_dump() for t in tickets],
    })


# ── DDL & 申请进度 ──

@router.get("/deadlines", response_model=ApiResponse)
def list_deadlines(
    student_id: int = Query(...), upcoming_days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    _check_student_exists(db, student_id)
    deadlines = student_service.list_deadlines(db, student_id, upcoming_days)
    return ApiResponse(data={
        "count": len(deadlines),
        "items": [DeadlineResponse.model_validate(d).model_dump() for d in deadlines],
    })


@router.get("/applications", response_model=ApiResponse)
def query_applications(student_id: int = Query(...)):
    return ApiResponse(msg="申请进度数据需从教务系统实时获取", data={
        "source": "external_edu_system",
        "note": "请提供 edu_system_id，系统将调用教务API获取实时申请状态",
        "stages": ["document_prep 材料准备", "submitted 已提交", "under_review 审核中",
                    "offer_received 已获录取", "visa_processing 签证办理", "enrolled 已入学"],
    })


@router.get("/scores", response_model=ApiResponse)
def query_scores(student_id: int = Query(...)):
    return ApiResponse(msg="成绩数据需从教务系统实时获取", data={
        "source": "external_edu_system",
        "note": "请提供 edu_system_id，系统将调用教务API获取实时成绩数据",
    })


# ── 会话管理 ──

@router.post("/sessions", response_model=ApiResponse)
def create_session(req: SessionCreate, db: Session = Depends(get_db)):
    _check_student_exists(db, req.student_id)
    sess = student_service.create_session(db, req.student_id, req.agent_type or "student")
    return ApiResponse(msg="会话已创建", data={"session_id": sess.id, "session_token": sess.session_token})


@router.delete("/sessions/{session_id}", response_model=ApiResponse)
def delete_session(session_id: int, db: Session = Depends(get_db)):
    if not student_service.delete_session(db, session_id):
        raise HTTPException(status_code=404, detail="会话不存在或已删除")
    return ApiResponse(msg="会话已删除")


# ── 系统配置 ──

@router.get("/configs", response_model=ApiResponse)
def get_system_configs(db: Session = Depends(get_db)):
    return ApiResponse(data=student_service.load_system_configs(db))


@router.post("/configs/refresh", response_model=ApiResponse)
def refresh_configs():
    config_manager.refresh()
    return ApiResponse(msg="配置已刷新", data={"emotion_threshold_red": config_manager.emotion_threshold_red})


# ── 营销触达 ──

@router.get("/marketing/touches", response_model=ApiResponse)
def list_marketing_touches(
    student_id: int | None = Query(None), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    result = student_service.list_marketing_touches(db, student_id=student_id, page=page, page_size=page_size)
    return ApiResponse(data={
        "total": result["total"], "page": result["page"], "page_size": result["page_size"],
        "items": [MarketingTouchResponse.model_validate(m).model_dump() for m in result["items"]],
    })
