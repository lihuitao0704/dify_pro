"""
智能留学顾问系统 - 配置文件
读取 .env 中的环境变量，提供数据库与大模型客户端配置。
"""
import os
from dotenv import load_dotenv

# 加载项目根目录的 .env
load_dotenv()


class Config:
    # ============================================
    # MySQL 数据库配置
    # ============================================
    MYSQL_HOST = os.getenv("DB_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "123456")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "dify_pro")
    DEBUG = True

    # ============================================
    # 大模型（LongCat，OpenAI 兼容协议）配置
    # ============================================
    LONGCAT_API_KEY = os.getenv("LONGCAT_API_KEY", "")
    LONGCAT_BASE_URL = "https://api.longcat.chat/openai"
    LONGCAT_MODEL = "LongCat-2.0"

    # ============================================
    # NL2SQL 安全配置
    # ============================================
    # 允许 NL2SQL 查询的表（白名单）
    NL2SQL_ALLOWED_TABLES = ["user_profiles", "courses", "consultations"]
    # 单条查询最大返回行数
    NL2SQL_MAX_ROWS = 200
    # 是否允许写操作（INSERT / UPDATE / DELETE）
    NL2SQL_ALLOW_WRITE = True


config = Config()
