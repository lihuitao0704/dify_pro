"""
企业智能助手 - SQLAlchemy ORM 模型
映射数据库中所有相关表
"""
import sqlalchemy
from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, Date, DateTime,
    DECIMAL, SmallInteger, Index, func
)
from sqlalchemy.dialects.mysql import TINYINT
from enterprise_agent.database import Base


class IntentionCustomer(Base):
    """意向客户表"""
    __tablename__ = "intention_customer"

    customer_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="客户ID")
    customer_name = Column(String(64), nullable=False, comment="客户姓名")
    customer_age = Column(SmallInteger, comment="年龄")
    customer_gender = Column(String(8), comment="性别")
    customer_phone = Column(String(20), comment="联系电话")
    customer_source = Column(String(32), comment="客户来源")
    customer_demand = Column(Text, comment="客户需求")
    follow_record = Column(Text, comment="跟进记录")
    current_status = Column(
        String(16), nullable=False, default="意向中",
        comment="客户状态：已签约/意向中/已流失（数据库为ENUM，ORM用String避免编码兼容问题）"
    )
    create_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), comment="创建时间")
    update_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), comment="更新时间")
    sales_user_id = Column(BigInteger, nullable=False, comment="负责销售员工ID")

    __table_args__ = (
        Index("idx_sales_user", "sales_user_id"),
        Index("idx_status", "current_status"),
    )


class EmployeeDailyReport(Base):
    """员工日报表"""
    __tablename__ = "employee_daily_report"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="日报记录ID")
    user_id = Column(BigInteger, nullable=False, comment="提交员工ID")
    dept_id = Column(BigInteger, nullable=False, comment="所属部门ID")
    report_content = Column(Text, nullable=False, comment="日报内容")
    submit_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), comment="提交时间")
    report_date = Column(Date, nullable=False, comment="汇报日期")
    create_time = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    update_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_user_dept", "user_id", "dept_id"),
        Index("idx_report_date", "report_date"),
    )


class StudentComplaint(Base):
    """投诉反馈表"""
    __tablename__ = "student_complaint"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="投诉工单ID")
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    complaint_detail = Column(Text, nullable=False, comment="投诉内容")
    complaint_type = Column(String(32), comment="投诉类型")
    handle_status = Column(
        String(16), nullable=False, default="待处理", comment="处理状态：待处理/处理中/已完结/驳回"
    )
    handler_user_id = Column(BigInteger, comment="处理人员员工ID")
    create_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), comment="投诉提交时间")
    update_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), comment="最后处理时间")

    __table_args__ = (
        Index("idx_student", "student_id"),
        Index("idx_handler", "handler_user_id"),
        Index("idx_status", "handle_status"),
    )


class StudentScore(Base):
    """学生成绩表"""
    __tablename__ = "student_score"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="成绩记录ID")
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    subject = Column(String(64), nullable=False, comment="科目")
    score = Column(DECIMAL(5, 1), nullable=False, comment="分数")
    exam_type = Column(String(32), comment="考试类型")
    exam_date = Column(Date, comment="考试日期")
    admin_user_id = Column(BigInteger, nullable=False, comment="录入教师ID")
    input_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), comment="成绩录入时间")
    create_time = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    update_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_student", "student_id"),
        Index("idx_admin", "admin_user_id"),
    )


class Account(Base):
    """账户信息表（统一登录账户）"""
    __tablename__ = "account"

    user_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="用户ID")
    username = Column(String(64), nullable=False, unique=True, comment="用户名（登录用）")
    password = Column(String(128), nullable=False, comment="登录密码")
    real_name = Column(String(64), nullable=False, comment="真实姓名")
    user_type = Column(String(32), nullable=False, default="游客", comment="用户类型：员工/管理者/学员/游客")
    dept_id = Column(BigInteger, comment="所属部门ID")
    student_id = Column(BigInteger, comment="关联学生ID（学员时填写）")
    phone = Column(String(20), comment="手机号")
    email = Column(String(128), comment="邮箱")
    status = Column(TINYINT, nullable=False, default=1, comment="账号状态：0-禁用，1-启用")
    create_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), comment="创建时间")
    update_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), comment="更新时间")

    __table_args__ = (
        Index("idx_username", "username"),
        Index("idx_user_type", "user_type"),
        Index("idx_dept_id", "dept_id"),
    )


