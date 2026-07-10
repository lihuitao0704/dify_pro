"""
学生智能助手 API Service
格式参照 nl2sql5.py，提供 Dify Chatflow 所需的全部接口

数据库：student_assistant（4 张核心表 + 3 张辅助表）
启动：uvicorn main:app --reload --host 0.0.0.0 --port 8000
测试：curl -X POST http://localhost:8000/api/leave/submit -H "Content-Type: application/json" -H "Authorization: Bearer your-secret-api-key-change-me" -d '{"student_id":1001,"student_name":"张三","leave_type":"病假","start_time":"2026-07-10 14:00:00","end_time":"2026-07-10 18:00:00","reason":"感冒发烧"}'
"""
import os
import json
import pymysql
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ========== 数据库配置 ==========
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '123456',
    'database': 'student_assistant',
    'charset': 'utf8mb4'
}

# ========== 数据库工具函数 ==========
def get_db():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


def get_one(sql: str, params: tuple = None):
    """执行查询，返回单条记录（dict）"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))
    finally:
        conn.close()


def get_all(sql: str, params: tuple = None):
    """执行查询，返回多条记录（list[dict]）"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def execute(sql: str, params: tuple = None):
    """执行写操作（INSERT/UPDATE/DELETE），返回受影响行数"""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid, cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ========== Pydantic 模型 ==========

class LeaveSubmitRequest(BaseModel):
    student_id: int
    student_name: str
    leave_type: str
    start_time: str
    end_time: str
    reason: str


class MentalProfileUpdateRequest(BaseModel):
    student_id: int
    current_emotion: str
    risk_score: int
    risk_level: str


class MentalAlertCreateRequest(BaseModel):
    student_id: int
    student_name: str
    trigger_reason: str
    risk_level: str
    alert_content: str
    emotion_label: str
    risk_score: int


class TicketCreateRequest(BaseModel):
    student_id: int
    student_name: str
    title: str
    content: str
    summary: str
    category: str
    urgency: str


