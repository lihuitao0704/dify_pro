"""
全库完整表结构描述（基于 dify_pro 真实结构）。

用于通用 NL2SQL 接口（/nl2sql），给予 LLM 完整的 schema 视野，
便于生成跨模块的联合查询。仅列出与业务报告相关的核心表。
"""

FULL_SCHEMA: str = """
数据库 dify_pro 中有以下核心业务表：

═══════════════════════════════════════════════════════════
一、客户经营模块
═══════════════════════════════════════════════════════════

1. intention_customer（意向客户主表）
   - customer_id BIGINT PK, customer_name, customer_age, customer_gender,
     customer_phone, customer_source, customer_demand, follow_record,
     current_status ENUM('已签约','跟进中','已流失'),
     sales_user_id BIGINT FK→account.user_id, create_time, update_time

2. consultations（咨询记录）
   - id INT PK, user_id INT, course_id INT FK→courses.id,
     conversation_summary TEXT, recommended_courses TEXT,
     user_feedback VARCHAR(255), status VARCHAR(20), created_at

3. user_profiles（客户画像）
   - id INT PK, name, age, education, major, gpa,
     target_country, target_major, budget DECIMAL(12,2),
     language_level, language_score, phone, wechat,
     contact_method, consultation_status, created_at, updated_at

4. account（账户表）
   - user_id BIGINT PK, username, real_name,
     user_type VARCHAR(32)（sales/teacher/student/admin等）,
     dept_id BIGINT FK→organization.id, student_id BIGINT,
     phone, email, status TINYINT, create_time, update_time

5. organization（部门表）
   - id INT PK, dept_name, dept_desc, contact_user, contact_phone, create_time

═══════════════════════════════════════════════════════════
二、员工管理模块
═══════════════════════════════════════════════════════════

6. employee_daily_report（员工日报表）
   - id BIGINT PK, user_id BIGINT FK→account.user_id,
     dept_id BIGINT FK→organization.id,
     report_content TEXT（日报正文）,
     submit_time DATETIME, report_date DATE, create_time, update_time

═══════════════════════════════════════════════════════════
三、留学业务学生基础表
═══════════════════════════════════════════════════════════

7. application_progress（留学申请进度）
   - id BIGINT PK, student_id BIGINT, target_school, target_major,
     stage ENUM('document_prep','submitted','under_review',
                'offer_received','visa_processing','enrolled'),
     progress_detail TEXT, deadline DATE, next_action VARCHAR(255),
     handler_id BIGINT, create_time, update_time

8. academic_deadline（学业截止事项）
   - id BIGINT PK, student_id BIGINT,
     deadline_type ENUM('paper','exam','application','visa','other'),
     title VARCHAR(255), description TEXT, deadline DATETIME,
     reminder_enabled TINYINT, reminder_days JSON,
     status ENUM('pending','reminded','done','missed'), create_time, update_time

9. student_admin_service（请假/行政审批）
   - id BIGINT PK, student_id BIGINT,
     service_type ENUM('leave','exam_query','other'),
     leave_type ENUM('sick','personal','emergency'),
     start_time DATETIME, end_time DATETIME, reason TEXT,
     attachment_url VARCHAR(512),
     status ENUM('pending','approved','rejected','cancelled'),
     approver_id BIGINT, approval_comment VARCHAR(512),
     approval_time DATETIME, related_academic_id BIGINT, create_time, update_time

10. student_score（学生成绩）
    - id BIGINT PK, student_id BIGINT, subject VARCHAR(64),
      score DECIMAL(5,1), exam_type VARCHAR(32), exam_date DATE,
      admin_user_id BIGINT, input_time DATETIME, create_time, update_time

═══════════════════════════════════════════════════════════
四、投诉工单模块
═══════════════════════════════════════════════════════════

11. student_complaint（投诉单）
    - id BIGINT PK, student_id BIGINT, complaint_detail TEXT,
      complaint_type VARCHAR(32),
      handle_status ENUM('待处理','处理中','已解决','已关闭'),
      handler_user_id BIGINT FK→account.user_id, create_time, update_time

12. student_feedback_ticket（反馈工单：投诉/建议/咨询）
    - id BIGINT PK, student_id BIGINT,
      ticket_type ENUM('complaint','suggestion','consult'),
      category VARCHAR(64), title VARCHAR(255), content TEXT, detail TEXT,
      status ENUM('pending','processing','resolved','closed'),
      priority ENUM('low','medium','high','urgent'),
      assignee_id BIGINT, solution TEXT, satisfaction TINYINT,
      is_notified TINYINT, create_time, update_time

═══════════════════════════════════════════════════════════
五、学生心理健康模块
═══════════════════════════════════════════════════════════

13. student_psych_record（情绪打卡明细流水）
    - id BIGINT PK, student_id BIGINT, emotion_tag VARCHAR(64),
      emotion_score INT, interaction_content TEXT,
      trigger_keywords JSON, record_date DATE, create_time

14. student_psych_profile（学生心理汇总档案）
    - id BIGINT PK, student_id BIGINT, latest_emotion_tag VARCHAR(64),
      emotion_score INT, last_interaction_time DATETIME,
      risk_level ENUM('low','medium','high'), weekly_summary JSON,
      create_time, update_time

15. student_mental_alert（心理预警记录）
    - id INT PK, student_id INT, student_name VARCHAR(50),
      trigger_reason TEXT, risk_level VARCHAR(10), alert_content TEXT,
      emotion_label VARCHAR(30), risk_score INT,
      follow_up_status VARCHAR(20), assigned_teacher_id INT,
      assigned_teacher VARCHAR(50), action_taken TEXT,
      resolved_at DATETIME, created_at

16. student_psych_alert（轻量化心理告警）
    - id BIGINT PK, student_id BIGINT, trigger_reason TEXT,
      risk_level ENUM('low','medium','high'),
      status ENUM('pending','following','resolved','dismissed'),
      teacher_id BIGINT, follow_record TEXT,
      resolved_time DATETIME, create_time, update_time

17. student_mental_profile（心理画像/对话统计）
    - id INT PK, student_id INT, student_name VARCHAR(50),
      current_emotion VARCHAR(30), risk_score INT, risk_level VARCHAR(10),
      last_conversation TEXT, last_assessment_at DATETIME,
      history_notes JSON, total_chat_count INT, negative_count INT,
      consecutive_negative INT, teacher_notified TINYINT(1),
      created_at, updated_at

═══════════════════════════════════════════════════════════
六、辅助业务表
═══════════════════════════════════════════════════════════

18. courses（课程表）
    - id INT PK, course_name, category, sub_category, country,
      target_education, min_gpa, max_budget, min_budget,
      language_requirement, duration, price, description, highlights,
      is_active TINYINT, created_at

═══════════════════════════════════════════════════════════
关联关系：
- intention_customer.sales_user_id → account.user_id
- account.dept_id → organization.id
- employee_daily_report.user_id → account.user_id
- employee_daily_report.dept_id → organization.id
- consultations.course_id → courses.id
- student_psych_record/psych_profile/mental_alert/psych_alert/mental_profile
  通过 student_id 互相关联
- student_complaint.handler_user_id → account.user_id
- student_feedback_ticket.assignee_id → account.user_id
═══════════════════════════════════════════════════════════
"""
