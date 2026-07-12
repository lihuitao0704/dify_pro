"""
意向客户管理路由
POST   /api/agent/customer/add        - 录入客户
GET    /api/agent/customer/list       - 查询客户列表
GET    /api/agent/customer/{customer_id} - 客户详情
PUT    /api/agent/customer/status     - 更新客户状态
PUT    /api/agent/customer/follow     - 追加跟进记录
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import logging

from enterprise_agent.database import get_db
from enterprise_agent.models import IntentionCustomer, Account
from enterprise_agent.schemas import (
    ApiResponse, CustomerAddRequest, CustomerStatusUpdateRequest,
    CustomerFollowRequest
)
from enterprise_agent.utils import require_operator, is_manager

logger = logging.getLogger("enterprise_agent.customer")
router = APIRouter()


# ==================== POST /api/agent/customer/add ====================
@router.post("/customer/add", response_model=ApiResponse, summary="录入客户")
def add_customer(req: CustomerAddRequest, db: Session = Depends(get_db)):
    """
    录入意向客户
    仅员工/管理者可操作，sales_user_id 自动设为当前用户ID
    """
    try:
        require_operator(req.current_user_type)

        # 校验客户姓名不能为空
        if not req.customer_name or not req.customer_name.strip():
            return ApiResponse(code=400, msg="客户姓名不能为空")

        customer = IntentionCustomer(
            customer_name=req.customer_name.strip(),
            customer_age=req.customer_age,
            customer_gender=req.customer_gender,
            customer_phone=req.customer_phone,
            customer_source=req.customer_source,
            customer_demand=req.customer_demand,
            current_status="意向中",
            sales_user_id=req.current_user_id,
            create_time=datetime.now(),
            update_time=datetime.now(),
        )
        db.add(customer)
        db.flush()  # 获取自增ID
        db.commit()  # 显式提交事务

        logger.info(f"客户录入成功: ID={customer.customer_id}, 姓名={customer.customer_name}")
        return ApiResponse(data={"customer_id": customer.customer_id})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"客户录入失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"客户录入失败: {str(e)}")


# ==================== GET /api/agent/customer/list ====================
@router.get("/customer/list", response_model=ApiResponse, summary="查询客户列表")
def list_customer(
    keyword: Optional[str] = Query(None, description="模糊搜索姓名/电话"),
    status: Optional[str] = Query(None, description="筛选状态"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """
    查询客户列表
    - 管理者：查看全部
    - 员工：只看自己负责的（sales_user_id = current_user_id）
    """
    try:
        require_operator(current_user_type)
        is_mgr = is_manager(current_user_type)

        # 构建查询
        query = db.query(IntentionCustomer)

        # 员工只能看自己的
        if not is_mgr:
            query = query.filter(IntentionCustomer.sales_user_id == current_user_id)

        # 模糊搜索姓名/电话
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            query = query.filter(
                (IntentionCustomer.customer_name.like(kw)) |
                (IntentionCustomer.customer_phone.like(kw))
            )

        # 状态筛选
        if status:
            query = query.filter(IntentionCustomer.current_status == status)

        # 排序：最新在前
        query = query.order_by(IntentionCustomer.create_time.desc())

        # 分页
        total = query.count()
        customers = query.offset((page - 1) * page_size).limit(page_size).all()

        # 序列化
        data_list = []
        for c in customers:
            data_list.append({
                "customer_id": c.customer_id,
                "customer_name": c.customer_name,
                "customer_age": c.customer_age,
                "customer_gender": c.customer_gender,
                "customer_phone": c.customer_phone,
                "customer_source": c.customer_source,
                "customer_demand": c.customer_demand,
                "follow_record": c.follow_record,
                "current_status": c.current_status,
                "sales_user_id": c.sales_user_id,
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
        logger.error(f"查询客户列表失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


# ==================== GET /api/agent/customer/{customer_id} ====================
@router.get("/customer/{customer_id}", response_model=ApiResponse, summary="查询客户详情")
def get_customer(
    customer_id: int,
    current_user_id: int = Query(..., description="当前用户ID"),
    current_user_type: str = Query(..., description="当前用户类型"),
    db: Session = Depends(get_db),
):
    """
    查询客户详情
    - 管理者：可查看任意客户
    - 员工：只能查看自己负责的客户
    """
    try:
        require_operator(current_user_type)
        is_mgr = is_manager(current_user_type)

        customer = db.query(IntentionCustomer).filter(
            IntentionCustomer.customer_id == customer_id
        ).first()

        if not customer:
            return ApiResponse(code=404, msg="客户不存在")

        # 员工只能看自己的
        if not is_mgr and customer.sales_user_id != current_user_id:
            return ApiResponse(code=403, msg="无权查看此客户信息")

        data = {
            "customer_id": customer.customer_id,
            "customer_name": customer.customer_name,
            "customer_age": customer.customer_age,
            "customer_gender": customer.customer_gender,
            "customer_phone": customer.customer_phone,
            "customer_source": customer.customer_source,
            "customer_demand": customer.customer_demand,
            "follow_record": customer.follow_record,
            "current_status": customer.current_status,
            "sales_user_id": customer.sales_user_id,
            "create_time": customer.create_time.strftime("%Y-%m-%d %H:%M:%S") if customer.create_time else None,
            "update_time": customer.update_time.strftime("%Y-%m-%d %H:%M:%S") if customer.update_time else None,
        }
        return ApiResponse(data=data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询客户详情失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"查询失败: {str(e)}")


# ==================== PUT /api/agent/customer/status ====================
@router.put("/customer/status", response_model=ApiResponse, summary="更新客户状态")
def update_customer_status(req: CustomerStatusUpdateRequest, db: Session = Depends(get_db)):
    """
    更新客户状态（未签约/跟进中/已流失）
    - 管理者：可操作任意客户
    - 员工：只能操作自己负责的客户
    """
    try:
        require_operator(req.current_user_type)
        is_mgr = is_manager(req.current_user_type)

        # 校验状态值（匹配数据库ENUM：已签约/意向中/已流失）
        valid_statuses = ("已签约", "意向中", "已流失")
        if req.new_status not in valid_statuses:
            return ApiResponse(code=400, msg=f"无效状态值，可选：{', '.join(valid_statuses)}")

        customer = db.query(IntentionCustomer).filter(
            IntentionCustomer.customer_id == req.customer_id
        ).first()

        if not customer:
            return ApiResponse(code=404, msg="客户不存在")

        # 员工只能操作自己的
        if not is_mgr and customer.sales_user_id != req.current_user_id:
            return ApiResponse(code=403, msg="无权操作此客户")

        old_status = customer.current_status
        customer.current_status = req.new_status
        customer.update_time = datetime.now()

        db.commit()
        logger.info(f"客户状态更新: ID={req.customer_id}, {old_status} -> {req.new_status}")
        return ApiResponse(data={"customer_id": req.customer_id, "new_status": req.new_status})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新客户状态失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"更新失败: {str(e)}")


# ==================== PUT /api/agent/customer/follow ====================
@router.put("/customer/follow", response_model=ApiResponse, summary="追加跟进记录")
def follow_customer(req: CustomerFollowRequest, db: Session = Depends(get_db)):
    """
    追加跟进记录
    在原记录后面追加【时间】新内容，不覆盖原有记录
    """
    try:
        require_operator(req.current_user_type)
        is_mgr = is_manager(req.current_user_type)

        customer = db.query(IntentionCustomer).filter(
            IntentionCustomer.customer_id == req.customer_id
        ).first()

        if not customer:
            return ApiResponse(code=404, msg="客户不存在")

        # 员工只能操作自己的
        if not is_mgr and customer.sales_user_id != req.current_user_id:
            return ApiResponse(code=403, msg="无权操作此客户")

        # 追加跟进记录：【时间】内容
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_record = f"\n【{now_str}】{req.follow_record.strip()}"

        if customer.follow_record:
            customer.follow_record += new_record
        else:
            customer.follow_record = new_record

        customer.update_time = datetime.now()
        db.commit()

        logger.info(f"跟进记录已追加: 客户ID={req.customer_id}")
        return ApiResponse(data={"customer_id": req.customer_id, "follow_record": customer.follow_record})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"追加跟进记录失败: {e}", exc_info=True)
        return ApiResponse(code=500, msg=f"追加失败: {str(e)}")
