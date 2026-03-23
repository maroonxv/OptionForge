"""
engine_factory.py - VnPy 引擎工厂

职责:
提供 VnPy 核心引擎（EventEngine + MainEngine）的统一创建接口，
消除 child_process.py 和 run_recorder.py 之间的重复初始化代码。

调用方在获取 EngineBundle 后，各自负责添加网关和应用
（PortfolioStrategyApp / DataRecorderApp），因为这部分逻辑各进程不同。
"""
from dataclasses import dataclass

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine

from src.main.bootstrap.vnpy_logging import configure_vnpy_logging


@dataclass
class EngineBundle:
    """
    VnPy 引擎组合
    
    封装 EventEngine 和 MainEngine 实例，由 create_engines() 返回。
    """
    event_engine: EventEngine
    main_engine: MainEngine


def create_engines(vnpy_log_dir: str | None = None) -> EngineBundle:
    """
    创建并返回 VnPy 核心引擎实例。
    
    此函数提取自 child_process.py._init_engines() 和 
    run_recorder.py._init_engines() 的公共部分。
    
    Returns:
        EngineBundle: 包含 EventEngine 和 MainEngine 的组合
    
    Example:
        >>> bundle = create_engines()
        >>> bundle.event_engine  # EventEngine 实例
        >>> bundle.main_engine   # MainEngine 实例
    """
    configure_vnpy_logging(vnpy_log_dir)
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    return EngineBundle(event_engine=event_engine, main_engine=main_engine)
