from sqlalchemy import (
    Column, BigInteger, String, Integer, Text, Date, DateTime, func
)
from app.database import Base


class Account(Base):
    """账户表"""
    __tablename__ = "account"

    user_id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, comment="登录账号")
    real_name = Column(String(64), nullable=False, comment="真实姓名")
    user_type = Column(String(32), nullable=False, comment="用户类型")
    dept_id = Column(BigInteger, nullable=True, comment="部门ID")
    create_time = Column(DateTime, default=func.now())
    update_time = Column(DateTime, default=func.now(), onupdate=func.now())


class IntentionCustomer(Base):
    """意向客户表"""
    __tablename__ = "intention_customer"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    customer_name = Column(String(64), nullable=False, comment="客户姓名")
    customer_age = Column(Integer, nullable=True, comment="年龄")
    customer_gender = Column(String(16), nullable=True, comment="性别")
    customer_phone = Column(String(32), nullable=True, comment="联系电话")
    customer_source = Column(String(64), nullable=True, comment="来源渠道")
    customer_demand = Column(Text, nullable=True, comment="客户需求")
    sales_user_id = Column(BigInteger, nullable=False, comment="负责员工ID")
    status = Column(String(32), nullable=False, default="意向中", comment="客户状态")
    follow_record = Column(Text, nullable=True, comment="跟进记录")
    create_time = Column(DateTime, default=func.now())
    update_time = Column(DateTime, default=func.now(), onupdate=func.now())


class EmployeeDailyReport(Base):
    """员工日报表"""
    __tablename__ = "employee_daily_report"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, comment="员工ID")
    dept_id = Column(BigInteger, nullable=True, comment="部门ID")
    report_content = Column(Text, nullable=False, comment="日报内容")
    report_date = Column(Date, nullable=False, comment="日报日期")
    create_time = Column(DateTime, default=func.now())


class LeaveApplication(Base):
    """请假申请表（兼容 学生/员工 两种申请类型）"""
    __tablename__ = "leave_application"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    student_name = Column(String(64), nullable=True, comment="学生姓名（替学生请假时使用）")
    leave_type = Column(String(32), nullable=False, comment="请假类型")
    start_date = Column(Date, nullable=False, comment="开始日期")
    end_date = Column(Date, nullable=False, comment="结束日期")
    reason = Column(Text, nullable=False, comment="请假事由")
    applicant_type = Column(String(16), nullable=False, comment="申请人类型：学生/员工")
    applicant_id = Column(BigInteger, nullable=False, default=0, comment="申请人ID")
    status = Column(Integer, nullable=False, default=0, comment="状态：0待审批 1已通过 2已驳回")
    approval_user = Column(String(64), nullable=True, comment="审批人姓名")
    create_time = Column(DateTime, default=func.now())


class Organization(Base):
    """组织架构表"""
    __tablename__ = "organization"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    org_name = Column(String(128), nullable=False, comment="组织名称")
    parent_id = Column(BigInteger, nullable=True, comment="上级组织ID")
    org_level = Column(Integer, nullable=False, default=1, comment="层级")
    manager_id = Column(BigInteger, nullable=True, comment="负责人ID")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序")
    status = Column(Integer, nullable=False, default=1, comment="状态：1启用 0停用")
    create_time = Column(DateTime, default=func.now())
    update_time = Column(DateTime, default=func.now(), onupdate=func.now())
