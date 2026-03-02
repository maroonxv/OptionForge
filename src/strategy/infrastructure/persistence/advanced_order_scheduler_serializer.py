"""
AdvancedOrderScheduler 序列化器

负责 AdvancedOrderScheduler 的序列化和反序列化，将领域对象转换为可持久化格式。
"""
from typing import Dict, Any, Optional

from src.strategy.domain.domain_service.execution.advanced_order_scheduler import AdvancedOrderScheduler
from src.strategy.domain.value_object.trading.order_execution import AdvancedSchedulerConfig
from src.strategy.domain.value_object.trading.advanced_order import AdvancedOrder


class AdvancedOrderSchedulerSerializer:
    """
    AdvancedOrderScheduler 序列化器
    
    提供静态方法将 AdvancedOrderScheduler 实例序列化为字典格式，
    以及从字典反序列化恢复实例。
    
    Examples:
        >>> scheduler = AdvancedOrderScheduler(config)
        >>> data = AdvancedOrderSchedulerSerializer.to_dict(scheduler)
        >>> restored = AdvancedOrderSchedulerSerializer.from_dict(data)
    """
    
    @staticmethod
    def to_dict(scheduler: AdvancedOrderScheduler) -> Dict[str, Any]:
        """
        将 AdvancedOrderScheduler 序列化为字典
        
        Args:
            scheduler: AdvancedOrderScheduler 实例
            
        Returns:
            JSON 兼容的字典，包含配置和订单状态
            
        Raises:
            ValueError: 如果 scheduler 为 None
            
        Examples:
            >>> config = AdvancedSchedulerConfig(default_batch_size=10)
            >>> scheduler = AdvancedOrderScheduler(config)
            >>> data = AdvancedOrderSchedulerSerializer.to_dict(scheduler)
            >>> data['config']['default_batch_size']
            10
        """
        if scheduler is None:
            raise ValueError("scheduler cannot be None")
        
        return {
            "config": {
                "default_batch_size": scheduler.config.default_batch_size,
                "default_interval_seconds": scheduler.config.default_interval_seconds,
                "default_num_slices": scheduler.config.default_num_slices,
                "default_volume_randomize_ratio": scheduler.config.default_volume_randomize_ratio,
                "default_price_offset_ticks": scheduler.config.default_price_offset_ticks,
                "default_price_tick": scheduler.config.default_price_tick,
            },
            "orders": {
                oid: order.to_dict() for oid, order in scheduler._orders.items()
            },
        }
    
    @staticmethod
    def from_dict(
        data: Dict[str, Any],
        config: Optional[AdvancedSchedulerConfig] = None
    ) -> AdvancedOrderScheduler:
        """
        从字典反序列化 AdvancedOrderScheduler
        
        Args:
            data: 序列化的字典数据
            config: 可选的配置对象，如果为 None 则从 data 中读取
            
        Returns:
            AdvancedOrderScheduler 实例
            
        Raises:
            ValueError: 如果 data 为 None 或格式无效
            
        Examples:
            >>> data = {
            ...     "config": {"default_batch_size": 10, "default_interval_seconds": 60},
            ...     "orders": {}
            ... }
            >>> scheduler = AdvancedOrderSchedulerSerializer.from_dict(data)
            >>> scheduler.config.default_batch_size
            10
        """
        if data is None:
            raise ValueError("data cannot be None")
        
        # 如果没有提供配置对象，从数据中读取
        if config is None:
            cfg_data = data.get("config", {})
            # 使用默认值处理缺失字段
            defaults = AdvancedSchedulerConfig()
            config = AdvancedSchedulerConfig(
                default_batch_size=cfg_data.get("default_batch_size", defaults.default_batch_size),
                default_interval_seconds=cfg_data.get("default_interval_seconds", defaults.default_interval_seconds),
                default_num_slices=cfg_data.get("default_num_slices", defaults.default_num_slices),
                default_volume_randomize_ratio=cfg_data.get("default_volume_randomize_ratio", defaults.default_volume_randomize_ratio),
                default_price_offset_ticks=cfg_data.get("default_price_offset_ticks", defaults.default_price_offset_ticks),
                default_price_tick=cfg_data.get("default_price_tick", defaults.default_price_tick),
            )
        
        # 创建调度器实例
        scheduler = AdvancedOrderScheduler(config)
        
        # 恢复订单状态
        for oid, order_data in data.get("orders", {}).items():
            scheduler._orders[oid] = AdvancedOrder.from_dict(order_data)
        
        return scheduler