class LeaveApplication(Base):
    """请假申请表（支持学生和员工）"""
    __tablename__ = "leave_application"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="请假ID")
    student_name = Column(String(50), comment="学生姓名（applicant_type=学生时填写）")
    leave_type = Column(String(20), nullable=False, comment="请假类型：事假/病假/年假/其他")
    start_date = Column(Date, nullable=False, comment="请假开始日期")
    end_date = Column(Date, nullable=False, comment="请假结束日期")
    reason = Column(Text, comment="请假原因")
    status = Column(TINYINT, nullable=False, default=0, comment="0-待审批/1-已通过/2-已驳回")
    approval_user = Column(String(50), comment="审批人姓名")
    applicant_type = Column(String(20), nullable=False, default="学生", comment="申请人类型：学生/员工")
    applicant_id = Column(BigInteger, nullable=False, comment="申请人ID（学生ID或员工ID）")
    create_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), comment="创建时间")
    update_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), comment="更新时间")

    __table_args__ = (
        Index("idx_applicant", "applicant_type", "applicant_id"),
        Index("idx_status", "status"),
        Index("idx_dates", "start_date", "end_date"),
    )


class StudentInfo(Base):
    """学生信息表"""
    __tablename__ = "student_info"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键")
    user_id = Column(BigInteger, comment="关联系统用户ID")
    lead_id = Column(BigInteger, comment="关联意向客户ID")
    name = Column(String(64), nullable=False, comment="学生姓名")
    gender = Column(String(4), comment="性别 M=男 F=女")
    phone = Column(String(32), comment="手机号")
    email = Column(String(128), comment="邮箱")
    wechat = Column(String(64), comment="微信号")
    birth_date = Column(Date, comment="出生日期")
    id_card = Column(String(32), comment="身份证号/护照号")
    project_id = Column(BigInteger, comment="关联项目ID")
    project_name = Column(String(128), comment="关联项目名称")
    enroll_date = Column(Date, comment="入学日期")
    student_no = Column(String(32), comment="学号/学员号")
    education = Column(String(32), comment="最高学历")
    school = Column(String(128), comment="毕业/在读院校")
    major = Column(String(128), comment="原专业")
    graduation_year = Column(String(16), comment="毕业年份")
    language_exam = Column(String(32), comment="语言考试类型")
    language_score = Column(DECIMAL(5, 2), comment="语言考试成绩")
    consultant_id = Column(BigInteger, comment="顾问ID")
    contract_id = Column(BigInteger, comment="关联合同ID")
    status = Column(String(8), nullable=False, default="在读", comment="在读状态：在读/休学/毕业/退学")
    remark = Column(Text, comment="备注")
    create_time = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    update_time = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_name", "name"),
        Index("idx_phone", "phone"),
        Index("idx_lead_id", "lead_id"),
        Index("idx_consultant", "consultant_id"),
        Index("idx_status", "status"),
        Index("idx_project", "project_id"),
    )


class Department(Base):
    """部门信息表"""
    __tablename__ = "department"

    dept_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="部门ID")
    dept_name = Column(String(64), nullable=False, comment="部门名称")
    dept_desc = Column(Text, comment="部门职责描述")
    manager_id = Column(BigInteger, comment="部门负责人ID（关联employee.emp_id）")
    parent_dept_id = Column(BigInteger, default=0, comment="上级部门ID")
    status = Column(TINYINT, default=1)
    create_time = Column(DateTime, server_default=func.current_timestamp())
    update_time = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_manager", "manager_id"),
    )


class Employee(Base):
    """员工信息表"""
    __tablename__ = "employee"

    emp_id = Column(BigInteger, primary_key=True, autoincrement=True, comment="员工ID")
    emp_name = Column(String(64), nullable=False, comment="姓名")
    dept_id = Column(BigInteger, comment="所属部门ID")
    position = Column(String(64), comment="职位")
    phone = Column(String(20), comment="手机号")
    email = Column(String(128), comment="邮箱")
    status = Column(TINYINT, default=1, comment="1-在职 0-离职")
    create_time = Column(DateTime, server_default=func.current_timestamp())
    update_time = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_dept", "dept_id"),
    )


