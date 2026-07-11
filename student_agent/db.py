"""
数据库层：11张表建表 + CRUD 工具 + NL2SQL 执行
连接池 + 启动时自动建库建表，填充种子数据（幂等：已存在则跳过）
v2: 使用连接池（Pooling），替代每次新建连接
"""

import pymysql
from datetime import datetime
from queue import Queue, Empty
from .config import DB_CONFIG


# ============================================================
#  连接池
# ============================================================
_pool = None
_POOL_SIZE = 5

def _get_pool():
    global _pool
    if _pool is None:
        _pool = Queue(maxsize=_POOL_SIZE)
        for _ in range(_POOL_SIZE):
            _pool.put(_create_conn())
    return _pool

def _create_conn():
    return pymysql.connect(**DB_CONFIG)

def get_conn():
    """获取数据库连接（来自连接池）"""
    try:
        return _get_pool().get_nowait()
    except Empty:
        return _create_conn()

def _release_conn(conn):
    """归还连接到连接池"""
    try:
        _get_pool().put_nowait(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def get_conn_no_db():
    """获取不指定数据库的连接（用于建库）"""
    cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    return pymysql.connect(**cfg)


# ============================================================
#  通用 CRUD
# ============================================================

def query(sql: str, params: tuple = None) -> list[dict]:
    """执行 SELECT，返回 list[dict]（连接池版）"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            if not rows:
                return []
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in rows]
    finally:
        _release_conn(conn)


def query_one(sql: str, params: tuple = None) -> dict | None:
    """执行 SELECT，返回单条 dict 或 None（连接池版）"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
    finally:
        _release_conn(conn)


def execute(sql: str, params: tuple = None) -> int:
    """执行 INSERT/UPDATE/DELETE，返回 lastrowid"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        _release_conn(conn)


def execute_many(sql: str, params_list: list[tuple]):
    """批量执行 INSERT/UPDATE/DELETE"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, params_list)
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release_conn(conn)


# ============================================================
#  表级别的便捷方法
# ============================================================

def insert(table: str, data: dict) -> int:
    """插入一条记录，返回自增ID"""
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["%s"] * len(data))
    values = tuple(data.values())
    sql = f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})"
    return execute(sql, values)


def update(table: str, where: dict, data: dict) -> int:
    """更新记录，返回 affected_rows（不再错误地返回 lastrowid）"""
    set_clause = ", ".join([f"`{k}` = %s" for k in data])
    where_clause = " AND ".join([f"`{k}` = %s" for k in where])
    values = tuple(data.values()) + tuple(where.values())
    sql = f"UPDATE `{table}` SET {set_clause} WHERE {where_clause}"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, values)
            conn.commit()
            return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        _release_conn(conn)


def delete(table: str, where: dict) -> int:
    """删除记录，返回 affected_rows"""
    where_clause = " AND ".join([f"`{k}` = %s" for k in where])
    sql = f"DELETE FROM `{table}` WHERE {where_clause}"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(where.values()))
            conn.commit()
            return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        _release_conn(conn)


# ============================================================
#  建库 + 建表（11张）
# ============================================================

