"""
会话管理：conversation_session（主表）+ conversation_message（明细表）
每次对话同时写两张表，session_id 串联多轮
"""

import uuid
from datetime import datetime
import pymysql
from . import db as _db
from .config import MAX_HISTORY_TURNS


def new_session_id() -> str:
    """生成新会话ID"""
    return uuid.uuid4().hex[:12]


def get_history(session_id: str, limit: int = None) -> list[dict]:
    """获取会话最近 N 轮对话 [{role, content}]"""
    if limit is None:
        limit = MAX_HISTORY_TURNS * 2

    rows = _db.query(
        """SELECT role, content FROM conversation_message
           WHERE session_id = %s ORDER BY id DESC LIMIT %s""",
        (session_id, limit)
    )
    rows.reverse()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def save_turn(session_id: str, student_id: int,
              user_msg: str, assistant_msg: str,
              intent: str = "", emotion: str = ""):
    """记录一轮对话：更新会话主表 + 插入两条消息明细"""

    # 查会话是否已存在
    session = _db.query_one(
        "SELECT session_id, total_turns, emotion_start FROM conversation_session WHERE session_id = %s",
        (session_id,)
    )

    if session:
        # 更新已有会话
        _db.update("conversation_session", {"session_id": session_id}, {
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_turns": session["total_turns"] + 1,
            "emotion_end": emotion,
        })
        # 更新意图列表（去重拼接）
        old_intents = _db.query_one(
            "SELECT main_intents FROM conversation_session WHERE session_id = %s",
            (session_id,)
        ) or {}
        old_list = old_intents.get("main_intents", "") or ""
        new_set = set(old_list.split(",")) | set(intent.split(","))
        new_intents = ",".join([i for i in new_set if i])
        _db.update("conversation_session", {"session_id": session_id}, {
            "main_intents": new_intents,
        })
    else:
        # 新建会话（处理连接池延迟导致的重复键）
        try:
            _db.insert("conversation_session", {
                "session_id": session_id,
                "student_id": student_id,
                "total_turns": 1,
                "main_intents": intent,
                "emotion_start": emotion,
                "emotion_end": emotion,
            })
        except pymysql.err.IntegrityError:
            # 仅重复键走 update，其他异常向上抛出
            _db.update("conversation_session", {"session_id": session_id}, {
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_turns": 1,
                "emotion_end": emotion,
            })

    # 插两条消息明细
    _db.insert("conversation_message", {
        "session_id": session_id,
        "student_id": student_id,
        "role": "user",
        "content": user_msg,
        "intent": intent,
        "emotion_detected": emotion,
    })
    _db.insert("conversation_message", {
        "session_id": session_id,
        "student_id": student_id,
        "role": "assistant",
        "content": assistant_msg,
    })


def get_emotion_history(student_id: int, days: int = 14) -> list[dict]:
    """获取学生近期情绪记录（从消息明细表查）。表不存在时降级返回空"""
    try:
        rows = _db.query(
            """SELECT emotion_detected, intent, created_at
               FROM conversation_message
               WHERE student_id = %s AND role = 'user' AND emotion_detected != ''
               AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
               ORDER BY created_at DESC""",
            (student_id, days)
        )
    except Exception:
        return []
    return [
        {"emotion": r["emotion_detected"], "date": str(r["created_at"]),
         "intent": r.get("intent", "")}
        for r in rows
    ]


def get_student_context(student_id: int) -> dict:
    """聚合学生全局上下文"""
    student = _db.query_one(
        "SELECT * FROM student WHERE id = %s", (student_id,)
    )
    mental = _db.query_one(
        """SELECT current_emotion, risk_score, risk_level, negative_keywords_count,
                  consecutive_negative_days, teacher_notified
           FROM mental_health_profile WHERE student_id = %s""",
        (student_id,)
    )
    return {
        "student": student,
        "mental": mental,
    }


def get_session_summary(student_id: int, limit: int = 10) -> list[dict]:
    """查学生最近的会话列表（供前端面板展示）"""
    return _db.query(
        """SELECT session_id, start_time, end_time, total_turns, main_intents,
                  emotion_start, emotion_end
           FROM conversation_session
           WHERE student_id = %s
           ORDER BY start_time DESC LIMIT %s""",
        (student_id, limit)
    )
