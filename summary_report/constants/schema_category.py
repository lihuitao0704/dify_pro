"""
按「查询类型」聚合的 schema 与注册表。

用于通用 NL2SQL 接口（/nl2sql）的 query_type 表单筛选：
  - general    : 使用 FULL_SCHEMA（全量 19 张表，默认值，向后兼容）
  - student    : 仅学生相关表（留学业务 + 投诉工单 + 心理健康）
  - enterprise : 仅企业相关表（客户经营 + 员工管理 + 课程）

每个 schema 末尾的「分类说明」行仅供 LLM 理解范围边界，不参与 SQL 生成。
"""

from summary_report.constants.report_context import (
    ENTERPRISE_REPORT_CONTEXT,
    GENERAL_REPORT_CONTEXT,
    STUDENT_REPORT_CONTEXT,
)
from summary_report.constants.schema_all import FULL_SCHEMA

# ── 学生类 schema ────────────────────────────────────────────
STUDENT_SCHEMA: str = """
以下为学生相关模块的表结构：

═══════════════════════════════════════════════════════════
一、留学业务学生基础表
═══════════════════════════════════════════════════════════

1. application_progress（留学申请进度）
   - id INT PK, student_id INT,
     program_name VARCHAR(200)（申请项目名称）,
     university VARCHAR(200)（目标院校）,
     current_step VARCHAR(100)（当前步骤）,
     step_order INT（步骤序）,
     steps JSON（步骤明细 [{step,status,completed_at,notes}]）,
     application_status VARCHAR(30)（in_progress/completed/withdrawn）,
     submitted_date DATE, estimated_completion DATE,
     notes TEXT, updated_by VARCHAR(100),
     created_at DATETIME, updated_at DATETIME

2. academic_deadline（学业截止事项）
   - id BIGINT PK, student_id BIGINT,
     deadline_type ENUM('paper','exam','application','visa','other'),
     title VARCHAR(255), description TEXT, deadline DATETIME,
     reminder_enabled TINYINT, reminder_days JSON,
     status ENUM('pending','reminded','done','missed'), create_time, update_time

3. student_admin_service（请假/行政审批）
   - id BIGINT PK, student_id BIGINT,
     service_type ENUM('leave','exam_query','other'),
     leave_type ENUM('sick','personal','emergency'),
     start_time DATETIME, end_time DATETIME, reason TEXT,
     attachment_url VARCHAR(512),
     status ENUM('pending','approved','rejected','cancelled'),
     approver_id BIGINT, approval_comment VARCHAR(512),
     approval_time DATETIME, related_academic_id BIGINT, create_time, update_time

4. student_score（学生成绩）
   - id BIGINT PK, student_id BIGINT, subject VARCHAR(64),
     score DECIMAL(5,1), exam_type VARCHAR(32), exam_date DATE,
     admin_user_id BIGINT, input_time DATETIME, create_time, update_time

═══════════════════════════════════════════════════════════
二、投诉工单模块
═══════════════════════════════════════════════════════════

5. student_complaint（投诉单）
   - id BIGINT PK, student_id BIGINT, complaint_detail TEXT,
     complaint_type VARCHAR(32),
     handle_status ENUM('待处理','处理中','已完结','驳回'),
     handler_user_id BIGINT FK→account.user_id, create_time, update_time

6. student_feedback_ticket（反馈工单：投诉/建议/咨询）
   - id BIGINT PK, student_id BIGINT,
     ticket_type ENUM('complaint','suggestion','consult'),
     category VARCHAR(64), title VARCHAR(255), content TEXT, detail TEXT,
     status ENUM('pending','processing','resolved','closed'),
     priority ENUM('low','medium','high','urgent'),
     assignee_id BIGINT, solution TEXT, satisfaction TINYINT,
     is_notified TINYINT, create_time, update_time

═══════════════════════════════════════════════════════════
三、学生心理健康模块
═══════════════════════════════════════════════════════════

7. student_psych_record（情绪打卡明细流水）
   - id BIGINT PK, student_id BIGINT, emotion_tag VARCHAR(64),
     emotion_score INT, interaction_content TEXT,
     trigger_keywords JSON, record_date DATE, create_time

8. student_psych_profile（学生心理汇总档案）
   - id BIGINT PK, student_id BIGINT, latest_emotion_tag VARCHAR(64),
     emotion_score INT, last_interaction_time DATETIME,
     risk_level ENUM('low','medium','high'), weekly_summary JSON,
     create_time, update_time

9. student_mental_alert（心理预警记录）
   - id INT PK, student_id INT, student_name VARCHAR(50),
     trigger_reason TEXT, risk_level VARCHAR(10), alert_content TEXT,
     emotion_label VARCHAR(30), risk_score INT,
     follow_up_status VARCHAR(20), assigned_teacher_id INT,
     assigned_teacher VARCHAR(50), action_taken TEXT,
     resolved_at DATETIME, created_at

10. student_psych_alert（轻量化心理告警）
    - id BIGINT PK, student_id BIGINT, trigger_reason TEXT,
      risk_level ENUM('low','medium','high'),
      status ENUM('pending','following','resolved','dismissed'),
      teacher_id BIGINT, follow_record TEXT,
      resolved_time DATETIME, create_time, update_time

11. student_mental_profile（心理画像/对话统计）
    - id INT PK, student_id INT, student_name VARCHAR(50),
      current_emotion VARCHAR(30), risk_score INT, risk_level VARCHAR(10),
      last_conversation TEXT, last_assessment_at DATETIME,
      history_notes JSON, total_chat_count INT, negative_count INT,
      consecutive_negative INT, teacher_notified TINYINT(1),
      created_at, updated_at

═══════════════════════════════════════════════════════════
关联关系：
- 上述所有表通过 student_id 互相关联
- student_complaint.handler_user_id → account.user_id
- student_feedback_ticket.assignee_id → account.user_id
═══════════════════════════════════════════════════════════

【分类说明：本类别仅包含学生相关数据表（留学业务、投诉工单、心理健康），不涉及客户经营、员工日报等企业模块。如需查询客户/员工数据，请使用 enterprise 类别。】
"""

