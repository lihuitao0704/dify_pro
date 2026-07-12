"""
Pydantic 请求 / 响应模型 + 表结构定义

合并自:
  - study_abroad_agent/schemas.py
  - Event & Lecture Registration/Event_Lecture.py (SCHEMA)
  - customer_agent/database.py (TABLE_SCHEMAS)
"""
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field

# ============================================
# 通用响应
# ============================================
class StandardResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[Any] = None


# ============================================
# 用户画像
# ============================================
class ProfileCreate(BaseModel):
    conversation_id: str = Field(default="0", description="会话 ID")
    name: Optional[str] = None
    age: Optional[int] = Field(None, ge=0, le=150)
    major: Optional[str] = None
    education: Optional[str] = None
    target_major: Optional[str] = None
    language_score: Optional[str] = None
    target_country: Optional[str] = None
    gpa: Optional[float] = Field(None, ge=0, le=4)
    budget: Optional[int] = None
    phone: Optional[str] = None
    wechat: Optional[str] = None
    email: Optional[str] = None
    consultation_status: Optional[str] = Field(
        None, pattern="^(collecting|recommended|finished)$"
    )
    assess: Optional[str] = Field(None, description="是否研判")
    development: Optional[str] = Field(None, description="发展需求")
    abilities: Optional[str] = Field(None, description="综合能力")
    is_closed_loop: Optional[str] = Field(
        None, alias="is_Closed-loop", description="是否接受封闭式实训"
    )


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = Field(None, ge=0, le=150)
    major: Optional[str] = None
    education: Optional[str] = None
    target_major: Optional[str] = None
    language_score: Optional[str] = None
    target_country: Optional[str] = None
    gpa: Optional[float] = Field(None, ge=0, le=4)
    budget: Optional[int] = None
    phone: Optional[str] = None
    wechat: Optional[str] = None
    email: Optional[str] = None
    consultation_status: Optional[str] = Field(
        None, pattern="^(collecting|recommended|finished)$"
    )
    assess: Optional[str] = Field(None, description="是否研判")
    development: Optional[str] = Field(None, description="发展需求")
    abilities: Optional[str] = Field(None, description="综合能力")
    is_closed_loop: Optional[str] = Field(
        None, alias="is_Closed-loop", description="是否接受封闭式实训"
    )


# ============================================
# 课程
# ============================================
class CourseCreate(BaseModel):
    course_name: str = Field(..., min_length=1)
    category: str = Field(..., pattern="^(留学方案|语言课程|背景提升)$")
    sub_category: Optional[str] = ""
    country: Optional[str] = ""
    target_education: Optional[str] = ""
    min_gpa: Optional[float] = 0.00
    max_budget: Optional[float] = None
    min_budget: Optional[float] = None
    language_requirement: Optional[str] = ""
    duration: Optional[str] = ""
    price: Optional[float] = 0.00
    description: Optional[str] = None
    highlights: Optional[str] = None
    is_active: Optional[int] = Field(1, ge=0, le=1)


class CourseUpdate(BaseModel):
    course_name: Optional[str] = None
    category: Optional[str] = Field(None, pattern="^(留学方案|语言课程|背景提升)$")
    sub_category: Optional[str] = None
    country: Optional[str] = None
    target_education: Optional[str] = None
    min_gpa: Optional[float] = None
    max_budget: Optional[float] = None
    min_budget: Optional[float] = None
    language_requirement: Optional[str] = None
    duration: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    highlights: Optional[str] = None
    is_active: Optional[int] = Field(None, ge=0, le=1)


# ============================================
# 咨询记录
# ============================================
class ConsultationCreate(BaseModel):
    conversation_id: str = Field(..., min_length=1, description="会话 ID")
    course_id: Optional[int] = None
    conversation_summary: Optional[str] = ""
    recommend_ids: Optional[List[int]] = Field(default_factory=list)
    user_feedback: Optional[str] = ""
    status: Optional[str] = Field(
        "new", pattern="^(new|recommended|interested|not_interested|consulting)$"
    )


