"""
customer_agent 持久化层（最小化的业务写入 API）

面向 router.py 暴露高级语义函数，封装 SQL 细节。
设计原则：
  1. 所有 SQL 参数化 — 拒绝拼接
  2. 写操作失败返回 {"ok": False, "reason": "error", "msg": "..."} — 不抛异常
     让 router.py 可以降级回纯内存流程
  3. profile_upsert 是增量更新：只写非空字段，已存在的字段不覆盖
  4. register 系列先查后写（has_registered 预检），UNIQUE 约束兜底

写入目标统一为 user_profiles（画像+报名时的姓名/电话都补到画像），
  *_registrations 表只存报名关系。
"""

import logging

from customer_agent.db import get_db

log = logging.getLogger(__name__)

# user_profiles 表可写字段（对齐 study_abroad_agent）
PROFILE_EDITABLE_FIELDS = [
    "name", "age", "major", "education", "target_major", "language_score",
    "target_country", "gpa", "budget", "phone", "wechat", "email",
    "consultation_status", "assess", "development", "abilities",
    "is_Closed-loop",
]

# profile 字段 → 用户可读中文名（用于"已记住"反馈文案）
PROFILE_FIELD_LABELS = {
    "name": "姓名",
    "age": "年龄",
    "major": "专业",
    "education": "学历",
    "target_major": "意向专业",
    "language_score": "语言成绩",
    "target_country": "目标国家",
    "gpa": "GPA",
    "budget": "预算",
    "phone": "手机",
    "wechat": "微信",
    "email": "邮箱",
}


def _safe(fn, *args, **kwargs):
    """包装 DB 调用：出错返回 None（由调用方决定降级策略）。"""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        log.warning("[persist] DB 操作失败（降级为内存模式）: %s", e)
        return None


# ============================================================
# 用户画像（user_profiles）
# ============================================================
def profile_upsert(conversation_id: str, fields: dict) -> dict:
    """
    按 conversation_id 增量更新 user_profiles。
    - 不存在 → INSERT（只写非空字段 + conversation_id）
    - 存在 → UPDATE 第一条匹配记录（只写非空字段，不覆盖已有值）

    返回 {"ok": True, "id": int, "action": "insert"|"update"|"noop"}
          {"ok": False, "reason": "error", "msg": "..."}
    """
    if not fields:
        return {"ok": True, "id": None, "action": "noop"}

    # 过滤：只保留可写字段且非空
    clean = {k: v for k, v in fields.items()
             if k in PROFILE_EDITABLE_FIELDS and v not in (None, "")}
    if not clean:
        return {"ok": True, "id": None, "action": "noop"}

    def _do():
        db = get_db()
        rows = db.query(
            "SELECT * FROM user_profiles WHERE conversation_id = %s ORDER BY id ASC LIMIT 1",
            (conversation_id,),
        )
        if not rows:
            # INSERT
            cols = ["conversation_id"] + [f"`{k}`" for k in clean]
            vals = [conversation_id] + list(clean.values())
            placeholders = ", ".join(["%s"] * len(cols))
            sql = f"INSERT INTO user_profiles ({', '.join(cols)}) VALUES ({placeholders})"
            new_id = db.execute(sql, tuple(vals))
            return {"ok": True, "id": new_id, "action": "insert"}

        # UPDATE 第一条
        profile = rows[0]
        # 增量：不覆盖已有值（只填空的字段）
        to_update = {k: v for k, v in clean.items()
                     if profile.get(k) in (None, "")}
        if not to_update:
            return {"ok": True, "id": profile["id"], "action": "noop"}
        sets = ", ".join(f"`{k}` = %s" for k in to_update)
        vals = list(to_update.values()) + [profile["id"]]
        db.execute(f"UPDATE user_profiles SET {sets} WHERE id = %s", tuple(vals))
        return {"ok": True, "id": profile["id"], "action": "update"}

    result = _safe(_do)
    if result is None:
        return {"ok": False, "reason": "error", "msg": "DB 不可用"}
    return result


def profile_get(conversation_id: str) -> dict | None:
    """查第一条匹配 profile，不存在返回 None，DB 不可用返回 None。"""

    def _do():
        db = get_db()
        row = db.query_one(
            "SELECT * FROM user_profiles WHERE conversation_id = %s ORDER BY id ASC LIMIT 1",
            (conversation_id,),
        )
        return row

    return _safe(_do)


# ============================================================
# 活动/讲座查询（用于获取标题反馈给用户）
# ============================================================
def activity_get_name(activity_id: str | int) -> str | None:
    """读 activities.title。"""

    def _do():
        db = get_db()
        row = db.query_one(
            "SELECT title FROM activities WHERE activity_id = %s", (activity_id,)
        )
        return row["title"] if row else None

    result = _safe(_do)
    return result


def lecture_get_name(lecture_id: str | int) -> str | None:
    """读 lectures.title。"""

    def _do():
        db = get_db()
        row = db.query_one(
            "SELECT title FROM lectures WHERE lecture_id = %s", (lecture_id,)
        )
        return row["title"] if row else None

    result = _safe(_do)
    return result


# ============================================================
# 报名写入 + 去重
# ============================================================
def has_registered(table: str, ref_id: str | int, name: str, phone: str) -> bool:
    """去重预检：table ∈ {lecture_registrations, activity_registrations}。"""

    if table not in ("lecture_registrations", "activity_registrations"):
        return False
    id_col = "lecture_id" if table == "lecture_registrations" else "activity_id"

    def _do():
        db = get_db()
        row = db.query_one(
            f"SELECT registration_id FROM {table} "
            f"WHERE {id_col} = %s AND name = %s AND phone = %s LIMIT 1",
            (ref_id, name, phone),
        )
        return row is not None

    result = _safe(_do)
    return False if result is None else result


def activity_register(activity_id: str | int, name: str, phone: str) -> dict:
    """
    写 activity_registrations。
    返回:
      {"ok": True, "id": int}
      {"ok": False, "reason": "duplicate"|"error", "msg": str}
    """
    return _do_register("activity_registrations", "activity_id", activity_id, name, phone)


def lecture_register(lecture_id: str | int, name: str, phone: str) -> dict:
    """
    写 lecture_registrations。
    返回同上。
    """
    return _do_register("lecture_registrations", "lecture_id", lecture_id, name, phone)


def _do_register(table: str, id_col: str, ref_id: str | int,
                 name: str, phone: str) -> dict:
    """通用报名写入。UNIQUE 约束兜底。"""

    def _do():
        db = get_db()
        try:
            new_id = db.execute(
                f"INSERT INTO {table} ({id_col}, name, phone) VALUES (%s, %s, %s)",
                (ref_id, name, phone),
            )
            return {"ok": True, "id": new_id}
        except Exception as e:
            err = str(e)
            if "Duplicate" in err or "1062" in err or "UNIQUE" in err.upper():
                return {"ok": False, "reason": "duplicate",
                        "msg": "你已报名过这项活动，无需重复报名"}
            raise

    result = _safe(_do)
    if result is None:
        return {"ok": False, "reason": "error", "msg": "DB 不可用"}
    return result
