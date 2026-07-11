"""
数据库连接配置

安全策略：
    - 生产环境所有敏感信息通过环境变量注入
    - 开发环境通过项目根目录 .env 文件提供配置
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# ============================================================
# .env 加载
# ============================================================

try:
    from dotenv import load_dotenv
    _env_file = PROJECT_ROOT / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except ImportError:
    pass

# ============================================================
# 数据库配置
# ============================================================

DB_HOST = os.getenv("DB_HOST", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "")

_raw_port = os.getenv("DB_PORT", "3306")
try:
    DB_PORT = int(_raw_port)
except (ValueError, TypeError):
    raise ValueError(
        f"DB_PORT must be an integer, got: '{_raw_port}'. "
        "Check your .env or environment variables."
    )

DB_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"

# ============================================================
# API 认证
# ============================================================

API_TOKEN = os.getenv("API_TOKEN", "dev-token")
API_AUTH_ENABLED = os.getenv("API_AUTH_ENABLED", "true").lower() == "true"

CORS_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8000,http://localhost:3000,http://127.0.0.1:8000",
    ).split(",")
    if o.strip()
]

# ============================================================
# NL2SQL — LLM 配置
# ============================================================

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
_raw_timeout = os.getenv("NL2SQL_TIMEOUT", "30")
try:
    NL2SQL_REQUEST_TIMEOUT = int(_raw_timeout)
except (ValueError, TypeError):
    raise ValueError(
        f"NL2SQL_TIMEOUT must be an integer, got: '{_raw_timeout}'."
    )


# ============================================================
# 启动检查（供 main.py lifespan 调用，不在 import 时执行）
# ============================================================

def startup_check() -> dict:
    """返回 {'ready': bool, 'missing': [...], 'warnings': [...]}。
    调用方不需要靠字符串内容判断严重程度。"""
    result = {"ready": True, "missing": [], "warnings": []}
    missing = [k for k, v in
               [("DB_HOST", DB_HOST), ("DB_USER", DB_USER),
                ("DB_PASSWORD", DB_PASSWORD), ("DB_NAME", DB_NAME)]
               if not v]
    if missing:
        result["ready"] = False
        result["missing"] = missing
    if DB_PASSWORD in ("123456", "password", "admin", "root"):
        result["warnings"].append("Database password is too weak")
    if API_TOKEN == "dev-token" and API_AUTH_ENABLED:
        result["warnings"].append("Using default API token 'dev-token'")
    return result