ALL_TABLES_SQL = r"""

-- ==================== 基础层 ====================

CREATE TABLE IF NOT EXISTS student (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(50)  NOT NULL,
    phone               VARCHAR(20),
    email               VARCHAR(100),
    education           VARCHAR(20)  COMMENT '本科/硕士/高中',
    major               VARCHAR(100) COMMENT '专业',
    school              VARCHAR(100) COMMENT '毕业院校',
    gpa                 VARCHAR(10),
    language_score      VARCHAR(50)  COMMENT 'IELTS 7.0 / TOEFL 100',
    target_country      VARCHAR(100) COMMENT '意向留学国家',
    target_degree       VARCHAR(20)  COMMENT '本科/硕士/博士',
    target_major        VARCHAR(100) COMMENT '意向专业',
    assigned_teacher_id INT          COMMENT 'FK→teacher',
    contract_status     VARCHAR(20)  DEFAULT 'active' COMMENT 'active/completed/terminated',
    enrollment_date     DATE,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_teacher (assigned_teacher_id),
    INDEX idx_status (contract_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS teacher (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL,
    phone       VARCHAR(20),
    email       VARCHAR(100),
    department  VARCHAR(50)  COMMENT '教学部/咨询部/心理辅导',
    role        VARCHAR(20)  COMMENT '班主任/审批人/心理辅导/销售顾问',
    is_active   TINYINT(1) DEFAULT 1,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_department (department),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ==================== 业务层 ====================

CREATE TABLE IF NOT EXISTS leave_request (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    student_id      INT NOT NULL,
    leave_type      VARCHAR(20)  NOT NULL COMMENT '事假/病假/其他',
    start_time      DATETIME NOT NULL,
    end_time        DATETIME NOT NULL,
    reason          TEXT,
    attachment_url  VARCHAR(500),
    status          VARCHAR(20)  DEFAULT 'pending' COMMENT 'pending/approved/rejected',
    approver_id     INT          COMMENT 'FK→teacher',
    approver_name   VARCHAR(50),
    approval_remark TEXT,
    approved_at     DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_status (status),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS mental_health_profile (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    student_id              INT NOT NULL UNIQUE,
    current_emotion         VARCHAR(30)  DEFAULT '正常' COMMENT '正常/焦虑/低落/孤独/适应困难/积极',
    risk_score              INT          DEFAULT 0  COMMENT '0-100',
    risk_level              VARCHAR(10)  DEFAULT 'low' COMMENT 'low/medium/high/critical',
    emotion_history         JSON         COMMENT '[{date,emotion,score,trigger}]',
    negative_keywords_count INT          DEFAULT 0,
    consecutive_negative_days INT        DEFAULT 0,
    last_conversation       TEXT,
    last_assessment_at      DATETIME,
    teacher_notified        TINYINT(1)   DEFAULT 0,
    created_at              DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_risk (risk_level),
    INDEX idx_emotion (current_emotion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS mental_health_alert (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    student_id          INT NOT NULL,
    trigger_reason      TEXT NOT NULL,
    risk_level          VARCHAR(10) NOT NULL COMMENT 'high/critical',
    alert_content       TEXT        COMMENT '完整预警内容',
    emotion_label       VARCHAR(30) COMMENT '触发时的情绪标签',
    risk_score          INT,
    follow_up_status    VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/in_progress/resolved',
    assigned_teacher_id INT,
    assigned_teacher    VARCHAR(50),
    action_taken        TEXT,
    resolved_at         DATETIME,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_status (follow_up_status),
    INDEX idx_risk (risk_level),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS feedback_ticket (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    student_id    INT NOT NULL,
    title         VARCHAR(200),
    content       TEXT NOT NULL,
    summary       TEXT         COMMENT 'AI自动生成摘要',
    category      VARCHAR(50)  COMMENT '签证办理/院校申请/生活服务/教学质量/其他',
    urgency       VARCHAR(10)  DEFAULT 'normal' COMMENT 'normal/urgent',
    status        VARCHAR(20)  DEFAULT 'open' COMMENT 'open/processing/resolved/closed',
    priority      INT          DEFAULT 5 COMMENT '1-10',
    handler_id    INT,
    handler_name  VARCHAR(50),
    resolution    TEXT,
    satisfaction  VARCHAR(10)  COMMENT 'satisfied/neutral/unsatisfied',
    resolved_at   DATETIME,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_status (status),
    INDEX idx_category (category),
    INDEX idx_urgency (urgency)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS academic_schedule (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    student_id       INT NOT NULL,
    event_type       VARCHAR(30)  NOT NULL COMMENT '论文DDL/考试/选课截止/答辩/其他',
    title            VARCHAR(200) NOT NULL,
    course_name      VARCHAR(100),
    description      TEXT,
    deadline         DATETIME NOT NULL,
    priority         VARCHAR(10)  DEFAULT 'medium' COMMENT 'low/medium/high',
    status           VARCHAR(20)  DEFAULT 'upcoming' COMMENT 'upcoming/reminded/completed',
    source_system    VARCHAR(50)  COMMENT '教务系统/manual',
    reminder_24h_sent TINYINT(1) DEFAULT 0,
    reminder_3d_sent  TINYINT(1) DEFAULT 0,
    reminder_7d_sent  TINYINT(1) DEFAULT 0,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_deadline (deadline),
    INDEX idx_type (event_type),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS reminder_log (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    student_id     INT NOT NULL,
    schedule_id    INT COMMENT 'FK→academic_schedule',
    remind_type    VARCHAR(30)  COMMENT '考前提醒/DDL提醒/选课截止',
    remind_channel VARCHAR(20)  DEFAULT 'agent' COMMENT 'agent推送/微信/短信',
    message        TEXT,
    sent_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_read        TINYINT(1) DEFAULT 0,
    INDEX idx_student (student_id),
    INDEX idx_sent (sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS application_progress (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    student_id            INT NOT NULL,
    program_name          VARCHAR(200) NOT NULL COMMENT '申请项目名称',
    university            VARCHAR(200),
    current_step          VARCHAR(100) COMMENT '当前步骤',
    step_order            INT         COMMENT '步骤序号',
    steps                 JSON        COMMENT '[{step,status,completed_at,notes}]',
    application_status    VARCHAR(30) DEFAULT 'in_progress' COMMENT 'in_progress/completed/withdrawn',
    submitted_date        DATE,
    estimated_completion  DATE,
    notes                 TEXT,
    updated_by            VARCHAR(50),
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_status (application_status),
    INDEX idx_step (current_step)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS upgrade_interest (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    student_id            INT NOT NULL,
    interest_degree       VARCHAR(20)  COMMENT '硕士咨询/博士咨询/语言培训/背景提升',
    interest_country      VARCHAR(100),
    interest_major        VARCHAR(100),
    detected_source       VARCHAR(50)  COMMENT '对话识别/主动询问/行为分析',
    detected_at           DATETIME,
    conversation_snippet  TEXT         COMMENT '触发此意向的对话片段',
    conversion_status     VARCHAR(20)  DEFAULT 'identified' COMMENT 'identified/contacted/interested/converted/lost',
    recommended_program   TEXT         COMMENT 'AI推荐的项目',
    recommendation_text   TEXT         COMMENT 'AI生成的推荐话术',
    sales_notes           TEXT,
    contacted_at          DATETIME,
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_status (conversion_status),
    INDEX idx_degree (interest_degree)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ==================== Agent层 ====================

CREATE TABLE IF NOT EXISTS conversation_log (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    student_id       INT,
    session_id       VARCHAR(50)  NOT NULL COMMENT '会话ID，串联多轮对话',
    role             VARCHAR(10)  NOT NULL COMMENT 'user/assistant/system',
    content          TEXT NOT NULL,
    intent           VARCHAR(100) COMMENT '识别到的意图',
    emotion_detected VARCHAR(30)  COMMENT '本轮检测的情绪',
    tokens_used      INT          DEFAULT 0,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_session (session_id),
    INDEX idx_intent (intent),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

"""


