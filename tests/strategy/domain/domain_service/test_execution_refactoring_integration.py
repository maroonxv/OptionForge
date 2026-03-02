"""
执行服务重构集成测试

验证重构后的执行服务使用基础设施层组件的行为与重构前一致。

测试内容:
1. 使用序列化器保存和恢复 SmartOrderExecutor 状态
2. 使用序列化器保存和恢复 AdvancedOrderScheduler 状态
3. 使用配置加载器从 YAML 创建执行服务实例
4. 验证重构前后行为一致

**Validates: Requirements 5.1, 5.2, 5.5, 7.3**
"""

import sys
from datetime import datetime
from unittest.mock import MagicMock

# Mock vnpy modules
for _name in [
    "vnpy",
    "vnpy.event",
    "vnpy.trader",
    "vnpy.trader.setting",
    "vnpy.trader.engine",
    "vnpy.trader.database",
    "vnpy.trader.constant",
    "vnpy.trader.object",
    "vnpy_mysql",
]:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()

from src.strategy.domain.domain_service.execution.smart_order_executor import (  # noqa: E402
    SmartOrderExecutor,
)
from src.strategy.domain.domain_service.execution.advanced_order_scheduler import (  # noqa: E402
    AdvancedOrderScheduler,
)
from src.strategy.domain.value_object.trading.order_execution import (  # noqa: E402
    OrderExecutionConfig,
    AdvancedSchedulerConfig,
)
from src.strategy.domain.value_object.trading.order_instruction import (  # noqa: E402
    OrderInstruction,
    Direction,
    Offset,
    OrderType,
)
from src.strategy.infrastructure.persistence.smart_order_executor_serializer import (  # noqa: E402
    SmartOrderExecutorSerializer,
)
from src.strategy.infrastructure.persistence.advanced_order_scheduler_serializer import (  # noqa: E402
    AdvancedOrderSchedulerSerializer,
)
from src.main.config.domain_service_config_loader import (  # noqa: E402
    create_smart_order_executor,
    create_advanced_order_scheduler,
)


class TestSmartOrderExecutorRefactoring:
    """测试 SmartOrderExecutor 重构后的序列化和配置加载功能"""

    def test_serializer_preserves_executor_state(self):
        """
        测试序列化器能够保存和恢复 SmartOrderExecutor 的完整状态
        
        **Validates: Requirements 5.1, 5.5**
        """
        # 创建配置
        config = OrderExecutionConfig(
            timeout_seconds=30,
            max_retries=3,
            slippage_ticks=2,
            price_tick=0.2,
        )
        
        # 创建执行器并注册订单
        executor = SmartOrderExecutor(config)
        instruction = OrderInstruction(
            vt_symbol="IO2506-C-4000.CFFEX",
            direction=Direction.LONG,
            offset=Offset.OPEN,
            volume=10,
            price=100.0,
            signal="test",
            order_type=OrderType.LIMIT,
        )
        managed_order = executor.register_order("order_1", instruction)
        
        # 序列化
        data = SmartOrderExecutorSerializer.to_dict(executor)
        
        # 验证序列化数据包含配置和订单
        assert "config" in data
        assert "orders" in data
        assert data["config"]["timeout_seconds"] == 30
        assert data["config"]["max_retries"] == 3
        assert "order_1" in data["orders"]
        
        # 反序列化
        restored = SmartOrderExecutorSerializer.from_dict(data)
        
        # 验证配置恢复正确
        assert restored.config.timeout_seconds == config.timeout_seconds
        assert restored.config.max_retries == config.max_retries
        assert restored.config.slippage_ticks == config.slippage_ticks
        assert restored.config.price_tick == config.price_tick
        
        # 验证订单恢复正确
        assert len(restored._orders) == 1
        assert "order_1" in restored._orders
        restored_order = restored._orders["order_1"]
        assert restored_order.vt_orderid == "order_1"
        assert restored_order.instruction.vt_symbol == instruction.vt_symbol
        assert restored_order.instruction.volume == instruction.volume
        assert restored_order.is_active == managed_order.is_active

    def test_config_loader_creates_executor_with_defaults(self):
        """
        测试配置加载器能够从部分配置创建执行器，缺失字段使用默认值
        
        **Validates: Requirements 5.1, 5.5**
        """
        # 部分配置
        config_dict = {
            "timeout_seconds": 60,
            "max_retries": 5,
        }
        
        # 使用配置加载器创建执行器
        executor = create_smart_order_executor(config_dict)
        
        # 验证提供的配置项
        assert executor.config.timeout_seconds == 60
        assert executor.config.max_retries == 5
        
        # 验证缺失的配置项使用默认值
        defaults = OrderExecutionConfig()
        assert executor.config.slippage_ticks == defaults.slippage_ticks
        assert executor.config.price_tick == defaults.price_tick

    def test_executor_behavior_unchanged_after_refactoring(self):
        """
        测试重构后执行器的业务逻辑行为保持不变
        
        **Validates: Requirements 5.1, 5.5, 7.3**
        """
        config = OrderExecutionConfig(
            timeout_seconds=30,
            max_retries=3,
            slippage_ticks=2,
            price_tick=0.2,
        )
        executor = SmartOrderExecutor(config)
        
        # 测试自适应价格计算
        instruction = OrderInstruction(
            vt_symbol="IO2506-C-4000.CFFEX",
            direction=Direction.LONG,
            offset=Offset.OPEN,
            volume=10,
            price=100.0,
            signal="test",
            order_type=OrderType.LIMIT,
        )
        
        adaptive_price = executor.calculate_adaptive_price(
            instruction, bid_price=99.8, ask_price=100.2, price_tick=0.2
        )
        
        # 买入方向应该在卖价基础上加滑点
        expected_price = 100.2 + 2 * 0.2  # ask_price + slippage_ticks * price_tick
        assert abs(adaptive_price - expected_price) < 1e-10
        
        # 测试价格对齐
        rounded_price = executor.round_price_to_tick(100.15, 0.2)
        assert abs(rounded_price - 100.2) < 1e-10


