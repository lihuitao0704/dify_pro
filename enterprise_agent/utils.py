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


# ==================== 共享日期工具（消除路由间重复代码） ====================

def _flexible_parse_date(date_str: str):
    """
    灵活解析日期字符串。支持多种格式：
    - YYYY-MM-DD / YYYY-M-D（标准与无前导零）
    - YYYY/MM/DD / YYYY/M/D（斜杠分隔）
    - YYYY年MM月DD日（中文格式）
    返回 datetime.date 对象，失败返回 None。
    """
    from datetime import datetime

    date_str = date_str.strip()

    # 尝试多种格式
    formats = [
        "%Y-%m-%d", "%Y-%-m-%-d",
        "%Y/%m/%d", "%Y/%-m/%-d",
        "%Y年%m月%d日", "%Y年%-m月%-d日",
    ]
    # 先尝试完整格式列表
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, AttributeError):
            continue

    # 尝试从带时间的字符串中提取日期部分 "2026-01-01 10:00:00"
    for sep in [" ", "T"]:
        if sep in date_str:
            try:
                return datetime.strptime(date_str.split(sep)[0], "%Y-%m-%d").date()
            except (ValueError, AttributeError):
                continue

    return None


def parse_date(date_str: str, field_name: str = "日期"):
    """
    验证并解析日期字符串。
    支持 YYYY-MM-DD、YYYY-M-D、YYYY/MM/DD、YYYY年MM月DD日 等格式。
    成功返回 datetime.date 对象，失败抛出 HTTPException。
    """
    result = _flexible_parse_date(date_str)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name}格式错误，请使用 YYYY-MM-DD 格式（如 2026-01-01）",
        )
    return result


def parse_and_validate_dates(start_date: str, end_date: str):
    """
    解析并校验起止日期对。
    返回 (start_date_obj, end_date_obj)。
    自动抛出 HTTPException。
    """
    start = parse_date(start_date, "开始日期")
    end = parse_date(end_date, "结束日期")

    if end < start:
        raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")

    return start, end
