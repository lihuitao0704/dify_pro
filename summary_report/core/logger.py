"""
统一日志模块

使用标准库 logging，提供统一的格式与命名规范，全项目通过
``get_logger(__name__)`` 获取 logger，方便按模块定位问题。
"""

import logging
import sys
from typing import Optional

_CONFIGURED: bool = False

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    """初始化全局日志配置，幂等（多次调用只生效一次）。"""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    获取命名 logger。

    首次调用时会自动初始化日志配置，使用者无需手动 setup。
    """
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
