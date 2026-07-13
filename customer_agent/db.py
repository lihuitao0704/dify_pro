"""
customer_agent MySQL 直连封装

提供最小化的同步 MySQL 访问能力，供 persist.py 和 services/ 调用。
- Database 类：PyMySQL + DictCursor
- 懒加载单例：首次 get_db() 时创建连接（uvicorn 每个 worker 各一份）
- 连接失败不阻塞主流程：调用方捕获异常后降级为纯内存模式

合并自 study_abroad_agent/database.py 的线程安全模式 + 参数统一走 config.py。
表结构定义已迁移至 customer_agent/schemas.py (TABLE_SCHEMAS)。
"""

import logging
import threading

import pymysql
from pymysql.cursors import DictCursor

from customer_agent.config import config

log = logging.getLogger(__name__)

# 线程局部存储：每个线程一个 Database 实例
_local = threading.local()


class Database:
    """PyMySQL 连接封装，返回字典游标。"""

    def __init__(self):
        self.conn = pymysql.connect(
            host=config.MYSQL_HOST,
            port=config.MYSQL_PORT,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD,
            database=config.MYSQL_DATABASE,
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=int(config.MYSQL_TIMEOUT),
            read_timeout=int(config.MYSQL_TIMEOUT),
            write_timeout=int(config.MYSQL_TIMEOUT),
            autocommit=True,
        )

    def query(self, sql, params=None):
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def query_one(self, sql, params=None):
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def execute(self, sql, params=None):
        """执行写操作，返回 lastrowid。"""
        with self.conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.lastrowid

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


def get_db() -> Database:
    """获取当前线程的 Database 实例（懒加载单例）。"""
    db = getattr(_local, "db", None)
    if db is None:
        db = Database()
        _local.db = db
    return db


def is_available() -> bool:
    """探测 MySQL 是否可用（仅在启动/健康检查时调用，不在热路径）。"""
    try:
        db = get_db()
        db.query("SELECT 1")
        return True
    except Exception as e:
        log.warning("[db] MySQL 不可用，降级为纯内存模式: %s", e)
        return False


def close_db():
    """关闭当前线程的连接（用于测试清理或优雅关闭）。"""
    db = getattr(_local, "db", None)
    if db is not None:
        db.close()
        _local.db = None


# 向后兼容：模块级单供快速导入；新建代码请用 get_db()
from customer_agent.schemas import TABLE_SCHEMAS, get_table_schemas  # noqa: E402,F401
