"""
学生智能助手 Agent 配置
自动从 .env 文件加载，修改 .env 即可
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
    print(f"[Config] 已加载 .env: {_env_path}")

# ========== MySQL 数据库配置 ==========
DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "192.168.48.121"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "123456"),
    "database": os.getenv("MYSQL_DATABASE", "student_assistant"),
    "charset": "utf8mb4",
}

# ========== LLM 配置（OpenAI 兼容接口） ==========
LLM_CONFIG = {
    "api_key": os.getenv("LLM_API_KEY", "sk-your-api-key-here"),
    "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
    "model": os.getenv("LLM_MODEL", "deepseek-chat"),
}

# ========== 服务配置 ==========
AGENT_PORT = int(os.getenv("AGENT_PORT", "8000"))
AGENT_HOST = os.getenv("AGENT_HOST", "0.0.0.0")

# ========== 企业助手（教师端）地址 ==========
TEACHER_AGENT_URL = os.getenv("TEACHER_AGENT_URL", "http://127.0.0.1:8001")
ENTERPRISE_AGENT_URL = os.getenv("ENTERPRISE_AGENT_URL", TEACHER_AGENT_URL)

# ========== Agent 配置 ==========
MAX_HISTORY_TURNS = 10          # 多轮对话保留最近 N 轮
INTENT_CONFIDENCE_THRESHOLD = 0.7  # 意图置信度阈值，低于此值降级为追问
EMOTION_ALERT_THRESHOLD = 70    # 情绪风险分 >= 70 触发预警

# ========== 鉴权配置 ==========
API_TOKEN = os.getenv("STUDENT_API_TOKEN", "student-secret-2026")
API_AUTH_ENABLED = os.getenv("STUDENT_API_AUTH", "false").lower() in ("1", "true", "yes")
