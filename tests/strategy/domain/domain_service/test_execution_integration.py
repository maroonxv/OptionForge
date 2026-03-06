"""
执行服务集成测试

测试上层直接编排 SmartOrderExecutor 与 AdvancedOrderScheduler 的工作流程：
1. 高级订单子单使用自适应价格计算后的价格
2. 子单超时后触发重试流程
3. 重试耗尽时产生 OrderRetryExhaustedEvent 事件
4. 高级订单全部子单成交后产生完成事件

Validates: Requirements 8.1, 8.2, 8.3, 8.4
"""

import sys
from datetime import datetime, timedelta
from typing import List, Tuple
from unittest.mock import MagicMock

import pytest

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
from src.strategy.domain.event.event_types import (  # noqa: E402
    DomainEvent,
    IcebergCompleteEvent,
    OrderRetryExhaustedEvent,
)
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
# Helpers
# ---------------------------------------------------------------------------

def _make_instruction(
    vt_symbol: str = "rb2501.SHFE",
    direction: Direction = Direction.LONG,
    offset: Offset = Offset.OPEN,
    volume: int = 10,
    price: float = 4000.0,
) -> OrderInstruction:
    return OrderInstruction(
        vt_symbol=vt_symbol,
        direction=direction,
        offset=offset,
        volume=volume,
        price=price,
        signal="test",
        order_type=OrderType.LIMIT,
    )


def _process_pending_children(
    scheduler: AdvancedOrderScheduler,
    executor: SmartOrderExecutor,
    current_time: datetime,
    bid_price: float,
    ask_price: float,
    price_tick: float,
) -> Tuple[List[OrderInstruction], List[DomainEvent]]:
    """上层直接编排：调度待提交子单并生成自适应价格指令。"""
    instructions: List[OrderInstruction] = []
    events: List[DomainEvent] = []

    pending_children = scheduler.get_pending_children(current_time)
    for child in pending_children:
        parent_order = scheduler.get_order(child.parent_id)
        if parent_order is None:
            continue

        original_instruction = parent_order.request.instruction
        child_instruction = OrderInstruction(
            vt_symbol=original_instruction.vt_symbol,
            direction=original_instruction.direction,
            offset=original_instruction.offset,
            volume=child.volume,
            price=original_instruction.price,
            signal=original_instruction.signal,
            order_type=original_instruction.order_type,
        )

        adaptive_price = executor.calculate_adaptive_price(
            child_instruction, bid_price, ask_price, price_tick
        )
        rounded_price = executor.round_price_to_tick(adaptive_price, price_tick)

        final_instruction = OrderInstruction(
            vt_symbol=original_instruction.vt_symbol,
            direction=original_instruction.direction,
            offset=original_instruction.offset,
            volume=child.volume,
            price=rounded_price,
            signal=original_instruction.signal,
            order_type=original_instruction.order_type,
        )
        instructions.append(final_instruction)

    return instructions, events


def _check_timeouts_and_retry(
    executor: SmartOrderExecutor,
    current_time: datetime,
    price_tick: float,
) -> Tuple[List[str], List[OrderInstruction], List[DomainEvent]]:
    """上层直接编排：检查超时并准备重试指令。"""
    cancel_ids, timeout_events = executor.check_timeouts(current_time)
    retry_instructions: List[OrderInstruction] = []
    all_events: List[DomainEvent] = list(timeout_events)

    for vt_orderid in cancel_ids:
        managed_order = executor.get_managed_order(vt_orderid)
        if managed_order is None:
            continue

        retry_instruction, retry_events = executor.prepare_retry(
            managed_order, price_tick
        )
        all_events.extend(retry_events)
        if retry_instruction is not None:
            retry_instructions.append(retry_instruction)

    return cancel_ids, retry_instructions, all_events


# ===========================================================================
# Test 1: 子单使用自适应价格 (Req 8.1)
# ===========================================================================


class TestChildOrdersUseAdaptivePricing:
    """Validates: Requirements 8.1"""

    def test_child_orders_use_adaptive_pricing(self):
        """高级订单子单经上层编排后，价格应为自适应计算结果而非原始价格。"""
        slippage_ticks = 3
        price_tick = 0.2
        bid_price = 4000.0
        ask_price = 4002.0

        config = OrderExecutionConfig(slippage_ticks=slippage_ticks, price_tick=price_tick)
        executor = SmartOrderExecutor(config)
        scheduler = AdvancedOrderScheduler()

        instruction = _make_instruction(direction=Direction.LONG, volume=10, price=4000.0)
        scheduler.submit_iceberg(instruction, batch_size=5)

        current_time = datetime.now()
        instructions, events = _process_pending_children(
            scheduler=scheduler,
            executor=executor,
            current_time=current_time,
            bid_price=bid_price,
            ask_price=ask_price,
            price_tick=price_tick,
        )

        assert len(instructions) == 1
        expected_adaptive = ask_price + slippage_ticks * price_tick
        expected_rounded = executor.round_price_to_tick(expected_adaptive, price_tick)

        assert instructions[0].price == pytest.approx(expected_rounded, abs=1e-9)
        assert instructions[0].price != instruction.price
        assert events == []

    def test_sell_child_orders_use_adaptive_pricing(self):
        """卖出方向子单的自适应价格 = bid_price - slippage_ticks * price_tick。"""
        slippage_ticks = 2
        price_tick = 0.5
        bid_price = 5000.0
        ask_price = 5002.0

        config = OrderExecutionConfig(slippage_ticks=slippage_ticks, price_tick=price_tick)
        executor = SmartOrderExecutor(config)
        scheduler = AdvancedOrderScheduler()

        instruction = _make_instruction(direction=Direction.SHORT, volume=5, price=5000.0)
        scheduler.submit_iceberg(instruction, batch_size=5)

        instructions, _ = _process_pending_children(
            scheduler=scheduler,
            executor=executor,
            current_time=datetime.now(),
            bid_price=bid_price,
            ask_price=ask_price,
            price_tick=price_tick,
        )

        assert len(instructions) == 1
        expected_adaptive = bid_price - slippage_ticks * price_tick
        expected_rounded = executor.round_price_to_tick(expected_adaptive, price_tick)
        assert instructions[0].price == pytest.approx(expected_rounded, abs=1e-9)


