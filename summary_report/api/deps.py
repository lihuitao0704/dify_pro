"""
依赖注入（FastAPI Depends）。

把跨路由复用的资源 / 校验逻辑抽象为可注入依赖，供多个路由调用。
目前保留占位结构便于后续扩展（如鉴权、限流、请求日志）。
"""

from functools import lru_cache

from summary_report.core.config import DB_CONFIG, LLM_MODEL
from summary_report.core.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_db_config() -> dict:
    """
    缓存的数据库配置依赖。

    使用 lru_cache 保证全局只读取一次，后续注入直接复用。
    """
    logger.info("加载数据库配置: host=%s, database=%s", DB_CONFIG["host"], DB_CONFIG["database"])
    return DB_CONFIG


@lru_cache(maxsize=1)
def get_model_name() -> str:
    """缓存的 LLM 模型名依赖。"""
    return LLM_MODEL
