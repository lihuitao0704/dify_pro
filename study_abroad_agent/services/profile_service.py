"""
用户画像服务 —— 完整 CRUD
"""
from typing import Optional, List
from study_abroad_agent.database import get_db

EDITABLE_FIELDS = [
    "name", "age", "major", "education", "target_major", "language_score",
    "target_country", "gpa", "budget", "phone", "wechat", "email",
    "consultation_status",
]

REQUIRED_FIELDS = ["education", "target_major", "language_score"]

STATUS_ALLOWED = {"collecting", "recommended", "finished"}


class ProfileService:

    # ---------- 查询 ----------
    @staticmethod
    def get_by_conversation_id(conversation_id: str) -> Optional[dict]:
        return get_db().query_one(
            "SELECT * FROM user_profiles WHERE conversation_id = %s", (conversation_id,)
        )

    @staticmethod
    def get_by_id(profile_id: int) -> Optional[dict]:
        return get_db().query_one(
            "SELECT * FROM user_profiles WHERE id = %s", (profile_id,)
        )

    @staticmethod
    def list_profiles(
        country: Optional[str] = None,
        education: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        sql = "SELECT * FROM user_profiles WHERE 1=1"
        params: list = []
        if country:
            sql += " AND target_country LIKE %s"
            params.append(f"%{country}%")
        if education:
            sql += " AND education = %s"
            params.append(education)
        if status and status in STATUS_ALLOWED:
            sql += " AND consultation_status = %s"
            params.append(status)
        if keyword:
            sql += " AND (name LIKE %s OR conversation_id LIKE %s)"
            params.append(f"%{keyword}%")
            params.append(f"%{keyword}%")
        sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return get_db().query(sql, tuple(params))

    # ---------- 创建 ----------
    @staticmethod
    def create(data: dict) -> dict:
        """根据传入字段创建一条画像，返回最新对象。"""
        cols = ["conversation_id"]
        vals = [data["conversation_id"]]
        for f in EDITABLE_FIELDS:
            if data.get(f) is not None:
                cols.append(f)
                vals.append(data[f])
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO user_profiles ({col_names}) VALUES ({placeholders})"
        new_id = get_db().execute(sql, tuple(vals))
        return ProfileService.get_by_id(new_id) or {}

    # ---------- 保存/增量更新 ----------
    @staticmethod
    def save_profile(conversation_id: str, data: dict) -> dict:
        profile = ProfileService.get_by_conversation_id(conversation_id)
        if not profile:
            data = dict(data)
            data["conversation_id"] = conversation_id
            return ProfileService.create(data)

        update_fields, values = [], []
        for field in EDITABLE_FIELDS:
            if field in data and data[field] is not None:
                update_fields.append(f"{field}=%s")
                values.append(data[field])
        if update_fields:
            sql = f"UPDATE user_profiles SET {','.join(update_fields)} WHERE conversation_id=%s"
            values.append(conversation_id)
            get_db().execute(sql, tuple(values))
        return ProfileService.get_by_conversation_id(conversation_id)

    @staticmethod
    def update_by_id(profile_id: int, data: dict) -> Optional[dict]:
        update_fields, values = [], []
        for k, v in data.items():
            if k in EDITABLE_FIELDS and v is not None:
                update_fields.append(f"{k}=%s")
                values.append(v)
        if not update_fields:
            return ProfileService.get_by_id(profile_id)
        sql = f"UPDATE user_profiles SET {','.join(update_fields)} WHERE id=%s"
        values.append(profile_id)
        get_db().execute(sql, tuple(values))
        return ProfileService.get_by_id(profile_id)

    # ---------- 删除 ----------
    @staticmethod
    def delete_by_conversation_id(conversation_id: str) -> None:
        get_db().execute(
            "DELETE FROM user_profiles WHERE conversation_id = %s", (conversation_id,)
        )

    @staticmethod
    def delete_by_id(profile_id: int) -> None:
        get_db().execute("DELETE FROM user_profiles WHERE id = %s", (profile_id,))

    # ---------- 画像完整性 ----------
    @staticmethod
    def check_profile(conversation_id: str) -> dict:
        profile = ProfileService.get_by_conversation_id(conversation_id)
        if not profile:
            return {"complete": False, "missing": list(REQUIRED_FIELDS)}
        missing = []
        for field in REQUIRED_FIELDS:
            value = profile.get(field)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                missing.append(field)
        return {"complete": len(missing) == 0, "missing": missing}

    # ---------- 缺失问题 ----------
    @staticmethod
    def get_missing_question(conversation_id: str) -> Optional[dict]:
        check = ProfileService.check_profile(conversation_id)
        if check["complete"]:
            return None
        mapping = {
            "education": "请问您目前的最高学历是什么？",
            "target_major": "您计划申请什么专业？",
            "language_score": "目前有雅思、托福或者其他语言成绩吗？",
        }
        field = check["missing"][0]
        return {"field": field, "question": mapping.get(field, f"请补充字段 {field}")}
