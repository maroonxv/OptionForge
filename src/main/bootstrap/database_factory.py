"""统一数据库连接工厂（单例）。

职责:
- 验证环境变量完整性
- 注入 VnPy SETTINGS 并配置表名 (dbbardata, dbtickdata)
- 支持 eager / lazy 初始化
- 提供 VnPy 数据库实例和底层 Peewee 连接
- 连接失败时抛出异常，不回退 SQLite

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 3.1, 3.2, 3.4, 3.5
"""

import importlib
import logging
import os
from typing import Any, ClassVar, List, Optional

from src.strategy.infrastructure.persistence.exceptions import (
    DatabaseConfigError,
    DatabaseConnectionError,
)

logger = logging.getLogger(__name__)

DRIVER_EXTENSION_MODULES = {
    "postgres": "vnpy_postgresql",
    "postgresql": "vnpy_postgresql",
}

REQUIRED_ENV_VARS = [
    "VNPY_DATABASE_DRIVER",
    "VNPY_DATABASE_HOST",
    "VNPY_DATABASE_DATABASE",
    "VNPY_DATABASE_USER",
    "VNPY_DATABASE_PASSWORD",
]


class DatabaseFactory:
    """统一数据库连接工厂（单例）"""

    _instance: ClassVar[Optional["DatabaseFactory"]] = None
    _db: Optional[Any] = None
    _peewee_db: Optional[Any] = None
    _initialized: bool = False

    @classmethod
    def get_instance(cls) -> "DatabaseFactory":
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self, eager: bool = True, timeout: float = 5.0) -> None:
        """初始化数据库连接。

        - 验证环境变量完整性
        - 注入 VnPy SETTINGS
        - 配置表名 (dbbardata, dbtickdata)
        - eager=True 时立即建立连接并验证
        - 连接失败时抛出 DatabaseConnectionError
        - 环境变量缺失时抛出 DatabaseConfigError
        """
        # 1. 验证环境变量
        missing = self.validate_env_vars()
        if missing:
            raise DatabaseConfigError(missing)

        # 2. 注入 VnPy SETTINGS
        self._inject_vnpy_settings()

        # 3. 配置表名
        self._configure_table_names()

        self._initialized = True

        # 4. eager 模式下立即连接并验证
        if eager:
            self._create_connections(timeout)

        host = os.getenv("VNPY_DATABASE_HOST", "")
        database = os.getenv("VNPY_DATABASE_DATABASE", "")
        logger.info(f"DatabaseFactory 初始化完成: host={host}, database={database}")

    def get_database(self) -> Any:
        """获取 VnPy 数据库实例。

        如果尚未初始化，执行 lazy 初始化。
        """
        if self._db is None:
            if not self._initialized:
                self.initialize(eager=True)
            else:
                self._create_connections()
        return self._db

    def get_peewee_db(self) -> Any:
        """获取底层 Peewee 数据库连接（用于 strategy_state 表操作）。"""
        if self._peewee_db is None:
            if not self._initialized:
                self.initialize(eager=True)
            else:
                self._create_connections()
        return self._peewee_db

    def validate_connection(self, timeout: float = 5.0) -> bool:
        """验证数据库连接是否可用。"""
        if self._peewee_db is None:
            return False
        try:
            self._peewee_db.execute_sql("SELECT 1")
            return True
        except Exception:
            return False

    @staticmethod
    def validate_env_vars() -> List[str]:
        """检查必需的环境变量，返回缺失的变量名列表。"""
        missing = []
        for var in REQUIRED_ENV_VARS:
            value = os.environ.get(var)
            if not value or not value.strip():
                missing.append(var)
        return missing

    def reset(self) -> None:
        """重置工厂状态（仅用于测试）。"""
        self._db = None
        self._peewee_db = None
        self._initialized = False
        DatabaseFactory._instance = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_vnpy_settings() -> None:
        """从环境变量注入 VnPy SETTINGS。"""
        from vnpy.trader.setting import SETTINGS

        driver = os.getenv("VNPY_DATABASE_DRIVER", "").strip()
        SETTINGS["database.driver"] = driver
        SETTINGS["database.name"] = driver
        SETTINGS["database.database"] = os.getenv("VNPY_DATABASE_DATABASE", "").strip()
        SETTINGS["database.host"] = os.getenv("VNPY_DATABASE_HOST", "localhost").strip()

        try:
            port = int(os.getenv("VNPY_DATABASE_PORT", "5432").strip())
        except (ValueError, TypeError):
            port = 5432
        SETTINGS["database.port"] = port

        SETTINGS["database.user"] = os.getenv("VNPY_DATABASE_USER", "").strip()
        SETTINGS["database.password"] = os.getenv("VNPY_DATABASE_PASSWORD", "")

    @staticmethod
    def _configure_table_names() -> None:
        """配置数据库扩展表名。"""
        extension_module = DatabaseFactory._load_driver_extension_module()
        if extension_module is None:
            return

        db_bar_data = getattr(extension_module, "DbBarData", None)
        if db_bar_data is not None:
            db_bar_data._meta.table_name = "dbbardata"

        db_tick_data = getattr(extension_module, "DbTickData", None)
        if db_tick_data is not None:
            db_tick_data._meta.table_name = "dbtickdata"

    @staticmethod
    def _load_driver_extension_module() -> Optional[Any]:
        driver = os.getenv("VNPY_DATABASE_DRIVER", "").strip().lower()
        module_name = DRIVER_EXTENSION_MODULES.get(driver)
        if not module_name:
            return None

        try:
            return importlib.import_module(module_name)
        except Exception:
            return None

    def _create_connections(self, timeout: float = 5.0) -> None:
        """创建数据库连接。"""
        host = os.getenv("VNPY_DATABASE_HOST", "")
        database = os.getenv("VNPY_DATABASE_DATABASE", "")

        try:
            # 获取 VnPy 数据库实例
            from vnpy.trader.database import get_database
            self._db = get_database()

            # 获取底层 Peewee 连接
            if hasattr(self._db, "db"):
                self._peewee_db = self._db.db
            else:
                extension_module = self._load_driver_extension_module()
                if extension_module is not None and hasattr(extension_module, "db"):
                    self._peewee_db = extension_module.db

            # 验证连接
            if self._peewee_db is not None:
                self._peewee_db.execute_sql("SELECT 1")

        except Exception as e:
            self._db = None
            self._peewee_db = None
            raise DatabaseConnectionError(host, database, e) from e
