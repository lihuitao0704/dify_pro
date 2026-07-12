"""
enterprise_agent JWT + 密码安全模块
"""
import os
import hashlib
import logging
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# ── 配置 ──
_JWT_SECRET = os.getenv("JWT_SECRET", "yuejiao-enterprise-2024-secret-key")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

# ── FastAPI Bearer 依赖 ──
_bearer_scheme = HTTPBearer(auto_error=False)


async def bearer_token(credentials: HTTPAuthorizationCredentials | None = None) -> dict | None:
    """FastAPI 依赖：从 Bearer token 提取用户信息，失败返回 None"""
    if credentials is None:
        return None
    return verify_jwt(credentials.credentials)


# ── JWT ──

def create_jwt(payload: dict) -> str:
    """签发 JWT"""
    data = dict(payload)
    data.setdefault("iat", datetime.utcnow())
    data.setdefault("exp", datetime.utcnow() + timedelta(hours=_JWT_EXPIRE_HOURS))
    return jwt.encode(data, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def verify_jwt(token: str) -> dict | None:
    """验证 JWT，返回 payload 或 None"""
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning("JWT 已过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("JWT 无效: %s", e)
        return None


# ── 密码哈希 ──

def hash_password(password: str) -> str:
    """bcrypt 哈希密码"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _sha256_hash(password: str) -> str:
    """旧版 SHA256 哈希（兼容历史数据）"""
    return hashlib.sha256(f"yuejiao_salt_{password}".encode()).hexdigest()


def verify_password_compat(password: str, stored_hash: str) -> tuple[bool, bool]:
    """
    验证密码，兼容 bcrypt / 旧版 SHA256 / 明文。

    返回:
        (is_valid: bool, needs_migrate: bool)
        - is_valid: 密码是否正确
        - needs_migrate: 是否需要迁移为 bcrypt
    """
    # 尝试 bcrypt
    try:
        if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
            return (True, False)
    except (ValueError, UnicodeDecodeError):
        pass  # 不是有效的 bcrypt hash

    # 兼容旧版 SHA256
    if stored_hash == _sha256_hash(password):
        return (True, True)

    # 兼容明文（开发/过渡阶段）
    if stored_hash == password:
        return (True, True)

    return (False, False)


def migrate_hash(password: str) -> str:
    """将明文密码哈希为 bcrypt（用于旧 SHA256 → bcrypt 升级）"""
    return hash_password(password)