class TestAdvancedOrderSchedulerRefactoring:
    """测试 AdvancedOrderScheduler 重构后的序列化和配置加载功能"""

    def test_serializer_preserves_scheduler_state(self):
        """
        测试序列化器能够保存和恢复 AdvancedOrderScheduler 的完整状态
        
        **Validates: Requirements 5.2, 5.5**
        """
        # 创建配置
        config = AdvancedSchedulerConfig(
            default_batch_size=10,
            default_interval_seconds=60,
            default_num_slices=5,
        )
        
        # 创建调度器并提交冰山单
        scheduler = AdvancedOrderScheduler(config)
        instruction = OrderInstruction(
            vt_symbol="IO2506-C-4000.CFFEX",
            direction=Direction.LONG,
            offset=Offset.OPEN,
            volume=50,
            price=100.0,
            signal="test",
            order_type=OrderType.LIMIT,
        )
        order = scheduler.submit_iceberg(instruction, batch_size=10)
        
        # 序列化
        data = AdvancedOrderSchedulerSerializer.to_dict(scheduler)
        
        # 验证序列化数据
        assert "config" in data
        assert "orders" in data
        assert data["config"]["default_batch_size"] == 10
        assert order.order_id in data["orders"]
        
        # 反序列化
        restored = AdvancedOrderSchedulerSerializer.from_dict(data)
        
        # 验证配置恢复正确
        assert restored.config.default_batch_size == config.default_batch_size
        assert restored.config.default_interval_seconds == config.default_interval_seconds
        assert restored.config.default_num_slices == config.default_num_slices
        
        # 验证订单恢复正确
        assert len(restored._orders) == 1
        restored_order = restored.get_order(order.order_id)
        assert restored_order is not None
        assert restored_order.order_id == order.order_id
        assert len(restored_order.child_orders) == 5  # 50 / 10 = 5 子单
        assert restored_order.status == order.status

    def test_config_loader_creates_scheduler_with_defaults(self):
        """
        测试配置加载器能够从部分配置创建调度器，缺失字段使用默认值
        
        **Validates: Requirements 5.2, 5.5**
        """
        # 部分配置
        config_dict = {
            "default_batch_size": 20,
            "default_num_slices": 10,
        }
        
        # 使用配置加载器创建调度器
        scheduler = create_advanced_order_scheduler(config_dict)
        
        # 验证提供的配置项
        assert scheduler.config.default_batch_size == 20
        assert scheduler.config.default_num_slices == 10
        
        # 验证缺失的配置项使用默认值
        defaults = AdvancedSchedulerConfig()
        assert scheduler.config.default_interval_seconds == defaults.default_interval_seconds
        assert scheduler.config.default_volume_randomize_ratio == defaults.default_volume_randomize_ratio

    def test_scheduler_behavior_unchanged_after_refactoring(self):
        """
        测试重构后调度器的业务逻辑行为保持不变
        
        **Validates: Requirements 5.2, 5.5, 7.3**
        """
        config = AdvancedSchedulerConfig(default_batch_size=10)
        scheduler = AdvancedOrderScheduler(config)
        
        # 提交冰山单
        instruction = OrderInstruction(
            vt_symbol="IO2506-C-4000.CFFEX",
            direction=Direction.LONG,
            offset=Offset.OPEN,
            volume=35,
            price=100.0,
            signal="test",
            order_type=OrderType.LIMIT,
        )
        order = scheduler.submit_iceberg(instruction, batch_size=10)
        
        # 验证拆单逻辑
        assert len(order.child_orders) == 4  # 35 / 10 = 3 个完整批次 + 1 个余数批次
        assert order.child_orders[0].volume == 10
        assert order.child_orders[1].volume == 10
        assert order.child_orders[2].volume == 10
        assert order.child_orders[3].volume == 5  # 余数
        
        # 验证子单 ID 格式
        for i, child in enumerate(order.child_orders):
            assert child.child_id == f"{order.order_id}_child_{i}"
            assert child.parent_id == order.order_id


