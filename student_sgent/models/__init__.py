"""
SQLAlchemy 模型基类和引擎配置
"""

import logging
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger("models")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import (  # noqa: E402
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_ECHO, startup_check,
)

Base = declarative_base()


def _build_db_url():
    return URL.create(
        "mysql+pymysql",
        username=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        query={"charset": "utf8mb4"},
    )


_engine = None
_SessionLocal = None
_init_lock = threading.Lock()


def _ensure_initialized():
    global _engine, _SessionLocal
    if _engine is None:
        with _init_lock:
            if _engine is None:
                status = startup_check()
                if not status["ready"]:
                    raise RuntimeError(
                        f"Missing env vars: {', '.join(status['missing'])}. "
                        "Set them in .env or environment."
                    )
                _engine = create_engine(
                    _build_db_url(),
                    pool_size=10,
                    max_overflow=20,
                    pool_recycle=3300,
                    pool_pre_ping=True,
                    echo=DB_ECHO,
                )
                _SessionLocal = sessionmaker(
                    bind=_engine,
                    expire_on_commit=False,
                )
                logger.info("Engine ready, pool_size=%d", _engine.pool.size())


def get_engine():
    _ensure_initialized()
    return _engine


@contextmanager
def get_session():
    _ensure_initialized()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


from .student import (
    ConversationSession, ConversationMessage,
    EmotionProfileSnapshot, RiskIntervention,
    FeedbackTicket, AcademicSchedule,
    DeadlineReminder, StudyIntention,
    StudentApplication,
)

__all__ = [
    "Base", "get_session", "get_engine",
    "ConversationSession", "ConversationMessage",
    "EmotionProfileSnapshot", "RiskIntervention",
    "FeedbackTicket", "AcademicSchedule",
    "DeadlineReminder", "StudyIntention",
    "StudentApplication",
]
