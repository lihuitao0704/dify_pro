"""
请假管理路由
POST   /api/agent/leave/student        - 替学生请假
POST   /api/agent/leave/employee       - 员工自己请假
POST   /api/agent/leave/batch_approve  - 批量审批（仅管理者）
GET    /api/agent/leave/todo           - 待审批列表
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import logging

from enterprise_agent.database import get_db
from enterprise_agent.models import LeaveApplication, Account
from enterprise_agent.schemas import (
    ApiResponse, LeaveStudentRequest, LeaveEmployeeRequest,
    LeaveBatchApproveRequest
)
from enterprise_agent.utils import require_operator, is_manager, parse_and_validate_dates

logger = logging.getLogger("enterprise_agent.leave")
router = APIRouter()

# 合法请假类型（两处复用，提为常量避免不一致）
VALID_LEAVE_TYPES = ("事假", "病假", "年假", "其他")


# ==================== POST /api/agent/leave/student ====================
@router.post("/leave/student", response_model=ApiResponse, summary="替学生请假")
def leave_student(req: LeaveStudentRequest, db: Session = Depends(get_db)):
    """
    替学生请假（员工/管理者操作）
    applicant_type='学生'，applicant_id 使用当前操作人ID（员工代填）
    student_name 记录学生姓名
    """
    try:
        require_operator(req.current_user_type)

        # 校验请假类型
        if req.leave_type not in VALID_LEAVE_TYPES:
            return ApiResponse(code=400, msg=f"无效请假类型，可选：{', '.join(VALID_LEAVE_TYPES)}")

        # 校验日期
        try:
            start, end = parse_and_validate_dates(req.start_date, req.end_date)
        except HTTPException as e:
            return ApiResponse(code=400, msg=e.detail)

        # 自动匹配审批人：查学生所属的辅导员/顾问
        approver_name = None
        try:
            from enterprise_agent.models import Student
            student_name = req.student_name.strip()
            stu = db.query(Student).filter(
                Student.name == student_name,
            ).first()
            if stu and stu.assigned_teacher_id:
                # 先查 Employee 表
                teacher = db.query(Employee).filter(
                    Employee.emp_id == stu.assigned_teacher_id,
                ).first()
                if teacher:
                    approver_name = teacher.emp_name
                else:
                    # 再查 Account 表
                    tea_acc = db.query(Account).filter(
                        Account.user_id == stu.assigned_teacher_id,
                    ).first()
                    if tea_acc:
                        approver_name = tea_acc.real_name

            # 兜底：学生无辅导员 → 找学生所在部门的负责人
            if not approver_name and stu:
                try:
                    stu_dept = db.query(Department).filter(
                        Department.manager_id.isnot(None),
                    ).first()
                    if stu_dept:
                        mgr = db.query(Employee).filter(
                            Employee.emp_id == stu_dept.manager_id,
                        ).first()
                        if mgr:
                            approver_name = mgr.emp_name
                except Exception:
                    pass
        except Exception:
            pass  # 查不到审批人不影响请假提交

        leave = LeaveApplication(
            leave_type=req.leave_type,
            start_date=start,
            end_date=end,
            reason=req.reason,
            status=0,
            student_name=req.student_name.strip(),
            applicant_type="学生",
            applicant_id=req.current_user_id,  # 操作人ID
            approval_user=approver_name,  # 预填审批人
            create_time=datetime.now(),
            update_time=datetime.now(),
        )
        db.add(leave)
        db.flush()
        db.commit()

        logger.info(f"替学生请假成功: ID={leave.id}, 学生={req.student_name}")
        return ApiResponse(data={"leave_id": leave.id})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"替学生请假失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"请假失败: {str(e)}")


# ==================== POST /api/agent/leave/employee ====================
@router.post("/leave/employee", response_model=ApiResponse, summary="员工自己请假")
def leave_employee(req: LeaveEmployeeRequest, db: Session = Depends(get_db)):
    """
    员工/管理者自己请假
    applicant_type='员工'，applicant_id = current_user_id
    """
    try:
        require_operator(req.current_user_type)

        # 校验请假类型
        if req.leave_type not in VALID_LEAVE_TYPES:
            return ApiResponse(code=400, msg=f"无效请假类型，可选：{', '.join(VALID_LEAVE_TYPES)}")

        # 校验日期
        try:
            start, end = parse_and_validate_dates(req.start_date, req.end_date)
        except HTTPException as e:
            return ApiResponse(code=400, msg=e.detail)

        # 从 Account 表查员工真实姓名和部门
        emp_account = db.query(Account).filter(
            Account.user_id == req.current_user_id,
        ).first()
        emp_name = emp_account.real_name if emp_account else f"用户{req.current_user_id}"

        # 自动匹配审批人：查员工所属部门的负责人
        approver_name = None
        if emp_account and emp_account.dept_id:
            from enterprise_agent.models import Department, Employee
            dept = db.query(Department).filter(
                Department.dept_id == emp_account.dept_id,
                Department.manager_id.isnot(None),
            ).first()
            if dept:
                mgr = db.query(Employee).filter(
                    Employee.emp_id == dept.manager_id,
                    Employee.status == 1,
                ).first()
                if mgr:
                    # 防止自己审批自己（部门负责人请假时转给其他部门）
                    if mgr.emp_name == emp_name:
                        fallback = db.query(Account.real_name).filter(
                            Account.user_type == "管理者",
                            Account.real_name != emp_name,
                        ).first()
                        approver_name = fallback[0] if fallback else None
                    else:
                        approver_name = mgr.emp_name
                else:
                    mgr_acc = db.query(Account).filter(
                        Account.user_id == dept.manager_id,
                    ).first()
                    if mgr_acc:
                        approver_name = mgr_acc.real_name if mgr_acc.real_name != emp_name else None

        leave = LeaveApplication(
            leave_type=req.leave_type,
            start_date=start,
            end_date=end,
            reason=req.reason,
            status=0,
            student_name=emp_name,  # 员工也填上姓名，方便列表展示
            applicant_type="员工",
            applicant_id=req.current_user_id,
            approval_user=approver_name,  # 预填审批人
            create_time=datetime.now(),
            update_time=datetime.now(),
        )
        db.add(leave)
        db.flush()
        db.commit()

        logger.info(f"员工请假成功: ID={leave.id}, 用户ID={req.current_user_id}")
        return ApiResponse(data={"leave_id": leave.id})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"员工请假失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"请假失败: {str(e)}")


# ==================== POST /api/agent/leave/batch_approve ====================
@router.post("/leave/batch_approve", response_model=ApiResponse, summary="批量审批（仅管理者）")
def batch_approve_leave(req: LeaveBatchApproveRequest, db: Session = Depends(get_db)):
    """
    批量审批请假（仅管理者可操作）
    action=approve 通过，action=reject 驳回
    """
    try:
        # 从数据库核实管理者身份（不信前端传参）
        approver = db.query(Account).filter(
            Account.user_id == req.current_user_id,
            Account.status == 1,
        ).first()
        if not approver or approver.user_type != "管理者":
            return ApiResponse(code=403, msg="权限不足：仅管理者可审批")

        if not req.leave_ids:
            return ApiResponse(code=400, msg="请假ID列表不能为空")

        if len(req.leave_ids) > 50:
            return ApiResponse(code=400, msg="单次最多审批 50 条记录")

        # 只查询指派给当前审批人的待审批记录
        leaves = db.query(LeaveApplication).filter(
            LeaveApplication.id.in_(req.leave_ids),
            LeaveApplication.status == 0,
            LeaveApplication.approval_user == approver.real_name,
        ).all()

        # 找出哪些ID不在待审批列表中（已被处理、不存在、或不属于自己审批）
        found_ids = {lv.id for lv in leaves}
        skipped_ids = [i for i in req.leave_ids if i not in found_ids]

        if not leaves:
            detail = "所有指定的请假ID均非待审批状态（可能已被处理）" if skipped_ids else "未找到待审批的申请记录"
            return ApiResponse(code=409, msg=detail)

        # 复用上面已查到的审批人信息
        approver_name = approver.real_name or f"用户{req.current_user_id}"

        new_status = 1 if req.action == "approve" else 2
        action_label = "通过" if req.action == "approve" else "驳回"
        now = datetime.now()

        approved_ids = []
        for leave in leaves:
            leave.status = new_status
            leave.approval_user = approver_name
            leave.update_time = now
            approved_ids.append(leave.id)

        db.commit()
        logger.info("批量审批完成: %s了 %d 条记录", action_label, len(approved_ids))

        result = {
            "action": action_label,
            "count": len(approved_ids),
            "leave_ids": approved_ids,
        }
        if skipped_ids:
            result["skipped_ids"] = skipped_ids
            result["warning"] = f"以下ID非待审批状态，已跳过: {skipped_ids}"

        return ApiResponse(data=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量审批失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"审批失败: {str(e)}")


# ==================== GET /api/agent/leave/todo ====================
@router.get("/leave/todo", response_model=ApiResponse, summary="待审批列表")
def todo_leave(
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """
    待审批列表
    - 管理者：仅查看自己管辖范围内的申请（approval_user 匹配自己姓名）
    - 员工：查看自己提交的申请
    """
    try:
        require_operator(current_user_type)
        is_mgr = is_manager(current_user_type)

        # 查当前用户的真实姓名（用于过滤审批范围）
        cur_account = db.query(Account.real_name).filter(
            Account.user_id == current_user_id,
        ).first()
        cur_real_name = cur_account[0] if cur_account else None

        # LEFT JOIN Account 表获取员工申请人姓名（一次性查询，消灭 N+1）
        query_with_names = db.query(
            LeaveApplication,
            Account.real_name.label("_account_real_name"),
        ).outerjoin(
            Account,
            Account.user_id == LeaveApplication.applicant_id,
        ).filter(
            LeaveApplication.status == 0,
        )

        if is_mgr and cur_real_name:
            # 管理者只看指派给自己的待审批
            query_with_names = query_with_names.filter(
                LeaveApplication.approval_user == cur_real_name,
            )
        elif is_mgr:
            # 查不到姓名→看不到任何待审批
            query_with_names = query_with_names.filter(False)
        else:
            query_with_names = query_with_names.filter(
                LeaveApplication.applicant_id == current_user_id,
            )

        rows = query_with_names.order_by(LeaveApplication.create_time.desc()).all()

        data_list = []
        for lv, acct_real_name in rows:
            applicant_name = lv.student_name or acct_real_name or f"用户{lv.applicant_id}"
            data_list.append({
                "id": lv.id,
                "student_name": lv.student_name,
                "applicant_name": applicant_name,
                "leave_type": lv.leave_type,
                "start_date": lv.start_date.strftime("%Y-%m-%d") if lv.start_date else None,
                "end_date": lv.end_date.strftime("%Y-%m-%d") if lv.end_date else None,
                "reason": lv.reason,
                "status": lv.status,
                "status_label": "待审批" if lv.status == 0 else ("已通过" if lv.status == 1 else "已驳回"),
                "applicant_type": lv.applicant_type,
                "applicant_id": lv.applicant_id,
                "create_time": lv.create_time.strftime("%Y-%m-%d %H:%M:%S") if lv.create_time else None,
            })

        return ApiResponse(data={
            "total": len(data_list),
            "list": data_list,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询待审批列表失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")
