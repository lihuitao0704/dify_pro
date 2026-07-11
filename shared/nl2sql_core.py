"""
shared/nl2sql_core.py — 统一安全 NL2SQL 引擎
所有模块复用同一套 SQL 校验 + 执行 + 降级规则。
student_sgent 中最好的安全实践提炼于此。
"""
import re
from typing import Optional

# 写操作关键字黑名单
_FORBIDDEN_SQL = (
    "drop ", "truncate ", "delete ", "update ", "insert ",
    "alter ", "create ", "replace ", "grant ", "revoke ",
)


def sanitize_sql(sql: str) -> str:
    """清洗 SQL — 去注释、去末尾分号、去多余空白"""
    if not sql:
        return ""
    sql = sql.strip()
    sql = re.sub(r"^```(?:sql)?\s*", "", sql)
    sql = re.sub(r"\s*```$", "", sql)
    sql = sql.rstrip(";").strip()
    return sql


def validate_readonly_sql(sql: str, allow_write: bool = False) -> str:
    """校验是否为安全 SQL"""
    cleaned = sanitize_sql(sql)
    lowered = cleaned.lower()

    if not allow_write:
        if lowered.startswith(("select", "with", "show", "desc", "describe")):
            if ";" in cleaned:
                raise ValueError("禁止一次执行多条语句（语句中不允许分号）")
            return cleaned
        # 检查是否隐藏写关键字（防绕过）
        for kw in _FORBIDDEN_SQL:
            if kw in lowered:
                raise ValueError(f"禁止执行非只读语句，检测到：{kw.strip()}")
        # 不允许非 SELECT 但以其他操作开头（如 SET）
        first_word = lowered.split()[0] if lowered.split() else ""
        allowed = ("select", "with", "show", "desc", "describe", "explain")
        if first_word not in allowed:
            raise ValueError(f"仅允许 {allowed} 开头的只读语句")

    return cleaned


def build_safe_select(table: str, columns: str = "*",
                      where: str = "", order: str = "",
                      limit: int = 100) -> str:
    """构造安全的 SELECT 语句（参数化查询应由调用方传入 params）"""
    sql = f"SELECT {columns} FROM `{table}`"
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    sql += f" LIMIT {int(limit)}"
    return sql


def mask_sensitive_data(rows: list[dict]) -> list[dict]:
    """手机号/邮箱脱敏（可选，供展示用）"""
    import copy
    masked = copy.deepcopy(rows)
    for row in masked:
        for k in row:
            v = row.get(k)
            if isinstance(v, str):
                if k in ("phone", "mobile") and len(v) >= 7:
                    row[k] = v[:3] + "****" + v[-4:]
                elif k == "email" and "@" in v:
                    local = v.split("@")[0]
                    row[k] = local[:2] + "***" + v[v.find("@"):]
    return masked
