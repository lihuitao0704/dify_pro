from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Organization
from app.routers import check_permission

router = APIRouter()


@router.get("/organization/tree")
def organization_tree(
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询组织架构树"""
    try:
        if not check_permission(current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        orgs = (
            db.query(Organization)
            .filter(Organization.status == 1)
            .order_by(Organization.sort_order, Organization.id)
            .all()
        )

        # 构建字典方便查找
        org_dict: dict[int, dict] = {}
        for org in orgs:
            org_dict[org.id] = {
                "id": org.id,
                "org_name": org.org_name,
                "parent_id": org.parent_id,
                "org_level": org.org_level,
                "manager_id": org.manager_id,
                "children": [],
            }

        # 组装树
        tree: list[dict] = []
        for org in orgs:
            node = org_dict[org.id]
            parent_id = node["parent_id"]
            if parent_id is None or parent_id not in org_dict:
                tree.append(node)
            else:
                org_dict[parent_id]["children"].append(node)

        return {"code": 0, "msg": "success", "data": tree}
    except Exception as e:
        return {"code": 500, "msg": str(e), "data": None}
