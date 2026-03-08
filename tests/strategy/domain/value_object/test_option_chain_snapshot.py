from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from src.strategy.domain.value_object.market.option_chain import OptionChainSnapshot


def test_option_chain_snapshot_builds_selector_frame() -> None:
    contracts = [
        SimpleNamespace(
            vt_symbol="IO2506-C-3800.CFFEX",
            option_type="CALL",
            option_underlying="IF2506",
            option_strike=3800,
            exchange=SimpleNamespace(value="CFFEX"),
            size=100,
            pricetick=0.2,
        ),
        SimpleNamespace(
            vt_symbol="OTHER.CFFEX",
            option_type=None,
        ),
    ]

    def get_tick(vt_symbol: str):
        return SimpleNamespace(
            bid_price_1=10.0,
            bid_volume_1=5,
            ask_price_1=10.2,
            ask_volume_1=8,
            last_price=10.1,
            volume=100,
            open_interest=500,
            implied_volatility=0.22,
            datetime=datetime(2026, 1, 2, 10, 0, 0),
        )

    chain = OptionChainSnapshot.from_contracts(
        underlying_vt_symbol="IF2506.CFFEX",
        underlying_price=3780.0,
        contracts=contracts,
        get_tick=get_tick,
        as_of=datetime(2026, 1, 2, 10, 0, 0),
    )

    frame = chain.to_selector_frame()

    assert len(chain.entries) == 1
    assert frame.iloc[0]["vt_symbol"] == "IO2506-C-3800.CFFEX"
    assert frame.iloc[0]["option_type"] == "call"
    assert frame.iloc[0]["implied_volatility"] == 0.22
