"""
src/main/bootstrap/ - 引擎初始化与共享启动逻辑

包含 VnPy 引擎工厂、数据库配置和录制路径补丁等共享模块。

导出:
    - create_engines: 创建 VnPy 核心引擎实例
    - EngineBundle: VnPy 引擎组合数据类
    - setup_vnpy_database: 从环境变量注入数据库配置到 VnPy SETTINGS
    - patch_ctp_pre_settlement_price: 为 CTP Tick 注入 pre_settlement_price
    - patch_data_recorder_setting_path: 重定向 data_recorder_setting.json 路径
"""
from src.main.bootstrap.engine_factory import create_engines, EngineBundle
from src.main.bootstrap.vnpy_logging import configure_vnpy_logging
from src.main.bootstrap.database_setup import setup_vnpy_database
from src.main.bootstrap.ctp_tick_patch import patch_ctp_pre_settlement_price
from src.main.bootstrap.recorder_patch import patch_data_recorder_setting_path

__all__ = [
    "create_engines",
    "EngineBundle",
    "configure_vnpy_logging",
    "setup_vnpy_database",
    "patch_ctp_pre_settlement_price",
    "patch_data_recorder_setting_path",
]
