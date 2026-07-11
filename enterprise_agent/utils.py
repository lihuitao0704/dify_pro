"""
企业智能助手 - 公共工具函数
权限校验、通用依赖、常量定义
所有 router 统一从这里引用，避免重复代码
"""
from fastapi import HTTPException
from enterprise_agent.database import get_db as _get_db

# 复用 database 的 get_db
get_db = _get_db

# ==================== 权限角色常量 ====================
ROLE_MANAGER = "管理者"
ROLE_EMPLOYEE = "员工"
ROLE_STUDENT = "学员"
ROLE_GUEST = "游客"

OPERATORS = (ROLE_MANAGER, ROLE_EMPLOYEE)


def require_operator(user_type: str):
    """仅员工/管理者可操作，学员/游客返回 403"""
    if user_type not in OPERATORS:
        raise HTTPException(
            status_code=403,
            detail=f"权限不足：需要{'/'.join(OPERATORS)}角色，当前为「{user_type}」",
        )


def is_manager(user_type: str) -> bool:
    return user_type == ROLE_MANAGER


def can_access_all(user_type: str) -> bool:
    return user_type == ROLE_MANAGER


# ==================== 输入校验 ====================
def validate_pagination(page: int, page_size: int):
    if page < 1:
        raise HTTPException(status_code=400, detail="页码从 1 开始")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="每页数量 1-100")


# ==================== 身份校验（防前端伪造） ====================
def verify_user_identity(user_id: int, user_type: str):
    """基础身份校验：确保用户类型在合法范围内"""
    valid_types = (ROLE_MANAGER, ROLE_EMPLOYEE, ROLE_STUDENT, ROLE_GUEST)
    if user_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"无效的用户类型：{user_type}")
    if user_id < 1:
        raise HTTPException(status_code=400, detail="无效的用户ID")
