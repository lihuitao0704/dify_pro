"""
智能留学顾问系统 - 配置文件
"""
import os

# ============================================
# MySQL 数据库配置
# ============================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "123456"),
    "database": os.getenv("DB_NAME", "dify_pro"),
    "charset": "utf8mb4",
    "cursorclass": None,  # 默认使用普通cursor，需要dict时在方法中指定
}

# ============================================
# API 服务配置
# ============================================
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8005))

# ============================================
# 课程推荐匹配规则配置
# ============================================
# 语言成绩不足时的阈值（仅德国和新加坡）
LANGUAGE_THRESHOLD = {
    "德国": {"德语B2": True, "TestDaF": 4, "TOEFL": 80, "IELTS": 6.0},
    "新加坡": {"TOEFL": 85, "IELTS": 6.0},
}

# 合作国家列表
SUPPORTED_COUNTRIES = ["德国", "新加坡"]

# 德国留学的语言考试类型
GERMAN_LANGUAGE_TESTS = ["TestDaF", "DSH", "Goethe", "telc", "德语"]

# GPA 偏低阈值（低于此值推荐背景提升）
GPA_LOW_THRESHOLD = 2.80

# 高预算阈值（超过此值推荐高端方案）
HIGH_BUDGET_THRESHOLD = 300000

# 留学方案预算比例建议
BUDGET_RATIO = {
    "tuition": 0.6,  # 学费占比
    "living": 0.35,  # 生活费占比
    "other": 0.05,   # 其他费用
}

# 各国预算建议（元/年）
COUNTRY_BUDGET_GUIDE = {
    "德国": {"low": 80000, "mid": 150000, "high": 250000, "note": "公立大学免学费，主要支出为生活费"},
    "新加坡": {"low": 100000, "mid": 200000, "high": 350000, "note": "含学费+生活费，公立大学有政府补贴"},
}
