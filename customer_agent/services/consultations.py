"""
咨询服务 CRUD

合并自 study_abroad_agent/services/consultation_service.py
"""
import json
from typing import Optional, List
from customer_agent.db import get_db

EDITABLE_FIELDS = [
    "course_id", "conversation_summary",
    "user_feedback", "status",
]

STATUS_ALLOWED = {"new", "recommended", "interested", "not_interested", "consulting"}


class ConsultationService:
    """咨询记录 CRUD。"""

    # ---------- 查询 ----------
    @staticmethod
    def get_by_id(consultation_id: int) -> Optional[dict]:
        return get_db().query_one(
            "SELECT * FROM consultations WHERE id = %s", (consultation_id,)
        )

    @staticmethod
    def get_by_conversation(conversation_id: str) -> List[dict]:
        sql = """
            SELECT c.*
            FROM consultations c
            JOIN user_profiles u ON u.id = c.user_id
            WHERE u.conversation_id = %s
            ORDER BY c.created_at DESC
        """
        return get_db().query(sql, (conversation_id,))

    @staticmethod
    def list_consultations(
        status: Optional[str] = None,
        user_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        sql = "SELECT * FROM consultations WHERE 1=1"
        params: list = []
        if status and status in STATUS_ALLOWED:
            sql += " AND status = %s"
            params.append(status)
        if user_id is not None:
            sql += " AND user_id = %s"
            params.append(user_id)
        sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return get_db().query(sql, tuple(params))

    # ---------- 创建 ----------
    @staticmethod
    def save(conversation_id: str, summary: str = "",
             recommend_ids: Optional[List[int]] = None, **kwargs) -> int:
        user_row = get_db().query_one(
            "SELECT id FROM user_profiles WHERE conversation_id = %s",
            (conversation_id,),
        )
        user_id = user_row["id"] if user_row else None
        recommended_courses = json.dumps(recommend_ids or [], ensure_ascii=False)
        sql = """
            INSERT INTO consultations
                (user_id, course_id, conversation_summary, recommended_courses,
                 user_feedback, status)
            VALUES
                (%s, %s, %s, %s, %s, %s)
        """
        return get_db().execute(
            sql,
            (
                user_id,
                kwargs.get("course_id"),
                summary,
                recommended_courses,
                kwargs.get("user_feedback", ""),
                kwargs.get("status", "new"),
            ),
        )

    # ---------- 更新 ----------
    @staticmethod
    def update(consultation_id: int, data: dict) -> Optional[dict]:
        update_fields, values = [], []
        for k in ("course_id", "conversation_summary", "user_feedback", "status"):
            if k in data and data[k] is not None:
                update_fields.append(f"{k}=%s")
                values.append(data[k])
        if "recommend_ids" in data and data["recommend_ids"] is not None:
            update_fields.append("recommended_courses=%s")
            values.append(json.dumps(data["recommend_ids"], ensure_ascii=False))
        if not update_fields:
            return ConsultationService.get_by_id(consultation_id)
        sql = f"UPDATE consultations SET {','.join(update_fields)} WHERE id=%s"
        values.append(consultation_id)
        get_db().execute(sql, tuple(values))
        return ConsultationService.get_by_id(consultation_id)

    # ---------- 删除 ----------
    @staticmethod
    def delete(consultation_id: int) -> None:
        get_db().execute("DELETE FROM consultations WHERE id = %s", (consultation_id,))
