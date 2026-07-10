"""
系统配置热加载管理器
从 system_configs 表读取配置，覆盖 config.py 默认值。
支持运行时热刷新，无需重启服务。
"""
import logging
import threading
import time
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from utils.database import SessionLocal

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    配置优先级：system_configs 表 > config.py 默认值
    首次使用自动从数据库加载，每 5 分钟自动刷新。
    """

    _instance = None
    _lock = threading.Lock()
    _config_cache: dict[str, str] = {}
    _last_refresh: float = 0
    _refresh_interval: float = 60  # 1 分钟（降低过期检查开销）
    _check_interval: float = 5     # 每 5 秒才检查一次是否过期

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def _ensure_loaded(self):
        """惰性加载，首次从DB拉取，之后每 5s 检查是否过期，减少 time.time() 调用"""
        if not self._config_cache:
            self.refresh()
            return
        now = time.time()
        if now - self._last_refresh > self._check_interval:
            if now - self._last_refresh > self._refresh_interval:
                self.refresh()

    def refresh(self):
        """从 system_configs 表重新加载所有配置（线程安全）"""
        with self._lock:
            db: Session | None = None
            try:
                db = SessionLocal()
                rows = db.execute(
                    text("SELECT config_key, config_value FROM system_configs WHERE config_value IS NOT NULL")
                ).fetchall()
                self._config_cache = {r[0]: r[1] for r in rows}
                self._last_refresh = time.time()
                logger.info(f"配置热加载完成，共 {len(self._config_cache)} 条")
            except Exception as e:
                logger.warning(f"配置加载失败，沿用缓存: {e}")
            finally:
                if db:
                    db.close()

    # ── 类型安全的取值方法 ──

    def get_float(self, key: str, default: float = 0.0) -> float:
        self._ensure_loaded()
        val = self._config_cache.get(key)
        if val is None:
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def get_int(self, key: str, default: int = 0) -> int:
        self._ensure_loaded()
        val = self._config_cache.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_decimal(self, key: str, default: Decimal | None = None) -> Decimal:
        self._ensure_loaded()
        val = self._config_cache.get(key)
        if val is None:
            return default or Decimal("0")
        try:
            return Decimal(val)
        except Exception:
            return default or Decimal("0")

    def get_str(self, key: str, default: str = "") -> str:
        self._ensure_loaded()
        return self._config_cache.get(key, default)

    # ── 阈值的便捷属性（优先数据库，回退 config.py） ──

    @property
    def emotion_threshold_red(self) -> float:
        return self.get_float("emotion_threshold_red", settings.EMOTION_THRESHOLD_RED)

    @property
    def emotion_threshold_yellow(self) -> float:
        return self.get_float("emotion_threshold_yellow", settings.EMOTION_THRESHOLD_YELLOW)

    @property
    def emotion_threshold_blue(self) -> float:
        return self.get_float("emotion_threshold_blue", settings.EMOTION_THRESHOLD_BLUE)

    @property
    def sla_hours(self) -> int:
        return self.get_int("sla_hours", settings.SLA_HOURS)

    @property
    def max_leave_days(self) -> int:
        return self.get_int("max_leave_days", settings.MAX_LEAVE_DAYS)

    @property
    def marketing_cooldown_days(self) -> int:
        return self.get_int("marketing_cooldown_days", settings.MARKETING_COOLDOWN_DAYS)


# 全局单例
config_manager = ConfigManager()