class ConsultationUpdate(BaseModel):
    conversation_summary: Optional[str] = None
    course_id: Optional[int] = None
    recommend_ids: Optional[List[int]] = None
    user_feedback: Optional[str] = None
    status: Optional[str] = Field(
        None, pattern="^(new|recommended|interested|not_interested|consulting)$"
    )


# ============================================
# 推荐
# ============================================
class RecommendRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)


# ============================================
# NL2SQL
# ============================================
class NL2SQLRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        description=(
            "自然语言问题，例如：德国留学方案有哪些？"
            "讲座什么时候？帮我报名讲座3，姓名张三，手机13800138000"
        ),
    )
    include_sql: bool = Field(
        default=False, description="响应中是否返回模型生成的 SQL"
    )
    polish: bool = Field(
        default=False, description="是否返回自然语言润色回答 (活动讲座场景)"
    )


# ============================================
# 活动 / 讲座 (对齐 Event_Lecture 的请求格式)
# ============================================
class EventNL2SQLRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description=(
            "自然语言问题，例如：近期有哪些留学讲座？"
            "帮我报名讲座3，姓名张三，手机13800138000"
            "删除报名手机号13800138000的记录"
        ),
    )


# ============================================
# 表结构定义 (供 NL2SQL prompt 使用)
# ============================================
TABLE_SCHEMAS = {
    "user_profiles": """
CREATE TABLE user_profiles (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    conversation_id VARCHAR(100) NOT NULL DEFAULT '0' COMMENT '会话ID',
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
    assess VARCHAR(100) DEFAULT NULL COMMENT '是否研判',
    development VARCHAR(100) DEFAULT NULL COMMENT '发展需求',
    abilities VARCHAR(100) DEFAULT NULL COMMENT '综合能力',
    `is_Closed-loop` VARCHAR(100) DEFAULT NULL COMMENT '是否接受封闭式实训',
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
    "lectures": """
CREATE TABLE lectures (
    lecture_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL COMMENT '讲座主题',
    event_time DATETIME COMMENT '讲座时间',
    location VARCHAR(200) DEFAULT '' COMMENT '地点（线上填链接，线下填地址）',
    registration_method VARCHAR(100) DEFAULT '' COMMENT '报名方式（扫码/链接/对话报名）',
    speaker VARCHAR(50) DEFAULT '' COMMENT '主讲人'
) COMMENT='讲座表';""",
    "activities": """
CREATE TABLE activities (
    activity_id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL COMMENT '活动主题',
    event_time DATETIME COMMENT '活动时间',
    location VARCHAR(200) DEFAULT '' COMMENT '活动地点',
    registration_method VARCHAR(100) DEFAULT '' COMMENT '报名方式'
) COMMENT='活动表';""",
    "lecture_registrations": """
CREATE TABLE lecture_registrations (
    registration_id INT AUTO_INCREMENT PRIMARY KEY,
    lecture_id INT NOT NULL COMMENT '关联讲座ID(lectures.lecture_id)',
    name VARCHAR(50) NOT NULL COMMENT '报名人姓名',
    phone VARCHAR(30) NOT NULL COMMENT '报名人手机号'
) COMMENT='讲座报名表';""",
    "activity_registrations": """
CREATE TABLE activity_registrations (
    registration_id INT AUTO_INCREMENT PRIMARY KEY,
    activity_id INT NOT NULL COMMENT '关联活动ID(activities.activity_id)',
    name VARCHAR(50) NOT NULL COMMENT '报名人姓名',
    phone VARCHAR(30) NOT NULL COMMENT '报名人手机号'
) COMMENT='活动报名表';""",
}


def get_table_schemas(table_names):
    """根据表名列表拼接建表语句，供 NL2SQL prompt 使用。"""
    parts = []
    for t in table_names:
        if t in TABLE_SCHEMAS:
            parts.append(TABLE_SCHEMAS[t].strip())
    return "\n\n".join(parts)
