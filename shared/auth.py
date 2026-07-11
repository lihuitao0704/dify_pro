"""
shared/auth.py — 统一鉴权工具
提供 JWT / Bearer <REDACTED> 验证，供所有 Agent 模块共用。
"""
import os
import time
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional

JWT_SECRET = os.getenv("JWT_SECRET", "dify-pro-secret-2026")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))


def hash_password(password: str, salt: str = "dify-salt") -> str:
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def verify_password(password: str, hashed: str, salt: str = "dify-salt") -> bool:
    return hash_password(password, salt) == hashed


def create_jwt(payload: dict, secret: str = JWT_SECRET,
               expire_hours: int = JWT_EXPIRE_HOURS) -> str:
    """生成 JWT（HS256）— 纯标准库实现"""
    import json, base64
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    header = {"alg": "HS256", "typ": "JWT"}
    now_ts = int(time.time())
    body = {
        **payload,
        "iat": now_ts,
        "exp": now_ts + expire_hours * 3600,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    b = _b64url(json.dumps(body, separators=(",", ":")).encode())
    sig_input = f"{h}.{b}".encode()
    sig = hmac.new(secret.encode(), sig_input, hashlib.sha256).digest()
    return f"{h}.{b}.{_b64url(sig)}"


def verify_jwt(token: str, secret: str = JWT_SECRET) -> Optional[dict]:
    """验证 JWT，失败返回 None"""
    import json, base64
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        sig_input = f"{parts[0]}.{parts[1]}".encode()
        expected = hmac.new(secret.encode(), sig_input, hashlib.sha256).digest()
        def _b64url_decode(s):
            pad = (4 - len(s) % 4) % 4
            return base64.urlsafe_b64decode(s + ("=" * pad))
        actual = _b64url_decode(parts[2])
        if not hmac.compare_digest(expected, actual):
            return None
        decoded = _b64url_decode(parts[1])
        body = json.loads(decoded)
        if body.get("exp", 0) < int(time.time()):
            return None
        return body
    except Exception:
        return None


def bearer_token(request_headers: dict) -> Optional[str]:
    auth = request_headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[-1].strip()
    return None
