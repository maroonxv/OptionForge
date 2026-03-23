"""
recorder_process.py - 独立行情录制入口

职责:
1. 初始化 VnPy 引擎 (EventEngine, MainEngine)
2. 加载 DataRecorderApp (行情录制)
3. 连接 CTP 网关
4. 仅录制行情，不运行策略

重构说明:
- 原文件位置: src/main/run_recorder.py
- 新文件位置: src/main/process/recorder_process.py
- 使用 bootstrap/ 共享模块替换重复代码
"""
import sys
import time
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

# 添加项目根目录到 Python 路径 (现在位于 src/main/process/ 下，需要向上三级)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# VnPy 导入
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy_datarecorder import DataRecorderApp

# 内部模块 - 使用兼容导入路径
from src.main.config.gateway_manager import GatewayManager
from src.main.config.config_loader import ConfigLoader
from src.main.utils.logging_setup import setup_logging

# 共享启动模块
from src.main.bootstrap import (
    create_engines,
    setup_vnpy_database,
    patch_data_recorder_setting_path,
)
from src.main.utils.signal_handler import register_shutdown_signals


class RecorderProcess:
    """
    行情录制进程
    
    负责连接 CTP 网关并录制行情数据，不运行策略。
    """

    def __init__(
        self,
        log_level: str = "INFO",
        log_dir: str = "logs/runner",
    ) -> None:
        """
        初始化行情录制进程
        
        Args:
            log_level: 日志级别
            log_dir: 日志目录
        """
        self.log_level = log_level
        self.log_dir = log_dir

        self.logger = logging.getLogger(__name__)

        self.event_engine: Optional[EventEngine] = None
        self.main_engine: Optional[MainEngine] = None
        self.gateway_manager: Optional[GatewayManager] = None
        self.recorder_engine: Optional[Any] = None

        self.running: bool = False
        self.gateway_config: Dict[str, Any] = {}

        # 使用共享模块注册信号处理器
        register_shutdown_signals(self._handle_shutdown)

    def _handle_shutdown(self, signum: int, frame) -> None:
        """处理关闭信号"""
        self.logger.info(f"收到信号 {signum}，准备关闭")
        self.running = False

    def run(self) -> None:
        """
        运行行情录制进程
        """
        self.running = True
        self.logger.info("行情录制进程启动")

        try:
            self._load_configs()
            
            # 使用共享模块设置数据库配置
            if not setup_vnpy_database():
                self.logger.warning("数据库配置未成功注入，数据录制可能无法工作")
            
            # 使用共享模块设置录制路径补丁
            patch_data_recorder_setting_path()
            
            self._init_engines()
            self._connect_gateways()
            self._wait_for_connection()
            
            self._run_event_loop()
        except Exception as e:
            self.logger.error(f"录制进程异常: {e}", exc_info=True)
            sys.exit(1)
        finally:
            self.shutdown()

    def _load_configs(self) -> None:
        """加载配置"""
        self.logger.info("加载配置...")
        self.gateway_config = ConfigLoader.load_gateway_config()

    def _init_engines(self) -> None:
        """初始化 VnPy 引擎"""
        self.logger.info("初始化 VnPy 引擎...")
        
        # 使用共享模块创建引擎
        bundle = create_engines()
        self.event_engine = bundle.event_engine
        self.main_engine = bundle.main_engine
        
        # 初始化网关管理器
        self.gateway_manager = GatewayManager(self.main_engine)
        self.gateway_manager.set_config(self.gateway_config)
        self.gateway_manager.add_gateways()

        # 添加数据录制应用
        self.recorder_engine = self.main_engine.add_app(DataRecorderApp)
        self.logger.info("DataRecorder 已加载")

    def _connect_gateways(self) -> None:
        """连接交易网关"""
        self.logger.info("连接交易网关...")
        self.gateway_manager.connect_all()

    def _wait_for_connection(self, timeout: float = 60.0) -> None:
        """等待网关连接成功"""
        self.logger.info(f"等待网关连接 (超时: {timeout}s)...")
        self.gateway_manager.wait_for_ready("recording", timeout)
        self.logger.info("网关连接成功")

    def _run_event_loop(self) -> None:
        """运行事件循环"""
        self.logger.info("进入事件循环")
        while self.running:
            time.sleep(1.0)

    def shutdown(self) -> None:
        """关闭录制进程"""
        self.logger.info("正在关闭...")
        self.running = False
        if self.gateway_manager:
            self.gateway_manager.disconnect_all()
        elif self.main_engine:
            self.main_engine.close()
        self.logger.info("已关闭")


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="独立行情录制")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--log-dir", default="logs/runner")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    setup_logging(args.log_level, args.log_dir, "recorder")
    
    process = RecorderProcess(
        log_level=args.log_level,
        log_dir=args.log_dir
    )
    process.run()
