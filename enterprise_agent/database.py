"""
企业智能助手 - 数据库会话管理
修复：避免 PendingRollbackError 和会话双重关闭
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator

from enterprise_agent.config import DATABASE_URL, logger

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator:
    """
    FastAPI 依赖注入：获取数据库会话
    异常时 rollback，正常时 commit，始终 close
    修复：在 finally 中只 close，不 commit（避免已 rollback 后再次 commit）
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    else:
        db.commit()
    finally:
        db.close()


# 禁止在 NL2SQL 中出现的 SQL 关键字（不区分大小写）
FORBIDDEN_SQL_KEYWORDS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE",
    "CREATE", "EXEC", "EXECUTE", "CALL", "MERGE", "REPLACE",
    "GRANT", "REVOKE", "RENAME", "LOAD", "IMPORT", "INTO OUTFILE",
    "SELECT INTO", "INFORMATION_SCHEMA", "MYSQL.", "SYSTEM",
    ";",  # 多条语句
    "--",  # SQL 注释注入
    "/*",  # 块注释注入
]


def _validate_sql_safe(sql: str):
    """校验SQL安全性：仅允许安全的SELECT查询"""
    sql_upper = sql.strip().upper()

    # 1. 必须以 SELECT 开头
    if not sql_upper.startswith("SELECT"):
        raise ValueError("只允许执行 SELECT 查询")

    # 2. 禁止危险关键字
    for kw in FORBIDDEN_SQL_KEYWORDS:
        if kw in sql_upper:
            raise ValueError(f"查询包含禁止的关键字「{kw}」，已拦截")

    # 3. 禁止多语句（包含分号但不在字符串内）
    in_string = False
    for i, ch in enumerate(sql):
        if ch in ("'", '"'):
            in_string = not in_string
        if ch == ";" and not in_string and i != len(sql) - 1:
            raise ValueError("禁止多条语句执行")

    # 4. 限制返回行数（避免内存溢出）
    if "LIMIT" not in sql_upper:
        sql_stripped = sql.strip()
        if sql_stripped.endswith(";"):
            sql_stripped = sql_stripped[:-1]
        return sql_stripped + " LIMIT 200"
    return sql


def execute_raw_sql(sql: str, params: dict = None) -> list:
    """执行原始SQL（仅限SELECT），含安全校验，返回字典列表"""
    safe_sql = _validate_sql_safe(sql)

    db = SessionLocal()
    try:
        result = db.execute(text(safe_sql), params or {})
        columns = result.keys()
        rows = result.fetchall()
        data = [dict(zip(columns, row)) for row in rows]
        return data
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def test_connection() -> bool:
    """测试数据库连接"""
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            logger.info("Database OK: %s", DATABASE_URL.split("@")[1].split("?")[0])
            return True
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()
    except Exception as e:
        logger.error("Connection failed: %s", e)
        return False
