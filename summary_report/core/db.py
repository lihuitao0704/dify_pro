"""
数据库连接与执行封装

提供：
  - ``get_connection()``：获取 pymysql 连接（默认字典游标）
  - ``execute_sql()``：批量执行 SQL 列表，自动区分 SELECT 与写操作
  - ``fetch_table_names()``：查询当前库中所有表名（用于 init_db 校验）

设计说明：
  为保持轻量与原有行为一致，这里采用每次请求创建新连接的简单模式。
  如后续 QPS 升高，可无缝替换为连接池（如 DBUtils.PooledDB）而不影响上层。
"""

from typing import Any, Dict, List, Optional

import pymysql
from pymysql.cursors import DictCursor

from summary_report.core.config import DB_CONFIG
from summary_report.core.logger import get_logger

logger = get_logger(__name__)


def get_connection() -> pymysql.connections.Connection:
    """创建并返回一个新的数据库连接（字典游标）。"""
    return pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)


def fetch_table_names() -> List[str]:
    """
    查询当前数据库中所有 BASE TABLE 的表名列表。

    供 init_db.py 校验所需表是否已存在，无需额权限查询 information_schema。
    """
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s
                  AND TABLE_TYPE = 'BASE TABLE'
                """,
                (DB_CONFIG["database"],),
            )
            return [row["TABLE_NAME"] for row in cursor.fetchall()]
    finally:
        conn.close()


def execute_sql(sql_list: List[str]) -> List[Dict[str, Any]]:
    """
    遍历执行 SQL 数组。

    - SELECT 语句：抓取列名与数据行
    - 写操作语句：提交并记录影响行数

    Args:
        sql_list: 待执行的 SQL 字符串列表。

    Returns:
        每条 SQL 的执行结果字典，结构统一为：
        - SELECT -> {sql, type, columns, rows, count}
        - 写操作 -> {sql, type, affected_rows}

    Raises:
        Exception: 执行失败时回滚并向上抛。
    """
    conn = get_connection()
    all_results: List[Dict[str, Any]] = []
    try:
        for sql in sql_list:
            with conn.cursor() as cursor:
                try:
                    cursor.execute(sql)
                except pymysql.MySQLError as exc:
                    # 将数据库错误包装为 ValueError，上层会转为 400 并附带具体原因
                    raise ValueError(
                        "SQL 执行失败: %s | 出错语句: %s" % (exc, sql[:200])
                    ) from exc
                sql_type = sql.strip().upper().split()[0]
                if sql_type == "SELECT":
                    rows = cursor.fetchall() or []
                    columns = list(rows[0].keys()) if rows else (
                        [desc[0] for desc in cursor.description] if cursor.description else []
                    )
                    all_results.append(
                        {
                            "sql": sql,
                            "type": "SELECT",
                            "columns": columns,
                            "rows": rows,
                            "count": len(rows),
                        }
                    )
                else:
                    conn.commit()
                    all_results.append(
                        {
                            "sql": sql,
                            "type": sql_type,
                            "affected_rows": cursor.rowcount,
                        }
                    )
        return all_results
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
