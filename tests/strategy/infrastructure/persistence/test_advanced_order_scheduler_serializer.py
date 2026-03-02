"""
AdvancedOrderSchedulerSerializer 单元测试

测试序列化器的基本功能、边界条件和错误处理。
"""
import pytest
from datetime import datetime, timedelta

from src.strategy.infrastructure.persistence.advanced_order_scheduler_serializer import AdvancedOrderSchedulerSerializer
from src.strategy.domain.domain_service.execution.advanced_order_scheduler import AdvancedOrderScheduler
from src.strategy.domain.value_object.trading.order_execution import AdvancedSchedulerConfig
from src.strategy.domain.value_object.trading.order_instruction import OrderInstruction, Direction, Offset, OrderType
from src.strategy.domain.value_object.trading.advanced_order import (
    AdvancedOrder, AdvancedOrderRequest, AdvancedOrderType, AdvancedOrderStatus,
    ChildOrder, SliceEntry
)


class TestAdvancedOrderSchedulerSerializer:
    """AdvancedOrderSchedulerSerializer 单元测试"""
    
    def test_serialize_basic_scheduler(self):
        """测试基本序列化"""
        config = AdvancedSchedulerConfig(
            default_batch_size=10,
            default_interval_seconds=60,
            default_num_slices=5,
            default_volume_randomize_ratio=0.1,
            default_price_offset_ticks=1,
            default_price_tick=0.01
        )
        scheduler = AdvancedOrderScheduler(config)
        
        data = AdvancedOrderSchedulerSerializer.to_dict(scheduler)
        
        assert data["config"]["default_batch_size"] == 10
        assert data["config"]["default_interval_seconds"] == 60
        assert data["config"]["default_num_slices"] == 5
        assert data["config"]["default_volume_randomize_ratio"] == 0.1
        assert data["config"]["default_price_offset_ticks"] == 1
        assert data["config"]["default_price_tick"] == 0.01
        assert data["orders"] == {}
    
    def test_deserialize_basic_scheduler(self):
        """测试基本反序列化"""
        data = {
            "config": {
                "default_batch_size": 10,
                "default_interval_seconds": 60,
                "default_num_slices": 5,
                "default_volume_randomize_ratio": 0.1,
                "default_price_offset_ticks": 1,
                "default_price_tick": 0.01
            },
            "orders": {}
        }
        
        scheduler = AdvancedOrderSchedulerSerializer.from_dict(data)
        
        assert scheduler.config.default_batch_size == 10
        assert scheduler.config.default_interval_seconds == 60
        assert scheduler.config.default_num_slices == 5
        assert scheduler.config.default_volume_randomize_ratio == 0.1
        assert scheduler.config.default_price_offset_ticks == 1
        assert scheduler.config.default_price_tick == 0.01
        assert len(scheduler._orders) == 0
    
    def test_serialize_scheduler_with_orders(self):
        """测试包含订单的序列化"""
        config = AdvancedSchedulerConfig()
        scheduler = AdvancedOrderScheduler(config)
        
        # 创建高级订单
        instruction = OrderInstruction(
            vt_symbol="IO2401-C-4000.CFFEX",
            direction=Direction.LONG,
            offset=Offset.OPEN,
            volume=100,
            price=100.0,
            signal="test_signal",
            order_type=OrderType.LIMIT
        )
        
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.ICEBERG,
            instruction=instruction,
            batch_size=10,
            interval_seconds=60
        )
        
        order = AdvancedOrder(
            order_id="order_001",
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            filled_volume=0,
            created_time=datetime(2024, 1, 15, 10, 30, 0)
        )
        
        scheduler._orders["order_001"] = order
        
        data = AdvancedOrderSchedulerSerializer.to_dict(scheduler)
        
        assert "order_001" in data["orders"]
        order_data = data["orders"]["order_001"]
        assert order_data["order_id"] == "order_001"
        assert order_data["request"]["order_type"] == "iceberg"
        assert order_data["status"] == "executing"
    
    def test_deserialize_scheduler_with_orders(self):
        """测试包含订单的反序列化"""
        data = {
            "config": {
                "default_batch_size": 10,
                "default_interval_seconds": 60
            },
            "orders": {
                "order_001": {
                    "order_id": "order_001",
                    "request": {
                        "order_type": "iceberg",
                        "instruction": {
                            "vt_symbol": "IO2401-C-4000.CFFEX",
                            "direction": "long",
                            "offset": "open",
                            "volume": 100,
                            "price": 100.0,
                            "signal": "test_signal",
                            "order_type": "limit"
                        },
                        "batch_size": 10,
                        "time_window_seconds": 0,
                        "num_slices": 0,
                        "volume_profile": [],
                        "interval_seconds": 60,
                        "per_order_volume": 0,
                        "volume_randomize_ratio": 0.0,
                        "price_offset_ticks": 0,
                        "price_tick": 0.0
                    },
                    "status": "executing",
                    "filled_volume": 0,
                    "child_orders": [],
                    "created_time": "2024-01-15T10:30:00",
                    "slice_schedule": []
                }
            }
        }
        
        scheduler = AdvancedOrderSchedulerSerializer.from_dict(data)
        
        assert len(scheduler._orders) == 1
        assert "order_001" in scheduler._orders
        order = scheduler._orders["order_001"]
        assert order.order_id == "order_001"
        assert order.request.order_type == AdvancedOrderType.ICEBERG
        assert order.status == AdvancedOrderStatus.EXECUTING
    
    def test_serialize_scheduler_with_child_orders(self):
        """测试包含子单的序列化"""
        config = AdvancedSchedulerConfig()
        scheduler = AdvancedOrderScheduler(config)
        
        instruction = OrderInstruction(
            vt_symbol="IO2401-C-4000.CFFEX",
            direction=Direction.LONG,
            offset=Offset.OPEN,
            volume=100,
            price=100.0,
            signal="test_signal",
            order_type=OrderType.LIMIT
        )
        
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.TWAP,
            instruction=instruction,
            time_window_seconds=300,
            num_slices=5
        )
        
        child1 = ChildOrder(
            child_id="child_001",
            parent_id="order_001",
            volume=20,
            scheduled_time=datetime(2024, 1, 15, 10, 30, 0),
            is_submitted=True,
            is_filled=False,
            price_offset=0.5
        )
        
        order = AdvancedOrder(
            order_id="order_001",
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            filled_volume=0,
            child_orders=[child1],
            created_time=datetime(2024, 1, 15, 10, 30, 0)
        )
        
        scheduler._orders["order_001"] = order
        
        data = AdvancedOrderSchedulerSerializer.to_dict(scheduler)
        
        order_data = data["orders"]["order_001"]
        assert len(order_data["child_orders"]) == 1
        child_data = order_data["child_orders"][0]
        assert child_data["child_id"] == "child_001"
        assert child_data["volume"] == 20
        assert child_data["is_submitted"] is True
        assert child_data["price_offset"] == 0.5
    
    def test_roundtrip_serialization(self):
        """测试往返序列化"""
        config = AdvancedSchedulerConfig(
            default_batch_size=20,
            default_interval_seconds=120,
            default_num_slices=10,
            default_volume_randomize_ratio=0.2,
            default_price_offset_ticks=2,
            default_price_tick=0.05
        )
        scheduler = AdvancedOrderScheduler(config)
        
        # 创建多个订单
        for i in range(3):
            instruction = OrderInstruction(
                vt_symbol=f"IO2401-C-{4000 + i * 100}.CFFEX",
                direction=Direction.LONG if i % 2 == 0 else Direction.SHORT,
                offset=Offset.OPEN,
                volume=100 + i * 10,
                price=100.0 + i * 10,
                signal=f"signal_{i}",
                order_type=OrderType.LIMIT
            )
            
            request = AdvancedOrderRequest(
                order_type=AdvancedOrderType.ICEBERG,
                instruction=instruction,
                batch_size=10 + i,
                interval_seconds=60 + i * 10
            )
            
            order = AdvancedOrder(
                order_id=f"order_{i:03d}",
                request=request,
                status=AdvancedOrderStatus.EXECUTING,
                filled_volume=i * 5,
                created_time=datetime(2024, 1, 15, 10, 30, i)
            )
            
            scheduler._orders[f"order_{i:03d}"] = order
        
        # 序列化
        data = AdvancedOrderSchedulerSerializer.to_dict(scheduler)
        
        # 反序列化
        restored = AdvancedOrderSchedulerSerializer.from_dict(data)
        
        # 验证配置
        assert restored.config.default_batch_size == scheduler.config.default_batch_size
        assert restored.config.default_interval_seconds == scheduler.config.default_interval_seconds
        assert restored.config.default_num_slices == scheduler.config.default_num_slices
        assert restored.config.default_volume_randomize_ratio == scheduler.config.default_volume_randomize_ratio
        assert restored.config.default_price_offset_ticks == scheduler.config.default_price_offset_ticks
        assert restored.config.default_price_tick == scheduler.config.default_price_tick
        
        # 验证订单
        assert len(restored._orders) == len(scheduler._orders)
        for oid in scheduler._orders:
            assert oid in restored._orders
            orig_order = scheduler._orders[oid]
            rest_order = restored._orders[oid]
            assert rest_order.order_id == orig_order.order_id
            assert rest_order.status == orig_order.status
            assert rest_order.filled_volume == orig_order.filled_volume
    
    def test_deserialize_with_missing_config_fields(self):
        """测试缺失配置字段的默认值处理"""
        data = {
            "config": {
                "default_batch_size": 15
                # 其他字段缺失
            },
            "orders": {}
        }
        
        scheduler = AdvancedOrderSchedulerSerializer.from_dict(data)
        
        # 验证提供的字段
        assert scheduler.config.default_batch_size == 15
        
        # 验证缺失字段使用默认值
        defaults = AdvancedSchedulerConfig()
        assert scheduler.config.default_interval_seconds == defaults.default_interval_seconds
        assert scheduler.config.default_num_slices == defaults.default_num_slices
        assert scheduler.config.default_volume_randomize_ratio == defaults.default_volume_randomize_ratio
        assert scheduler.config.default_price_offset_ticks == defaults.default_price_offset_ticks
        assert scheduler.config.default_price_tick == defaults.default_price_tick
    
    def test_deserialize_with_empty_config(self):
        """测试空配置使用默认值"""
        data = {
            "config": {},
            "orders": {}
        }
        
        scheduler = AdvancedOrderSchedulerSerializer.from_dict(data)
        
        # 所有字段应使用默认值
        defaults = AdvancedSchedulerConfig()
        assert scheduler.config.default_batch_size == defaults.default_batch_size
        assert scheduler.config.default_interval_seconds == defaults.default_interval_seconds
        assert scheduler.config.default_num_slices == defaults.default_num_slices
        assert scheduler.config.default_volume_randomize_ratio == defaults.default_volume_randomize_ratio
        assert scheduler.config.default_price_offset_ticks == defaults.default_price_offset_ticks
        assert scheduler.config.default_price_tick == defaults.default_price_tick
    
    def test_serialize_none_scheduler_raises_error(self):
        """测试序列化 None 抛出错误"""
        with pytest.raises(ValueError, match="scheduler cannot be None"):
            AdvancedOrderSchedulerSerializer.to_dict(None)
    
    def test_deserialize_none_data_raises_error(self):
        """测试反序列化 None 抛出错误"""
        with pytest.raises(ValueError, match="data cannot be None"):
            AdvancedOrderSchedulerSerializer.from_dict(None)
    
    def test_deserialize_missing_orders_key(self):
        """测试缺失 orders 键"""
        data = {
            "config": {
                "default_batch_size": 10
            }
            # orders 键缺失
        }
        
        scheduler = AdvancedOrderSchedulerSerializer.from_dict(data)
        
        # 应该创建空的订单字典
        assert len(scheduler._orders) == 0
    
    def test_serialize_scheduler_with_slice_schedule(self):
        """测试包含时间片调度的序列化"""
        config = AdvancedSchedulerConfig()
        scheduler = AdvancedOrderScheduler(config)
        
        instruction = OrderInstruction(
            vt_symbol="IO2401-C-4000.CFFEX",
            direction=Direction.LONG,
            offset=Offset.OPEN,
            volume=100,
            price=100.0,
            signal="test_signal",
            order_type=OrderType.LIMIT
        )
        
        request = AdvancedOrderRequest(
            order_type=AdvancedOrderType.TWAP,
            instruction=instruction,
            time_window_seconds=300,
            num_slices=5
        )
        
        slice1 = SliceEntry(
            scheduled_time=datetime(2024, 1, 15, 10, 30, 0),
            volume=20
        )
        slice2 = SliceEntry(
            scheduled_time=datetime(2024, 1, 15, 10, 31, 0),
            volume=20
        )
        
        order = AdvancedOrder(
            order_id="order_001",
            request=request,
            status=AdvancedOrderStatus.EXECUTING,
            filled_volume=0,
            slice_schedule=[slice1, slice2],
            created_time=datetime(2024, 1, 15, 10, 30, 0)
        )
        
        scheduler._orders["order_001"] = order
        
        data = AdvancedOrderSchedulerSerializer.to_dict(scheduler)
        
        order_data = data["orders"]["order_001"]
        assert len(order_data["slice_schedule"]) == 2
        assert order_data["slice_schedule"][0]["volume"] == 20
        assert order_data["slice_schedule"][1]["volume"] == 20
        
        # 反序列化并验证
        restored = AdvancedOrderSchedulerSerializer.from_dict(data)
        restored_order = restored._orders["order_001"]
        assert len(restored_order.slice_schedule) == 2
        assert restored_order.slice_schedule[0].volume == 20
