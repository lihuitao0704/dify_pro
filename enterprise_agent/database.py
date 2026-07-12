"""
企业智能助手 - 数据库会话管理
修复：避免 PendingRollbackError 和会话双重关闭
"""
import re
import threading
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
    FastAPI 依赖注入：获取数据库会话。
    注意：不再自动 commit！写操作必须在成功后显式调用 db.commit()。
    异常时 rollback（仅当异常冒泡到此处，router 自行 catch 后需自行处理），
    始终 close。
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ==================== SQL 安全校验（enterprise_agent 内部实现） ====================

# 禁止关键字（正则边界匹配，不依赖 shared 模块）
_FORBIDDEN_SQL_RE = [
    re.compile(r'\bDROP\b', re.I), re.compile(r'\bTRUNCATE\b', re.I),
    re.compile(r'\bDELETE\b', re.I), re.compile(r'\bUPDATE\b', re.I),
    re.compile(r'\bINSERT\b', re.I), re.compile(r'\bALTER\b', re.I),
    re.compile(r'\bCREATE\b', re.I), re.compile(r'\bREPLACE\b', re.I),
    re.compile(r'\bGRANT\b', re.I), re.compile(r'\bREVOKE\b', re.I),
    re.compile(r'\bRENAME\b', re.I), re.compile(r'\bLOAD\b', re.I),
    re.compile(r'\bMERGE\b', re.I), re.compile(r'\bCALL\b', re.I),
    re.compile(r'\bEXEC\b', re.I), re.compile(r'\bEXECUTE\b', re.I),
    re.compile(r'\bINTO\s+OUTFILE\b', re.I),
    re.compile(r'\bSELECT\s+INTO\b', re.I),
]

ALLOWED_NL2SQL_TABLES = {
    "intention_customer", "employee_daily_report", "leave_application",
    "student_score", "student_complaint", "student", "employee",
    "department", "account", "application_record", "appointment",
    "document_checklist", "student_mental_alert", "mental_health_profile",
    "student_psych_record", "student_info",
}

QUERY_TIMEOUT_SECONDS = 10
_DEFAULT_LIMIT = 200


def validate_select_sql(sql: str) -> str:
    """
    校验 SQL 是否为安全的 SELECT 查询。
    返回清洗后的 SQL，或抛出 ValueError。
    """
    cleaned = sql.strip()
    if not cleaned:
        raise ValueError("SQL 语句为空")

    cleaned = re.sub(r"^```(?:sql)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.I)
    cleaned = cleaned.rstrip(";").strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)

    lowered = cleaned.lower()

    # 必须以 SELECT 开头
    if not lowered.lstrip().startswith("select"):
        raise ValueError("仅允许 SELECT 查询")

    # 禁止危险关键字
    for pattern in _FORBIDDEN_SQL_RE:
        if pattern.search(cleaned):
            raise ValueError(f"查询包含禁止的关键字，已拦截")

    # 禁止多条语句
    if ";" in cleaned:
        raise ValueError("禁止执行多条语句")

    # 禁止注释注入
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise ValueError("禁止使用 SQL 注释")

    # 检查引号闭合
    for q in ["'", '"']:
        if cleaned.count(q) % 2 != 0:
            raise ValueError(f"SQL 中存在未闭合的引号")

    # 自动追加 LIMIT
    if not re.search(r'\bLIMIT\b', cleaned, re.I):
        cleaned += f" LIMIT {_DEFAULT_LIMIT}"

    return cleaned


def execute_raw_sql(sql: str, params: dict = None,
                    timeout: int = QUERY_TIMEOUT_SECONDS) -> list:
    """
    执行原始SQL（仅限SELECT），含安全校验 + 超时保护。
    超时后立即关闭会话释放连接，后台线程自行消亡。
    返回字典列表。
    """
    safe_sql = validate_select_sql(sql)

    db = SessionLocal()
    cancel_event = threading.Event()
    result_holder, exc_holder = [], []

    def _run():
        try:
            if cancel_event.is_set():
                return
            r = db.execute(text(safe_sql), params or {})
            if cancel_event.is_set():
                return
            cols = r.keys()
            result_holder[:] = [dict(zip(cols, row)) for row in r.fetchall()]
        except Exception as e:
            # 超时后会话已被关闭，此时报错是预期的，不处理
            if not cancel_event.is_set():
                exc_holder.append(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        cancel_event.set()
        # 关闭 session 释放连接回池。后台线程的 execute() 会因 session closed 而失败。
        # pool_pre_ping=True 确保下次使用时自动检测并重建断开的连接。
        db.close()
        logger.error(
            "SQL查询执行超时(%ds)，已释放连接: %s",
            timeout, safe_sql[:100],
        )
        raise TimeoutError(f"查询执行超时（{timeout}秒），连接已释放")

    try:
        if exc_holder:
            raise exc_holder[0]
        return result_holder
    finally:
        db.close()


def test_connection() -> bool:
    """测试数据库连接（完成后 rollback 释放事务，避免残留 open transaction）"""
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
            db.rollback()  # 释放事务，避免残留连接被 pool_pre_ping 误判为可用
            db.close()
    except Exception as e:
        logger.error("Connection failed: %s", e)
        return False