class TestSerializationRoundTrip:
    """测试序列化往返的完整性"""

    def test_executor_round_trip_with_multiple_orders(self):
        """
        测试包含多个订单的执行器序列化往返
        
        **Validates: Requirements 5.1, 5.5, 7.3**
        """
        config = OrderExecutionConfig(
            timeout_seconds=45,
            max_retries=4,
            slippage_ticks=3,
            price_tick=0.5,
        )
        executor = SmartOrderExecutor(config)
        
        # 注册多个订单
        for i in range(3):
            instruction = OrderInstruction(
                vt_symbol=f"IO250{6+i}-C-4000.CFFEX",
                direction=Direction.LONG if i % 2 == 0 else Direction.SHORT,
                offset=Offset.OPEN,
                volume=10 * (i + 1),
                price=100.0 + i * 10,
                signal=f"test_{i}",
                order_type=OrderType.LIMIT,
            )
            executor.register_order(f"order_{i}", instruction)
        
        # 序列化 → 反序列化
        data = SmartOrderExecutorSerializer.to_dict(executor)
        restored = SmartOrderExecutorSerializer.from_dict(data)
        
        # 验证所有订单都恢复了
        assert len(restored._orders) == 3
        for i in range(3):
            order_id = f"order_{i}"
            assert order_id in restored._orders
            original = executor._orders[order_id]
            restored_order = restored._orders[order_id]
            assert restored_order.instruction.vt_symbol == original.instruction.vt_symbol
            assert restored_order.instruction.volume == original.instruction.volume

    def test_scheduler_round_trip_with_twap_order(self):
        """
        测试包含 TWAP 订单的调度器序列化往返
        
        **Validates: Requirements 5.2, 5.5, 7.3**
        """
        config = AdvancedSchedulerConfig(
            default_num_slices=5,
            default_interval_seconds=60,
        )
        scheduler = AdvancedOrderScheduler(config)
        
        # 提交 TWAP 订单
        instruction = OrderInstruction(
            vt_symbol="IO2506-C-4000.CFFEX",
            direction=Direction.LONG,
            offset=Offset.OPEN,
            volume=100,
            price=100.0,
            signal="test",
            order_type=OrderType.LIMIT,
        )
        start_time = datetime(2026, 1, 15, 10, 0, 0)
        order = scheduler.submit_twap(
            instruction,
            time_window_seconds=300,
            num_slices=5,
            start_time=start_time,
        )
        
        # 序列化 → 反序列化
        data = AdvancedOrderSchedulerSerializer.to_dict(scheduler)
        restored = AdvancedOrderSchedulerSerializer.from_dict(data)
        
        # 验证 TWAP 订单恢复正确
        restored_order = restored.get_order(order.order_id)
        assert restored_order is not None
        assert len(restored_order.child_orders) == 5
        assert len(restored_order.slice_schedule) == 5
        
        # 验证时间片调度
        from datetime import timedelta
        for i, slice_entry in enumerate(restored_order.slice_schedule):
            assert slice_entry.volume == 20  # 100 / 5 = 20
            expected_time = start_time + timedelta(seconds=i * 60)  # 每 60 秒一片
            assert slice_entry.scheduled_time == expected_time
