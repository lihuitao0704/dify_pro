"""
心理健康管理路由
GET    /api/agent/mental/alerts       - 心理预警列表（管理者看全部，教师看自己的学生）
PUT    /api/agent/mental/handle       - 处理预警（更新处理状态）
GET    /api/agent/mental/profile/{student_id} - 学生心理档案
POST   /api/agent/mental/record       - 记录心理观测
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from enterprise_agent.database import get_db
from enterprise_agent.models import StudentMentalAlert, MentalHealthProfile, StudentPsychRecord, Student
from enterprise_agent.schemas import ApiResponse
from enterprise_agent.utils import require_operator, is_manager

logger = logging.getLogger("enterprise_agent.mental_health")
router = APIRouter()


@router.get("/mental/alerts", response_model=ApiResponse, summary="心理预警列表")
def list_mental_alerts(
    risk_level: Optional[str] = Query(None, description="筛选风险等级：low/medium/high"),
    status: Optional[str] = Query(None, description="处理状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询心理预警列表"""
    try:
        require_operator(current_user_type)

        query = db.query(StudentMentalAlert)

        if risk_level:
            query = query.filter(StudentMentalAlert.risk_level == risk_level)
        if status:
            query = query.filter(StudentMentalAlert.follow_up_status == status)

        total = query.count()
        alerts = query.order_by(StudentMentalAlert.created_at.desc()).offset(
            (page - 1) * page_size).limit(page_size).all()

        data_list = []
        for a in alerts:
            data_list.append({
                "id": a.id,
                "student_id": a.student_id,
                "student_name": a.student_name,
                "trigger_reason": a.trigger_reason,
                "risk_level": a.risk_level,
                "emotion_label": a.emotion_label,
                "risk_score": a.risk_score,
                "follow_up_status": a.follow_up_status or "待处理",
                "assigned_teacher": a.assigned_teacher,
                "created_at": a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else None,
            })

        return ApiResponse(data={"total": total, "page": page, "page_size": page_size, "list": data_list})

    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询预警失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


@router.put("/mental/handle", response_model=ApiResponse, summary="处理心理预警")
def handle_mental_alert(
    alert_id: int = Query(..., description="预警ID"),
    action_taken: str = Query("", description="处理措施"),
    follow_up_status: str = Query("处理中", description="处理状态"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """处理心理预警"""
    try:
        require_operator(current_user_type)

        alert = db.query(StudentMentalAlert).filter(StudentMentalAlert.id == alert_id).first()
        if not alert:
            return ApiResponse(code=404, msg="预警记录不存在")

        alert.follow_up_status = follow_up_status
        if action_taken:
            alert.action_taken = action_taken
        if follow_up_status == "已完结":
            alert.resolved_at = datetime.now()
        db.commit()

        logger.info("预警处理: id=%s, status=%s", alert_id, follow_up_status)
        return ApiResponse(data={"alert_id": alert_id, "status": follow_up_status})

    except HTTPException:
        raise
    except Exception as e:
        logger.error("处理预警失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"处理失败: {str(e)}")


@router.get("/mental/profile/{student_id}", response_model=ApiResponse, summary="学生心理档案")
def get_mental_profile(
    student_id: int,
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询学生心理档案"""
    try:
        require_operator(current_user_type)

        profile = db.query(MentalHealthProfile).filter(
            MentalHealthProfile.student_id == student_id
        ).first()

        student = db.query(Student).filter(Student.id == student_id).first()
        if not profile:
            return ApiResponse(data={
                "student_id": student_id,
                "student_name": student.name if student else "未知",
                "message": "暂无档案数据",
            })

        return ApiResponse(data={
            "student_id": profile.student_id,
            "student_name": student.name if student else "未知",
            "current_emotion": profile.current_emotion,
            "risk_level": profile.risk_level,
            "risk_score": profile.risk_score,
            "consecutive_negative_days": profile.consecutive_negative_days,
            "last_assessment_at": profile.last_assessment_at.strftime("%Y-%m-%d %H:%M:%S") if profile.last_assessment_at else None,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询档案失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


@router.post("/mental/record", response_model=ApiResponse, summary="记录心理观测")
def record_mental_observation(
    student_id: int = Query(..., description="学生ID"),
    emotion_tag: str = Query("", description="情绪标签"),
    emotion_score: int = Query(0, ge=0, le=100, description="情绪评分(0-100)"),
    interaction_content: str = Query("", description="沟通内容"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """记录心理观测数据"""
    try:
        require_operator(current_user_type)

        record = StudentPsychRecord(
            student_id=student_id,
            emotion_tag=emotion_tag,
            emotion_score=emotion_score,
            interaction_content=interaction_content,
            record_date=datetime.now().date(),
            create_time=datetime.now(),
        )
        db.add(record)
        db.flush()
        db.commit()

        logger.info("心理观测记录: student=%s, emotion=%s, score=%s", student_id, emotion_tag, emotion_score)
        return ApiResponse(data={"record_id": record.id})

    except HTTPException:
        raise
    except Exception as e:
        logger.error("记录失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"记录失败: {str(e)}")
