from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LeaveApplication
from app.schemas import StudentLeaveRequest, EmployeeLeaveRequest, BatchApproveRequest
from app.routers import check_permission, get_account

router = APIRouter()


@router.post("/leave/student")
def add_student_leave(req: StudentLeaveRequest, db: Session = Depends(get_db)):
    """替学生请假（员工/管理者可操作）"""
    try:
        if not check_permission(req.current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        start = datetime.strptime(req.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(req.end_date, "%Y-%m-%d").date()

        leave = LeaveApplication(
            student_name=req.student_name,
            leave_type=req.leave_type,
            start_date=start,
            end_date=end,
            reason=req.reason,
            applicant_type="学生",
            applicant_id=0,
            status=0,
        )
        db.add(leave)
        db.commit()
        db.refresh(leave)
        return {"code": 0, "msg": "success", "data": {"leave_id": leave.id}}
    except Exception as e:
        db.rollback()
        return {"code": 500, "msg": str(e), "data": None}


@router.post("/leave/employee")
def add_employee_leave(req: EmployeeLeaveRequest, db: Session = Depends(get_db)):
    """员工自己请假（员工/管理者可操作）"""
    try:
        if not check_permission(req.current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        start = datetime.strptime(req.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(req.end_date, "%Y-%m-%d").date()

        leave = LeaveApplication(
            leave_type=req.leave_type,
            start_date=start,
            end_date=end,
            reason=req.reason,
            applicant_type="员工",
            applicant_id=req.current_user_id,
            status=0,
        )
        db.add(leave)
        db.commit()
        db.refresh(leave)
        return {"code": 0, "msg": "success", "data": {"leave_id": leave.id}}
    except Exception as e:
        db.rollback()
        return {"code": 500, "msg": str(e), "data": None}


@router.post("/leave/batch_approve")
def batch_approve_leave(req: BatchApproveRequest, db: Session = Depends(get_db)):
    """批量审批请假（仅管理者）"""
    try:
        if req.current_user_type != "管理者":
            return {"code": 403, "msg": "仅管理者可审批", "data": None}

        # 查当前用户的 real_name
        user = get_account(db, req.current_user_id)
        approval_user = user.real_name if user else "未知"

        if req.action == "approve":
            new_status = 1
        elif req.action == "reject":
            new_status = 2
        else:
            return {"code": 400, "msg": "action 参数无效，请使用 approve 或 reject", "data": None}

        updated = (
            db.query(LeaveApplication)
            .filter(LeaveApplication.id.in_(req.leave_ids))
            .update(
                {"status": new_status, "approval_user": approval_user},
                synchronize_session=False,
            )
        )
        db.commit()
        return {"code": 0, "msg": "success", "data": {"updated_count": updated}}
    except Exception as e:
        db.rollback()
        return {"code": 500, "msg": str(e), "data": None}


@router.get("/leave/todo")
def todo_list(
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询待办审批列表"""
    try:
        if not check_permission(current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        if current_user_type == "员工":
            # 员工看自己提交的请假单
            query = db.query(LeaveApplication).filter(
                LeaveApplication.applicant_id == current_user_id,
                LeaveApplication.applicant_type == "员工",
            )
        else:
            # 管理者看全部待审批的
            query = db.query(LeaveApplication).filter(LeaveApplication.status == 0)

        leaves = query.order_by(LeaveApplication.create_time.desc()).all()

        data = [
            {
                "id": l.id,
                "student_name": l.student_name,
                "leave_type": l.leave_type,
                "start_date": l.start_date.strftime("%Y-%m-%d") if l.start_date else None,
                "end_date": l.end_date.strftime("%Y-%m-%d") if l.end_date else None,
                "reason": l.reason,
                "applicant_type": l.applicant_type,
                "applicant_id": l.applicant_id,
                "status": l.status,
                "approval_user": l.approval_user,
                "create_time": l.create_time.strftime("%Y-%m-%d %H:%M:%S") if l.create_time else None,
            }
            for l in leaves
        ]
        return {"code": 0, "msg": "success", "data": data}
    except Exception as e:
        return {"code": 500, "msg": str(e), "data": None}
