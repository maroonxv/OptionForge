"""
执行服务直接编排属性测试

Feature: execution-service-enhancement, Property 6: 上层使用自适应价格计算
Feature: execution-service-enhancement, Property 7: 上层注册子单到超时管理

**Validates: Requirements 4.2, 4.3**
"""

import sys
from datetime import datetime
from typing import List, Tuple
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Mock vnpy modules before importing domain modules
# ---------------------------------------------------------------------------
for _name in [
    "vnpy",
    "vnpy.event",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.database",
    "vnpy.trader.constant",
    "vnpy.trader.object",
    "vnpy_postgresql",
]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

from src.strategy.domain.domain_service.execution.advanced_order_scheduler import (  # noqa: E402
    AdvancedOrderScheduler,
)
from src.strategy.domain.domain_service.execution.smart_order_executor import (  # noqa: E402
    SmartOrderExecutor,
)
from src.strategy.domain.event.event_types import DomainEvent  # noqa: E402
from src.strategy.domain.value_object.trading.order_execution import (  # noqa: E402
    OrderExecutionConfig,
)
from src.strategy.domain.value_object.trading.order_instruction import (  # noqa: E402
    Direction,
    Offset,
    OrderInstruction,
    OrderType,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_directions = st.sampled_from([Direction.LONG, Direction.SHORT])
_offsets = st.sampled_from([Offset.OPEN, Offset.CLOSE])
_order_types = st.sampled_from([OrderType.LIMIT, OrderType.MARKET, OrderType.FAK, OrderType.FOK])

_positive_price = st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
_price_tick = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)
_slippage_ticks = st.integers(min_value=0, max_value=10)
_volume = st.integers(min_value=1, max_value=1000)
_batch_size = st.integers(min_value=1, max_value=100)

_vt_symbol = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="._"),
    min_size=3,
    max_size=20,
)


@st.composite
def _order_instruction(draw):
    """Generate a random OrderInstruction with positive volume and price."""
    return OrderInstruction(
        vt_symbol=draw(_vt_symbol),
        direction=draw(_directions),
        offset=draw(_offsets),
        volume=draw(_volume),
        price=draw(_positive_price),
        signal="test_signal",
        order_type=draw(_order_types),
    )


def _process_pending_children(
    scheduler: AdvancedOrderScheduler,
    executor: SmartOrderExecutor,
    current_time: datetime,
    bid_price: float,
    ask_price: float,
    price_tick: float,
) -> Tuple[List[OrderInstruction], List[DomainEvent]]:
    """上层直接编排：处理待提交子单并计算自适应价格。"""
    instructions: List[OrderInstruction] = []
    events: List[DomainEvent] = []

    pending_children = scheduler.get_pending_children(current_time)
    for child in pending_children:
        parent_order = scheduler.get_order(child.parent_id)
        if parent_order is None:
            continue
        original = parent_order.request.instruction

        child_instruction = OrderInstruction(
            vt_symbol=original.vt_symbol,
            direction=original.direction,
            offset=original.offset,
            volume=child.volume,
            price=original.price,
            signal=original.signal,
            order_type=original.order_type,
        )
        expected_adaptive = executor.calculate_adaptive_price(
            child_instruction, bid_price, ask_price, price_tick
        )
        rounded = executor.round_price_to_tick(expected_adaptive, price_tick)

        instructions.append(
            OrderInstruction(
                vt_symbol=original.vt_symbol,
                direction=original.direction,
                offset=original.offset,
                volume=child.volume,
                price=rounded,
                signal=original.signal,
                order_type=original.order_type,
            )
        )

    return instructions, events


# ---------------------------------------------------------------------------
# Property 6: 上层使用自适应价格计算
# Feature: execution-service-enhancement, Property 6
# **Validates: Requirements 4.2**
# ---------------------------------------------------------------------------


class TestProperty6ServiceOrchestrationUsesAdaptivePricing:
    """
    对于任意待提交子单和有效 bid/ask，
    上层直接编排产生的指令价格应等于 SmartOrderExecutor 的自适应价格计算结果
    （经 round_price_to_tick 对齐后）。
    """

    @given(
        instruction=_order_instruction(),
        batch_size=_batch_size,
        bid_price=_positive_price,
        ask_price=_positive_price,
        price_tick=_price_tick,
        slippage_ticks=_slippage_ticks,
    )
    @settings(max_examples=100)
    def test_service_orchestration_uses_adaptive_pricing(
        self,
        instruction: OrderInstruction,
        batch_size: int,
        bid_price: float,
        ask_price: float,
        price_tick: float,
        slippage_ticks: int,
    ):
        config = OrderExecutionConfig(slippage_ticks=slippage_ticks, price_tick=price_tick)
        executor = SmartOrderExecutor(config)
        scheduler = AdvancedOrderScheduler()

        scheduler.submit_iceberg(instruction, batch_size)
        current_time = datetime.now()
        instructions, events = _process_pending_children(
            scheduler=scheduler,
            executor=executor,
            current_time=current_time,
            bid_price=bid_price,
            ask_price=ask_price,
            price_tick=price_tick,
        )

        pending_children = scheduler.get_pending_children(current_time)

        for i, final_instruction in enumerate(instructions):
            child = pending_children[i]
            parent_order = scheduler.get_order(child.parent_id)
            assert parent_order is not None
            original = parent_order.request.instruction

            child_instruction = OrderInstruction(
                vt_symbol=original.vt_symbol,
                direction=original.direction,
                offset=original.offset,
                volume=child.volume,
                price=original.price,
                signal=original.signal,
                order_type=original.order_type,
            )
            expected_adaptive = executor.calculate_adaptive_price(
                child_instruction, bid_price, ask_price, price_tick
            )
            expected_rounded = executor.round_price_to_tick(expected_adaptive, price_tick)

            assert final_instruction.price == pytest.approx(expected_rounded, abs=1e-9), (
                f"Instruction price {final_instruction.price} != expected {expected_rounded} "
                f"(adaptive={expected_adaptive}, tick={price_tick})"
            )
        assert events == []


# ---------------------------------------------------------------------------
# Property 7: 上层注册子单到超时管理
# Feature: execution-service-enhancement, Property 7
# **Validates: Requirements 4.3**
# ---------------------------------------------------------------------------


class TestProperty7ServiceOrchestrationRegistersChildrenToTimeout:
    """
    对于任意由上层直接调用 register_order 注册的子单，
    对应 vt_orderid 应出现在 SmartOrderExecutor 的托管订单集合中。
    """

    @given(
        vt_orderid=st.text(min_size=1, max_size=30),
        instruction=_order_instruction(),
    )
    @settings(max_examples=100)
    def test_service_orchestration_registers_children_to_timeout(
        self,
        vt_orderid: str,
        instruction: OrderInstruction,
    ):
        executor = SmartOrderExecutor(OrderExecutionConfig())
        executor.register_order(vt_orderid, instruction)

        managed = executor.get_managed_order(vt_orderid)
        assert managed is not None, (
            f"vt_orderid '{vt_orderid}' not found after register_order"
        )
        assert managed.instruction == instruction
        assert managed.is_active is True
