"""
员工管理模块相关表结构（用于 NL2SQL 提示词）。

基于 dify_pro 真实表结构。覆盖：
  - employee_daily_report  员工日报
  - account                员工账户（user_type 区分角色）
  - department             部门
"""

EMPLOYEE_SCHEMA: str = """
以下为员工日报相关表结构：

1. employee_daily_report（员工日报表）
   - id: BIGINT PK
   - user_id: BIGINT, 员工ID，关联 account.user_id
   - dept_id: BIGINT, 部门ID，关联 department.dept_id
   - report_content: TEXT, 日报正文（含今日工作/产出/计划/风险等）
   - submit_time: DATETIME, 提交时间
   - report_date: DATE, 日报日期
   - create_time: DATETIME, 创建时间
   - update_time: DATETIME, 更新时间

2. account（账户表）
   - user_id: BIGINT PK, 用户ID
   - username: VARCHAR(64), 用户名
   - real_name: VARCHAR(64), 真实姓名（员工姓名）
   - user_type: VARCHAR(32), 用户类型（sales/teacher/student/admin等）
   - dept_id: BIGINT, 关联 department.dept_id
   - student_id: BIGINT, 学生ID（如适用）
   - phone: VARCHAR(20)
   - email: VARCHAR(128)
   - status: TINYINT, 状态
   - create_time: DATETIME
   - update_time: DATETIME

3. department（部门表）
   - dept_id: BIGINT PK
   - dept_name: VARCHAR(50), 部门名称
   - dept_desc: TEXT, 部门描述
   - manager_id: BIGINT, 部门负责人ID（关联 account.user_id）
   - parent_dept_id: BIGINT, 上级部门ID
   - status: TINYINT, 状态
   - create_time: DATETIME
   - update_time: DATETIME

关联关系：
- employee_daily_report.user_id → account.user_id（员工）
- employee_daily_report.dept_id → department.dept_id（部门）
- account.dept_id → department.dept_id

注意：日报内容全部存放在 report_content 文本字段中，
      SQL 中如需检索特定内容可用 LIKE 匹配关键词。
"""
