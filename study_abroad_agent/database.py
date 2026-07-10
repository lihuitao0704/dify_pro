"""
数据库连接模块

提供：
1. Database 类 —— PyMySQL 连接封装（query / query_one / execute）
2. get_db()  —— 兼容旧代码的全局单例快捷方式
3. 表结构描述工具，供 NL2SQL 服务生成 prompt
"""
import pymysql
from pymysql.cursors import DictCursor
from config import config


class Database:
    """PyMySQL 连接封装，返回字典游标。"""

    def __init__(self):
        self.conn = pymysql.connect(
            host=config.MYSQL_HOST,
            port=config.MYSQL_PORT,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD,
            database=config.MYSQL_DATABASE,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True,
        )

    def query(self, sql, params=None):
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def query_one(self, sql, params=None):
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def execute(self, sql, params=None):
        """执行写操作，返回 lastrowid。"""
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid

    def close(self):
        self.conn.close()


# 全局单例，兼容旧代码
db = Database()


def get_db() -> Database:
    """返回全局 Database 实例（FastAPI 依赖注入用）。"""
    return db


# ============================================
# 表结构描述（供 NL2SQL prompt 使用）
# ============================================
TABLE_SCHEMAS = {
    "user_profiles": """
CREATE TABLE user_profiles (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conversation_id VARCHAR(100) NOT NULL UNIQUE COMMENT 'Dify会话ID',
    name VARCHAR(50) DEFAULT NULL COMMENT '姓名',
    age INT DEFAULT NULL COMMENT '年龄',
    major VARCHAR(100) DEFAULT NULL COMMENT '专业',
    education VARCHAR(50) DEFAULT NULL COMMENT '学历(本科/硕士/高中/博士)',
    target_major VARCHAR(100) DEFAULT NULL COMMENT '意向专业',
    language_score VARCHAR(50) DEFAULT NULL COMMENT '语言成绩(如 IELTS 6.5、TOEFL 95)',
    target_country VARCHAR(50) DEFAULT NULL COMMENT '目标国家(德国/新加坡)',
    gpa DECIMAL(3,2) DEFAULT NULL COMMENT 'GPA',
    budget INT DEFAULT NULL COMMENT '预算(人民币元)',
    phone VARCHAR(30) DEFAULT NULL COMMENT '手机号',
    wechat VARCHAR(50) DEFAULT NULL COMMENT '微信',
    email VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
    consultation_status ENUM('collecting','recommended','finished') DEFAULT 'collecting',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) COMMENT='用户信息表';""",
    "courses": """
CREATE TABLE courses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    course_name VARCHAR(200) NOT NULL COMMENT '课程名称',
    category VARCHAR(50) NOT NULL COMMENT '课程类别(留学方案/语言课程/背景提升)',
    sub_category VARCHAR(50) DEFAULT '' COMMENT '子类别',
    country VARCHAR(100) DEFAULT '' COMMENT '目标国家',
    target_education VARCHAR(50) DEFAULT '' COMMENT '适用学历',
    min_gpa DECIMAL(3,2) DEFAULT 0.00 COMMENT '最低GPA要求',
    max_budget DECIMAL(12,2) DEFAULT NULL COMMENT '最高预算',
    min_budget DECIMAL(12,2) DEFAULT NULL COMMENT '最低预算',
    language_requirement VARCHAR(50) DEFAULT '' COMMENT '语言要求',
    duration VARCHAR(50) DEFAULT '' COMMENT '课程时长',
    price DECIMAL(12,2) DEFAULT 0.00 COMMENT '课程价格(元)',
    description TEXT COMMENT '课程描述',
    highlights TEXT COMMENT '课程亮点',
    is_active TINYINT(1) DEFAULT 1 COMMENT '是否上架',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) COMMENT='课程表';""",
    "consultations": """
CREATE TABLE consultations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT DEFAULT NULL COMMENT '用户ID(关联user_profiles.id)',
    course_id INT DEFAULT NULL COMMENT '推荐课程ID(关联courses.id)',
    conversation_summary TEXT COMMENT '对话摘要',
    recommended_courses TEXT COMMENT '推荐的课程列表(JSON)',
    user_feedback VARCHAR(255) DEFAULT '' COMMENT '用户反馈',
    status VARCHAR(20) DEFAULT 'new' COMMENT '状态(new/recommended/interested/not_interested/consulting)',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) COMMENT='咨询记录表';""",
}


def get_table_schemas(table_names):
    """根据表名列表拼接建表语句，供 NL2SQL prompt 使用。"""
    parts = []
    for t in table_names:
        if t in TABLE_SCHEMAS:
            parts.append(TABLE_SCHEMAS[t].strip())
    return "\n\n".join(parts)
