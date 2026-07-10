"""
全局配置读取（基于 .env）

提供数据库、LLM、应用级别的配置单例，统一由 dotenv 加载环境变量，
并提供合理的默认值，避免缺少某个 key 直接崩溃。
"""

import os

from dotenv import load_dotenv

# 加载项目根目录的 .env，已存在环境变量时不会被覆盖
load_dotenv()

# ── 数据库配置 ──────────────────────────────────────────────
DB_CONFIG: dict = {
    "host": os.getenv("DB_HOST", "192.168.48.121"),
    "user": os.getenv("DB_USER", "offer"),
    "password": os.getenv("DB_PASSWORD", "123456"),
    "database": os.getenv("DB_NAME", "dify_pro"),
    "charset": os.getenv("DB_CHARSET", "utf8mb4"),
}

# ── LLM 配置 ────────────────────────────────────────────────
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
LLM_BASE_URL: str = os.getenv(
    "LLM_BASE_URL",
    "https://ws-ypbgci9xxhkaw467.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
)
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen-plus")

# ── 应用配置 ────────────────────────────────────────────────
APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))

# ── NL2SQL 行为配置 ─────────────────────────────────────────
# 每条报告最多返回多少行给 LLM 润色，避免 token 超限
MAX_ROWS_FOR_POLISH: int = int(os.getenv("MAX_ROWS_FOR_POLISH", "50"))
# 报告润色后的目标字数上限（提示给 LLM）
REPORT_MAX_CHARS: int = int(os.getenv("REPORT_MAX_CHARS", "1200"))
