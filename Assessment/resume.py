"""
简历信息录入 - 业务逻辑模块
负责：Pydantic 模型定义 + 生成数据库插入的自然语言指令
"""
from typing import Optional

from pydantic import BaseModel, Field


# ============================================
# 请求模型
# ============================================
class ResumeRequest(BaseModel):
    """学生信息录入请求体"""

    # ---- 必填字段 ----
    name: str = Field(..., description="姓名")
    age: int = Field(..., description="年龄")
    major: str = Field(..., description="当前专业")
    education: str = Field(..., description="当前学历")
    target_major: str = Field(..., description="目标申请专业")
    language_score: str = Field(..., description="语言成绩（如雅思/托福分数）")
    target_country: str = Field(..., description="目标留学国家")
    gpa: float = Field(..., description="GPA 成绩")
    budget: float = Field(..., description="留学预算")
    phone: str = Field(..., description="手机号码")
    development: str = Field(..., description="发展需求")
    abilities: str = Field(..., description="综合能力")
    closed_loop: str = Field(..., description="封闭式实训")

    # ---- 选填字段 ----
    wechat: Optional[str] = Field(None, description="微信号")
    email: Optional[str] = Field(None, description="电子邮箱")
    conversation_id: Optional[str] = Field(None, description="会话 ID")


# ============================================
# 文本生成函数
# ============================================
def generate_insert_instruction(data: ResumeRequest) -> str:
    """
    将用户输入的字段拼接成一句自然语言插库指令。

    示例输出：
        "请将姓名为张三，年龄为22，当前专业为车辆工程...等的数据插入到用户信息表中。"
    """

    # 定义字段顺序和中文标签（与 user_profiles 表字段对应）
    field_mapping = [
        ("姓名", data.name),
        ("年龄", data.age),
        ("当前专业", data.major),
        ("当前学历", data.education),
        ("目标申请专业", data.target_major),
        ("语言成绩", data.language_score),
        ("目标留学国家", data.target_country),
        ("GPA", data.gpa),
        ("留学预算", data.budget),
        ("手机号码", data.phone),
        ("发展需求", data.development),
        ("综合能力", data.abilities),
        ("封闭式实训", data.closed_loop),
        ("微信号", data.wechat),
        ("电子邮箱", data.email),
        ("会话ID", data.conversation_id),
    ]

    # 拼接每个字段，选填字段为空时显示「无」
    parts = []
    for label, value in field_mapping:
        display_value = value if value is not None else "无"
        parts.append(f"{label}为{display_value}")

    # 用逗号连接所有字段，末尾加句号
    content = "，".join(parts)
    return f"请将{content}等的数据插入到用户信息表中。"