class Student(Base):
    """学生表（独立的student表，与student_info分开）
    已扩展：新增留学相关的结构化字段
    """
    __tablename__ = "student"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))
    education = Column(String(20))
    major = Column(String(100))
    school = Column(String(100))
    gpa = Column(String(10), comment="GPA绩点（如 3.5/4.0）")
    language_exam_type = Column(String(20), comment="语言考试类型：IELTS/TOEFL/PTE/其他")
    language_overall = Column(String(50), comment="语言考试总分（如 7.5）")
    language_listening = Column(String(50), comment="听力成绩")
    language_reading = Column(String(50), comment="阅读成绩")
    language_writing = Column(String(50), comment="写作成绩")
    language_speaking = Column(String(50), comment="口语成绩")
    gre_score = Column(Integer, comment="GRE总分")
    gmat_score = Column(Integer, comment="GMAT总分")
    target_country = Column(String(100))
    target_degree = Column(String(20))
    target_major = Column(String(100))
    target_schools = Column(Text, comment="目标院校列表（JSON数组）")
    assigned_teacher_id = Column(Integer)
    contract_status = Column(String(20))
    enrollment_date = Column(Date)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class ApplicationRecord(Base):
    """留学申请记录表 - 核心业务流程追踪"""
    __tablename__ = "application_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    university = Column(String(128), nullable=False, comment="目标大学")
    program_name = Column(String(128), nullable=False, comment="申请项目名称")
    program_type = Column(String(32), comment="学位类型：本科/硕士/博士/交换")
    intake = Column(String(16), comment="入学季：2026Fall/2027Spring")
    application_status = Column(
        String(20), nullable=False, default="draft",
        comment="状态：draft/ submitted/ under_review/ interview/ offer/ rejected/ withdrawn/ enrolled"
    )
    current_step = Column(String(64), comment="当前进行到的步骤")
    submitted_date = Column(Date, comment="提交日期")
    decision_date = Column(Date, comment="录取/拒绝通知日期")
    is_offer_accepted = Column(String(8), comment="是否接受offer：yes/no/待定")
    deposit_paid = Column(String(8), comment="押金支付：yes/no")
    personnel_id = Column(BigInteger, comment="负责文案/顾问ID")
    notes = Column(Text, comment="备注")
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_app_student", "student_id"),
        Index("idx_app_status", "application_status"),
    )


class DocumentChecklist(Base):
    """申请材料清单表"""
    __tablename__ = "document_checklist"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    application_id = Column(BigInteger, nullable=False, comment="关联申请记录ID")
    doc_name = Column(String(128), nullable=False, comment="材料名称")
    doc_type = Column(String(32), comment="材料类型：transcript/ps/cv/recommendation/certificate/other")
    status = Column(String(16), nullable=False, default="pending", comment="状态：pending/ collected/ submitted/ approved")
    deadline = Column(Date, comment="材料截止日期")
    collected_at = Column(DateTime, comment="收集完成时间")
    file_url = Column(String(256), comment="文件存储路径")
    notes = Column(Text, comment="备注")
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_doc_application", "application_id"),
    )


class Appointment(Base):
    """咨询/面谈预约记录表"""
    __tablename__ = "appointment"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False, comment="学生ID")
    consultant_id = Column(BigInteger, comment="顾问ID")
    appointment_type = Column(String(32), comment="预约类型：咨询/选校/文书/签证/行前")
    appointment_date = Column(DateTime, comment="预约时间")
    duration_minutes = Column(Integer, default=60, comment="时长（分钟）")
    status = Column(String(16), nullable=False, default="scheduled",
                    comment="状态：scheduled/ completed/ cancelled/ noshow")
    notes = Column(Text, comment="沟通记录/纪要")
    follow_up_required = Column(String(8), comment="是否需要跟进：yes/no")
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    __table_args__ = (
        Index("idx_appt_student", "student_id"),
        Index("idx_appt_consultant", "consultant_id"),
        Index("idx_appt_date", "appointment_date"),
    )


class StudentMentalAlert(Base):
    """学生心理预警表"""
    __tablename__ = "student_mental_alert"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, nullable=False)
    student_name = Column(String(50))
    trigger_reason = Column(Text, nullable=False)
    risk_level = Column(String(10), nullable=False)
    alert_content = Column(Text)
    emotion_label = Column(String(30))
    risk_score = Column(Integer)
    follow_up_status = Column(String(20))
    assigned_teacher_id = Column(Integer)
    assigned_teacher = Column(String(50))
    action_taken = Column(Text)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.current_timestamp())


class MentalHealthProfile(Base):
    """学生心理健康档案表"""
    __tablename__ = "mental_health_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, nullable=False)
    current_emotion = Column(String(30))
    risk_score = Column(Integer)
    risk_level = Column(String(10))
    emotion_history = Column(sqlalchemy.JSON)
    negative_keywords_count = Column(Integer)
    consecutive_negative_days = Column(Integer)
    last_conversation = Column(Text)
    last_assessment_at = Column(DateTime)
    teacher_notified = Column(TINYINT)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class StudentPsychRecord(Base):
    """学生心理记录表"""
    __tablename__ = "student_psych_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False)
    emotion_tag = Column(String(64))
    emotion_score = Column(Integer)
    interaction_content = Column(Text)
    trigger_keywords = Column(sqlalchemy.JSON)
    record_date = Column(Date, nullable=False)
    create_time = Column(DateTime, server_default=func.current_timestamp())


class StudentPsychProfile(Base):
    """学生心理画像表"""
    __tablename__ = "student_psych_profile"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_id = Column(BigInteger, nullable=False)
    latest_emotion_tag = Column(String(64))
    emotion_score = Column(Integer)
    last_interaction_time = Column(DateTime)
    risk_level = Column(String(16))
    weekly_summary = Column(sqlalchemy.JSON)
    create_time = Column(DateTime, server_default=func.current_timestamp())
    update_time = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