# ============================================================
#  种子数据
# ============================================================

SEED_DATA_SQL = r"""

-- 教师
INSERT IGNORE INTO teacher (id, name, phone, email, department, role) VALUES
(201, '陈老师', '13800000201', 'chen@school.com', '教学部', '班主任'),
(202, '刘老师', '13800000202', 'liu@school.com', '教学部', '班主任'),
(203, '张顾问', '13800000203', 'zhang@school.com', '咨询部', '销售顾问'),
(204, '王主管', '13800000204', 'wang@school.com', '学生服务部', '心理辅导');

-- 学生
INSERT IGNORE INTO student (id, name, phone, email, education, major, school, gpa, language_score, target_country, target_degree, target_major, assigned_teacher_id, contract_status, enrollment_date) VALUES
(1001, '张三', '13900001001', 'zhangsan@mail.com', '本科', '计算机科学', '清华大学', '3.6', 'IELTS 7.0', '新加坡', '硕士', '计算机科学', 201, 'active', '2026-03-01'),
(1002, '李四', '13900001002', 'lisi@mail.com', '本科', '金融工程', '北京大学', '3.4', 'TOEFL 100', '新加坡', '硕士', '金融工程', 201, 'active', '2026-03-01'),
(1003, '王五', '13900001003', 'wangwu@mail.com', '本科', '电子工程', '浙江大学', '3.8', 'IELTS 7.5', '新加坡', '硕士', '电子工程', 202, 'active', '2026-04-01'),
(1004, '赵六', '13900001004', 'zhaoliu@mail.com', '硕士', '工商管理', '复旦大学', '3.2', 'GMAT 650', '法国', 'MBA', 'MBA', 202, 'active', '2026-05-01'),
(1005, '孙七', '13900001005', 'sunqi@mail.com', '本科', '统计学', '上海交通大学', '3.5', 'IELTS 6.5', '新加坡', '硕士', '数据科学', 201, 'active', '2026-04-15');

-- 请假记录
INSERT IGNORE INTO leave_request (id, student_id, leave_type, start_time, end_time, reason, status, approver_id, approver_name, approval_remark, approved_at) VALUES
(1, 1001, '病假', '2026-07-10 14:00:00', '2026-07-10 18:00:00', '感冒发烧去校医院', 'pending', NULL, NULL, NULL, NULL),
(2, 1002, '事假', '2026-07-12 08:00:00', '2026-07-12 17:00:00', '银行办理开户', 'approved', 201, '陈老师', '已批准，注意安全', '2026-07-11 09:30:00'),
(3, 1003, '病假', '2026-07-08 10:00:00', '2026-07-09 18:00:00', '急性肠胃炎', 'approved', 201, '陈老师', '已批，好好休息', '2026-07-08 10:15:00'),
(4, 1004, '事假', '2026-07-15 13:00:00', '2026-07-15 17:00:00', '领事馆面签', 'rejected', 202, '刘老师', '该时段有重要考试，请改期', '2026-07-14 08:00:00'),
(5, 1001, '事假', '2026-07-20 08:00:00', '2026-07-22 18:00:00', '搬家整理', 'pending', NULL, NULL, NULL, NULL);

-- 心理画像
INSERT IGNORE INTO mental_health_profile (id, student_id, current_emotion, risk_score, risk_level, emotion_history, negative_keywords_count, consecutive_negative_days, last_conversation, last_assessment_at, teacher_notified) VALUES
(1, 1001, '正常', 5, 'low', '[{"date":"2026-07-08","emotion":"正常","score":5}]', 1, 0, '谢谢你，今天心情还不错', '2026-07-09 10:00:00', 0),
(2, 1002, '焦虑', 45, 'medium', '[{"date":"2026-07-07","emotion":"焦虑","score":40},{"date":"2026-07-09","emotion":"焦虑","score":45}]', 8, 3, '最近快考试了压力好大，晚上一直睡不着', '2026-07-09 08:30:00', 0),
(3, 1003, '积极', 0, 'low', '[{"date":"2026-07-08","emotion":"积极","score":0}]', 0, 0, '刚拿到offer了！超级开心', '2026-07-08 16:00:00', 0),
(4, 1004, '孤独', 72, 'high', '[{"date":"2026-07-05","emotion":"孤独","score":55},{"date":"2026-07-07","emotion":"孤独","score":65},{"date":"2026-07-09","emotion":"孤独","score":72}]', 15, 4, '来这边三个月了一个朋友都没有，感觉所有人都在孤立我', '2026-07-09 11:00:00', 1),
(5, 1005, '适应困难', 35, 'medium', '[{"date":"2026-07-06","emotion":"适应困难","score":30},{"date":"2026-07-08","emotion":"适应困难","score":35}]', 6, 2, '这边的食物一直吃不惯，天天下雨心情也很差', '2026-07-08 14:00:00', 0);

-- 心理预警
INSERT IGNORE INTO mental_health_alert (id, student_id, trigger_reason, risk_level, alert_content, emotion_label, risk_score, follow_up_status, assigned_teacher_id, assigned_teacher, action_taken, resolved_at) VALUES
(1, 1004, '连续多日表达强烈孤独感与被孤立感，风险评分持续上升至72', 'high', '最近真的很难受，来这边三个月了一个朋友都没有，感觉所有人都在孤立我，有时候想干脆回国算了。', '孤独', 72, 'pending', NULL, NULL, NULL, NULL),
(2, 1002, '期末周压力诱发持续失眠，焦虑评分上升至45', 'medium', '最近快考试了压力好大，晚上一直睡不着，白天又没精神复习。', '焦虑', 45, 'in_progress', 201, '陈老师', NULL, NULL),
(3, 1005, '对当地饮食与气候不适应，连续两周情绪低落', 'medium', '这边的食物一直吃不惯，天天下雨心情也很差，身体各种不舒服。', '适应困难', 35, 'in_progress', 202, '刘老师', NULL, NULL),
(4, 1003, '历史轻度焦虑已恢复正常，记录备查', 'low', '之前考试周有点紧张，现在考完了好多了。', '正常', 10, 'resolved', 201, '陈老师', '一对一谈话疏导，情绪已恢复', '2026-07-06 15:00:00');

-- 反馈工单
INSERT IGNORE INTO feedback_ticket (id, student_id, title, content, summary, category, urgency, status, priority, handler_id, handler_name, resolution, satisfaction, resolved_at) VALUES
(1, 1002, '签证材料反馈延迟', '我的签证材料已经提交两周了，一直没有反馈，不知道现在到什么状态了，很着急。', '签证材料提交两周未获反馈，学生情绪焦虑', '签证办理', 'urgent', 'open', 10, NULL, NULL, NULL, NULL, NULL),
(2, 1001, '宿舍空调报修三次无人处理', '宿舍空调从上周开始坏，我已经报了三次维修，每次都说过两天来但一直没人来，新加坡这么热根本没法住。', '空调报修三次无响应，已持续一周', '生活服务', 'urgent', 'processing', 9, 204, '王主管', NULL, NULL, NULL),
(3, 1003, '选课系统体验优化建议', '选课系统每次到高峰期就崩溃，能不能建议学校升级一下服务器？', '建议升级选课系统服务器，完善课程介绍', '教学质量', 'normal', 'open', 3, NULL, NULL, NULL, NULL, NULL),
(4, 1005, '住宿安排与承诺不符', '当初说好是单人间，到了发现是双人间，和室友作息完全不一样，严重影响休息和学习。', '实际住宿与合同约定的单人间不符', '生活服务', 'urgent', 'open', 7, NULL, NULL, NULL, NULL, NULL),
(5, 1002, '院校申请文书修改', '我的PS和CV已经写好了，但感觉语言不够地道，能不能安排导师帮我修改一下？', '申请文书需要导师审核修改', '院校申请', 'normal', 'resolved', 5, 203, '张顾问', '已安排导师一对一修改，学生满意', 'satisfied', '2026-07-05 16:00:00'),
(6, 1004, '语言课程时间冲突', '报了雅思冲刺班，但是上课时间和我专业课冲突了，能不能换到周末班？', '语言课程与专业课时间冲突，申请换班', '教学质量', 'normal', 'resolved', 4, 202, '刘老师', '协调后换至周六班', 'satisfied', '2026-07-03 11:00:00');

-- 学业日程
INSERT IGNORE INTO academic_schedule (id, student_id, event_type, title, course_name, description, deadline, priority, status) VALUES
(1, 1001, '论文DDL', '期末论文提交', '学术写作', '字数要求3000字，提交至Turnitin', '2026-07-20 23:59:00', 'high', 'upcoming'),
(2, 1001, '考试', '期中考试', '高等数学', '闭卷考试，地点：教学楼A201', '2026-07-15 09:00:00', 'high', 'upcoming'),
(3, 1002, '论文DDL', '毕业论文终稿', '毕业论文', '提交至教务系统，需导师签字', '2026-08-01 17:00:00', 'high', 'upcoming'),
(4, 1002, '答辩', '期末项目答辩', '软件工程', '小组项目，每组15分钟', '2026-07-25 14:00:00', 'high', 'upcoming'),
(5, 1003, '考试', '期末考试', '经济学原理', '开卷考试', '2026-07-18 10:00:00', 'medium', 'upcoming'),
(6, 1004, '论文DDL', '论文修改提交', '社会学导论', '根据导师意见修改后重新提交', '2026-07-22 23:59:00', 'medium', 'upcoming'),
(7, 1005, '论文DDL', '期末项目报告', '数据科学', '需包含代码和数据分析结果', '2026-07-28 18:00:00', 'high', 'upcoming');

-- 申请进度
INSERT IGNORE INTO application_progress (id, student_id, program_name, university, current_step, step_order, steps, application_status, submitted_date, estimated_completion) VALUES
(1, 1001, '计算机科学硕士', '新加坡国立大学', '文书审核', 4, '["选校定校","材料准备","文书撰写","文书审核","递交申请","等待Offer","签证办理"]', 'in_progress', '2026-06-15', '2026-09-01'),
(2, 1002, '金融工程硕士', '南洋理工大学', '递交申请', 5, '["选校定校","材料准备","文书撰写","文书审核","递交申请","等待Offer","签证办理"]', 'in_progress', '2026-05-20', '2026-08-15'),
(3, 1003, '电子工程硕士', '新加坡管理大学', '等待Offer', 6, '["选校定校","材料准备","文书撰写","文书审核","递交申请","等待Offer","签证办理"]', 'in_progress', '2026-04-10', '2026-08-01'),
(4, 1004, 'MBA', '欧洲工商管理学院', '材料准备', 2, '["选校定校","材料准备","文书撰写","文书审核","递交申请","等待Offer","签证办理"]', 'in_progress', '2026-07-01', '2026-10-01'),
(5, 1005, '数据科学硕士', '新加坡国立大学', '文书审核', 4, '["选校定校","材料准备","文书撰写","文书审核","递交申请","等待Offer","签证办理"]', 'in_progress', '2026-06-01', '2026-09-15');

-- 升学意向
INSERT IGNORE INTO upgrade_interest (id, student_id, interest_degree, interest_country, interest_major, detected_source, detected_at, conversation_snippet, conversion_status) VALUES
(1, 1003, '博士咨询', '新加坡', '电子工程', '对话识别', '2026-07-05 14:00:00', '我在想要不要继续读个博士...', 'identified');

"""


