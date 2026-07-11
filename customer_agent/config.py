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
    # LLM（LongCat-2.0，OpenAI 兼容协议）
    # ============================================
    LLM_API_KEY = os.getenv("LONGCAT_API_KEY", "")
    LLM_BASE_URL = os.getenv(
        "LONGCAT_BASE_URL", "https://api.longcat.chat/openai"
    )
    LLM_MODEL = os.getenv("LONGCAT_MODEL", "LongCat-2.0")
    LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "8"))  # 秒，超时走规则降级

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


config = Config()
