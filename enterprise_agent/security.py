"""
enterprise_agent/security.py — 安全工具模块
提供 bcrypt 密码哈希 + JWT 签发验证 + 兼容旧哈希迁移。
仅供 enterprise_agent 内部使用。
"""
import os
import time
import json
import base64
import hashlib
import hmac
import logging
from typing import Optional

import bcrypt

_logger = logging.getLogger("enterprise_agent.security")

JWT_SECRET = os.getenv("JWT_SECRET", "dify-pro-secret-2026")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))


# ==================== 密码哈希（bcrypt） ====================

def hash_password(password: str) -> str:
    """bcrypt 密码哈希（自动加盐）"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """验证 bcrypt 密码"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, AttributeError):
        return False


# ==================== 兼容旧版哈希迁移 ====================

_SHA256_SALT = os.getenv("PASSWORD_SALT", "dify-salt")


def _sha256_hash(password: str) -> str:
    return hashlib.sha256(f"{_SHA256_SALT}:{password}".encode()).hexdigest()


def verify_password_compat(password: str, hashed: str) -> tuple:
    """
    兼容验证：bcrypt → SHA256 → 明文（向下兼容已有数据）。
    返回 (is_valid: bool, needs_migrate: bool)。
    needs_migrate=True 表示密码正确但用的是旧版哈希/明文，调用方应更新存储。
    """
    # 1. bcrypt
    if verify_password(password, hashed):
        return True, False
    # 2. SHA256（旧版哈希）
    if _sha256_hash(password) == hashed:
        return True, True
    # 3. 明文（最旧版本——种子数据遗留）→ 强制迁移
    if hashed == password:
        return True, True
    return False, False


def migrate_hash(password: str) -> str:
    """
    强制将密码升级为 bcrypt 哈希。
    无论当前是什么算法，直接返回 bcrypt 哈希。
    """
    return hash_password(password)


# ==================== JWT ====================

def create_jwt(payload: dict, secret: str = JWT_SECRET,
               expire_hours: int = JWT_EXPIRE_HOURS) -> str:
    """生成 JWT（HS256）"""
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = {"alg": "HS256", "typ": "JWT"}
    now_ts = int(time.time())
    body = {**payload, "iat": now_ts, "exp": now_ts + expire_hours * 3600}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    b = _b64url(json.dumps(body, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{h}.{b}".encode(), hashlib.sha256).digest()
    return f"{h}.{b}.{_b64url(sig)}"


def verify_jwt(token: str, secret: str = JWT_SECRET) -> Optional[dict]:
    """验证 JWT，失败返回 None（记录日志但不暴露细节）"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            _logger.warning("JWT 格式异常: token 段数=%d", len(parts))
            return None

        sig_input = f"{parts[0]}.{parts[1]}".encode()
        expected = hmac.new(secret.encode(), sig_input, hashlib.sha256).digest()

        def _b64url_decode(s):
            pad = (4 - len(s) % 4) % 4
            return base64.urlsafe_b64decode(s + ("=" * pad))

        if not hmac.compare_digest(expected, _b64url_decode(parts[2])):
            _logger.warning("JWT 签名校验失败")
            return None

        body = json.loads(_b64url_decode(parts[1]))
        if body.get("exp", 0) < int(time.time()):
            _logger.warning("JWT 已过期: exp=%d", body.get("exp", 0))
            return None

        return body
    except (json.JSONDecodeError, base64.binascii.Error) as e:
        _logger.warning("JWT 解码失败: %s", e)
        return None
    except Exception as e:
        _logger.warning("JWT 验证异常: %s", e)
        return None


def bearer_token(request_headers: dict) -> Optional[str]:
    """从请求头提取 Bearer token"""
    auth = request_headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[-1].strip()
    return None
