"""
全域客户经营模块相关表结构（用于 NL2SQL 提示词）。

基于 dify_pro 真实表结构。覆盖：
  - intention_customer     意向客户主表
  - consultations          咨询记录
  - user_profiles          用户（客户）画像
  - account                账户（含销售顾问 user_type='sales'）
  - organization           组织架构（部门）
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
   - create_time: DATETIME, 创建时间
   - update_time: DATETIME, 更新时间

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
   - id: INT PK
   - conversation_id: INT, 关联咨询记录
   - name: VARCHAR(50), 姓名
   - age: INT, 年龄
   - education: VARCHAR(50), 学历
   - major: VARCHAR(100), 专业
   - gpa: DECIMAL(3,2), GPA
   - target_country: VARCHAR(100), 目标国家
   - target_major: VARCHAR(100), 目标专业
   - budget: DECIMAL(12,2), 预算
   - language_score: VARCHAR(50), 语言成绩
   - phone: VARCHAR(20), 手机号
   - wechat: VARCHAR(50), 微信
   - email: VARCHAR(128), 邮箱
   - consultation_status: VARCHAR(20), 咨询状态
   - created_at: DATETIME
   - updated_at: DATETIME

4. account（账户表，含销售顾问）
   - user_id: BIGINT PK, 用户ID
   - username: VARCHAR(64), 用户名
   - real_name: VARCHAR(64), 真实姓名
   - user_type: VARCHAR(32), 用户类型（sales/teacher/student/admin等）
   - dept_id: BIGINT, 关联 organization.id
   - student_id: BIGINT, 学生ID（如适用）
   - phone: VARCHAR(20)
   - email: VARCHAR(128)
   - status: TINYINT, 状态
   - create_time: DATETIME

5. organization（组织架构/部门表）
   - id: INT PK
   - dept_name: VARCHAR(50), 部门名称
   - dept_desc: TEXT, 部门描述
   - contact_user: VARCHAR(50), 联系人
   - contact_phone: VARCHAR(20), 联系电话
   - create_time: DATETIME

关联关系：
- intention_customer.sales_user_id → account.user_id（销售顾问）
- account.dept_id → organization.id（所属部门）
- consultations.user_id → account.user_id
- user_profiles 通过 name/phone 与 intention_customer 做业务关联
"""
