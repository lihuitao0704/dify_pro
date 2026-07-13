"""
全域客户经营模块相关表结构（用于 NL2SQL 提示词）。

基于 dify_pro 真实表结构。覆盖：
  - intention_customer     意向客户主表
  - consultations          咨询记录
  - user_profiles          用户（客户）画像
  - account                账户（含销售顾问 user_type='sales'）
  - department             组织架构（部门）
"""

CUSTOMER_SCHEMA: str = """
以下为全域客户经营相关表结构：

1. intention_customer（意向客户主表）
   - customer_id: BIGINT PK, 客户ID
   - customer_name: VARCHAR(64), 客户姓名
   - customer_age: TINYINT, 年龄
   - customer_gender: VARCHAR(8), 性别
   - customer_phone: VARCHAR(20), 手机号
   - customer_source: VARCHAR(32), 来源渠道（官网/地推/转介绍/广告投放/社交媒体等）
   - customer_demand: TEXT, 客户需求描述
   - follow_record: TEXT, 跟进记录
   - current_status: ENUM('已签约','跟进中','已流失'), 当前状态
   - sales_user_id: BIGINT, 关联销售顾问 account.user_id
   - create_time: DATETIME, 线索录入时间（非签约时间）
   - update_time: DATETIME, 记录最后更新时间（状态变更时也会更新，可近似代表"已签约/已流失"等状态的发生时间）

2. consultations（咨询记录表）
   - id: INT PK
   - user_id: INT, 关联客户/用户
   - course_id: INT, 关联课程 courses.id
   - conversation_summary: TEXT, 咨询对话摘要
   - recommended_courses: TEXT, 推荐课程
   - user_feedback: VARCHAR(255), 用户反馈
   - status: VARCHAR(20), 咨询状态
   - created_at: DATETIME, 创建时间

3. user_profiles（用户/客户画像表）
   - id: BIGINT PK
   - conversation_id: VARCHAR(64), Dify会话ID
   - name: VARCHAR(50), 姓名
   - age: INT, 年龄
   - major: VARCHAR(100), 专业
   - education: VARCHAR(50), 学历
   - target_major: VARCHAR(100), 目标专业
   - language_score: VARCHAR(50), 语言成绩
   - target_country: VARCHAR(100), 目标国家
   - gpa: DECIMAL(3,2), GPA
   - budget: INT, 预算（人民币元）
   - phone: VARCHAR(20), 手机号
   - wechat: VARCHAR(50), 微信
   - email: VARCHAR(128), 邮箱
   - consultation_status: ENUM('new','recommended','interested','not_interested','consulting'), 咨询状态
   - assess: VARCHAR(50), 是否评估
   - development: VARCHAR(50), 拓展方向
   - abilities: VARCHAR(50), 综合能力
   - is_Closed_loop: VARCHAR(10), 是否闭环实训
   - created_at: TIMESTAMP
   - updated_at: TIMESTAMP

4. account（账户表，含销售顾问）
   - user_id: BIGINT PK, 用户ID
   - username: VARCHAR(64), 用户名
   - real_name: VARCHAR(64), 真实姓名
   - user_type: VARCHAR(32), 用户类型（sales/teacher/student/admin等）
   - dept_id: BIGINT, 关联 department.dept_id
   - student_id: BIGINT, 学生ID（如适用）
   - phone: VARCHAR(20)
   - email: VARCHAR(128)
   - status: TINYINT, 状态
   - create_time: DATETIME
   - update_time: DATETIME

5. department（组织架构/部门表）
   - dept_id: BIGINT PK
   - dept_name: VARCHAR(50), 部门名称
   - dept_desc: TEXT, 部门描述
   - manager_id: BIGINT, 部门负责人ID（关联 employee.emp_id）
   - parent_dept_id: BIGINT, 上级部门ID
   - status: TINYINT, 状态
   - create_time: DATETIME
   - update_time: DATETIME

关联关系：
- intention_customer.sales_user_id → account.user_id（销售顾问）
- account.dept_id → department.dept_id（所属部门）
- consultations.user_id → account.user_id
- user_profiles 通过 name/phone 与 intention_customer 做业务关联
"""
