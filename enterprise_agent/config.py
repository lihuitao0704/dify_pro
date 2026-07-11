"""
企业智能助手 - 全局配置
优先级: 环境变量 > .env 文件 > 默认值
"""
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()  # 尝试从系统环境变量加载

# ==================== 数据库配置 ====================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "192.168.48.121"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "offer"),
    "password": os.getenv("DB_PASSWORD", "123456"),
    "database": os.getenv("DB_NAME", "dify_pro"),
    "charset": "utf8mb4",
}

# 日志创建（在引用前定义）
logger = logging.getLogger("agent")

# 安全警告：检测到默认密码
if DB_CONFIG["password"] in ("123456", "password", "root", "admin"):
    logger.warning(
        "SECURITY: Using default database password '%s'! "
        "Set DB_PASSWORD in .env or environment variable.",
        DB_CONFIG["password"],
    )

DATABASE_URL = (
    f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    f"?charset={DB_CONFIG['charset']}"
)

# ==================== 应用配置 ====================
APP_CONFIG = {
    "title": "企业智能助手 API",
    "description": "意向客户 / 请假 / 日报 / 组织架构 / 待办 / 投诉 / 成绩 / 知识库 / NL2SQL",
    "version": "2.0.0",
    "host": os.getenv("APP_HOST", "0.0.0.0"),
    "port": int(os.getenv("APP_PORT", "8001")),
    "debug": os.getenv("APP_DEBUG", "true").lower() == "true",
}

# ==================== 日志配置（修复中文乱码） ====================
_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

# 根治 Windows 终端中文乱码：设置 stdout/stderr 编码为 utf-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 用英文日志格式（避免中文在部分终端显示问题）
_log_format = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"

logging.basicConfig(
    level=_log_level,
    format=_log_format,
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)

logger.info("Config loaded: host=%s, db=%s", DB_CONFIG["host"], DB_CONFIG["database"])