# ========== API 路由 ==========

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务启动时自动初始化辅助表"""
    print("[启动] 正在初始化辅助表...")
    init_supporting_tables()
    print("[启动] 初始化完成，服务就绪")
    print(f"[启动] API 文档: http://localhost:8004/docs")
    print(f"[启动] 接口地址: http://localhost:8004")
    yield


app = FastAPI(title="学生智能助手 API", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.get("/")
def root():
    return {
        "service": "学生智能助手 API",
        "version": "1.0",
        "database": DB_CONFIG['database'],
        "endpoints": [
            "POST /api/leave/submit",
            "GET  /api/leave/status/{student_id}",
            "GET  /api/mental/profile/{student_id}",
            "POST /api/mental/profile/update",
            "POST /api/mental/alert/create",
            "POST /api/ticket/create",
            "GET  /api/ticket/status/{student_id}",
            "GET  /api/academic/deadlines/{student_id}",
            "GET  /api/application/progress/{student_id}",
            "GET  /api/student/profile/{student_id}",
        ]
    }


# ==================== 分支1：请假服务 ====================

@app.post("/api/leave/submit")
def submit_leave(body: LeaveSubmitRequest, request: Request):
    """
    提交请假申请 → 写入 student_admin_service 表
    Dify 调用：分支1 - 请假-提交API
    """
    try:
        new_id, _ = execute(
            """INSERT INTO student_admin_service
               (student_id, student_name, service_type, leave_type, start_time, end_time, reason, approval_status)
               VALUES (%s, %s, 'leave', %s, %s, %s, %s, 'pending')""",
            (body.student_id, body.student_name, body.leave_type,
             body.start_time, body.end_time, body.reason)
        )
        return {
            "success": True,
            "id": new_id,
            "message": "请假申请已成功提交",
            "approval_status": "pending",
            "note": "当前状态为等待班主任审批，审批完成后将通知你"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"提交失败：{str(e)}",
            "message": "请假提交时出现错误，请联系管理员"
        }


@app.get("/api/leave/status/{student_id}")
def get_leave_status(student_id: int, request: Request):
    """
    查询学生请假记录 → 从 student_admin_service 表读取
    Dify 调用：（备用）查询请假审批状态
    """
    try:
        records = get_all(
            """SELECT id, leave_type, start_time, end_time, reason,
                      approval_status, approver_name, approved_at, approval_remark, created_at
               FROM student_admin_service
               WHERE student_id = %s AND service_type = 'leave'
               ORDER BY created_at DESC""",
            (student_id,)
        )
        return {
            "success": True,
            "student_id": student_id,
            "total": len(records),
            "records": records
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 分支2：心理关怀 ====================

@app.get("/api/mental/profile/{student_id}")
def get_mental_profile(student_id: int, request: Request):
    """
    查询学生心理画像 → 从 student_mental_profile 表读取
    Dify 调用：（备用）查询心理状态历史
    """
    try:
        profile = get_one(
            """SELECT student_id, student_name, current_emotion, risk_score, risk_level,
                      total_chat_count, negative_count, consecutive_negative, teacher_notified,
                      last_assessment_at, created_at, updated_at
               FROM student_mental_profile WHERE student_id = %s""",
            (student_id,)
        )
        if not profile:
            return {
                "success": True,
                "student_id": student_id,
                "profile": None,
                "message": "该学生暂无心理画像记录"
            }
        return {"success": True, "profile": profile}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/mental/profile/update")
def update_mental_profile(body: MentalProfileUpdateRequest, request: Request):
    """
    更新学生心理画像 → upsert student_mental_profile 表
    Dify 调用：分支2 medium → 心理-更新画像
    """
    try:
        # 先查是否存在
        existing = get_one(
            "SELECT id FROM student_mental_profile WHERE student_id = %s",
            (body.student_id,)
        )
        if existing:
            execute(
                """UPDATE student_mental_profile
                   SET current_emotion = %s, risk_score = %s, risk_level = %s,
                       last_assessment_at = NOW(), updated_at = NOW()
                   WHERE student_id = %s""",
                (body.current_emotion, body.risk_score, body.risk_level, body.student_id)
            )
        else:
            execute(
                """INSERT INTO student_mental_profile
                   (student_id, current_emotion, risk_score, risk_level, last_assessment_at)
                   VALUES (%s, %s, %s, %s, NOW())""",
                (body.student_id, body.current_emotion, body.risk_score, body.risk_level)
            )
        return {
            "success": True,
            "student_id": body.student_id,
            "message": "心理画像已更新",
            "updated_fields": {
                "current_emotion": body.current_emotion,
                "risk_score": body.risk_score,
                "risk_level": body.risk_level
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/mental/alert/create")
def create_mental_alert(body: MentalAlertCreateRequest, request: Request):
    """
    创建高危心理预警 → 写入 student_mental_alert 表
    Dify 调用：分支2 high → 心理-创建预警
    """
    try:
        new_id, _ = execute(
            """INSERT INTO student_mental_alert
               (student_id, student_name, trigger_reason, risk_level, alert_content,
                emotion_label, risk_score, follow_up_status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')""",
            (body.student_id, body.student_name, body.trigger_reason, body.risk_level,
             body.alert_content, body.emotion_label, body.risk_score)
        )

        # 同时标记 student_mental_profile 的 teacher_notified
        execute(
            "UPDATE student_mental_profile SET teacher_notified = 1, updated_at = NOW() WHERE student_id = %s",
            (body.student_id,)
        )

        return {
            "success": True,
            "alert_id": new_id,
            "student_id": body.student_id,
            "risk_level": body.risk_level,
            "message": "高危预警已创建，已通知相关老师跟进处理",
            "follow_up_status": "pending"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 分支3：售后反馈 ====================

@app.post("/api/ticket/create")
def create_ticket(body: TicketCreateRequest, request: Request):
    """
    创建售后反馈工单 → 写入 student_feedback_ticket 表
    Dify 调用：分支3 → 工单-创建
    """
    try:
        # 生成工单编号
        import datetime
        ticket_number = f"TK-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

        # urgency 映射优先级：urgent → 10, normal → 5
        priority = 10 if body.urgency == 'urgent' else 5

        new_id, _ = execute(
            """INSERT INTO student_feedback_ticket
               (student_id, student_name, title, content, summary, category, urgency, status, priority)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s)""",
            (body.student_id, body.student_name, body.title, body.content,
             body.summary, body.category, body.urgency, priority)
        )

        return {
            "success": True,
            "ticket_id": new_id,
            "ticket_number": ticket_number,
            "student_id": body.student_id,
            "title": body.title,
            "urgency": body.urgency,
            "status": "open",
            "message": f"工单已创建（编号：{ticket_number}），预计24小时内处理",
            "note": "我们会认真对待每一条反馈"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/ticket/status/{student_id}")
def get_ticket_status(student_id: int, request: Request):
    """
    查询学生工单进度 → 从 student_feedback_ticket 表读取
    Dify 调用：（备用）查询历史工单
    """
    try:
        tickets = get_all(
            """SELECT id, title, category, urgency, status, priority,
                      handler_name, resolution, satisfaction, created_at, updated_at
               FROM student_feedback_ticket
               WHERE student_id = %s
               ORDER BY created_at DESC""",
            (student_id,)
        )
        return {
            "success": True,
            "student_id": student_id,
            "total": len(tickets),
            "tickets": tickets
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 分支4：学业考务 ====================

@app.get("/api/academic/deadlines/{student_id}")
def get_academic_deadlines(student_id: int, request: Request):
    """
    查询学生学业 DDL → 从 academic_deadlines 表读取
    Dify 调用：分支4 → 考务-查DDL
    """
    try:
        deadlines = get_all(
            """SELECT id, title, course_name, deadline_date,
                      DATE_FORMAT(deadline_date, '%%Y-%%m-%%d %%H:%%i') AS deadline_str,
                      DATEDIFF(deadline_date, NOW()) AS days_left,
                      status, description
               FROM academic_deadlines
               WHERE student_id = %s AND status != 'completed'
               ORDER BY deadline_date ASC""",
            (student_id,)
        )
        return {
            "success": True,
            "student_id": student_id,
            "total": len(deadlines),
            "deadlines": deadlines,
            "message": f"共有 {len(deadlines)} 项待完成的学业节点" if deadlines else "暂无待完成的学业节点"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 分支5：进度追踪 ====================

@app.get("/api/application/progress/{student_id}")
def get_application_progress(student_id: int, request: Request):
    """
    查询学生留学申请进度 → 从 application_progress 表读取
    Dify 调用：分支5 → 进度-查CRM
    """
    try:
        progress = get_all(
            """SELECT id, program_name, university, current_step,
                      application_status, submitted_date, last_updated,
                      DATE_FORMAT(submitted_date, '%%Y-%%m-%%d') AS submitted_date_str,
                      DATE_FORMAT(last_updated, '%%Y-%%m-%%d %%H:%%i') AS last_updated_str
               FROM application_progress
               WHERE student_id = %s
               ORDER BY last_updated DESC""",
            (student_id,)
        )

        if not progress:
            return {
                "success": True,
                "student_id": student_id,
                "applications": [],
                "message": "暂无申请记录"
            }

        # 为每条记录附加步骤详情
        for p in progress:
            steps_json = get_one(
                "SELECT steps FROM application_progress WHERE id = %s",
                (p['id'],)
            )
            if steps_json and steps_json.get('steps'):
                try:
                    p['steps'] = json.loads(steps_json['steps']) if isinstance(steps_json['steps'], str) else steps_json['steps']
                except (json.JSONDecodeError, TypeError):
                    p['steps'] = []

        return {
            "success": True,
            "student_id": student_id,
            "total": len(progress),
            "applications": progress
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 分支7：增值转化 ====================

@app.get("/api/student/profile/{student_id}")
def get_student_profile(student_id: int, request: Request):
    """
    查询学生综合画像 → 聚合多表数据
    Dify 调用：分支7 → 转化-查画像
    """
    try:
        # 从学生档案表取教育背景
        education = get_one(
            """SELECT student_id, student_name, education_level, major, gpa,
                      language_score, language_type, target_country, target_major,
                      enrollment_year, graduation_year
               FROM student_profile WHERE student_id = %s""",
            (student_id,)
        )

        # 从心理画像表取当前状态
        mental = get_one(
            "SELECT current_emotion, risk_level, total_chat_count FROM student_mental_profile WHERE student_id = %s",
            (student_id,)
        )

        return {
            "success": True,
            "student_id": student_id,
            "profile": {
                "education": education or {},
                "mental_status": mental or {},
                "summary": {
                    "background": f"{education['education_level']} | {education['major']} | GPA {education['gpa']}" if education else "暂无教育背景数据",
                    "language": f"{education['language_type']}: {education['language_score']}" if education else "暂无语言成绩",
                    "target": f"意向国家: {education['target_country']} | 意向专业: {education['target_major']}" if education else "暂无留学意向数据",
                    "current_emotion": mental['current_emotion'] if mental else "未知",
                    "engagement": f"已对话 {mental['total_chat_count']} 次" if mental else "暂无互动记录"
                }
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== 启动时建表 & 种子数据 ====================

def init_supporting_tables():
    """自动创建全部表并填充种子数据（幂等：表存在则跳过，数据存在则跳过）"""
    # 第一步：不指定数据库，先确保 student_assistant 库存在
    conn_no_db = pymysql.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        charset=DB_CONFIG['charset']
    )
    try:
        with conn_no_db.cursor() as cur:
            cur.execute("CREATE DATABASE IF NOT EXISTS student_assistant DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci")
        conn_no_db.commit()
    finally:
        conn_no_db.close()

    # 第二步：连接 student_assistant，建表 + 种子数据
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # ===== 核心表1：学生行政服务表（请假/考务）=====
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_admin_service (
                    id              INT AUTO_INCREMENT PRIMARY KEY,
                    student_id      INT NOT NULL,
                    student_name    VARCHAR(50),
                    service_type    VARCHAR(20) NOT NULL,
                    leave_type      VARCHAR(50),
                    start_time      DATETIME,
                    end_time        DATETIME,
                    reason          TEXT,
                    attachment_url  VARCHAR(500),
                    approval_status VARCHAR(20) DEFAULT 'pending',
                    approver_id     INT,
                    approver_name   VARCHAR(50),
                    approved_at     DATETIME,
                    approval_remark TEXT,
                    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_student_id (student_id),
                    INDEX idx_approval_status (approval_status),
                    INDEX idx_service_type (service_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # ===== 核心表2：心理健康画像表 =====
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_mental_profile (
                    id                  INT AUTO_INCREMENT PRIMARY KEY,
                    student_id          INT NOT NULL UNIQUE,
                    student_name        VARCHAR(50),
                    current_emotion     VARCHAR(30) DEFAULT '正常',
                    risk_score          INT DEFAULT 0,
                    risk_level          VARCHAR(10) DEFAULT 'low',
                    last_conversation   TEXT,
                    last_assessment_at  DATETIME,
                    history_notes       JSON,
                    total_chat_count    INT DEFAULT 0,
                    negative_count      INT DEFAULT 0,
                    consecutive_negative INT DEFAULT 0,
                    teacher_notified    TINYINT(1) DEFAULT 0,
                    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_student_id (student_id),
                    INDEX idx_risk_level (risk_level)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # ===== 核心表3：心理预警表 =====
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_mental_alert (
                    id                  INT AUTO_INCREMENT PRIMARY KEY,
                    student_id          INT NOT NULL,
                    student_name        VARCHAR(50),
                    trigger_reason      TEXT NOT NULL,
                    risk_level          VARCHAR(10) NOT NULL,
                    alert_content       TEXT,
                    emotion_label       VARCHAR(30),
                    risk_score          INT,
                    follow_up_status    VARCHAR(20) DEFAULT 'pending',
                    assigned_teacher_id INT,
                    assigned_teacher    VARCHAR(50),
                    action_taken        TEXT,
                    resolved_at         DATETIME,
                    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_student_id (student_id),
                    INDEX idx_follow_up_status (follow_up_status),
                    INDEX idx_risk_level (risk_level),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # ===== 核心表4：售后反馈工单表 =====
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_feedback_ticket (
                    id              INT AUTO_INCREMENT PRIMARY KEY,
                    student_id      INT NOT NULL,
                    student_name    VARCHAR(50),
                    title           VARCHAR(200),
                    content         TEXT NOT NULL,
                    summary         TEXT,
                    category        VARCHAR(50),
                    urgency         VARCHAR(10) DEFAULT 'normal',
                    status          VARCHAR(20) DEFAULT 'open',
                    priority        INT DEFAULT 0,
                    handler_id      INT,
                    handler_name    VARCHAR(50),
                    resolution      TEXT,
                    satisfaction    VARCHAR(10),
                    resolved_at     DATETIME,
                    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_student_id (student_id),
                    INDEX idx_status (status),
                    INDEX idx_category (category),
                    INDEX idx_urgency (urgency),
                    INDEX idx_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # ----- 辅助表1：学业DDL -----
            cur.execute("""
                CREATE TABLE IF NOT EXISTS academic_deadlines (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id INT NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    course_name VARCHAR(100),
                    deadline_date DATETIME NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_student_id (student_id),
                    INDEX idx_deadline_date (deadline_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # ----- 辅助表2：申请进度 -----
            cur.execute("""
                CREATE TABLE IF NOT EXISTS application_progress (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id INT NOT NULL,
                    program_name VARCHAR(200) NOT NULL,
                    university VARCHAR(200),
                    current_step VARCHAR(100),
                    steps JSON,
                    application_status VARCHAR(30) DEFAULT 'in_progress',
                    submitted_date DATE,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_student_id (student_id),
                    INDEX idx_status (application_status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # ----- 辅助表3：学生画像 -----
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_profile (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id INT NOT NULL UNIQUE,
                    student_name VARCHAR(50),
                    education_level VARCHAR(50),
                    major VARCHAR(100),
                    gpa DECIMAL(3,2),
                    language_score VARCHAR(20),
                    language_type VARCHAR(20),
                    target_country VARCHAR(50),
                    target_major VARCHAR(100),
                    enrollment_year INT,
                    graduation_year INT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_student_id (student_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            conn.commit()

        # ===== 种子数据：4张核心表 + 3张辅助表 =====

        # -- 表1：学生行政服务（请假/考务）--
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM student_admin_service")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    """INSERT INTO student_admin_service (student_id, student_name, service_type, leave_type, start_time, end_time, reason, attachment_url, approval_status, approver_id, approver_name, approved_at, approval_remark)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (1001, '张三', 'leave', '病假', '2026-07-10 14:00:00', '2026-07-10 18:00:00', '感冒发烧去校医院', None, 'pending', None, None, None, None),
                        (1002, '李四', 'leave', '事假', '2026-07-12 08:00:00', '2026-07-12 17:00:00', '银行办理开户', None, 'approved', 201, '陈老师', '2026-07-11 09:30:00', '已批准，注意安全'),
                        (1003, '王五', 'leave', '病假', '2026-07-08 10:00:00', '2026-07-09 18:00:00', '急性肠胃炎', 'http://files/cert_1003.pdf', 'approved', 201, '陈老师', '2026-07-08 10:15:00', '已批，好好休息'),
                        (1004, '赵六', 'leave', '事假', '2026-07-15 13:00:00', '2026-07-15 17:00:00', '领事馆面签', None, 'rejected', 202, '刘老师', '2026-07-14 08:00:00', '该时段有重要考试，请改期'),
                        (1001, '张三', 'leave', '事假', '2026-07-20 08:00:00', '2026-07-22 18:00:00', '搬家整理', None, 'pending', None, None, None, None),
                        (1005, '孙七', 'exam', None, '2026-07-25 09:00:00', '2026-07-25 11:00:00', '申请缓考：因身体原因申请期末考试延期', 'http://files/delay_1005.pdf', 'pending', None, None, None, None),
                    ]
                )
                conn.commit()

        # -- 表2：心理健康画像 --
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM student_mental_profile")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    """INSERT INTO student_mental_profile (student_id, student_name, current_emotion, risk_score, risk_level, last_conversation, last_assessment_at, history_notes, total_chat_count, negative_count, consecutive_negative, teacher_notified)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (1001, '张三', '正常', 5, 'low', '谢谢你，今天心情还不错', '2026-07-09 10:00:00', '[{"date":"2026-07-08","emotion":"正常","score":5}]', 12, 1, 0, 0),
                        (1002, '李四', '焦虑', 45, 'medium', '最近快考试了压力好大，晚上一直睡不着', '2026-07-09 08:30:00', '[{"date":"2026-07-07","emotion":"焦虑","score":40},{"date":"2026-07-09","emotion":"焦虑","score":45}]', 28, 8, 3, 0),
                        (1003, '王五', '积极', 0, 'low', '刚拿到offer了！超级开心', '2026-07-08 16:00:00', '[{"date":"2026-07-08","emotion":"积极","score":0}]', 8, 0, 0, 0),
                        (1004, '赵六', '孤独', 72, 'high', '来这边三个月了一个朋友都没有，感觉所有人都在孤立我', '2026-07-09 11:00:00', '[{"date":"2026-07-05","emotion":"孤独","score":55},{"date":"2026-07-07","emotion":"孤独","score":65},{"date":"2026-07-09","emotion":"孤独","score":72}]', 45, 15, 4, 1),
                        (1005, '孙七', '适应困难', 35, 'medium', '这边的食物一直吃不惯，天天下雨心情也很差', '2026-07-08 14:00:00', '[{"date":"2026-07-06","emotion":"适应困难","score":30},{"date":"2026-07-08","emotion":"适应困难","score":35}]', 20, 6, 2, 0),
                    ]
                )
                conn.commit()

        # -- 表3：心理预警 --
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM student_mental_alert")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    """INSERT INTO student_mental_alert (student_id, student_name, trigger_reason, risk_level, alert_content, emotion_label, risk_score, follow_up_status, assigned_teacher_id, assigned_teacher, action_taken, resolved_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (1004, '赵六', '连续多日表达强烈孤独感与被孤立感，风险评分持续上升至72', 'high', '最近真的很难受，来这边三个月了一个朋友都没有，感觉所有人都在孤立我，有时候想干脆回国算了。', '孤独', 72, 'pending', None, None, None, None),
                        (1002, '李四', '期末周压力诱发持续失眠，焦虑评分上升至45', 'medium', '最近快考试了压力好大，晚上一直睡不着，白天又没精神复习，感觉要挂科了。', '焦虑', 45, 'in_progress', 201, '陈老师', None, None),
                        (1005, '孙七', '对当地饮食与气候不适应，连续两周情绪低落', 'medium', '这边的食物一直吃不惯，天天下雨心情也很差，身体各种不舒服。', '适应困难', 35, 'in_progress', 202, '刘老师', None, None),
                        (1003, '王五', '该生历史上曾有一次轻度焦虑，已恢复正常，记录备查', 'low', '之前考试周有点紧张，现在考完了好多了。', '正常', 10, 'resolved', 201, '陈老师', '一对一谈话疏导，学生情绪已恢复正常', '2026-07-06 15:00:00'),
                    ]
                )
                conn.commit()

        # -- 表4：售后反馈工单 --
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM student_feedback_ticket")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    """INSERT INTO student_feedback_ticket (student_id, student_name, title, content, summary, category, urgency, status, priority, handler_id, handler_name, resolution, satisfaction, resolved_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (1002, '李四', '签证材料反馈延迟', '我的签证材料已经提交两周了，一直没有反馈，不知道现在到什么状态了，很着急。', '签证材料提交两周未获反馈，学生情绪焦虑', '签证办理', 'urgent', 'open', 8, None, None, None, None, None),
                        (1001, '张三', '宿舍空调报修三次无人处理', '宿舍空调从上周开始坏，我已经报了三次维修，每次都说过两天来但一直没人来，新加坡这么热根本没法住。', '空调报修三次无响应，已持续一周', '生活服务', 'urgent', 'in_progress', 9, 301, '王主管', None, None, None),
                        (1003, '王五', '选课系统体验优化建议', '选课系统每次到高峰期就崩溃，能不能建议学校升级一下服务器？另外课程介绍也写得太简略了。', '建议升级选课系统服务器，完善课程介绍', '教学质量', 'normal', 'open', 3, None, None, None, None, None),
                        (1005, '孙七', '住宿安排与承诺不符', '当初说好是单人间，到了发现是双人间，和室友作息完全不一样，严重影响休息和学习。', '实际住宿与合同约定的单人间不符', '生活服务', 'urgent', 'open', 7, None, None, None, None, None),
                        (1002, '李四', '院校申请文书需要修改', '我的PS和CV已经写好了，但感觉语言不够地道，能不能安排导师帮我修改一下？', '申请文书需要导师审核修改', '院校申请', 'normal', 'resolved', 5, 302, '张顾问', '已安排导师一对一修改，学生满意', 'satisfied', '2026-07-05 16:00:00'),
                        (1004, '赵六', '语言课程时间冲突', '报了雅思冲刺班，但是上课时间和我专业课冲突了，能不能换到周末班？', '语言课程与专业课时间冲突，申请换班', '教学质量', 'normal', 'resolved', 4, 303, '李教务', '协调后换至周六班，已确认', 'satisfied', '2026-07-03 11:00:00'),
                    ]
                )
                conn.commit()

        # -- 辅助表1：学业DDL --
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM academic_deadlines")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    """INSERT INTO academic_deadlines (student_id, title, course_name, deadline_date, status, description)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    [
                        (1001, '期末论文提交', '学术写作', '2026-07-20 23:59:00', 'pending', '字数要求3000字，提交至Turnitin'),
                        (1001, '期中考试', '高等数学', '2026-07-15 09:00:00', 'pending', '闭卷考试，地点：教学楼A201'),
                        (1002, '毕业论文终稿', '毕业论文', '2026-08-01 17:00:00', 'pending', '提交至教务系统，需导师签字'),
                        (1002, '期末项目答辩', '软件工程', '2026-07-25 14:00:00', 'pending', '小组项目，每组15分钟'),
                        (1003, '期末考试', '经济学原理', '2026-07-18 10:00:00', 'pending', '开卷考试'),
                        (1004, '论文修改提交', '社会学导论', '2026-07-22 23:59:00', 'pending', '根据导师意见修改后重新提交'),
                        (1005, '期末项目报告', '数据科学', '2026-07-28 18:00:00', 'pending', '需包含代码和数据分析结果'),
                    ]
                )
                conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM application_progress")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    """INSERT INTO application_progress (student_id, program_name, university, current_step, steps, application_status, submitted_date)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (1001, '计算机科学硕士', '新加坡国立大学', '文书审核',
                         '["选校定校 ✅","材料准备 ✅","文书撰写 ✅","文书审核 🔄","递交申请 ⏳","等待Offer ⏳","签证办理 ⏳"]',
                         'in_progress', '2026-06-15'),
                        (1002, '金融工程硕士', '南洋理工大学', '递交申请',
                         '["选校定校 ✅","材料准备 ✅","文书撰写 ✅","文书审核 ✅","递交申请 🔄","等待Offer ⏳","签证办理 ⏳"]',
                         'in_progress', '2026-05-20'),
                        (1003, '电子工程硕士', '新加坡管理大学', '等待Offer',
                         '["选校定校 ✅","材料准备 ✅","文书撰写 ✅","文书审核 ✅","递交申请 ✅","等待Offer 🔄","签证办理 ⏳"]',
                         'in_progress', '2026-04-10'),
                        (1004, 'MBA', '欧洲工商管理学院', '材料准备',
                         '["选校定校 ✅","材料准备 🔄","文书撰写 ⏳","文书审核 ⏳","递交申请 ⏳","等待Offer ⏳","签证办理 ⏳"]',
                         'in_progress', '2026-07-01'),
                        (1005, '数据科学硕士', '新加坡国立大学', '文书审核',
                         '["选校定校 ✅","材料准备 ✅","文书撰写 ✅","文书审核 🔄","递交申请 ⏳","等待Offer ⏳","签证办理 ⏳"]',
                         'in_progress', '2026-06-01'),
                    ]
                )
                conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM student_profile")
            if cur.fetchone()[0] == 0:
                cur.executemany(
                    """INSERT INTO student_profile (student_id, student_name, education_level, major, gpa, language_score, language_type, target_country, target_major, enrollment_year, graduation_year)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (1001, '张三', '本科', '计算机科学', 3.6, '7.0', '雅思', '新加坡', '计算机科学', 2026, 2027),
                        (1002, '李四', '本科', '金融工程', 3.4, '100', '托福', '新加坡', '金融工程', 2026, 2027),
                        (1003, '王五', '本科', '电子工程', 3.8, '7.5', '雅思', '新加坡', '电子工程', 2026, 2027),
                        (1004, '赵六', '硕士', '工商管理', 3.2, '650', 'GMAT', '法国', 'MBA', 2026, 2027),
                        (1005, '孙七', '本科', '统计学', 3.5, '6.5', '雅思', '新加坡', '数据科学', 2026, 2027),
                    ]
                )
                conn.commit()

    except Exception as e:
        print(f"[WARN] 辅助表初始化失败（可能已存在）：{e}")
    finally:
        conn.close()


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("student_api:app", host="0.0.0.0", port=8004)
