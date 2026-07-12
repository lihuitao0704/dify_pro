"""
课程表 CRUD 服务

合并自 study_abroad_agent/services/courses_service.py
"""
from typing import Optional, List
from customer_agent.db import get_db

ALLOWED_CATEGORIES = {"留学方案", "语言课程", "背景提升"}


class CoursesService:
    """课程表 CRUD。所有 DB 走 customer_agent.db.get_db() 线程安全单例。"""

    @staticmethod
    def list_courses(
        category: Optional[str] = None,
        country: Optional[str] = None,
        keyword: Optional[str] = None,
        is_active: Optional[int] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[dict]:
        """分页/筛选查询课程。"""
        sql = "SELECT * FROM courses WHERE 1=1"
        params: list = []
        if category and category in ALLOWED_CATEGORIES:
            sql += " AND category = %s"
            params.append(category)
        if country:
            sql += " AND country LIKE %s"
            params.append(f"%{country}%")
        if keyword:
            sql += " AND (course_name LIKE %s OR description LIKE %s)"
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
        if is_active is not None:
            sql += " AND is_active = %s"
            params.append(is_active)
        sql += " ORDER BY id ASC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return get_db().query(sql, tuple(params))

    @staticmethod
    def get_by_id(course_id: int) -> Optional[dict]:
        return get_db().query_one("SELECT * FROM courses WHERE id = %s", (course_id,))

    @staticmethod
    def create(data: dict) -> int:
        sql = """
            INSERT INTO courses (
                course_name, category, sub_category, country, target_education,
                min_gpa, max_budget, min_budget, language_requirement, duration,
                price, description, highlights, is_active
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
        """
        values = (
            data["course_name"],
            data["category"],
            data.get("sub_category") or "",
            data.get("country") or "",
            data.get("target_education") or "",
            data.get("min_gpa", 0.00),
            data.get("max_budget"),
            data.get("min_budget"),
            data.get("language_requirement") or "",
            data.get("duration") or "",
            data.get("price", 0.00),
            data.get("description"),
            data.get("highlights"),
            int(data.get("is_active", 1)),
        )
        return get_db().execute(sql, values)

    @staticmethod
    def update(course_id: int, data: dict) -> bool:
        fields = []
        values = []
        for k, v in data.items():
            if v is not None:
                fields.append(f"{k} = %s")
                values.append(v)
        if not fields:
            return False
        sql = f"UPDATE courses SET {', '.join(fields)} WHERE id = %s"
        values.append(course_id)
        get_db().execute(sql, tuple(values))
        return True

    @staticmethod
    def delete(course_id: int) -> bool:
        get_db().execute("DELETE FROM courses WHERE id = %s", (course_id,))
        return True

    @staticmethod
    def count(
        category: Optional[str] = None,
        country: Optional[str] = None,
        keyword: Optional[str] = None,
        is_active: Optional[int] = None,
    ) -> int:
        sql = "SELECT COUNT(*) AS c FROM courses WHERE 1=1"
        params: list = []
        if category and category in ALLOWED_CATEGORIES:
            sql += " AND category = %s"
            params.append(category)
        if country:
            sql += " AND country LIKE %s"
            params.append(f"%{country}%")
        if keyword:
            sql += " AND (course_name LIKE %s OR description LIKE %s)"
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
        if is_active is not None:
            sql += " AND is_active = %s"
            params.append(is_active)
        row = get_db().query_one(sql, tuple(params))
        return row["c"] if row else 0
