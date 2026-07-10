"""
查询结果序列化工具。

pymysql 返回的单元格可能包含 datetime / date / Decimal /
timedelta 等 JSON 不可序列化的类型，这里统一转换成
字符串或浮点数，便于 FastAPI 直接返回。
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Dict, List


def serialize_value(val: Any) -> Any:
    """
    将单个单元格值转换为 JSON 安全类型。

    规则：
    - None -> None
    - datetime / date / time -> isoformat 字符串
    - timedelta -> 总秒数字符串
    - Decimal / 其他数值 -> float
    - 兜底 -> str(val)
    """
    if val is None:
        return None
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if isinstance(val, timedelta):
        return str(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (int, float, str, bool)):
        return val
    return str(val)


def serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """序列化字典形式的一行记录。"""
    return {k: serialize_value(v) for k, v in row.items()}


def serialize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """序列化多行记录。"""
    return [serialize_row(row) for row in rows] if rows else []
