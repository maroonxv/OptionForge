"""BacktestRunner unit tests. Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5"""
import sys
from enum import Enum
from unittest.mock import MagicMock, patch


class _Exchange(str, Enum):
    SHFE = "SHFE"
    CFFEX = "CFFEX"
    DCE = "DCE"
    CZCE = "CZCE"
    INE = "INE"


class _Product(str, Enum):
    FUTURES = "FUTURES"
    OPTION = "OPTION"


class _OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class _Interval(str, Enum):
    MINUTE = "1m"


class _ContractData:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def vt_symbol(self):
        return f"{self.symbol}.{self.exchange.value}"


_cm = MagicMock()
_cm.Exchange = _Exchange
_cm.Product = _Product
_cm.OptionType = _OptionType
_cm.Interval = _Interval
_om = MagicMock()
_om.ContractData = _ContractData
for _n in ["vnpy", "vnpy.event", "vnpy.event.engine", "vnpy.trader", "vnpy.trader.setting", "vnpy.trader.engine", "vnpy.trader.database", "vnpy_postgresql", "vnpy_portfoliostrategy", "vnpy_portfoliostrategy.utility"]:
    if _n not in sys.modules:
        sys.modules[_n] = MagicMock()
sys.modules["vnpy.trader.constant"] = _cm
sys.modules["vnpy.trader.object"] = _om
sys.modules["src.strategy.strategy_entry"] = MagicMock()
