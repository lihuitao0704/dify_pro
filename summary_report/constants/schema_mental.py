"""
学生心理健康模块相关表结构（用于 NL2SQL 提示词）。

基于 dify_pro 真实表结构。覆盖：
  - student_psych_record    情绪打卡明细流水
  - student_psych_profile   学生心理汇总档案
  - student_mental_alert    心理预警记录
  - student_psych_alert     轻量化心理告警
  - student_mental_profile  心理画像（含对话统计）
"""

MENTAL_SCHEMA: str = """
以下为学生心理健康相关表结构：

1. student_psych_record（情绪打卡明细流水）
   - id: BIGINT PK
   - student_id: BIGINT, 学生ID
   - emotion_tag: VARCHAR(64), 情绪标签（开心/焦虑/孤独/平静/兴奋/沮丧等）
   - emotion_score: INT, 情绪评分（数值越高越好）
   - interaction_content: TEXT, 互动/对话内容
   - trigger_keywords: JSON, 触发关键词
   - record_date: DATE, 记录日期
   - create_time: DATETIME, 创建时间

2. student_psych_profile（学生心理汇总档案）
   - id: BIGINT PK
   - student_id: BIGINT, 学生ID
   - latest_emotion_tag: VARCHAR(64), 最近情绪标签
   - emotion_score: INT, 情绪评分
   - last_interaction_time: DATETIME, 最近互动时间
   - risk_level: ENUM('low','medium','high'), 风险等级（低/中/高）
   - weekly_summary: JSON, 周度汇总
   - create_time: DATETIME
   - update_time: DATETIME

3. student_mental_alert（心理预警记录）
   - id: INT PK
   - student_id: INT, 学生ID
   - student_name: VARCHAR(50), 学生姓名
   - trigger_reason: TEXT, 触发原因
   - risk_level: VARCHAR(10), 风险等级
   - alert_content: TEXT, 预警内容
   - emotion_label: VARCHAR(30), 情绪标签
   - risk_score: INT, 风险分数
   - follow_up_status: VARCHAR(20), 跟进状态
   - assigned_teacher_id: INT, 指派老师ID
   - assigned_teacher: VARCHAR(50), 指派老师姓名
   - action_taken: TEXT, 已采取措施
   - resolved_at: DATETIME, 解决时间
   - created_at: DATETIME, 创建时间

4. student_psych_alert（轻量化心理告警）
   - id: BIGINT PK
   - student_id: BIGINT, 学生ID
   - trigger_reason: TEXT, 触发原因
   - risk_level: ENUM('low','medium','high'), 风险等级
   - status: ENUM('pending','following','resolved','dismissed'), 状态（待处理/跟进中/已解决/已忽略）
   - teacher_id: BIGINT, 老师ID
   - follow_record: TEXT, 跟进记录
   - resolved_time: DATETIME, 解决时间
   - create_time: DATETIME
   - update_time: DATETIME

5. student_mental_profile（心理画像，含对话统计）
   - id: INT PK
   - student_id: INT, 学生ID
   - student_name: VARCHAR(50), 学生姓名
   - current_emotion: VARCHAR(30), 当前情绪
   - risk_score: INT, 风险分数
   - risk_level: VARCHAR(10), 风险等级
   - last_conversation: TEXT, 最近对话
   - last_assessment_at: DATETIME, 最近评估时间
   - history_notes: JSON, 历史记录
   - total_chat_count: INT, 总对话次数
   - negative_count: INT, 负面次数
   - consecutive_negative: INT, 连续负面次数
   - teacher_notified: TINYINT(1), 是否已通知老师
   - created_at: DATETIME
   - updated_at: DATETIME

关联关系：
- student_psych_record.student_id ↔ student_psych_profile.student_id
- student_mental_alert.student_id ↔ student_psych_profile.student_id
- student_psych_alert.student_id ↔ student_psych_profile.student_id
- student_mental_profile.student_id ↔ student_psych_profile.student_id
"""
