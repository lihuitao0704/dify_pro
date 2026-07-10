from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IntentionCustomer
from app.schemas import CustomerAddRequest, CustomerStatusRequest, CustomerFollowRequest
from app.routers import check_permission

router = APIRouter()


@router.post("/customer/add")
def add_customer(req: CustomerAddRequest, db: Session = Depends(get_db)):
    """录入意向客户"""
    try:
        if not check_permission(req.current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        customer = IntentionCustomer(
            customer_name=req.customer_name,
            customer_age=req.customer_age,
            customer_gender=req.customer_gender,
            customer_phone=req.customer_phone,
            customer_source=req.customer_source,
            customer_demand=req.customer_demand,
            sales_user_id=req.current_user_id,
            status="意向中",
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return {"code": 0, "msg": "success", "data": {"customer_id": customer.id}}
    except Exception as e:
        db.rollback()
        return {"code": 500, "msg": str(e), "data": None}


@router.get("/customer/list")
def list_customers(
    keyword: Optional[str] = Query(None, description="模糊搜索姓名/电话"),
    status: Optional[str] = Query(None, description="客户状态筛选"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询客户列表"""
    try:
        if not check_permission(current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        query = db.query(IntentionCustomer)

        # 员工只能看自己的客户
        if current_user_type == "员工":
            query = query.filter(IntentionCustomer.sales_user_id == current_user_id)

        # 模糊搜索
        if keyword:
            query = query.filter(
                or_(
                    IntentionCustomer.customer_name.like(f"%{keyword}%"),
                    IntentionCustomer.customer_phone.like(f"%{keyword}%"),
                )
            )

        # 状态筛选
        if status:
            query = query.filter(IntentionCustomer.status == status)

        # 按更新时间倒序
        customers = query.order_by(IntentionCustomer.update_time.desc()).all()

        data = [
            {
                "id": c.id,
                "customer_name": c.customer_name,
                "customer_age": c.customer_age,
                "customer_gender": c.customer_gender,
                "customer_phone": c.customer_phone,
                "customer_source": c.customer_source,
                "customer_demand": c.customer_demand,
                "sales_user_id": c.sales_user_id,
                "status": c.status,
                "follow_record": c.follow_record,
                "create_time": c.create_time.strftime("%Y-%m-%d %H:%M:%S") if c.create_time else None,
                "update_time": c.update_time.strftime("%Y-%m-%d %H:%M:%S") if c.update_time else None,
            }
            for c in customers
        ]
        return {"code": 0, "msg": "success", "data": data}
    except Exception as e:
        return {"code": 500, "msg": str(e), "data": None}


@router.get("/customer/{customer_id}")
def get_customer(
    customer_id: int,
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """查询客户详情"""
    try:
        if not check_permission(current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        customer = db.query(IntentionCustomer).filter(
            IntentionCustomer.id == customer_id
        ).first()
        if not customer:
            return {"code": 404, "msg": "客户不存在", "data": None}

        # 员工只能看自己的客户
        if current_user_type == "员工" and customer.sales_user_id != current_user_id:
            return {"code": 403, "msg": "无权限操作", "data": None}

        data = {
            "id": customer.id,
            "customer_name": customer.customer_name,
            "customer_age": customer.customer_age,
            "customer_gender": customer.customer_gender,
            "customer_phone": customer.customer_phone,
            "customer_source": customer.customer_source,
            "customer_demand": customer.customer_demand,
            "sales_user_id": customer.sales_user_id,
            "status": customer.status,
            "follow_record": customer.follow_record,
            "create_time": customer.create_time.strftime("%Y-%m-%d %H:%M:%S") if customer.create_time else None,
            "update_time": customer.update_time.strftime("%Y-%m-%d %H:%M:%S") if customer.update_time else None,
        }
        return {"code": 0, "msg": "success", "data": data}
    except Exception as e:
        return {"code": 500, "msg": str(e), "data": None}


@router.put("/customer/status")
def update_customer_status(req: CustomerStatusRequest, db: Session = Depends(get_db)):
    """更新客户状态"""
    try:
        if not check_permission(req.current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        customer = db.query(IntentionCustomer).filter(
            IntentionCustomer.id == req.customer_id
        ).first()
        if not customer:
            return {"code": 404, "msg": "客户不存在", "data": None}

        # 员工只能改自己的客户
        if req.current_user_type == "员工" and customer.sales_user_id != req.current_user_id:
            return {"code": 403, "msg": "无权限操作", "data": None}

        customer.status = req.new_status
        db.commit()
        return {"code": 0, "msg": "success", "data": None}
    except Exception as e:
        db.rollback()
        return {"code": 500, "msg": str(e), "data": None}


@router.put("/customer/follow")
def follow_customer(req: CustomerFollowRequest, db: Session = Depends(get_db)):
    """追加跟进记录"""
    try:
        if not check_permission(req.current_user_type):
            return {"code": 403, "msg": "无权限操作", "data": None}

        customer = db.query(IntentionCustomer).filter(
            IntentionCustomer.id == req.customer_id
        ).first()
        if not customer:
            return {"code": 404, "msg": "客户不存在", "data": None}

        # 员工只能跟进自己的客户
        if req.current_user_type == "员工" and customer.sales_user_id != req.current_user_id:
            return {"code": 403, "msg": "无权限操作", "data": None}

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_record = f"【{now_str}】{req.follow_record}\n"

        if customer.follow_record:
            customer.follow_record += new_record
        else:
            customer.follow_record = new_record

        db.commit()
        return {"code": 0, "msg": "success", "data": None}
    except Exception as e:
        db.rollback()
        return {"code": 500, "msg": str(e), "data": None}
