"""
OptionSelectorService 流动性增强测试

验证:
1. check_liquidity 的盘口有效性/深度/价差/陈旧度检查
2. DataFrame 过滤新增阈值
3. 评分流程先执行流动性过滤
4. 组合选择优先同到期日
"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd

from src.strategy.domain.domain_service.selection.option_selector_service import (
    OptionSelectorService,
)
from src.strategy.domain.value_object.combination.combination import CombinationType
from src.strategy.domain.value_object.selection.option_selector_config import OptionSelectorConfig


def _make_tick(**kwargs):
    base = {
        "vt_symbol": "OPT.TEST",
        "volume": 1000,
        "bid_price_1": 10.0,
        "ask_price_1": 10.2,
        "bid_volume_1": 2,
        "bid_volume_2": 2,
        "bid_volume_3": 2,
        "bid_volume_4": 2,
        "bid_volume_5": 2,
        "ask_volume_1": 2,
        "ask_volume_2": 2,
        "ask_volume_3": 2,
        "ask_volume_4": 2,
        "ask_volume_5": 2,
        "datetime": datetime.now(),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _make_contract(pricetick: float = 0.2):
    return SimpleNamespace(pricetick=pricetick)


class TestCheckLiquidityEnhancement:

    def test_rejects_invalid_quotes(self):
        selector = OptionSelectorService(
            OptionSelectorConfig(
                liquidity_min_volume=1,
                liquidity_min_bid_volume=1,
                liquidity_max_spread_ticks=10,
                liquidity_require_valid_quotes=True,
            )
        )
        tick = _make_tick(bid_price_1=10.0, ask_price_1=9.9)
        assert selector.check_liquidity(tick, _make_contract()) is False

    def test_supports_required_volume_with_depth_levels(self):
        selector = OptionSelectorService(
            OptionSelectorConfig(
                liquidity_min_volume=1,
                liquidity_min_bid_volume=1,
                liquidity_max_spread_ticks=10,
                liquidity_depth_levels=3,
            )
        )
        tick = _make_tick(bid_volume_1=1, bid_volume_2=1, bid_volume_3=2)
        assert selector.check_liquidity(
            tick,
            _make_contract(),
            required_volume=4,
            side="sell",
        ) is True

    def test_fails_when_depth_insufficient(self):
        selector = OptionSelectorService(
            OptionSelectorConfig(
                liquidity_min_volume=1,
                liquidity_min_bid_volume=1,
                liquidity_max_spread_ticks=10,
                liquidity_depth_levels=2,
            )
        )
        tick = _make_tick(bid_volume_1=1, bid_volume_2=1)
        assert selector.check_liquidity(
            tick,
            _make_contract(),
            required_volume=3,
            side="sell",
        ) is False

    def test_applies_max_relative_spread(self):
        selector = OptionSelectorService(
            OptionSelectorConfig(
                liquidity_min_volume=1,
                liquidity_min_bid_volume=1,
                liquidity_max_spread_ticks=100,
                liquidity_max_relative_spread=0.01,
            )
        )
        tick = _make_tick(bid_price_1=10.0, ask_price_1=10.5)
        assert selector.check_liquidity(tick, _make_contract()) is False

    def test_rejects_stale_tick(self):
        selector = OptionSelectorService(
            OptionSelectorConfig(
                liquidity_min_volume=1,
                liquidity_min_bid_volume=1,
                liquidity_max_spread_ticks=10,
                liquidity_max_tick_staleness_seconds=1,
            )
        )
        tick = _make_tick(datetime=datetime.now() - timedelta(seconds=10))
        assert selector.check_liquidity(tick, _make_contract()) is False


class TestDataframeLiquidityEnhancement:

    def test_select_option_respects_extended_filter(self):
        selector = OptionSelectorService(
            OptionSelectorConfig(
                min_bid_price=10.0,
                min_bid_volume=5,
                filter_min_ask_volume=20,
                filter_min_total_volume=100,
                filter_min_open_interest=200,
                filter_max_relative_spread=0.02,
                min_trading_days=1,
                max_trading_days=50,
            )
        )
        df = pd.DataFrame(
            [
                {
                    "vt_symbol": "BAD.TEST",
                    "option_type": "call",
                    "strike_price": 101.0,
                    "expiry_date": "2026-06-19",
                    "bid_price": 20.0,
                    "ask_price": 20.1,
                    "bid_volume": 30,
                    "ask_volume": 1,
                    "volume": 500,
                    "open_interest": 500,
                    "days_to_expiry": 10,
                },
                {
                    "vt_symbol": "GOOD.TEST",
                    "option_type": "call",
                    "strike_price": 102.0,
                    "expiry_date": "2026-06-19",
                    "bid_price": 20.0,
                    "ask_price": 20.1,
                    "bid_volume": 30,
                    "ask_volume": 30,
                    "volume": 500,
                    "open_interest": 500,
                    "days_to_expiry": 10,
                },
            ]
        )

        result = selector.select_option(
            contracts=df,
            option_type="call",
            underlying_price=100.0,
            strike_level=1,
        )
        assert result is not None
        assert result.vt_symbol == "GOOD.TEST"

    def test_score_candidates_filters_illiquid_contracts_first(self):
        selector = OptionSelectorService(
            OptionSelectorConfig(
                min_bid_price=10.0,
                min_bid_volume=5,
                min_trading_days=1,
                max_trading_days=50,
            )
        )
        df = pd.DataFrame(
            [
                {
                    "vt_symbol": "LIQ.TEST",
                    "option_type": "call",
                    "strike_price": 101.0,
                    "expiry_date": "2026-06-19",
                    "bid_price": 20.0,
                    "ask_price": 20.2,
                    "bid_volume": 20,
                    "ask_volume": 20,
                    "days_to_expiry": 10,
                },
                {
                    "vt_symbol": "ILLIQ.TEST",
                    "option_type": "call",
                    "strike_price": 102.0,
                    "expiry_date": "2026-06-19",
                    "bid_price": 20.0,
                    "ask_price": 20.2,
                    "bid_volume": 1,  # 低于 min_bid_volume
                    "ask_volume": 20,
                    "days_to_expiry": 10,
                },
            ]
        )

        scores = selector.score_candidates(
            contracts=df,
            option_type="call",
            underlying_price=100.0,
        )

        assert len(scores) == 1
        assert scores[0].option_contract.vt_symbol == "LIQ.TEST"


class TestCombinationExpiryGrouping:

    def test_strangle_prefers_same_expiry_group(self):
        selector = OptionSelectorService(
            OptionSelectorConfig(
                strike_level=1,
                min_bid_price=10.0,
                min_bid_volume=1,
                min_trading_days=1,
                max_trading_days=50,
            )
        )
        df = pd.DataFrame(
            [
                # expiry A: 可构造同到期日 Strangle
                {
                    "vt_symbol": "CALL_A_105",
                    "option_type": "call",
                    "strike_price": 105.0,
                    "expiry_date": "2026-06-19",
                    "bid_price": 20.0,
                    "ask_price": 20.2,
                    "bid_volume": 10,
                    "ask_volume": 10,
                    "days_to_expiry": 10,
                },
                {
                    "vt_symbol": "PUT_A_95",
                    "option_type": "put",
                    "strike_price": 95.0,
                    "expiry_date": "2026-06-19",
                    "bid_price": 20.0,
                    "ask_price": 20.2,
                    "bid_volume": 10,
                    "ask_volume": 10,
                    "days_to_expiry": 10,
                },
                # expiry B: Put 更接近平值，但没有可用 OTM Call
                {
                    "vt_symbol": "CALL_B_90",
                    "option_type": "call",
                    "strike_price": 90.0,
                    "expiry_date": "2026-07-17",
                    "bid_price": 20.0,
                    "ask_price": 20.2,
                    "bid_volume": 10,
                    "ask_volume": 10,
                    "days_to_expiry": 38,
                },
                {
                    "vt_symbol": "PUT_B_99",
                    "option_type": "put",
                    "strike_price": 99.0,
                    "expiry_date": "2026-07-17",
                    "bid_price": 20.0,
                    "ask_price": 20.2,
                    "bid_volume": 10,
                    "ask_volume": 10,
                    "days_to_expiry": 38,
                },
            ]
        )

        result = selector.select_combination(
            contracts=df,
            combination_type=CombinationType.STRANGLE,
            underlying_price=100.0,
            strike_level=1,
        )

        assert result is not None
        assert result.success is True
        assert len(result.legs) == 2
        assert result.legs[0].expiry_date == result.legs[1].expiry_date
