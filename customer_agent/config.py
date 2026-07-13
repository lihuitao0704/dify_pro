"""
客服Agent 配置
读取 .env 中的环境变量，集中管理所有可调参数。
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env（先找自身目录，再找项目根目录）
_env_self = Path(__file__).parent / ".env"
_root_env = Path(__file__).parent.parent / ".env"
if _env_self.exists():
    load_dotenv(_env_self)
elif _root_env.exists():
    load_dotenv(_root_env)


class Config:
    # ============================================
    # 服务本身
    # ============================================
    AGENT_PORT = int(os.getenv("CUSTOMER_AGENT_PORT", "9000"))
    AGENT_HOST = os.getenv("CUSTOMER_AGENT_HOST", "0.0.0.0")

    # ============================================
    # 知识库数据路径（指向 Knowledge/ 目录）
    # ============================================
    KNOWLEDGE_PATH = os.getenv(
        "KNOWLEDGE_PATH",
        str(Path(__file__).parent.parent / "Knowledge"),
    )

    # ============================================
    # MySQL 数据库配置 (合并 study_abroad_agent + Event&Lecture)
    # ============================================
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "offer")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "123456")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "dify_pro")
    MYSQL_TIMEOUT = int(os.getenv("MYSQL_TIMEOUT", "10"))  # 连接/读写超时秒

    # ============================================
    # NL2SQL 安全配置
    # ============================================
    # 允许 NL2SQL 操作的表（白名单）
    NL2SQL_ALLOWED_TABLES = [
        "user_profiles", "courses", "consultations",
        "lectures", "activities",
        "lecture_registrations", "activity_registrations",
    ]
    NL2SQL_MAX_ROWS = 200          # 单条查询最大返回行数
    NL2SQL_ALLOW_WRITE = True      # 是否允许 NL2SQL 写操作 (INSERT)

    # ============================================
    # LLM（LongCat-2.0，OpenAI 兼容协议）
    # ============================================
    LLM_API_KEY = os.getenv("LONGCAT_API_KEY", "")
    LLM_BASE_URL = os.getenv(
        "LONGCAT_BASE_URL", "https://api.longcat.chat/openai"
    )
    LLM_MODEL = os.getenv("LONGCAT_MODEL", "LongCat-2.0")
    # 秒，超时走规则降级。LongCat-2.0 实测 6-7s，原 8s 容易超时，
    # 配合 max_retries=0 单轮快失败，避免 8s×3=25s 的卡顿。
    LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))

    # ============================================
    # 桥接服务地址
    # ============================================
    STUDY_ABROAD_URL = os.getenv(
        "STUDY_ABROAD_URL", "http://127.0.0.1:5000"
    )
    EVENT_LECTURE_URL = os.getenv(
        "EVENT_LECTURE_URL", "http://127.0.0.1:8011"
    )
    ASSESSMENT_URL = os.getenv(
        "ASSESSMENT_URL", "http://127.0.0.1:8002"
    )
    BRIDGE_TIMEOUT = float(os.getenv("BRIDGE_TIMEOUT", "5"))  # 桥接HTTP超时

    # ============================================
    # Agent 行为配置
    # ============================================
    MAX_HISTORY_TURNS = 10          # 多轮对话保留最近 N 轮
    INTENT_CONFIDENCE_THRESHOLD = 0.65  # 意图置信度阈值
    KB_TOP_K = 4                    # 知识库返回 TopK 个片段
    FAQ_EXACT_MATCH_BONUS = 1.2     # FAQ精确匹配加权
    FAQ_FUZZY_MIN_OVERLAP = 2       # FAQ模糊匹配最少重合关键词数
    MAX_FOLLOWUP_ROUNDS = 3         # 多轮追问最大轮次
    REPLY_MAX_CHARS = 300           # 回复最大字数
    # 是否强制 LLM 实时改写所有检索结果（默认开启）；False 时直接返回原文（运营回退用）
    FORCE_REWRITE = os.getenv("FORCE_REWRITE", "1").lower() in ("1", "true", "yes")


config = Config()
