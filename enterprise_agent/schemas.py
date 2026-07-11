"""
企业智能助手 - Pydantic 请求/响应数据模型
统一响应格式：{"code": 0, "msg": "success", "data": ...}
"""
from datetime import date, datetime
from typing import Optional, Any, List
from pydantic import BaseModel, Field


# ==================== 统一响应模型 ====================
class ApiResponse(BaseModel):
    """统一API响应格式"""
    code: int = Field(0, description="状态码：0-成功，其他-失败")
    msg: str = Field("success", description="提示信息")
    data: Optional[Any] = Field(None, description="响应数据")

    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime("%Y-%m-%d %H:%M:%S"),
            date: lambda v: v.strftime("%Y-%m-%d"),
        }


# ==================== 通用权限模型 ====================
ALLOWED_USER_TYPES = ("员工", "管理者", "学员", "游客")


class CurrentUser(BaseModel):
    """当前用户信息（前端传递）"""
    current_user_id: int = Field(..., ge=1, description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")

    # Pydantic v1 兼容校验
    from pydantic import validator

    @validator("current_user_type")
    def validate_user_type(cls, v):
        if v not in ALLOWED_USER_TYPES:
            raise ValueError(f"无效的用户类型：{v}")
        return v

    @validator("current_user_id")
    def validate_user_id(cls, v):
        if v < 1:
            raise ValueError("无效的用户ID")
        return v


# ==================== 意向客户管理 ====================
class CustomerAddRequest(BaseModel):
    """录入客户请求"""
    customer_name: str = Field(..., min_length=1, max_length=64, description="客户姓名")
    customer_age: Optional[int] = Field(None, ge=0, le=150, description="年龄")
    customer_gender: Optional[str] = Field(None, max_length=8, description="性别")
    customer_phone: Optional[str] = Field(None, max_length=20, description="联系电话")
    customer_source: Optional[str] = Field(None, max_length=32, description="客户来源")
    customer_demand: Optional[str] = Field(None, description="客户需求")
    # 权限参数
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class CustomerListRequest(BaseModel):
    """查询客户列表请求（Query参数）"""
    keyword: Optional[str] = Field(None, description="模糊搜索关键词（姓名/电话）")
    status: Optional[str] = Field(None, description="筛选状态")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class CustomerStatusUpdateRequest(BaseModel):
    """更新客户状态请求"""
    customer_id: int = Field(..., description="客户ID")
    new_status: str = Field(..., description="新状态：未签约/跟进中/已流失")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class CustomerFollowRequest(BaseModel):
    """追加跟进记录请求"""
    customer_id: int = Field(..., description="客户ID")
    follow_record: str = Field(..., min_length=1, description="跟进内容")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


# ==================== 请假管理 ====================
class LeaveStudentRequest(BaseModel):
    """替学生请假请求"""
    student_name: str = Field(..., min_length=1, max_length=50, description="学生姓名")
    leave_type: str = Field(..., max_length=20, description="请假类型：事假/病假/年假/其他")
    start_date: str = Field(..., description="开始日期（YYYY-MM-DD）")
    end_date: str = Field(..., description="结束日期（YYYY-MM-DD）")
    reason: Optional[str] = Field(None, description="请假原因")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class LeaveEmployeeRequest(BaseModel):
    """员工请假请求"""
    leave_type: str = Field(..., max_length=20, description="请假类型：事假/病假/年假/其他")
    start_date: str = Field(..., description="开始日期（YYYY-MM-DD）")
    end_date: str = Field(..., description="结束日期（YYYY-MM-DD）")
    reason: Optional[str] = Field(None, description="请假原因")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class LeaveBatchApproveRequest(BaseModel):
    """批量审批请求"""
    leave_ids: List[int] = Field(..., min_length=1, description="请假ID列表")
    action: str = Field(..., pattern="^(approve|reject)$", description="审批动作：approve-通过，reject-驳回")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


# ==================== 日报管理 ====================
class ReportSubmitRequest(BaseModel):
    """提交日报请求"""
    report_content: str = Field(..., min_length=1, description="日报内容")
    report_date: str = Field(..., description="汇报日期（YYYY-MM-DD）")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class ReportListRequest(BaseModel):
    """查询日报列表请求（Query参数）"""
    start_date: Optional[str] = Field(None, description="开始日期（YYYY-MM-DD）")
    end_date: Optional[str] = Field(None, description="结束日期（YYYY-MM-DD）")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


# ==================== 投诉反馈 ====================
class ComplaintHandleRequest(BaseModel):
    """处理投诉请求"""
    complaint_id: int = Field(..., description="投诉ID")
    new_status: str = Field(..., pattern="^(处理中|已完结)$", description="新状态：处理中/已完结")
    handler_user_id: Optional[int] = Field(None, description="处理人员ID")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


# ==================== 成绩管理 ====================
class ScoreAddRequest(BaseModel):
    """录入成绩请求"""
    student_id: int = Field(..., description="学生ID")
    subject: str = Field(..., max_length=64, description="科目")
    score: float = Field(..., ge=0, le=100, description="分数")
    exam_type: Optional[str] = Field(None, max_length=32, description="考试类型")
    exam_date: Optional[str] = Field(None, description="考试日期（YYYY-MM-DD）")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class ScoreListRequest(BaseModel):
    """查询成绩请求（Query参数）"""
    student_id: Optional[int] = Field(None, description="学生ID")
    subject: Optional[str] = Field(None, description="科目")


# ==================== 知识库问答 ====================
class KnowledgeQueryRequest(BaseModel):
    """知识库问答请求"""
    question: str = Field(..., min_length=1, description="用户问题")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


# ==================== NL2SQL ====================
class NL2SQLRequest(BaseModel):
    """自然语言转SQL请求"""
    query: str = Field(..., min_length=1, description="自然语言查询")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")