# ============================================================
#  逐表定义（避免 split(';') 问题）
# ============================================================

TABLE_LIST = [
    ("student", """CREATE TABLE IF NOT EXISTS student (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    name                VARCHAR(50)  NOT NULL,
    phone               VARCHAR(20),
    email               VARCHAR(100),
    education           VARCHAR(20)  COMMENT '本科/硕士/高中',
    major               VARCHAR(100) COMMENT '专业',
    school              VARCHAR(100) COMMENT '毕业院校',
    gpa                 VARCHAR(10),
    language_score      VARCHAR(50)  COMMENT 'IELTS 7.0 / TOEFL 100',
    target_country      VARCHAR(100) COMMENT '意向留学国家',
    target_degree       VARCHAR(20)  COMMENT '本科/硕士/博士',
    target_major        VARCHAR(100) COMMENT '意向专业',
    assigned_teacher_id INT          COMMENT 'FK→teacher',
    contract_status     VARCHAR(20)  DEFAULT 'active' COMMENT 'active/completed/terminated',
    enrollment_date     DATE,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_teacher (assigned_teacher_id),
    INDEX idx_status (contract_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),

    ("mental_health_profile", """CREATE TABLE IF NOT EXISTS mental_health_profile (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    student_id              INT NOT NULL UNIQUE,
    current_emotion         VARCHAR(30)  DEFAULT '正常' COMMENT '正常/焦虑/低落/孤独/适应困难/积极',
    risk_score              INT          DEFAULT 0  COMMENT '0-100',
    risk_level              VARCHAR(10)  DEFAULT 'low' COMMENT 'low/medium/high/critical',
    emotion_history         JSON         COMMENT '[{date,emotion,score,trigger}]',
    negative_keywords_count INT          DEFAULT 0,
    consecutive_negative_days INT        DEFAULT 0,
    last_conversation       TEXT,
    last_assessment_at      DATETIME,
    teacher_notified        TINYINT(1)   DEFAULT 0,
    created_at              DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_risk (risk_level),
    INDEX idx_emotion (current_emotion)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),

    ("mental_health_alert", """CREATE TABLE IF NOT EXISTS mental_health_alert (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    student_id          INT NOT NULL,
    trigger_reason      TEXT NOT NULL,
    risk_level          VARCHAR(10) NOT NULL COMMENT 'high/critical',
    alert_content       TEXT        COMMENT '完整预警内容',
    emotion_label       VARCHAR(30) COMMENT '触发时的情绪标签',
    risk_score          INT,
    follow_up_status    VARCHAR(20) DEFAULT 'pending' COMMENT 'pending/in_progress/resolved',
    assigned_teacher_id INT,
    assigned_teacher    VARCHAR(50),
    action_taken        TEXT,
    resolved_at         DATETIME,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_status (follow_up_status),
    INDEX idx_risk (risk_level),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),

    ("feedback_ticket", """CREATE TABLE IF NOT EXISTS feedback_ticket (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    student_id    INT NOT NULL,
    title         VARCHAR(200),
    content       TEXT NOT NULL,
    summary       TEXT         COMMENT 'AI自动生成摘要',
    category      VARCHAR(50)  COMMENT '签证办理/院校申请/生活服务/教学质量/其他',
    urgency       VARCHAR(10)  DEFAULT 'normal' COMMENT 'normal/urgent',
    status        VARCHAR(20)  DEFAULT 'open' COMMENT 'open/processing/resolved/closed',
    priority      INT          DEFAULT 5 COMMENT '1-10',
    handler_id    INT,
    handler_name  VARCHAR(50),
    resolution    TEXT,
    satisfaction  VARCHAR(10)  COMMENT 'satisfied/neutral/unsatisfied',
    resolved_at   DATETIME,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_status (status),
    INDEX idx_category (category),
    INDEX idx_urgency (urgency)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),

    ("academic_schedule", """CREATE TABLE IF NOT EXISTS academic_schedule (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    student_id       INT NOT NULL,
    event_type       VARCHAR(30)  NOT NULL COMMENT '论文DDL/考试/选课截止/答辩/其他',
    title            VARCHAR(200) NOT NULL,
    course_name      VARCHAR(100),
    description      TEXT,
    deadline         DATETIME NOT NULL,
    priority         VARCHAR(10)  DEFAULT 'medium' COMMENT 'low/medium/high',
    status           VARCHAR(20)  DEFAULT 'upcoming' COMMENT 'upcoming/reminded/completed',
    source_system    VARCHAR(50)  COMMENT '教务系统/manual',
    reminder_24h_sent TINYINT(1) DEFAULT 0,
    reminder_3d_sent  TINYINT(1) DEFAULT 0,
    reminder_7d_sent  TINYINT(1) DEFAULT 0,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_deadline (deadline),
    INDEX idx_type (event_type),
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),

    ("reminder_log", """CREATE TABLE IF NOT EXISTS reminder_log (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    student_id     INT NOT NULL,
    schedule_id    INT COMMENT 'FK→academic_schedule',
    remind_type    VARCHAR(30)  COMMENT '考前提醒/DDL提醒/选课截止',
    remind_channel VARCHAR(20)  DEFAULT 'agent' COMMENT 'agent推送/微信/短信',
    message        TEXT,
    sent_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_read        TINYINT(1) DEFAULT 0,
    INDEX idx_student (student_id),
    INDEX idx_sent (sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),

    ("application_progress", """CREATE TABLE IF NOT EXISTS application_progress (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    student_id            INT NOT NULL,
    program_name          VARCHAR(200) NOT NULL COMMENT '申请项目名称',
    university            VARCHAR(200),
    current_step          VARCHAR(100) COMMENT '当前步骤',
    step_order            INT         COMMENT '步骤序号',
    steps                 JSON        COMMENT '[{step,status,completed_at,notes}]',
    application_status    VARCHAR(30) DEFAULT 'in_progress' COMMENT 'in_progress/completed/withdrawn',
    submitted_date        DATE,
    estimated_completion  DATE,
    notes                 TEXT,
    updated_by            VARCHAR(50),
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_status (application_status),
    INDEX idx_step (current_step)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),

    ("upgrade_interest", """CREATE TABLE IF NOT EXISTS upgrade_interest (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    student_id            INT NOT NULL,
    interest_degree       VARCHAR(20)  COMMENT '硕士咨询/博士咨询/语言培训/背景提升',
    interest_country      VARCHAR(100),
    interest_major        VARCHAR(100),
    detected_source       VARCHAR(50)  COMMENT '对话识别/主动询问/行为分析',
    detected_at           DATETIME,
    conversation_snippet  TEXT         COMMENT '触发此意向的对话片段',
    conversion_status     VARCHAR(20)  DEFAULT 'identified' COMMENT 'identified/contacted/interested/converted/lost',
    recommended_program   TEXT         COMMENT 'AI推荐的项目',
    recommendation_text   TEXT         COMMENT 'AI生成的推荐话术',
    sales_notes           TEXT,
    contacted_at          DATETIME,
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_student (student_id),
    INDEX idx_status (conversion_status),
    INDEX idx_degree (interest_degree)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),

    ("conversation_session", """CREATE TABLE IF NOT EXISTS conversation_session (
    session_id      VARCHAR(50) PRIMARY KEY COMMENT '会话ID',
    student_id      INT NOT NULL COMMENT '学生ID',
    start_time      DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '会话开始时间',
    end_time        DATETIME COMMENT '会话最后活跃时间',
    total_turns     INT DEFAULT 0 COMMENT '共几轮对话',
    main_intents    VARCHAR(200) COMMENT '涉及哪些意图，逗号分隔',
    emotion_start   VARCHAR(30) COMMENT '会话开始时的情绪',
    emotion_end     VARCHAR(30) COMMENT '会话结束时的情绪',
    INDEX idx_student (student_id),
    INDEX idx_start (start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),

    ("conversation_message", """CREATE TABLE IF NOT EXISTS conversation_message (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id       VARCHAR(50) NOT NULL COMMENT 'FK→conversation_session',
    student_id       INT COMMENT '学生ID（冗余，方便直接查）',
    role             VARCHAR(10) NOT NULL COMMENT 'user/assistant',
    content          TEXT NOT NULL COMMENT '消息内容',
    intent           VARCHAR(100) COMMENT '本条消息的意图',
    emotion_detected VARCHAR(30) COMMENT '本条消息的情绪',
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_student (student_id),
    INDEX idx_intent (intent),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""),
]


# ============================================================
#  种子数据写入
# ============================================================

def _seed_all():
    """写入种子数据（幂等：存在则跳过）"""
    # ── student ──
    if not query("SELECT 1 FROM student LIMIT 1"):
        execute_many(
            """INSERT INTO student (id, name, phone, email, education, major, school, gpa, language_score,
               target_country, target_degree, target_major, assigned_teacher_id, contract_status, enrollment_date)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (1001, '张三', '13900001001', 'zhangsan@mail.com', '本科', '计算机科学', '清华大学', '3.6', 'IELTS 7.0', '新加坡', '硕士', '计算机科学', 201, 'active', '2026-03-01'),
                (1002, '李四', '13900001002', 'lisi@mail.com', '本科', '金融工程', '北京大学', '3.4', 'TOEFL 100', '新加坡', '硕士', '金融工程', 201, 'active', '2026-03-01'),
                (1003, '王五', '13900001003', 'wangwu@mail.com', '本科', '电子工程', '浙江大学', '3.8', 'IELTS 7.5', '新加坡', '硕士', '电子工程', 202, 'active', '2026-04-01'),
                (1004, '赵六', '13900001004', 'zhaoliu@mail.com', '硕士', '工商管理', '复旦大学', '3.2', 'GMAT 650', '法国', 'MBA', 'MBA', 202, 'active', '2026-05-01'),
                (1005, '孙七', '13900001005', 'sunqi@mail.com', '本科', '统计学', '上海交通大学', '3.5', 'IELTS 6.5', '新加坡', '硕士', '数据科学', 201, 'active', '2026-04-15'),
            ])

    # ── mental_health_profile ──
    if not query("SELECT 1 FROM mental_health_profile LIMIT 1"):
        import json as _json
        execute_many(
            """INSERT INTO mental_health_profile (id, student_id, current_emotion, risk_score, risk_level,
               emotion_history, negative_keywords_count, consecutive_negative_days, last_conversation,
               last_assessment_at, teacher_notified)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (1, 1001, '正常', 5, 'low', _json.dumps([{"date":"2026-07-08","emotion":"正常","score":5}]), 1, 0, '谢谢你，今天心情还不错', '2026-07-09 10:00:00', 0),
                (2, 1002, '焦虑', 45, 'medium', _json.dumps([{"date":"2026-07-07","emotion":"焦虑","score":40},{"date":"2026-07-09","emotion":"焦虑","score":45}]), 8, 3, '最近快考试了好焦虑晚上一直睡不着', '2026-07-09 08:30:00', 0),
                (3, 1003, '积极', 0, 'low', _json.dumps([{"date":"2026-07-08","emotion":"积极","score":0}]), 0, 0, '刚拿到offer了超级开心', '2026-07-08 16:00:00', 0),
                (4, 1004, '孤独', 72, 'high', _json.dumps([{"date":"2026-07-05","emotion":"孤独","score":55},{"date":"2026-07-07","emotion":"孤独","score":65},{"date":"2026-07-09","emotion":"孤独","score":72}]), 15, 4, '来这边三个月了一个朋友都没有', '2026-07-09 11:00:00', 1),
                (5, 1005, '适应困难', 35, 'medium', _json.dumps([{"date":"2026-07-06","emotion":"适应困难","score":30},{"date":"2026-07-08","emotion":"适应困难","score":35}]), 6, 2, '天天下雨心情也很差', '2026-07-08 14:00:00', 0),
            ])

    # ── mental_health_alert ──
    if not query("SELECT 1 FROM mental_health_alert LIMIT 1"):
        execute_many(
            """INSERT INTO mental_health_alert (id, student_id, trigger_reason, risk_level, alert_content,
               emotion_label, risk_score, follow_up_status, assigned_teacher_id, assigned_teacher, action_taken, resolved_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (1, 1004, '连续多日表达强烈孤独感与被孤立感，风险评分持续上升至72', 'high', '最近真的很难受，来这边三个月了一个朋友都没有', '孤独', 72, 'pending', None, None, None, None),
                (2, 1002, '期末周压力诱发持续失眠，焦虑评分上升至45', 'medium', '最近快考试了压力好大晚上一直睡不着', '焦虑', 45, 'in_progress', 201, '陈老师', None, None),
                (3, 1005, '对当地饮食与气候不适应，连续两周情绪低落', 'medium', '天天下雨心情也很差身体各种不舒服', '适应困难', 35, 'in_progress', 202, '刘老师', None, None),
                (4, 1003, '历史轻度焦虑已恢复正常，记录备查', 'low', '之前考试周有点紧张现在考完了好多了', '正常', 10, 'resolved', 201, '陈老师', '一对一谈话疏导情绪已恢复', '2026-07-06 15:00:00'),
            ])

    # ── feedback_ticket ──
    if not query("SELECT 1 FROM feedback_ticket LIMIT 1"):
        execute_many(
            """INSERT INTO feedback_ticket (id, student_id, title, content, summary, category, urgency, status, priority,
               handler_id, handler_name, resolution, satisfaction, resolved_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (1, 1002, '签证材料反馈延迟', '我的签证材料已经提交两周了一直没有反馈', '签证材料提交两周未获反馈', '签证办理', 'urgent', 'open', 10, None, None, None, None, None),
                (2, 1001, '宿舍空调报修三次无人处理', '宿舍空调从上周开始坏我已经报了三次维修', '空调报修三次无响应已持续一周', '生活服务', 'urgent', 'processing', 9, 204, '王主管', None, None, None),
                (3, 1003, '选课系统体验优化建议', '选课系统每次到高峰期就崩溃', '建议升级选课系统服务器', '教学质量', 'normal', 'open', 3, None, None, None, None, None),
                (4, 1005, '住宿安排与承诺不符', '当初说好是单人间到了发现是双人间', '实际住宿与合同约定的单人间不符', '生活服务', 'urgent', 'open', 7, None, None, None, None, None),
                (5, 1002, '院校申请文书修改', '我的PS和CV已经写好了但感觉语言不够地道', '申请文书需要导师审核修改', '院校申请', 'normal', 'resolved', 5, 203, '张顾问', '已安排导师一对一修改', 'satisfied', '2026-07-05 16:00:00'),
                (6, 1004, '语言课程时间冲突', '报了雅思冲刺班但是上课时间和我专业课冲突', '语言课程与专业课时间冲突申请换班', '教学质量', 'normal', 'resolved', 4, 202, '刘老师', '协调后换至周六班', 'satisfied', '2026-07-03 11:00:00'),
            ])

    # ── academic_schedule ──
    if not query("SELECT 1 FROM academic_schedule LIMIT 1"):
        execute_many(
            """INSERT INTO academic_schedule (id, student_id, event_type, title, course_name, description, deadline, priority, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (1, 1001, '论文DDL', '期末论文提交', '学术写作', '字数要求3000字提交至Turnitin', '2026-07-20 23:59:00', 'high', 'upcoming'),
                (2, 1001, '考试', '期中考试', '高等数学', '闭卷考试地点教学楼A201', '2026-07-15 09:00:00', 'high', 'upcoming'),
                (3, 1002, '论文DDL', '毕业论文终稿', '毕业论文', '提交至教务系统需导师签字', '2026-08-01 17:00:00', 'high', 'upcoming'),
                (4, 1002, '答辩', '期末项目答辩', '软件工程', '小组项目每组15分钟', '2026-07-25 14:00:00', 'high', 'upcoming'),
                (5, 1003, '考试', '期末考试', '经济学原理', '开卷考试', '2026-07-18 10:00:00', 'medium', 'upcoming'),
                (6, 1004, '论文DDL', '论文修改提交', '社会学导论', '根据导师意见修改后重新提交', '2026-07-22 23:59:00', 'medium', 'upcoming'),
                (7, 1005, '论文DDL', '期末项目报告', '数据科学', '需包含代码和数据分析结果', '2026-07-28 18:00:00', 'high', 'upcoming'),
            ])

    # ── application_progress ──
    if not query("SELECT 1 FROM application_progress LIMIT 1"):
        import json as _json2
        execute_many(
            """INSERT INTO application_progress (id, student_id, program_name, university, current_step, step_order, steps,
               application_status, submitted_date, estimated_completion)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (1, 1001, '计算机科学硕士', '新加坡国立大学', '文书审核', 4,
                 _json2.dumps(['选校定校','材料准备','文书撰写','文书审核','递交申请','等待Offer','签证办理']),
                 'in_progress', '2026-06-15', '2026-09-01'),
                (2, 1002, '金融工程硕士', '南洋理工大学', '递交申请', 5,
                 _json2.dumps(['选校定校','材料准备','文书撰写','文书审核','递交申请','等待Offer','签证办理']),
                 'in_progress', '2026-05-20', '2026-08-15'),
                (3, 1003, '电子工程硕士', '新加坡管理大学', '等待Offer', 6,
                 _json2.dumps(['选校定校','材料准备','文书撰写','文书审核','递交申请','等待Offer','签证办理']),
                 'in_progress', '2026-04-10', '2026-08-01'),
                (4, 1004, 'MBA', '欧洲工商管理学院', '材料准备', 2,
                 _json2.dumps(['选校定校','材料准备','文书撰写','文书审核','递交申请','等待Offer','签证办理']),
                 'in_progress', '2026-07-01', '2026-10-01'),
                (5, 1005, '数据科学硕士', '新加坡国立大学', '文书审核', 4,
                 _json2.dumps(['选校定校','材料准备','文书撰写','文书审核','递交申请','等待Offer','签证办理']),
                 'in_progress', '2026-06-01', '2026-09-15'),
            ])

    # ── upgrade_interest ──
    if not query("SELECT 1 FROM upgrade_interest LIMIT 1"):
        execute("""INSERT INTO upgrade_interest (id, student_id, interest_degree, interest_country, interest_major,
                   detected_source, detected_at, conversation_snippet, conversion_status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (1, 1003, '博士咨询', '新加坡', '电子工程', '对话识别', '2026-07-05 14:00:00', '我在想要不要继续读个博士', 'identified'))


# ============================================================
#  初始化入口
# ============================================================

def init_database():
    """建库 → 建表 → 种子数据（全部幂等）"""
    # Step 1: 建库
    conn = get_conn_no_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` "
                "DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        print(f"[DB] 数据库 `{DB_CONFIG['database']}` 已就绪")
    finally:
        conn.close()

    # Step 2: 建表（逐表执行，不依赖分号切割）
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for name, sql in TABLE_LIST:
                try:
                    cur.execute(sql)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        print(f"[DB] 建表警告 [{name}]: {str(e)[:100]}")
            conn.commit()
        print(f"[DB] {len(TABLE_LIST)} 张表已就绪（教师表由教师Agent管理）")
    finally:
        conn.close()

    # Step 3: 种子数据（用 insert 函数，避免 split(';') 问题）
    _seed_all()
    print("[DB] 种子数据已写入")


def get_schema_description() -> str:
    """生成表结构描述文本，供 NL2SQL 的 LLM prompt 使用"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES")
            tables = [row[0] for row in cur.fetchall()]

            lines = ["数据库 student_assistant 包含以下表：\n"]
            for table in tables:
                cur.execute(f"DESC `{table}`")
                cols = cur.fetchall()
                lines.append(f"\n表 `{table}`：")
                for col in cols:
                    field, typ, null, key, default, extra = col
                    flags = []
                    if key == "PRI": flags.append("主键")
                    if extra == "auto_increment": flags.append("自增")
                    comment = ""
                    lines.append(f"  - {field}: {typ}{' ' + ', '.join(flags) if flags else ''}{comment}")
            return "\n".join(lines)
    finally:
        conn.close()


# ============================================================
#  直接运行 → 初始化数据库
# ============================================================

if __name__ == "__main__":
    init_database()
    print("\n表结构预览：")
    print(get_schema_description())