# ===========================================================================
# Test 2: 子单超时触发重试 (Req 8.2)
# ===========================================================================


class TestChildTimeoutTriggersRetry:
    """Validates: Requirements 8.2"""

    def test_child_timeout_triggers_retry(self):
        """子单注册后超时，直接编排应返回撤销 ID 和重试指令。"""
        timeout_seconds = 1
        price_tick = 0.2

        config = OrderExecutionConfig(
            timeout_seconds=timeout_seconds,
            max_retries=3,
            slippage_ticks=2,
            price_tick=price_tick,
        )
        executor = SmartOrderExecutor(config)

        instruction = _make_instruction(price=4000.0)
        vt_orderid = "order_001"
        executor.register_order(vt_orderid, instruction)

        assert executor.get_managed_order(vt_orderid) is not None

        managed = executor.get_managed_order(vt_orderid)
        assert managed is not None
        managed.submit_time = datetime.now() - timedelta(seconds=2)

        cancel_ids, retry_instructions, events = _check_timeouts_and_retry(
            executor=executor,
            current_time=datetime.now(),
            price_tick=price_tick,
        )

        assert vt_orderid in cancel_ids
        assert len(retry_instructions) == 1
        assert retry_instructions[0].vt_symbol == instruction.vt_symbol
        assert len(events) >= 1


# ===========================================================================
# Test 3: 重试耗尽产生 OrderRetryExhaustedEvent (Req 8.3)
# ===========================================================================


class TestRetryExhaustedProducesEvent:
    """Validates: Requirements 8.3"""

    def test_retry_exhausted_produces_event(self):
        """max_retries=0 时，第一次超时即耗尽重试，应产生 OrderRetryExhaustedEvent。"""
        timeout_seconds = 1
        price_tick = 0.2

        config = OrderExecutionConfig(
            timeout_seconds=timeout_seconds,
            max_retries=0,
            slippage_ticks=2,
            price_tick=price_tick,
        )
        executor = SmartOrderExecutor(config)

        instruction = _make_instruction(vt_symbol="IF2506.CFFEX", price=3800.0)
        vt_orderid = "order_exhausted"
        executor.register_order(vt_orderid, instruction)

        managed = executor.get_managed_order(vt_orderid)
        assert managed is not None
        managed.submit_time = datetime.now() - timedelta(seconds=2)

        cancel_ids, retry_instructions, events = _check_timeouts_and_retry(
            executor=executor,
            current_time=datetime.now(),
            price_tick=price_tick,
        )

        assert vt_orderid in cancel_ids
        assert len(retry_instructions) == 0

        retry_exhausted_events = [
            e for e in events if isinstance(e, OrderRetryExhaustedEvent)
        ]
        assert len(retry_exhausted_events) == 1

        evt = retry_exhausted_events[0]
        assert evt.vt_symbol == "IF2506.CFFEX"
        assert evt.total_retries == 0
        assert evt.original_price == 3800.0
        assert evt.final_price == 3800.0


# ===========================================================================
# Test 4: 全部子单成交产生完成事件 (Req 8.4)
# ===========================================================================


class TestAllChildrenFilledProducesCompleteEvent:
    """Validates: Requirements 8.4"""

    def test_all_children_filled_produces_complete_event(self):
        """冰山单全部子单成交后，scheduler.on_child_filled 应返回完成事件。"""
        scheduler = AdvancedOrderScheduler()

        instruction = _make_instruction(
            vt_symbol="rb2501.SHFE", volume=5, price=4000.0
        )
        order = scheduler.submit_iceberg(instruction, batch_size=5)

        assert len(order.child_orders) == 1
        child = order.child_orders[0]

        events = scheduler.on_child_filled(child.child_id)

        assert len(events) == 1
        assert isinstance(events[0], IcebergCompleteEvent)

        evt = events[0]
        assert evt.order_id == order.order_id
        assert evt.vt_symbol == "rb2501.SHFE"
        assert evt.total_volume == 5
        assert evt.filled_volume == 5

    def test_multiple_children_filled_sequentially(self):
        """多个子单依次成交，只有最后一个成交时才产生完成事件。"""
        scheduler = AdvancedOrderScheduler()

        instruction = _make_instruction(volume=10, price=4000.0)
        order = scheduler.submit_iceberg(instruction, batch_size=3)

        assert len(order.child_orders) == 4

        for child in order.child_orders[:3]:
            events = scheduler.on_child_filled(child.child_id)
            assert not any(isinstance(e, IcebergCompleteEvent) for e in events)

        events = scheduler.on_child_filled(order.child_orders[3].child_id)
        complete_events = [e for e in events if isinstance(e, IcebergCompleteEvent)]
        assert len(complete_events) == 1
        assert complete_events[0].filled_volume == 10
