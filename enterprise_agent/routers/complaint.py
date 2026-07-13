"""
投诉反馈路由
GET  /api/agent/complaint/list   - 查询投诉列表
PUT  /api/agent/complaint/handle - 处理投诉
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import logging

from enterprise_agent.database import get_db
from enterprise_agent.models import StudentComplaint, Account, Employee
from enterprise_agent.schemas import ApiResponse, ComplaintHandleRequest
from enterprise_agent.utils import require_operator, is_manager

logger = logging.getLogger("enterprise_agent.complaint")
router = APIRouter()

# 辅导员可处理的投诉类型
_COUNSELOR_COMPLAINT_TYPES = ("后勤", "生活服务", "服务")


def _get_user_position(db: Session, user_id: int) -> str:
    """通过 Account 关联 Employee 获取用户职位"""
    acct = db.query(Account.real_name).filter(Account.user_id == user_id).first()
    if not acct or not acct[0]:
        return ""
    emp = db.query(Employee.position).filter(Employee.emp_name == acct[0]).first()
    return emp[0] if emp else ""


# ==================== GET /api/agent/complaint/list ====================
@router.get("/complaint/list", response_model=ApiResponse, summary="查询投诉列表")
def list_complaint(
    status: Optional[str] = Query(None, description="筛选状态：待处理/处理中/已完结/驳回"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """
    查询投诉列表
    - 教务部（教务专员/教务总监）：查看全部
    - 辅导员：仅查看后勤/生活服务/服务类型的投诉
    - 其他员工：只看自己负责的（handler_user_id）
    """
    try:
        require_operator(current_user_type)
        is_mgr = is_manager(current_user_type)

        query = db.query(StudentComplaint)

        # 查当前用户的部门和职位
        acct = db.query(Account.dept_id).filter(Account.user_id == current_user_id).first()
        user_dept_id = acct[0] if acct else None
        position = _get_user_position(db, current_user_id) if is_mgr else ""

        if is_mgr and user_dept_id == 3:  # 教务部
            if position == "学生辅导员":
                # 辅导员只看后勤/生活服务/服务
                query = query.filter(
                    StudentComplaint.complaint_type.in_(_COUNSELOR_COMPLAINT_TYPES)
                )
            # 教务总监/专员 → 全部可见
        else:
            # 非教务部员工/管理者：只看自己负责的
            query = query.filter(StudentComplaint.handler_user_id == current_user_id)

        # 状态筛选
        if status:
            valid_statuses = ("待处理", "处理中", "已完结", "驳回")
            if status not in valid_statuses:
                return ApiResponse(code=400, msg=f"无效状态值，可选：{', '.join(valid_statuses)}")
            query = query.filter(StudentComplaint.handle_status == status)

        # 排序
        query = query.order_by(StudentComplaint.create_time.desc())

        # 分页
        total = query.count()
        complaints = query.offset((page - 1) * page_size).limit(page_size).all()

        data_list = []
        for c in complaints:
            data_list.append({
                "id": c.id,
                "student_id": c.student_id,
                "complaint_detail": c.complaint_detail,
                "complaint_type": c.complaint_type,
                "handle_status": c.handle_status,
                "handler_user_id": c.handler_user_id,
                "create_time": c.create_time.strftime("%Y-%m-%d %H:%M:%S") if c.create_time else None,
                "update_time": c.update_time.strftime("%Y-%m-%d %H:%M:%S") if c.update_time else None,
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
        logger.error(f"查询投诉列表失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


# ==================== PUT /api/agent/complaint/handle ====================
@router.put("/complaint/handle", response_model=ApiResponse, summary="处理投诉")
def handle_complaint(req: ComplaintHandleRequest, db: Session = Depends(get_db)):
    """
    处理投诉
    更新状态为"处理中"或"已完结"
    员工/管理者可操作，但员工只能操作自己负责的投诉
    """
    try:
        require_operator(req.current_user_type)
        is_mgr = is_manager(req.current_user_type)

        complaint = db.query(StudentComplaint).filter(
            StudentComplaint.id == req.complaint_id
        ).first()

        if not complaint:
            return ApiResponse(code=404, msg="投诉记录不存在")

        if is_mgr:
            position = _get_user_position(db, req.current_user_id)
            # 辅导员只能处理生活类投诉
            if position == "学生辅导员" and complaint.complaint_type not in _COUNSELOR_COMPLAINT_TYPES:
                return ApiResponse(code=403, msg="辅导员仅可处理后勤/生活服务/服务类型的投诉")
        elif complaint.handler_user_id and complaint.handler_user_id != req.current_user_id:
            return ApiResponse(code=403, msg="无权操作此投诉工单")

        # 更新状态
        complaint.handle_status = req.new_status

        # 如果传了 handler_user_id 则更新
        if req.handler_user_id is not None:
            complaint.handler_user_id = req.handler_user_id
        elif not complaint.handler_user_id:
            # 如果之前没有负责人，自动设为当前用户
            complaint.handler_user_id = req.current_user_id

        complaint.update_time = datetime.now()
        db.commit()

        logger.info(f"投诉处理更新: ID={req.complaint_id}, 状态={req.new_status}, 处理人={complaint.handler_user_id}")
        return ApiResponse(data={
            "complaint_id": req.complaint_id,
            "new_status": req.new_status,
            "handler_user_id": complaint.handler_user_id,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理投诉失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"处理失败: {str(e)}")
