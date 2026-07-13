"""
留学申请核心业务路由
教育服务全生命周期管理：申请记录、材料清单、咨询预约
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, date
import logging

from enterprise_agent.database import get_db
from enterprise_agent.models import (
    ApplicationRecord, DocumentChecklist, Appointment, Student, StudentInfo, Account,
)
from enterprise_agent.schemas import ApiResponse
from enterprise_agent.utils import require_operator, is_manager, parse_date

logger = logging.getLogger("enterprise_agent.application")
router = APIRouter()


# ==================== 留学申请记录 ====================

@router.get("/application/list", response_model=ApiResponse, summary="申请列表")
def list_applications(
    student_id: Optional[int] = Query(None, description="学生ID"),
    status: Optional[str] = Query(None, description="筛选状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询留学申请列表（员工/管理者可查看）"""
    try:
        require_operator(current_user_type)

        query = db.query(ApplicationRecord)

        if student_id:
            query = query.filter(ApplicationRecord.student_id == student_id)
        if status:
            query = query.filter(ApplicationRecord.application_status == status)

        total = query.count()
        apps = query.order_by(ApplicationRecord.updated_at.desc()).offset(
            (page - 1) * page_size).limit(page_size).all()

        data_list = []
        for a in apps:
            data_list.append({
                "id": a.id,
                "student_id": a.student_id,
                "university": a.university,
                "program_name": a.program_name,
                "program_type": a.program_type,
                "intake": a.intake,
                "application_status": a.application_status,
                "current_step": a.current_step,
                "submitted_date": a.submitted_date.isoformat() if a.submitted_date else None,
                "decision_date": a.decision_date.isoformat() if a.decision_date else None,
                "is_offer_accepted": a.is_offer_accepted,
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
            })

        return ApiResponse(data={
            "total": total, "page": page, "page_size": page_size, "list": data_list,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询申请列表失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


from pydantic import BaseModel as PydanticBaseModel

class _CreateAppRequest(PydanticBaseModel):
    student_id: int
    university: str
    program_name: str
    program_type: str = "硕士"
    intake: str = ""
    current_user_id: int
    current_user_type: str


@router.post("/application/create", response_model=ApiResponse, summary="创建申请记录")
def create_application(req: _CreateAppRequest, db: Session = Depends(get_db)):
    """创建留学申请记录"""
    try:
        require_operator(req.current_user_type)

        app = ApplicationRecord(
            student_id=req.student_id,
            university=req.university.strip(),
            program_name=req.program_name.strip(),
            program_type=req.program_type,
            intake=req.intake,
            application_status="draft",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(app)
        db.flush()
        db.commit()

        logger.info("创建申请记录: id=%s, student=%s, uni=%s", app.id, req.student_id, req.university)
        return ApiResponse(data={"application_id": app.id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建申请记录失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"创建失败: {str(e)}")


@router.put("/application/status", response_model=ApiResponse, summary="更新申请状态")
def update_application_status(
    application_id: int = Query(..., description="申请ID"),
    new_status: str = Query(..., description="新状态"),
    current_step: str = Query("", description="当前步骤"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """更新申请进度状态"""
    try:
        require_operator(current_user_type)

        valid_statuses = ("draft", "submitted", "under_review", "interview",
                          "offer", "rejected", "withdrawn", "enrolled")
        if new_status not in valid_statuses:
            return ApiResponse(code=400, msg=f"无效状态，可选: {', '.join(valid_statuses)}")

        app = db.query(ApplicationRecord).filter(
            ApplicationRecord.id == application_id,
        ).first()
        if not app:
            return ApiResponse(code=404, msg="申请记录不存在")

        app.application_status = new_status
        if current_step:
            app.current_step = current_step
        app.updated_at = datetime.now()

        # 自动记录状态变更时间
        if new_status == "submitted" and not app.submitted_date:
            app.submitted_date = date.today()
        elif new_status in ("offer", "rejected") and not app.decision_date:
            app.decision_date = date.today()

        db.commit()
        logger.info("更新申请状态: id=%s, status=%s", application_id, new_status)
        return ApiResponse(data={"application_id": application_id, "new_status": new_status})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新申请状态失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"更新失败: {str(e)}")


# ==================== 材料清单 ====================

@router.get("/document/list", response_model=ApiResponse, summary="材料清单")
def list_documents(
    application_id: Optional[int] = Query(None, description="申请ID"),
    status: Optional[str] = Query(None, description="筛选状态"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询申请材料清单"""
    try:
        require_operator(current_user_type)
        query = db.query(DocumentChecklist)
        if application_id:
            query = query.filter(DocumentChecklist.application_id == application_id)
        if status:
            query = query.filter(DocumentChecklist.status == status)

        docs = query.order_by(DocumentChecklist.deadline.asc()).all()
        data_list = []
        for d in docs:
            data_list.append({
                "id": d.id,
                "application_id": d.application_id,
                "doc_name": d.doc_name,
                "doc_type": d.doc_type,
                "status": d.status,
                "deadline": d.deadline.isoformat() if d.deadline else None,
                "notes": d.notes,
            })
        return ApiResponse(data={"total": len(data_list), "list": data_list})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询材料清单失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


@router.put("/document/status", response_model=ApiResponse, summary="更新材料状态")
def update_document_status(
    document_id: int = Query(..., description="材料ID"),
    new_status: str = Query(..., description="新状态: pending/collected/submitted/approved"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """更新材料收集状态"""
    try:
        require_operator(current_user_type)
        doc = db.query(DocumentChecklist).filter(DocumentChecklist.id == document_id).first()
        if not doc:
            return ApiResponse(code=404, msg="材料记录不存在")

        doc.status = new_status
        if new_status == "collected" and not doc.collected_at:
            doc.collected_at = datetime.now()
        doc.updated_at = datetime.now()
        db.commit()

        return ApiResponse(data={"document_id": document_id, "new_status": new_status})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("更新材料状态失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"更新失败: {str(e)}")


# ==================== 咨询预约 ====================

@router.get("/appointment/list", response_model=ApiResponse, summary="预约列表")
def list_appointments(
    student_id: Optional[int] = Query(None, description="学生ID"),
    status: Optional[str] = Query(None, description="筛选状态"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询咨询预约记录"""
    try:
        require_operator(current_user_type)
        query = db.query(Appointment)
        if student_id:
            query = query.filter(Appointment.student_id == student_id)
        if status:
            query = query.filter(Appointment.status == status)

        apps = query.order_by(Appointment.appointment_date.desc()).all()
        data_list = []
        for a in apps:
            data_list.append({
                "id": a.id,
                "student_id": a.student_id,
                "consultant_id": a.consultant_id,
                "appointment_type": a.appointment_type,
                "appointment_date": a.appointment_date.strftime("%Y-%m-%d %H:%M") if a.appointment_date else None,
                "status": a.status,
                "notes": a.notes,
            })
        return ApiResponse(data={"total": len(data_list), "list": data_list})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询预约列表失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


@router.post("/appointment/create", response_model=ApiResponse, summary="创建预约")
def create_appointment(
    student_id: int = Query(..., description="学生ID"),
    appointment_type: str = Query("咨询", description="预约类型"),
    appointment_date: str = Query(..., description="预约时间 YYYY-MM-DD HH:MM"),
    consultant_id: Optional[int] = Query(None, description="顾问ID"),
    notes: str = Query("", description="备注"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """创建咨询预约"""
    try:
        require_operator(current_user_type)
        try:
            apt_time = datetime.strptime(appointment_date, "%Y-%m-%d %H:%M")
        except ValueError:
            return ApiResponse(code=400, msg="时间格式错误，请使用 YYYY-MM-DD HH:MM 格式")

        apt = Appointment(
            student_id=student_id,
            consultant_id=consultant_id or current_user_id,
            appointment_type=appointment_type,
            appointment_date=apt_time,
            status="scheduled",
            notes=notes,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(apt)
        db.flush()
        db.commit()

        return ApiResponse(data={"appointment_id": apt.id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建预约失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"创建失败: {str(e)}")


# ==================== 学生信息查询 ====================

@router.get("/student/list", response_model=ApiResponse, summary="学生列表")
def list_students(
    keyword: Optional[str] = Query(None, description="搜索姓名/电话/学号"),
    status: Optional[str] = Query(None, description="在读状态：在读/休学/毕业/退学"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """
    查询学生信息列表
    所有员工/管理者可查看，学员和游客不可查看
    """
    try:
        require_operator(current_user_type)

        query = db.query(StudentInfo)

        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            query = query.filter(
                (StudentInfo.name.like(kw)) |
                (StudentInfo.phone.like(kw)) |
                (StudentInfo.student_no.like(kw)) |
                (StudentInfo.school.like(kw)) |
                (StudentInfo.major.like(kw)) |
                (StudentInfo.project_name.like(kw))
            )
        if status:
            query = query.filter(StudentInfo.status == status)

        total = query.count()
        students = query.order_by(StudentInfo.id.asc()).offset(
            (page - 1) * page_size).limit(page_size).all()

        data_list = []
        for s in students:
            # 查关联的顾问姓名
            consultant_name = None
            if s.consultant_id:
                from enterprise_agent.models import Employee
                teacher = db.query(Employee.emp_name).filter(
                    Employee.emp_id == s.consultant_id,
                ).first()
                if not teacher:
                    teacher = db.query(Account.real_name).filter(
                        Account.user_id == s.consultant_id,
                    ).first()
                if teacher:
                    consultant_name = teacher[0]

            data_list.append({
                "id": s.id,
                "name": s.name,
                "phone": s.phone,
                "gender": s.gender,
                "email": s.email,
                "education": s.education,
                "school": s.school,
                "major": s.major,
                "project_name": s.project_name,
                "student_no": s.student_no,
                "status": s.status,
                "language_exam": s.language_exam,
                "language_score": float(s.language_score) if s.language_score else None,
                "consultant_name": consultant_name,
                "enroll_date": s.enroll_date.isoformat() if s.enroll_date else None,
                "create_time": s.create_time.strftime("%Y-%m-%d") if s.create_time else None,
            })

        return ApiResponse(data={
            "total": total, "page": page, "page_size": page_size, "list": data_list,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询学生列表失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


@router.get("/student/{student_id}", response_model=ApiResponse, summary="学生详情")
def get_student(
    student_id: int,
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询单个学生详细信息（来自 student_info 表）"""
    try:
        require_operator(current_user_type)

        s = db.query(StudentInfo).filter(StudentInfo.id == student_id).first()
        if not s:
            return ApiResponse(code=404, msg="学生不存在")

        # 查顾问姓名
        consultant_name = None
        if s.consultant_id:
            from enterprise_agent.models import Employee
            teacher = db.query(Employee.emp_name).filter(
                Employee.emp_id == s.consultant_id,
            ).first()
            if not teacher:
                teacher = db.query(Account.real_name).filter(
                    Account.user_id == s.consultant_id,
                ).first()
            if teacher:
                consultant_name = teacher[0]

        return ApiResponse(data={
            "id": s.id,
            "name": s.name,
            "gender": s.gender,
            "phone": s.phone,
            "email": s.email,
            "wechat": s.wechat,
            "birth_date": s.birth_date.isoformat() if s.birth_date else None,
            "id_card": s.id_card,
            "education": s.education,
            "school": s.school,
            "major": s.major,
            "graduation_year": s.graduation_year,
            "language_exam": s.language_exam,
            "language_score": float(s.language_score) if s.language_score else None,
            "project_name": s.project_name,
            "enroll_date": s.enroll_date.isoformat() if s.enroll_date else None,
            "student_no": s.student_no,
            "status": s.status,
            "consultant_id": s.consultant_id,
            "consultant_name": consultant_name,
            "remark": s.remark,
            "create_time": s.create_time.strftime("%Y-%m-%d %H:%M:%S") if s.create_time else None,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询学生详情失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")
