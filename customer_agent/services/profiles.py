"""
用户画像 CRUD 服务

合并自 study_abroad_agent/services/profile_service.py
与 customer_agent/persist.py (profile_upsert 的增量语义) 互补：
  - persist.py           负责对话流程里的"增量写入 + 报名去重"
  - services/profiles.py 负责对外 REST 接口的完整 CRUD
"""
from typing import Optional, List
from customer_agent.db import get_db

EDITABLE_FIELDS = [
    "name", "age", "major", "education", "target_major", "language_score",
    "target_country", "gpa", "budget", "phone", "wechat", "email",
    "consultation_status", "assess", "development", "abilities",
    "is_Closed-loop",
]

REQUIRED_FIELDS = ["education", "target_major", "language_score"]

STATUS_ALLOWED = {"collecting", "recommended", "finished"}


class ProfileService:
    """用户画像 CRUD。"""

    # ---------- 查询 ----------
    @staticmethod
    def get_by_conversation_id(conversation_id: str) -> List[dict]:
        """按 conversation_id 查询，返回多条记录列表。"""
        return get_db().query(
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
        name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        wechat: Optional[str] = None,
        target_country: Optional[str] = None,
        target_major: Optional[str] = None,
        major: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        """多字段组合查询，任意字段均可作为筛选条件。"""
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
            sql += " AND (name LIKE %s OR conversation_id LIKE %s OR phone LIKE %s)"
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw])
        if name:
            sql += " AND name LIKE %s"
            params.append(f"%{name}%")
        if phone:
            sql += " AND phone LIKE %s"
            params.append(f"%{phone}%")
        if email:
            sql += " AND email LIKE %s"
            params.append(f"%{email}%")
        if wechat:
            sql += " AND wechat LIKE %s"
            params.append(f"%{wechat}%")
        if target_country:
            sql += " AND target_country LIKE %s"
            params.append(f"%{target_country}%")
        if target_major:
            sql += " AND target_major LIKE %s"
            params.append(f"%{target_major}%")
        if major:
            sql += " AND major LIKE %s"
            params.append(f"%{major}%")
        sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        return get_db().query(sql, tuple(params))

    # ---------- 创建 ----------
    @staticmethod
    def create(data: dict) -> dict:
        """根据传入字段创建一条画像，返回最新对象。"""
        data = ProfileService._normalize_data(data)
        cols = []
        vals = []
        cols.append("conversation_id")
        vals.append(data.get("conversation_id", "0"))
        for f in EDITABLE_FIELDS:
            if data.get(f) is not None:
                cols.append(f"`{f}`")
                vals.append(data[f])
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO user_profiles ({col_names}) VALUES ({placeholders})"
        new_id = get_db().execute(sql, tuple(vals))
        return ProfileService.get_by_id(new_id) or {}

    # ---------- 保存/增量更新 ----------
    @staticmethod
    def _normalize_data(data: dict) -> dict:
        normalized = dict(data)
        if "is_closed_loop" in normalized:
            normalized["is_Closed-loop"] = normalized.pop("is_closed_loop")
        return normalized

    @staticmethod
    def save_profile(conversation_id: str, data: dict) -> dict:
        """存在则增量更新（按 conversation_id 匹配第一条），不存在则创建。"""
        data = ProfileService._normalize_data(data)
        profiles = ProfileService.get_by_conversation_id(conversation_id)
        if not profiles:
            data = dict(data)
            data["conversation_id"] = conversation_id
            return ProfileService.create(data)

        profile = profiles[0]
        update_fields, values = [], []
        for field in EDITABLE_FIELDS:
            if field in data and data[field] is not None:
                update_fields.append(f"`{field}`=%s")
                values.append(data[field])
        if update_fields:
            sql = f"UPDATE user_profiles SET {','.join(update_fields)} WHERE id=%s"
            values.append(profile["id"])
            get_db().execute(sql, tuple(values))
        return ProfileService.get_by_id(profile["id"])

    @staticmethod
    def update_by_id(profile_id: int, data: dict) -> Optional[dict]:
        data = ProfileService._normalize_data(data)
        update_fields, values = [], []
        for k, v in data.items():
            if k in EDITABLE_FIELDS and v is not None:
                update_fields.append(f"`{k}`=%s")
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
        profiles = ProfileService.get_by_conversation_id(conversation_id)
        if not profiles:
            return {"complete": False, "missing": list(REQUIRED_FIELDS)}
        profile = profiles[0]
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
