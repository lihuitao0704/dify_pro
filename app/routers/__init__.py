# routers 公共模块

from sqlalchemy.orm import Session
from app.models import Account


def check_permission(current_user_type: str) -> bool:
    """权限校验：员工/管理者可操作，学员/游客无权限"""
    return current_user_type in ("员工", "管理者")


def get_account(db: Session, user_id: int):
    """根据用户ID查询账户信息"""
    return db.query(Account).filter(Account.user_id == user_id).first()
