"""
数据库连接管理模块
基于 SQLAlchemy 2.0，提供同步引擎与会话工厂
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# 创建数据库引擎
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,         # 基础连接数
    max_overflow=40,      # 峰值溢出连接数（最大并发 60）
    pool_pre_ping=True,   # 每次取出连接前先 ping，避免使用已断开的连接
    pool_recycle=3600,    # 连接最大复用时间 1 小时
    pool_timeout=10,      # 等待连接超时秒数
    echo=False,           # 生产环境关闭 SQL 日志
)

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 基类
Base = declarative_base()


def get_db():
    """
    FastAPI 依赖注入：获取数据库会话
    请求结束时自动关闭会话，防止连接泄漏

    使用方式:
        @app.get("/api/xxx")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
