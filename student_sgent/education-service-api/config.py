"""
系统配置模块
从 .env 文件加载环境变量，集中管理所有配置项
"""
import os
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件（用 Path.resolve 保证绝对路径，避免 __file__ 相对路径坑）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _get_env_int(key: str, default: int) -> int:
    """安全获取整数环境变量，防止空字符串导致 int('') 报错"""
    val = os.getenv(key, "").strip()
    return int(val) if val else default


class Settings:
    """全局配置单例"""

    # ========== 数据库配置 ==========
    DB_HOST: str = os.getenv("DB_HOST", "192.168.48.121")
    DB_PORT: int = _get_env_int("DB_PORT", 3306)
    DB_USER: str = os.getenv("DB_USER", "offer")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "123456")
    DB_NAME: str = os.getenv("DB_NAME", "test")

    @property
    def DATABASE_URL(self) -> str:
        """构建数据库连接串，密码做 URL 编码防止特殊字符炸连接串"""
        return (
            f"mysql+pymysql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

    # ========== DeepSeek API 配置 ==========
    # 注意：API Key 必须从 .env 读取，严禁硬编码
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv(
        "DEEPSEEK_BASE_URL",
        "https://api.deepseek.com/v1",
    )

    # ========== Dify 平台配置 ==========
    # 学生助手在 Dify 中的应用 API Key（需要在 Dify 后台获取）
    DIFY_STUDENT_API_KEY: str = os.getenv("DIFY_STUDENT_API_KEY", "")
    DIFY_BASE_URL: str = os.getenv("DIFY_BASE_URL", "http://localhost:8080")

    # ========== 心理预警阈值 ==========
    EMOTION_THRESHOLD_RED: float = -0.8     # 红色高危预警
    EMOTION_THRESHOLD_YELLOW: float = -0.4   # 黄色关注预警
    EMOTION_THRESHOLD_BLUE: float = -0.2    # 蓝色轻度标记（仅记录，不推送人工）

    # ========== 业务规则 ==========
    SLA_HOURS: int = 24           # 售后工单 SLA 时限（feedback_tickets 创建时使用）
    MAX_LEAVE_DAYS: int = 30      # 单次请假最大天数（service 层校验用）
    MARKETING_COOLDOWN_DAYS: int = 7  # 营销触达冷却天数（防骚扰逻辑用）

    # ========== 服务配置 ==========
    APP_TITLE: str = "教育服务系统 — 学生智能助手 API"
    APP_VERSION: str = "1.0.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000


settings = Settings()

# 启动时强制检查：.env 缺失 DeepSeek Key 则拒绝启动
if not settings.DEEPSEEK_API_KEY:
    raise RuntimeError(
        "DEEPSEEK_API_KEY 未配置！请在项目根目录的 .env 文件中设置\n"
        "参考 .env.example 模板"
    )
