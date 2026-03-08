"""BacktestRunner unit tests."""

from __future__ import annotations

import sys
from enum import Enum
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class _Exchange(str, Enum):
    CFFEX = "CFFEX"


class _Interval(str, Enum):
    MINUTE = "1m"


_cm = MagicMock()
_cm.Exchange = _Exchange
_cm.Interval = _Interval
_om = MagicMock()

for _name in [
    "vnpy",
    "vnpy.event",
    "vnpy.event.engine",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.database",
    "vnpy_postgresql",
    "vnpy_portfoliostrategy.utility",
    "chinese_calendar",
]:
    sys.modules.setdefault(_name, MagicMock())

sys.modules["vnpy.trader.constant"] = _cm
sys.modules["vnpy.trader.object"] = _om


def test_runner_uses_toml_strategy_config_and_injects_shared_settings() -> None:
    from src.backtesting.config import BacktestConfig
    from src.backtesting.runner import BacktestRunner

    engine = MagicMock()
    fake_portfolio = MagicMock()
    fake_portfolio.BacktestingEngine.return_value = engine
    fake_portfolio.StrategyEntry = MagicMock()

    registry = MagicMock()
    registry.get.return_value = SimpleNamespace(size=100, pricetick=0.2)

    strategy_config = {
        "strategy_contracts": {
            "indicator_service": "example.ema_cross_example.indicator_service:EmaCrossIndicatorService",
        },
        "service_activation": {
            "option_selector": True,
            "position_sizing": False,
        },
        "strategies": [
            {
                "class_name": "StrategyEntry",
                "strategy_name": "demo",
                "vt_symbols": ["IF"],
                "setting": {"max_positions": 5},
            }
        ],
    }

    runner = BacktestRunner(BacktestConfig(config_path="config/strategy_config.toml", start_date="2025-01-01", end_date="2025-01-31"))
    runner.registry = registry

    with patch.dict(sys.modules, {"vnpy_portfoliostrategy": fake_portfolio, "src.strategy.strategy_entry": MagicMock()}), \
         patch("src.backtesting.runner.ConfigLoader.load_strategy_config", return_value=strategy_config) as mock_load_config, \
         patch("src.backtesting.runner.SymbolGenerator.generate_recent", return_value=["IF2506.CFFEX"]), \
         patch("src.backtesting.runner.OptionDiscoveryService.discover", return_value=[]):
        runner.run()

    mock_load_config.assert_called_once_with("config/strategy_config.toml")
    assert engine.add_strategy.call_count == 1
    kwargs = engine.add_strategy.call_args.kwargs
    setting = kwargs["setting"]
    assert setting["strategy_full_config"] == strategy_config
    assert setting["service_activation"]["option_selector"] is True
    assert setting["strategy_contracts"]["indicator_service"].startswith("example.")
