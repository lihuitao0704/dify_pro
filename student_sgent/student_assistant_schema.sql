-- ============================================================
-- 学生智能助手数据库表结构
-- 目标数据库: test (MySQL 8.0+ / 兼容 MariaDB 10.5+)
-- 字符集: utf8mb4
-- 设计原则: 核心-业务-日志 三层隔离
-- ============================================================

CREATE DATABASE IF NOT EXISTS test
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE test;

-- ============================================================
-- 一、核心基础层
-- ============================================================

-- 1. 学生主表：充当数据总线，关联外部系统 ID
CREATE TABLE students (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    union_id            VARCHAR(64) NOT NULL COMMENT '全局唯一用户 ID（跨系统打通）',
    crm_customer_id     VARCHAR(64) DEFAULT NULL COMMENT 'CRM 系统客户 ID（进度追踪）',
    edu_system_id       VARCHAR(64) DEFAULT NULL COMMENT '教务系统学生 ID（DDL/成绩）',
    name                VARCHAR(32) DEFAULT NULL COMMENT '姓名（脱敏存储）',
    grade               TINYINT     DEFAULT NULL COMMENT '当前年级（用于营销画像）',
    target_country      VARCHAR(32) DEFAULT NULL COMMENT '意向国家',
    status              TINYINT     NOT NULL DEFAULT 0 COMMENT '0-正常 1-停用 2-流失',
    created_at          DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at          DATETIME    DEFAULT NULL COMMENT '软删除时间',

    UNIQUE KEY uk_union_id (union_id),
    KEY idx_crm_customer_id (crm_customer_id),
    KEY idx_edu_system_id (edu_system_id),
    KEY idx_grade (grade),
    KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学生主表';

-- 2. 会话主表：会话级记忆与审计追溯
CREATE TABLE conversation_sessions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id      BIGINT      NOT NULL COMMENT '关联学生主表',
    session_token   VARCHAR(64) NOT NULL COMMENT '会话令牌',
    agent_type      VARCHAR(32) DEFAULT NULL COMMENT '路由到的垂类 Agent',
    start_time      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time        DATETIME    DEFAULT NULL,
    message_count   INT         NOT NULL DEFAULT 0,
    created_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME    DEFAULT NULL,

    UNIQUE KEY uk_session_token (session_token),
    KEY idx_student_id (student_id),
    KEY idx_start_time (start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话主表';

-- 3. 消息明细表：存储原始对话，应用层 AES-256 加密
CREATE TABLE conversation_messages (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id      BIGINT          NOT NULL COMMENT '关联会话表',
    role            TINYINT         NOT NULL COMMENT '1-用户 2-AI 3-系统兜底',
    content         TEXT            COMMENT '对话原文（应用层加密）',
    emotion_score   DECIMAL(3,2)    DEFAULT NULL COMMENT '情绪实时打分 -1.0 ~ 1.0',
    cost_token      INT             DEFAULT NULL COMMENT '本次调用消耗 Token 数',
    llm_model       VARCHAR(16)     DEFAULT NULL COMMENT '实际调用的模型，如 gpt-4o/mini',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY idx_session_id_created_at (session_id, created_at),
    KEY idx_emotion_score (emotion_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息明细表';

-- ============================================================
-- 二、业务事务层
-- ============================================================

-- 4. 请假申请表：学生提交-班主任审批闭环
CREATE TABLE leave_applications (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id          BIGINT          NOT NULL COMMENT '关联学生主表',
    idempotent_key      VARCHAR(128)    NOT NULL COMMENT '幂等键：{student_id}_{start_date}_{type}',
    leave_type          TINYINT         NOT NULL DEFAULT 1 COMMENT '1-病假 2-事假 3-其他',
    start_date          DATE            NOT NULL,
    end_date            DATE            NOT NULL,
    reason              VARCHAR(255)    DEFAULT NULL,
    attachment_url      VARCHAR(512)    DEFAULT NULL COMMENT '病假条等附件 OSS 地址',
    status              TINYINT         NOT NULL DEFAULT 0 COMMENT '0-待审 1-通过 2-驳回 3-已撤销',
    approver_id         BIGINT          DEFAULT NULL COMMENT '审批人（班主任 ID）',
    approved_at         DATETIME        DEFAULT NULL,
    notify_status       TINYINT         NOT NULL DEFAULT 0 COMMENT '0-未推送 1-推送中 2-已送达',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at          DATETIME        DEFAULT NULL,

    UNIQUE KEY uk_idempotent_key (idempotent_key),
    KEY idx_status_approver_id (status, approver_id),
    KEY idx_student_id (student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='请假申请表';

-- 5. 售后反馈工单表：投诉提交-处理-满意度回调
CREATE TABLE feedback_tickets (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id          BIGINT          NOT NULL,
    category            TINYINT         NOT NULL COMMENT '1-签证 2-文书 3-费用 4-生活服务 5-其他',
    priority            TINYINT         NOT NULL DEFAULT 2 COMMENT '1-低 2-中 3-紧急',
    ai_summary          VARCHAR(500)    DEFAULT NULL COMMENT 'AI 智能摘要',
    full_content        TEXT            COMMENT '原始投诉内容（加密）',
    status              TINYINT         NOT NULL DEFAULT 0 COMMENT '0-待分配 1-处理中 2-待复核 3-已关闭',
    handler_id          BIGINT          DEFAULT NULL COMMENT '当前处理人',
    sla_deadline        DATETIME        NOT NULL COMMENT 'SLA 截止时间（创建+24h）',
    satisfaction_score  TINYINT         DEFAULT NULL COMMENT '1-5 星（关闭后回填）',
    closed_at           DATETIME        DEFAULT NULL,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at          DATETIME        DEFAULT NULL,

    KEY idx_student_id (student_id),
    KEY idx_category (category),
    KEY idx_priority (priority),
    KEY idx_status (status),
    KEY idx_sla_deadline (sla_deadline)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='售后反馈工单表';

-- ============================================================
-- 三、风险与分析层
-- ============================================================

-- 6. 心理画像日快照表：不存无限增长的聊天记录，每日汇总
CREATE TABLE emotion_profile_snapshots (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id          BIGINT          NOT NULL,
    snapshot_date       DATE            NOT NULL COMMENT '快照日期，如 2026-07-09',
    avg_emotion_score   DECIMAL(3,2)    DEFAULT NULL COMMENT '当日情绪均值',
    min_emotion_score   DECIMAL(3,2)    DEFAULT NULL COMMENT '当日最低谷值',
    peak_negative_tags  JSON            DEFAULT NULL COMMENT '高频负向标签，如 ["学业焦虑","孤独"]',
    daily_chat_count    INT             DEFAULT NULL COMMENT '当日交互轮数',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_student_snapshot (student_id, snapshot_date),
    KEY idx_snapshot_date (snapshot_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='心理画像日快照表';

-- 7. 心理预警干预记录表：触碰红线的离散事件
CREATE TABLE risk_interventions (
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id              BIGINT          NOT NULL,
    trigger_rule_id         INT             NOT NULL COMMENT '触发的规则 ID（关联配置表）',
    risk_level              TINYINT         NOT NULL COMMENT '1-黄（关注） 2-红（高危）',
    trigger_evidence        VARCHAR(500)    DEFAULT NULL COMMENT 'AI 二次确认摘要，不存完整对话',
    ai_raw_output           TEXT            COMMENT '模型输出的原始风险判断 JSON（审计留痕）',
    human_confirmed_status  TINYINT         NOT NULL DEFAULT 0 COMMENT '0-待人工确认 1-已确认属实 2-误报',
    handler_id              BIGINT          DEFAULT NULL COMMENT '介入的老师 ID',
    handled_at              DATETIME        DEFAULT NULL,
    created_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    KEY idx_student_id (student_id),
    KEY idx_risk_level (risk_level),
    KEY idx_human_confirmed_status (human_confirmed_status),
    KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='心理预警干预记录表';

-- ============================================================
-- 四、辅助与配置层
-- ============================================================

-- 8. 学业考务 DDL 提醒表：只存待推送任务和推送状态
CREATE TABLE deadline_reminders (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id      BIGINT          NOT NULL,
    event_type      TINYINT         NOT NULL COMMENT '1-论文截止 2-考试时间 3-选课开始',
    event_name      VARCHAR(128)    NOT NULL COMMENT '如 毕业论文初稿提交',
    deadline_time   DATETIME        NOT NULL COMMENT '截止时间（Cron 扫描）',
    push_status     TINYINT         NOT NULL DEFAULT 0 COMMENT '0-待推送 1-已推送 2-已读',
    push_at         DATETIME        DEFAULT NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    KEY idx_student_id (student_id),
    KEY idx_deadline_time (deadline_time),
    KEY idx_push_status (push_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='学业考务 DDL 提醒表';

-- 9. 增值转化触达日志表：防骚扰合规、效果分析
CREATE TABLE marketing_touch_logs (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id          BIGINT          NOT NULL,
    program_id          VARCHAR(64)     NOT NULL COMMENT '推荐的项目 ID',
    ai_generated_text   TEXT            COMMENT '模型生成的推荐话术（留痕）',
    user_clicked        TINYINT         NOT NULL DEFAULT 0 COMMENT '0-未点击 1-已点击（计算 CTR）',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    KEY idx_student_id (student_id),
    KEY idx_program_id (program_id),
    KEY idx_created_at (created_at),
    KEY idx_student_created_at (student_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='增值转化触达日志表';

-- 10. 系统配置表：运维神器，无需改代码即可调策略
CREATE TABLE system_configs (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    config_key      VARCHAR(128)    NOT NULL COMMENT '配置键',
    config_value    TEXT            COMMENT '配置值',
    description     VARCHAR(255)    DEFAULT NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_config_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统配置表';

-- ============================================================
-- 五、默认配置数据
-- ============================================================

INSERT INTO system_configs (config_key, config_value, description) VALUES
('risk_keywords', '["活着没意思","不想活了","自残","自杀","抑郁","焦虑","失眠"]', '心理高危关键词库'),
('sla_hours', '24', '售后工单 SLA 时限（小时）'),
('max_leave_days', '30', '单次请假最大天数'),
('emotion_threshold_red', '-0.8', '情绪红色预警阈值'),
('emotion_threshold_yellow', '-0.4', '情绪黄色关注阈值'),
('marketing_cooldown_days', '7', '同一学生营销触达最小间隔（天）'),
('message_hot_retention_days', '30', '消息热数据保留天数')
ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;

-- ============================================================
-- 六、ER 图关键关联说明
-- ============================================================
-- students(1) ----< conversation_sessions(N) ----< conversation_messages(N)
-- students(1) ----< leave_applications(N)
-- students(1) ----< feedback_tickets(N)
-- students(1) ----< emotion_profile_snapshots(N)
-- students(1) ----< risk_interventions(N)
-- students(1) ----< deadline_reminders(N)
-- students(1) ----< marketing_touch_logs(N)
-- system_configs 为全局配置表，无直接外键关联
-- ============================================================