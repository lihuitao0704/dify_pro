"""
投诉工单模块相关表结构（用于 NL2SQL 提示词）。

基于 dify_pro 真实表结构。覆盖：
  - student_complaint       投诉单
  - student_feedback_ticket 反馈/工单（含投诉/建议/咨询）
"""

COMPLAINT_SCHEMA: str = """
以下为投诉处理相关表结构：

1. student_complaint（投诉单）
   - id: BIGINT PK
   - student_id: BIGINT, 学生ID
   - complaint_detail: TEXT, 投诉详情
   - complaint_type: VARCHAR(32), 投诉类型（签证办理/院校申请/生活服务/课程质量/费用问题等）
   - handle_status: ENUM('待处理','处理中','已解决','已关闭'), 处理状态
   - handler_user_id: BIGINT, 处理人ID，关联 account.user_id
   - create_time: DATETIME, 创建时间
   - update_time: DATETIME, 更新时间

2. student_feedback_ticket（反馈工单，含投诉/建议/咨询）
   - id: BIGINT PK
   - student_id: BIGINT, 学生ID
   - ticket_type: ENUM('complaint','suggestion','consult'), 工单类型（投诉/建议/咨询）
   - category: VARCHAR(64), 分类
   - title: VARCHAR(255), 标题
   - content: TEXT, 内容
   - detail: TEXT, 详情
   - status: ENUM('pending','processing','resolved','closed'), 状态（待处理/处理中/已解决/已关闭）
   - priority: ENUM('low','medium','high','urgent'), 优先级（低/中/高/紧急）
   - assignee_id: BIGINT, 受理人ID
   - solution: TEXT, 解决方案
   - satisfaction: TINYINT, 满意度评分（数值）
   - is_notified: TINYINT, 是否已通知
   - create_time: DATETIME, 创建时间
   - update_time: DATETIME, 更新时间

关联关系：
- student_complaint.student_id ↔ student_feedback_ticket.student_id
- student_complaint.handler_user_id → account.user_id
- student_feedback_ticket.assignee_id → account.user_id

注意：投诉数据分散在两张表，student_complaint 是投诉主表，
      student_feedback_ticket 覆盖更全（投诉/建议/咨询），
      需要全面统计时建议以 student_feedback_ticket 为主。
"""