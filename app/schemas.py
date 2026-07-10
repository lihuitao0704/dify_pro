from pydantic import BaseModel, Field
from typing import Optional, List


# ========== 意向客户 ==========

class CustomerAddRequest(BaseModel):
    customer_name: str = Field(..., description="客户姓名")
    customer_age: Optional[int] = Field(None, description="年龄")
    customer_gender: Optional[str] = Field(None, description="性别")
    customer_phone: Optional[str] = Field(None, description="联系电话")
    customer_source: Optional[str] = Field(None, description="来源渠道")
    customer_demand: Optional[str] = Field(None, description="客户需求")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class CustomerStatusRequest(BaseModel):
    customer_id: int = Field(..., description="客户ID")
    new_status: str = Field(..., description="新状态")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class CustomerFollowRequest(BaseModel):
    customer_id: int = Field(..., description="客户ID")
    follow_record: str = Field(..., description="跟进内容")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


# ========== 日报 ==========

class ReportSubmitRequest(BaseModel):
    report_content: str = Field(..., description="日报内容")
    report_date: str = Field(..., description="日报日期 (YYYY-MM-DD)")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


# ========== 请假 ==========

class StudentLeaveRequest(BaseModel):
    student_name: str = Field(..., description="学生姓名")
    leave_type: str = Field(..., description="请假类型")
    start_date: str = Field(..., description="开始日期 (YYYY-MM-DD)")
    end_date: str = Field(..., description="结束日期 (YYYY-MM-DD)")
    reason: str = Field(..., description="请假事由")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class EmployeeLeaveRequest(BaseModel):
    leave_type: str = Field(..., description="请假类型")
    start_date: str = Field(..., description="开始日期 (YYYY-MM-DD)")
    end_date: str = Field(..., description="结束日期 (YYYY-MM-DD)")
    reason: str = Field(..., description="请假事由")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


class BatchApproveRequest(BaseModel):
    leave_ids: List[int] = Field(..., description="请假ID列表")
    action: str = Field(..., description="操作：approve/reject")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")


# ========== 对话 ==========

class ChatRequest(BaseModel):
    query: str = Field(..., description="用户输入")
    current_user_id: int = Field(..., description="当前用户ID")
    current_user_type: str = Field(..., description="当前用户类型")
