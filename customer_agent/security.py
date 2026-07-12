"""
customer_agent JWT 安全模块
签发 / 验证 Bearer Token
"""
import os
import jwt
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 密钥：生产环境必须通过环境变量覆盖
_JWT_SECRET = os.getenv("CUSTOMER_JWT_SECRET", "yuejiao-customer-agent-2024-secret")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_HOURS = int(os.getenv("CUSTOMER_JWT_EXPIRE_HOURS", "24"))


def create_token(user_id: int, username: str, user_type: str, real_name: str = "") -> str:
    """签发 JWT"""
    payload = {
        "user_id": user_id,
        "username": username,
        "user_type": user_type,
        "real_name": real_name,
        "exp": datetime.utcnow() + timedelta(hours=_JWT_EXPIRE_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """验证 JWT，返回 payload；无效/过期返回 None"""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT 过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("JWT 无效: %s", e)
        return None
