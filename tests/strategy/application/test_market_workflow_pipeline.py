from __future__ import annotations

import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.strategy.domain.aggregate.instrument_manager import InstrumentManager
from src.strategy.domain.aggregate.position_aggregate import PositionAggregate
from src.strategy.domain.value_object.market.option_contract import OptionContract
from src.strategy.domain.value_object.signal import (
    IndicatorComputationResult,
    OptionSelectionPreference,
    SignalDecision,
)


sys.modules.setdefault("vnpy", MagicMock())
sys.modules.setdefault("vnpy.trader", MagicMock())
sys.modules.setdefault("vnpy.trader.object", MagicMock())

from src.strategy.application.market_workflow import MarketWorkflow  # noqa: E402


class _IndicatorService:
    def calculate_bar(self, instrument, bar, context=None):
        instrument.indicators["demo"] = {"value": 1}
        return IndicatorComputationResult(
            indicator_key="demo",
            updated_indicator_keys=["demo"],
            values={"value": 1},
            summary="demo indicator",
        )


class _SignalService:
    def check_open_signal(self, instrument, context=None):
        return SignalDecision(
            action="open",
            signal_name="demo_open",
            rationale="unit test signal",
            selection_preference=OptionSelectionPreference(option_type="call", strike_level=1),
        )

    def check_close_signal(self, instrument, position, context=None):
        return None


class _MarketGateway:
    def __init__(self):
        self._contracts = [
            SimpleNamespace(
                vt_symbol="IO2506-C-3800.CFFEX",
                option_type="CALL",
                option_underlying="IF2506",
                option_strike=3800,
                exchange=SimpleNamespace(value="CFFEX"),
                size=100,
                pricetick=0.2,
            )
        ]

    def get_all_contracts(self):
        return self._contracts

    def get_tick(self, vt_symbol):
        return SimpleNamespace(
            vt_symbol=vt_symbol,
            bid_price_1=10.0,
            bid_volume_1=20,
            ask_price_1=10.2,
            ask_volume_1=20,
            last_price=10.1,
            volume=100,
            open_interest=500,
            datetime=datetime(2026, 1, 2, 10, 0, 0),
        )

    def get_contract(self, vt_symbol):
        return self._contracts[0]


def test_market_workflow_emits_decision_trace_for_open_pipeline() -> None:
    entry = SimpleNamespace()
    entry.bar_pipeline = None
    entry.target_aggregate = InstrumentManager()
    entry.position_aggregate = PositionAggregate()
    entry.market_gateway = _MarketGateway()
    entry.indicator_service = _IndicatorService()
    entry.signal_service = _SignalService()
    entry.option_selector_service = MagicMock()
    entry.option_selector_service.select_option_from_chain.return_value = OptionContract(
        vt_symbol="IO2506-C-3800.CFFEX",
        underlying_symbol="IF2506.CFFEX",
        option_type="call",
        strike_price=3800,
        expiry_date="2025-06-20",
        diff1=0.01,
        bid_price=10.0,
        bid_volume=20,
        ask_price=10.2,
        ask_volume=20,
        days_to_expiry=30,
    )
    entry.position_sizing_service = None
    entry.greeks_calculator = None
    entry.pricing_engine = None
    entry.monitor = MagicMock()
    entry.observability_config = {"emit_noop_decisions": False}
    entry.service_activation = {"option_chain": True, "decision_observability": True}
    entry.decision_journal = []
    entry.decision_journal_limit = 20
    entry.logger = MagicMock()
    entry.current_dt = datetime(2026, 1, 2, 10, 0, 0)
    entry._record_snapshot = lambda: None
    entry._register_signal_temporary_symbol = lambda vt_symbol: None
    entry.last_decision_trace = None
    entry.risk_thresholds = MagicMock()

    workflow = MarketWorkflow(entry)
    bar = SimpleNamespace(
        datetime=datetime(2026, 1, 2, 10, 0, 0),
        open_price=100.0,
        high_price=101.0,
        low_price=99.0,
        close_price=100.5,
        volume=1000,
    )

    workflow.process_bars({"IF2506.CFFEX": bar})

    assert entry.last_decision_trace is not None
    assert entry.decision_journal
    assert any(stage["stage"] == "selection" for stage in entry.decision_journal[-1]["stages"])
    entry.monitor.record_decision_trace.assert_called_once()
