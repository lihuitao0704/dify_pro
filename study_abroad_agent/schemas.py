"""
Pydantic 请求 / 响应模型
用于 FastAPI 入参自动校验和 Swagger 文档生成。
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
    conversation_id: str = Field(..., min_length=1, description="Dify 会话唯一 ID")
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


class ProfileCheck(BaseModel):
    complete: bool
    missing: List[str]


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
    conversation_id: str = Field(..., min_length=1, description="Dify 会话 ID")
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
        description="自然语言问题，例如：德国留学方案有哪些？GPA 3.0 以下能申请什么课程？",
    )
    include_sql: bool = Field(
        default=False, description="响应中是否包含模型生成的 SQL 语句"
    )


class NL2SQLResponse(BaseModel):
    question: str
    sql: Optional[str] = None
    rows: List[Dict[str, Any]]
    row_count: int
    elapsed_ms: float