# ── 企业类 schema ────────────────────────────────────────────
ENTERPRISE_SCHEMA: str = """
以下为企业相关模块的表结构：

═══════════════════════════════════════════════════════════
一、客户经营模块
═══════════════════════════════════════════════════════════

1. intention_customer（意向客户主表）
   - customer_id BIGINT PK, customer_name VARCHAR(64),
     customer_age TINYINT, customer_gender VARCHAR(8),
     customer_phone VARCHAR(20),
     customer_source VARCHAR(32)（官网/地推/转介绍/广告投放/社交媒体等）,
     customer_demand TEXT, follow_record TEXT,
     current_status ENUM('已签约','跟进中','已流失'),
     sales_user_id BIGINT FK→account.user_id,
     create_time, update_time

2. consultations（咨询记录）
   - id INT PK, user_id INT, course_id INT FK→courses.id,
     conversation_summary TEXT, recommended_courses TEXT,
     user_feedback VARCHAR(255), status VARCHAR(20), created_at

3. user_profiles（客户画像）
   - id BIGINT PK, conversation_id VARCHAR(64)（Dify会话ID）,
     name VARCHAR(50), age INT, major VARCHAR(100), education VARCHAR(50),
     target_major VARCHAR(100), language_score VARCHAR(50),
     target_country VARCHAR(100), gpa DECIMAL(3,2), budget INT,
     phone VARCHAR(20), wechat VARCHAR(50), email VARCHAR(128),
     consultation_status ENUM('new','recommended','interested','not_interested','consulting'),
     assess VARCHAR(50), development VARCHAR(50), abilities VARCHAR(50),
     is_Closed_loop VARCHAR(10),
     created_at TIMESTAMP, updated_at TIMESTAMP

4. account（账户表，含销售顾问/员工）
   - user_id BIGINT PK, username VARCHAR(64), real_name VARCHAR(64),
     user_type VARCHAR(32)（sales/teacher/student/admin等）,
     dept_id BIGINT FK→department.dept_id, student_id BIGINT,
     phone VARCHAR(20), email VARCHAR(128), status TINYINT,
     create_time, update_time

5. department（部门表）
   - dept_id BIGINT PK, dept_name VARCHAR(50), dept_desc TEXT,
     manager_id BIGINT（关联 employee.emp_id）,
     parent_dept_id BIGINT, status TINYINT,
     create_time, update_time

═══════════════════════════════════════════════════════════
二、员工管理模块
═══════════════════════════════════════════════════════════

6. employee_daily_report（员工日报表）
   - id BIGINT PK, user_id BIGINT FK→account.user_id,
     dept_id BIGINT FK→department.dept_id,
     report_content TEXT（日报正文）,
     submit_time DATETIME, report_date DATE, create_time, update_time

═══════════════════════════════════════════════════════════
三、辅助业务表
═══════════════════════════════════════════════════════════

7. courses（课程表）
   - id INT PK, course_name VARCHAR(200), category VARCHAR(50),
     sub_category VARCHAR(50), country VARCHAR(60),
     target_education VARCHAR(50), min_gpa DECIMAL(3,2),
     max_budget DECIMAL(12,2), min_budget DECIMAL(12,2),
     language_requirement VARCHAR(100), duration VARCHAR(50),
     price DECIMAL(12,2), description TEXT, highlights TEXT,
     is_active TINYINT, created_at

═══════════════════════════════════════════════════════════
关联关系：
- intention_customer.sales_user_id → account.user_id（销售顾问）
- account.dept_id → department.dept_id（所属部门）
- employee_daily_report.user_id → account.user_id（员工）
- employee_daily_report.dept_id → department.dept_id（部门）
- consultations.course_id → courses.id
═══════════════════════════════════════════════════════════

【分类说明：本类别仅包含企业相关数据表（客户经营、员工管理、课程），不涉及学生成绩、心理健康、留学申请等学生模块。如需查询学生数据，请使用 student 类别。】
"""

# ── query_type 注册表 ────────────────────────────────────────
# 查询类型 → (schema, report_context) 映射，供路由层按 query_type 分发

QUERY_TYPE_REGISTRY: dict[str, tuple[str, str]] = {
    "general": (FULL_SCHEMA, GENERAL_REPORT_CONTEXT),
    "student": (STUDENT_SCHEMA, STUDENT_REPORT_CONTEXT),
    "enterprise": (ENTERPRISE_SCHEMA, ENTERPRISE_REPORT_CONTEXT),
}


def resolve_query_type(query_type: str) -> tuple[str, str]:
    """
    根据 query_type 返回对应的 (schema, report_context)。

    Args:
        query_type: 查询类型标识，取值 general / student / enterprise。

    Returns:
        (schema, report_context) 元组。

    Raises:
        ValueError: query_type 不在注册表中时抛出。
    """
    if query_type not in QUERY_TYPE_REGISTRY:
        raise ValueError(
            f"不支持的查询类型: {query_type!r}，"
            f"可选值: {list(QUERY_TYPE_REGISTRY.keys())}"
        )
    return QUERY_TYPE_REGISTRY[query_type]
