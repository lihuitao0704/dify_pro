"""
日报管理路由
POST  /api/agent/report/submit  - 提交日报
GET   /api/agent/report/list    - 查询日报列表
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import logging

from enterprise_agent.database import get_db
from enterprise_agent.models import EmployeeDailyReport, Account
from enterprise_agent.schemas import ApiResponse, ReportSubmitRequest
from enterprise_agent.utils import require_operator, is_manager, parse_date

logger = logging.getLogger("enterprise_agent.report")
router = APIRouter()


# ==================== POST /api/agent/report/submit ====================
@router.post("/report/submit", response_model=ApiResponse, summary="提交日报")
def submit_report(req: ReportSubmitRequest, db: Session = Depends(get_db)):
    """
    提交日报
    user_id 和 dept_id 从 account 表查询
    """
    try:
        require_operator(req.current_user_type)

        # 从 account 表查询用户信息
        account = db.query(Account).filter(
            Account.user_id == req.current_user_id,
            Account.status == 1,
        ).first()

        if not account:
            return ApiResponse(code=404, msg="用户不存在或已禁用")

        # 员工必须有部门ID
        if not account.dept_id:
            return ApiResponse(code=400, msg="当前用户未分配部门，无法提交日报")

        # 校验日期
        try:
            report_date = parse_date(req.report_date, "汇报日期")
        except HTTPException as e:
            return ApiResponse(code=400, msg=e.detail)

        # 检查是否已提交过该日报
        existing = db.query(EmployeeDailyReport).filter(
            EmployeeDailyReport.user_id == req.current_user_id,
            EmployeeDailyReport.report_date == report_date,
        ).first()
        if existing:
            return ApiResponse(code=400, msg=f"{req.report_date} 的日报已提交，请勿重复提交")

        report = EmployeeDailyReport(
            user_id=req.current_user_id,
            dept_id=account.dept_id,
            report_content=req.report_content.strip(),
            submit_time=datetime.now(),
            report_date=report_date,
            create_time=datetime.now(),
            update_time=datetime.now(),
        )
        db.add(report)
        db.flush()
        db.commit()

        logger.info(f"日报提交成功: ID={report.id}, 用户ID={req.current_user_id}, 日期={req.report_date}")
        return ApiResponse(data={"report_id": report.id})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提交日报失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"提交失败: {str(e)}")


# ==================== GET /api/agent/report/list ====================
@router.get("/report/list", response_model=ApiResponse, summary="查询日报列表")
def list_report(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """
    查询日报列表
    - 员工：只看自己的
    - 管理者：看全部
    支持 start_date/end_date 筛选
    """
    try:
        require_operator(current_user_type)
        is_mgr = is_manager(current_user_type)

        query = db.query(EmployeeDailyReport)

        # 员工只看自己的
        if not is_mgr:
            query = query.filter(EmployeeDailyReport.user_id == current_user_id)

        # 日期筛选
        if start_date:
            try:
                sd = parse_date(start_date, "开始日期")
                query = query.filter(EmployeeDailyReport.report_date >= sd)
            except HTTPException as e:
                return ApiResponse(code=400, msg=e.detail)

        if end_date:
            try:
                ed = parse_date(end_date, "结束日期")
                query = query.filter(EmployeeDailyReport.report_date <= ed)
            except HTTPException as e:
                return ApiResponse(code=400, msg=e.detail)

        # 排序
        query = query.order_by(EmployeeDailyReport.report_date.desc(), EmployeeDailyReport.submit_time.desc())

        # 分页
        total = query.count()
        reports = query.offset((page - 1) * page_size).limit(page_size).all()

        data_list = []
        for r in reports:
            data_list.append({
                "id": r.id,
                "user_id": r.user_id,
                "dept_id": r.dept_id,
                "report_content": r.report_content,
                "submit_time": r.submit_time.strftime("%Y-%m-%d %H:%M:%S") if r.submit_time else None,
                "report_date": r.report_date.strftime("%Y-%m-%d") if r.report_date else None,
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
        logger.error(f"查询日报列表失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")
