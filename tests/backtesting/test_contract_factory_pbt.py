"""
ContractFactory 属性测试

Feature: backtesting-restructure
Property 5: 期货合约构建正确性
Property 6: 期权合约构建正确性
Validates: Requirements 5.1, 5.2, 5.3, 5.4
"""

import sys
from enum import Enum
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing contract_factory
# ---------------------------------------------------------------------------


class _Exchange(str, Enum):
    SHFE = "SHFE"
    CFFEX = "CFFEX"
    DCE = "DCE"
    CZCE = "CZCE"
    INE = "INE"


class _Product(str, Enum):
    FUTURES = "期货"
    OPTION = "期权"


class _OptionType(str, Enum):
    CALL = "看涨期权"
    PUT = "看跌期权"


class _ContractData:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        for attr in ("option_strike", "option_underlying", "option_type", "option_expiry"):
            if not hasattr(self, attr):
                setattr(self, attr, None)


_const_mod = MagicMock()
_const_mod.Exchange = _Exchange
_const_mod.Product = _Product
_const_mod.OptionType = _OptionType

_obj_mod = MagicMock()
_obj_mod.ContractData = _ContractData

for _name in ["vnpy", "vnpy.event", "vnpy.trader", "vnpy.trader.setting",
               "vnpy.trader.engine", "vnpy.trader.database", "vnpy_postgresql"]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

sys.modules["vnpy.trader.constant"] = _const_mod
sys.modules["vnpy.trader.object"] = _obj_mod

# ---------------------------------------------------------------------------
# Now safe to import
# ---------------------------------------------------------------------------

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from src.backtesting.config import (  # noqa: E402
    DEFAULT_PRODUCT_SPEC,
    EXCHANGE_MAP,
    OPTION_FUTURE_MAP,
    PRODUCT_SPECS,
)
from src.backtesting.contract.contract_factory import ContractFactory  # noqa: E402

# ---------------------------------------------------------------------------
# 策略：按交易所分组品种代码
# ---------------------------------------------------------------------------

_CZCE_PRODUCTS = sorted(k for k, v in EXCHANGE_MAP.items() if v == "CZCE")
_NON_CZCE_PRODUCTS = sorted(k for k, v in EXCHANGE_MAP.items() if v != "CZCE")

# 期权品种（CFFEX 带连字符格式）
_OPTION_PRODUCTS = sorted(OPTION_FUTURE_MAP.keys())  # IO, MO, HO

_year_st = st.integers(min_value=2020, max_value=2030)
_month_st = st.integers(min_value=1, max_value=12)
_type_st = st.sampled_from(["C", "P"])
_strike_st = st.integers(min_value=100, max_value=10000)


class TestFuturesContractProperty:
    """Property 5: 期货合约构建正确性

    *For any* 有效的期货格式 vt_symbol，ContractFactory.create() 返回的 ContractData 应满足：
    - product 为 Product.FUTURES
    - symbol 和 exchange 与输入一致
    - size 和 pricetick 与 PRODUCT_SPECS 中该品种的值一致（或使用默认值）

    **Validates: Requirements 5.1, 5.4**
    """

    @given(
        product_code=st.sampled_from(_NON_CZCE_PRODUCTS),
        year=_year_st,
        month=_month_st,
    )
    @settings(max_examples=100)
    def test_non_czce_futures_contract(
        self, product_code: str, year: int, month: int
    ):
        """非郑商所期货合约：2位年份+2位月份格式。

        **Validates: Requirements 5.1, 5.4**
        """
        exchange = EXCHANGE_MAP[product_code]
        symbol = f"{product_code}{year % 100:02d}{month:02d}"
        vt_symbol = f"{symbol}.{exchange}"

        contract = ContractFactory.create(vt_symbol)

        assert contract is not None, f"ContractFactory.create({vt_symbol!r}) 返回 None"
        assert contract.product == _Product.FUTURES, (
            f"{vt_symbol}: product={contract.product}, expected FUTURES"
        )
        assert contract.symbol == symbol, (
            f"{vt_symbol}: symbol={contract.symbol}, expected {symbol}"
        )
        assert contract.exchange == _Exchange(exchange), (
            f"{vt_symbol}: exchange={contract.exchange}, expected {exchange}"
        )

        expected_size, expected_pricetick = PRODUCT_SPECS.get(
            product_code, DEFAULT_PRODUCT_SPEC
        )
        assert contract.size == expected_size, (
            f"{vt_symbol}: size={contract.size}, expected {expected_size}"
        )
        assert contract.pricetick == expected_pricetick, (
            f"{vt_symbol}: pricetick={contract.pricetick}, expected {expected_pricetick}"
        )

    @given(
        product_code=st.sampled_from(_CZCE_PRODUCTS),
        year=_year_st,
        month=_month_st,
    )
    @settings(max_examples=100)
    def test_czce_futures_contract(
        self, product_code: str, year: int, month: int
    ):
        """郑商所期货合约：1位年份+2位月份格式。

        **Validates: Requirements 5.1, 5.4**
        """
        exchange = EXCHANGE_MAP[product_code]
        symbol = f"{product_code}{year % 10}{month:02d}"
        vt_symbol = f"{symbol}.{exchange}"

        contract = ContractFactory.create(vt_symbol)

        assert contract is not None, f"ContractFactory.create({vt_symbol!r}) 返回 None"
        assert contract.product == _Product.FUTURES, (
            f"{vt_symbol}: product={contract.product}, expected FUTURES"
        )
        assert contract.symbol == symbol, (
            f"{vt_symbol}: symbol={contract.symbol}, expected {symbol}"
        )
        assert contract.exchange == _Exchange(exchange), (
            f"{vt_symbol}: exchange={contract.exchange}, expected {exchange}"
        )

        expected_size, expected_pricetick = PRODUCT_SPECS.get(
            product_code, DEFAULT_PRODUCT_SPEC
        )
        assert contract.size == expected_size, (
            f"{vt_symbol}: size={contract.size}, expected {expected_size}"
        )
        assert contract.pricetick == expected_pricetick, (
            f"{vt_symbol}: pricetick={contract.pricetick}, expected {expected_pricetick}"
        )


