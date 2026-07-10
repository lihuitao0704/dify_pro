from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmployeeDailyReport
from app.schemas import ReportSubmitRequest
from app.routers import check_permission, get_account

router = APIRouter()


@router.post("/report/submit")
def submit_report(req: ReportSubmitRequest, db: Session = Depends(get_db)):
    """提交日报"""
    try:
        if not check_permission(req.current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        # 从 account 表查当前用户的部门
        user = get_account(db, req.current_user_id)
        dept_id = user.dept_id if user else None

        # 解析日期
        report_date = datetime.strptime(req.report_date, "%Y-%m-%d").date()

        report = EmployeeDailyReport(
            user_id=req.current_user_id,
            dept_id=dept_id,
            report_content=req.report_content,
            report_date=report_date,
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return {"code": 0, "msg": "success", "data": {"report_id": report.id}}
    except Exception as e:
        db.rollback()
        return {"code": 500, "msg": str(e), "data": None}


@router.get("/report/list")
def list_reports(
    start_date: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询日报列表"""
    try:
        if not check_permission(current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        query = db.query(EmployeeDailyReport)

        # 员工只看自己的
        if current_user_type == "员工":
            query = query.filter(EmployeeDailyReport.user_id == current_user_id)

        # 日期范围筛选
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            query = query.filter(EmployeeDailyReport.report_date >= start)
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(EmployeeDailyReport.report_date <= end)

        reports = query.order_by(EmployeeDailyReport.report_date.desc()).all()

        data = [
            {
                "id": r.id,
                "user_id": r.user_id,
                "dept_id": r.dept_id,
                "report_content": r.report_content,
                "report_date": r.report_date.strftime("%Y-%m-%d") if r.report_date else None,
                "create_time": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else None,
            }
            for r in reports
        ]
        return {"code": 0, "msg": "success", "data": data}
    except Exception as e:
        return {"code": 500, "msg": str(e), "data": None}
