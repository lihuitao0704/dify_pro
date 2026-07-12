"""
待办汇总路由
GET /api/agent/todo/all - 查询全部待办
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
import logging

from enterprise_agent.database import get_db
from enterprise_agent.models import LeaveApplication, StudentComplaint
from enterprise_agent.schemas import ApiResponse
from enterprise_agent.utils import require_operator

logger = logging.getLogger("enterprise_agent.todo")
router = APIRouter()


# ==================== GET /api/agent/todo/all ====================
@router.get("/todo/all", response_model=ApiResponse, summary="查询全部待办")
def todo_all(
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """
    查询全部待办
    - 管理者：查看全部待审批请假 + 待处理投诉
    - 员工：查看自己提交的待审批请假 + 待处理投诉
    - 返回合并列表 + 总数 total
    """
    require_operator(current_user_type)
    try:
        is_mgr = current_user_type == "管理者"
        items = []

        # ===== 1. 查询待审批请假 =====
        leave_query = db.query(LeaveApplication).filter(LeaveApplication.status == 0)
        if not is_mgr:
            leave_query = leave_query.filter(LeaveApplication.applicant_id == current_user_id)

        pending_leaves = leave_query.order_by(LeaveApplication.create_time.desc()).all()
        for lv in pending_leaves:
            items.append({
                "todo_type": "请假审批",
                "todo_id": lv.id,
                "title": f"{lv.applicant_type}请假",
                "detail": f"类型：{lv.leave_type}，{lv.start_date} 至 {lv.end_date}",
                "applicant_type": lv.applicant_type,
                "applicant_id": lv.applicant_id,
                "status": "待审批",
                "create_time": lv.create_time.strftime("%Y-%m-%d %H:%M:%S") if lv.create_time else None,
            })

        # ===== 2. 查询待处理投诉 =====
        complaint_query = db.query(StudentComplaint).filter(
            StudentComplaint.handle_status.in_(["待处理", "处理中"])
        )
        if not is_mgr:
            # 员工查看自己负责的投诉
            complaint_query = complaint_query.filter(
                StudentComplaint.handler_user_id == current_user_id
            )

        pending_complaints = complaint_query.order_by(StudentComplaint.create_time.desc()).all()
        for cp in pending_complaints:
            items.append({
                "todo_type": "投诉处理",
                "todo_id": cp.id,
                "title": f"投诉工单 #{cp.id}",
                "detail": cp.complaint_detail[:100] if cp.complaint_detail else "",
                "student_id": cp.student_id,
                "status": cp.handle_status,
                "create_time": cp.create_time.strftime("%Y-%m-%d %H:%M:%S") if cp.create_time else None,
            })

        # 按创建时间排序（最新在前）
        items.sort(key=lambda x: x.get("create_time") or "", reverse=True)

        return ApiResponse(data={
            "total": len(items),
            "leave_pending": len(pending_leaves),
            "complaint_pending": len(pending_complaints),
            "list": items,
        })

    except Exception as e:
        logger.error("查询待办汇总失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


# ==================== GET /api/agent/todo/pending_summary ====================
@router.get("/todo/pending_summary", response_model=ApiResponse, summary="主动待办推送摘要")
def todo_pending_summary():
    """
    获取待办推送摘要（供前端轮询或主动推送使用）
    返回各类待办的数量统计和提示文案
    """
    try:
        from enterprise_agent.todo_scheduler import get_pending_summary
        todos = get_pending_summary()
        total = sum(t.get("count", 0) for t in todos)
        return ApiResponse(data={
            "total": total,
            "has_pending": total > 0,
            "items": todos,
            "tip": f"您有 {total} 条待办事项需要处理" if total > 0 else "暂无待办事项",
        })
    except Exception as e:
        logger.error("查询待办推送摘要失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")