class TestOptionContractProperty:
    """Property 6: 期权合约构建正确性

    *For any* 有效的期权格式 vt_symbol（如 "MO2601-C-6300.CFFEX"），
    ContractFactory.create() 返回的 ContractData 应满足：
    - product 为 Product.OPTION
    - option_type 与 symbol 中的 C/P 标识一致
    - option_strike 与 symbol 中的行权价一致
    - 若品种存在反向映射（如 MO→IM），option_underlying 使用映射后的期货品种代码

    **Validates: Requirements 5.2, 5.3, 5.4**
    """

    @given(
        option_product=st.sampled_from(_OPTION_PRODUCTS),
        year=_year_st,
        month=_month_st,
        type_char=_type_st,
        strike=_strike_st,
    )
    @settings(max_examples=100)
    def test_cffex_option_contract(
        self,
        option_product: str,
        year: int,
        month: int,
        type_char: str,
        strike: int,
    ):
        """CFFEX 期权合约（带连字符格式）。

        **Validates: Requirements 5.2, 5.3, 5.4**
        """
        year_short = year % 100
        symbol = f"{option_product}{year_short:02d}{month:02d}-{type_char}-{strike}"
        vt_symbol = f"{symbol}.CFFEX"

        contract = ContractFactory.create(vt_symbol)

        assert contract is not None, f"ContractFactory.create({vt_symbol!r}) 返回 None"
        assert contract.product == _Product.OPTION, (
            f"{vt_symbol}: product={contract.product}, expected OPTION"
        )

        # option_type 与 C/P 一致
        expected_option_type = (
            _OptionType.CALL if type_char == "C" else _OptionType.PUT
        )
        assert contract.option_type == expected_option_type, (
            f"{vt_symbol}: option_type={contract.option_type}, expected {expected_option_type}"
        )

        # option_strike 与行权价一致
        assert contract.option_strike == float(strike), (
            f"{vt_symbol}: option_strike={contract.option_strike}, expected {float(strike)}"
        )

        # 反向映射：option_underlying 使用映射后的期货品种代码
        future_product = OPTION_FUTURE_MAP[option_product]
        expected_underlying = f"{future_product}{year_short:02d}{month:02d}"
        assert contract.option_underlying == expected_underlying, (
            f"{vt_symbol}: option_underlying={contract.option_underlying}, "
            f"expected {expected_underlying}"
        )

        # size/pricetick 正确
        expected_size, expected_pricetick = PRODUCT_SPECS.get(
            option_product, DEFAULT_PRODUCT_SPEC
        )
        assert contract.size == expected_size, (
            f"{vt_symbol}: size={contract.size}, expected {expected_size}"
        )
        assert contract.pricetick == expected_pricetick, (
            f"{vt_symbol}: pricetick={contract.pricetick}, expected {expected_pricetick}"
        )
