"""
成绩管理路由
POST /api/agent/score/add  - 录入成绩
GET  /api/agent/score/list - 查询成绩
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import logging

from enterprise_agent.database import get_db
from enterprise_agent.models import StudentScore
from enterprise_agent.schemas import ApiResponse, ScoreAddRequest
from enterprise_agent.utils import require_operator

logger = logging.getLogger("enterprise_agent.score")
router = APIRouter()


# ==================== POST /api/agent/score/add ====================
@router.post("/score/add", response_model=ApiResponse, summary="录入成绩")
def add_score(req: ScoreAddRequest, db: Session = Depends(get_db)):
    """
    录入成绩
    仅员工/管理者可操作，admin_user_id 自动设为当前用户
    """
    try:
        check_permission(req.current_user_type)

        # 校验分数范围
        if req.score < 0 or req.score > 100:
            return ApiResponse(code=400, msg="分数必须在0-100之间")

        if not req.subject or not req.subject.strip():
            return ApiResponse(code=400, msg="科目不能为空")

        # 解析考试日期
        exam_date = None
        if req.exam_date:
            try:
                exam_date = datetime.strptime(req.exam_date, "%Y-%m-%d").date()
            except ValueError:
                return ApiResponse(code=400, msg="考试日期格式错误，请使用 YYYY-MM-DD 格式")

        score = StudentScore(
            student_id=req.student_id,
            subject=req.subject.strip(),
            score=req.score,
            exam_type=req.exam_type,
            exam_date=exam_date,
            admin_user_id=req.current_user_id,
            input_time=datetime.now(),
            create_time=datetime.now(),
            update_time=datetime.now(),
        )
        db.add(score)
        db.flush()

        logger.info(f"成绩录入成功: ID={score.id}, 学生ID={req.student_id}, 科目={req.subject}")
        return ApiResponse(data={"score_id": score.id})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"录入成绩失败: {e}", exc_info=True)
        # 检查唯一键冲突
        if "Duplicate entry" in str(e):
            return ApiResponse(code=400, msg=f"该学生的 {req.subject} 成绩已存在，请勿重复录入")
        return ApiResponse(code=500, msg=f"录入失败: {str(e)}")


# ==================== GET /api/agent/score/list ====================
@router.get("/score/list", response_model=ApiResponse, summary="查询成绩")
def list_score(
    student_id: Optional[int] = Query(None, description="学生ID"),
    subject: Optional[str] = Query(None, description="科目"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """
    查询成绩列表
    员工/管理者可查看，支持按 student_id 和 subject 筛选
    """
    try:
        check_permission(current_user_type)

        query = db.query(StudentScore)

        if student_id is not None:
            query = query.filter(StudentScore.student_id == student_id)

        if subject:
            query = query.filter(StudentScore.subject == subject)

        # 排序
        query = query.order_by(StudentScore.input_time.desc())

        # 分页
        total = query.count()
        scores = query.offset((page - 1) * page_size).limit(page_size).all()

        data_list = []
        for s in scores:
            data_list.append({
                "id": s.id,
                "student_id": s.student_id,
                "subject": s.subject,
                "score": float(s.score) if s.score else None,
                "exam_type": s.exam_type,
                "exam_date": s.exam_date.strftime("%Y-%m-%d") if s.exam_date else None,
                "admin_user_id": s.admin_user_id,
                "input_time": s.input_time.strftime("%Y-%m-%d %H:%M:%S") if s.input_time else None,
            })

        return ApiResponse(data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "list": data_list,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询成绩失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")
