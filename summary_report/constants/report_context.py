"""
各报告固定描述文案（report context）。

在每份报告的 NL2SQL 润色阶段作为"报告背景"注入提示词，
引导 LLM 按对应业务场景输出专业报告，而不是泛泛的数据复述。

注意：文案中的字段/维度建议需与 schema_*.py 的真实字段保持一致。
"""

CUSTOMER_REPORT_CONTEXT: str = """
【全域客户经营分析报告】
核心目标：全面覆盖签约、跟进中、已流失三大客群。
- 意向客户：按 customer_source 分析渠道效果、按 current_status 分布、按 sales_user_id 解析顾问业绩
- 签约客户：复盘签约路径与高价值画像（target_country/budget/language_score）
- 流失客户：智能归因（已流失状态分布、来源渠道流失率）
数据源：intention_customer / consultations / user_profiles / account / department
输出：从精准获客到流失挽回的全链路决策支持报告
"""

EMPLOYEE_REPORT_CONTEXT: str = """
【员工日报智能汇总报告】
核心目标：对全员提交的 employee_daily_report 文本内容进行自动化梳理与提炼。
- 按 user_id + 关联 account.real_name 统计员工的日报提交情况
- 按 dept_id + 关联 department.dept_name 汇总部门产出
- 从 report_content 文本中提取关键成果、风险/阻塞项
- 帮助管理层快速感知团队整体工作进度与项目健康度
数据源：employee_daily_report / account / department
注意：日报内容在 report_content 文本字段，分析时使用 LIKE 匹配关键词
"""

MENTAL_REPORT_CONTEXT: str = """
【学生心理健康周报】
核心目标：为学子提供全方位的心理状态监测与关怀支持。
- 基于 student_psych_record 的 emotion_score / emotion_tag 统计整体情绪态势
- 按 student_psych_profile.risk_level(low/medium/high) 识别风险学生分布
- 通过 student_mental_alert / student_psych_alert 汇总预警与处理情况
- 通过 student_mental_profile 的 total_chat_count/negative_count/consecutive_negative 评估对话健康度
- 精准识别孤独感、学业焦虑或文化冲突等潜在风险学生
数据源：student_psych_record / student_psych_profile / student_mental_alert / student_psych_alert / student_mental_profile
"""

COMPLAINT_REPORT_CONTEXT: str = """
【投诉处理周报】
核心目标：全流程数据追踪，提升服务售后质量与响应效率。
- 以 student_feedback_ticket 统计本周投诉(ticket_type='complaint')总量及同环比
- 按 category/priority/status 分类统计分布与处理时效
- 按 handle_status ENUM('待处理','处理中','已解决','已关闭')统计积压
- 跟进 satisfaction 满意度评分
- student_complaint 作为投诉主表补充 complaint_type 维度
数据源：student_feedback_ticket / student_complaint / account
"""

# 通用 NL2SQL 的兜底上下文
GENERAL_REPORT_CONTEXT: str = (
    "通用数据库查询 dify_pro，覆盖客户经营、员工管理、留学申请、"
    "投诉工单、心理健康、课程六大模块。"
)

STUDENT_REPORT_CONTEXT: str = """
【学生数据分析报告】
核心目标：面向校内学生群体的全景数据洞察。
- 留学申请进度：按 current_step 分布统计各阶段学生数量、关注 estimated_completion 临近的待办事项
- 学业成绩：按 subject/exam_type 分析成绩分布与趋势
- 行政审批：请假(leave)审批效率与类型分布
- 心理健康：基于 student_psych_record 的情绪态势、按 risk_level 识别风险学生分布
- 投诉反馈：投诉(ticket_type='complaint')总量、处理时效与满意度
数据源：application_progress / academic_deadline / student_admin_service / student_score / student_complaint / student_feedback_ticket / student_psych_record / student_psych_profile / student_mental_alert / student_psych_alert / student_mental_profile
注意：本类查询不涉及客户经营、员工日报等企业模块数据
"""

ENTERPRISE_REPORT_CONTEXT: str = """
【企业经营分析报告】
核心目标：面向企业经营与内部管理的数据洞察。
- 客户经营：按 customer_source 分析渠道效果、按 current_status 分布（已签约/跟进中/已流失）、按 sales_user_id 解析顾问业绩
- 员工日报：按 user_id/dept_id 统计日报提交情况、从 report_content 提取关键成果
- 课程管理：课程按 category/country 分布与定价分析
数据源：intention_customer / consultations / user_profiles / account / department / employee_daily_report / courses
注意：本类查询不涉及学生成绩、心理健康、留学申请等学生模块数据
"""
