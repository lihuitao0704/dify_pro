"""
组织架构路由
GET /api/agent/organization/tree - 查询组织架构树
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from enterprise_agent.database import get_db
from enterprise_agent.models import Department, Employee, Account
from enterprise_agent.schemas import ApiResponse

logger = logging.getLogger("enterprise_agent.organization")
router = APIRouter()


# ==================== GET /api/agent/organization/tree ====================
@router.get("/organization/tree", response_model=ApiResponse, summary="组织架构树")
def organization_tree(
    current_user_id: Optional[int] = Query(None, description="当前用户ID"),
    current_user_type: Optional[str] = Query(None, description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """
    查询组织架构树
    - 所有人可看（员工/管理者/学员/游客）
    - 返回部门+负责人+员工列表
    - 以树形结构返回（支持多级部门）
    """
    try:
        # 获取所有部门
        departments = db.query(Department).filter(Department.status == 1).order_by(
            Department.parent_dept_id, Department.dept_id
        ).all()

        if not departments:
            return ApiResponse(data={"tree": []})

        # 获取所有在职员工
        employees = db.query(Employee).filter(Employee.status == 1).all()
        emp_map = {e.emp_id: e for e in employees}

        # 构建部门树
        dept_dict = {}
        for dept in departments:
            manager_name = None
            if dept.manager_id and dept.manager_id in emp_map:
                manager_name = emp_map[dept.manager_id].emp_name

            dept_employees = []
            for emp in employees:
                if emp.dept_id == dept.dept_id:
                    dept_employees.append({
                        "emp_id": emp.emp_id,
                        "emp_name": emp.emp_name,
                        "position": emp.position,
                        "phone": emp.phone,
                        "email": emp.email,
                    })

            dept_dict[dept.dept_id] = {
                "dept_id": dept.dept_id,
                "dept_name": dept.dept_name,
                "dept_desc": dept.dept_desc,
                "manager_id": dept.manager_id,
                "manager_name": manager_name,
                "parent_dept_id": dept.parent_dept_id or 0,
                "employees": dept_employees,
                "children": [],
            }

        # 构建树（根节点 parent_dept_id=0）
        tree = []
        for dept_id, dept in dept_dict.items():
            parent_id = dept["parent_dept_id"]
            if parent_id == 0 or parent_id not in dept_dict:
                tree.append(dept)
            else:
                if dept_id != parent_id:
                    dept_dict[parent_id]["children"].append(dept)

        return ApiResponse(data={"tree": tree})

    except Exception as e:
        logger.error("组织架构查询失败: %s", e, exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")
