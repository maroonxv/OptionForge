"""
StrategyEntry - 商品波动率策略入口 (Pragmatic DDD)

VnPy 策略模板实现，同时充当应用层。
on_* 回调直接编排领域逻辑，不再经过独立的 Application Service。
"""

from __future__ import annotations

from datetime import datetime
import os
from typing import Any, Dict, List, Optional, Set

from vnpy.event.engine import Event
from vnpy.trader.object import BarData, OrderData, PositionData, TickData, TradeData
from vnpy_portfoliostrategy import StrategyEngine, StrategyTemplate

from src.strategy.infrastructure.bar_pipeline import BarPipeline

from .application import (
    EventBridge,
    LifecycleWorkflow,
    MarketWorkflow,
    StateWorkflow,
    SubscriptionWorkflow,
)
from .domain.aggregate.combination_aggregate import CombinationAggregate
from .domain.aggregate.position_aggregate import PositionAggregate
from .domain.aggregate.target_instrument_aggregate import InstrumentManager
from .domain.domain_service.execution.smart_order_executor import SmartOrderExecutor
from .domain.domain_service.pricing import GreeksCalculator
from .domain.domain_service.pricing.pricing_engine import PricingEngine
from .domain.domain_service.risk.portfolio_risk_aggregator import PortfolioRiskAggregator
from .domain.domain_service.risk.position_sizing_service import PositionSizingService
from .domain.domain_service.selection.future_selection_service import FutureSelectionService
from .domain.domain_service.selection.option_selector_service import OptionSelectorService
from .domain.domain_service.signal.indicator_service import IndicatorService
from .domain.domain_service.signal.signal_service import SignalService
from .domain.event.event_types import PositionClosedEvent
from .domain.value_object.risk import RiskThresholds
from .domain.value_object.selection.selection import MarketData as SelectionMarketData
from .domain.value_object.signal.strategy_contract import DecisionTrace
from .infrastructure.gateway.vnpy_account_gateway import VnpyAccountGateway
from .infrastructure.gateway.vnpy_market_data_gateway import VnpyMarketDataGateway
from .infrastructure.gateway.vnpy_order_gateway import VnpyOrderGateway
from .infrastructure.gateway.vnpy_trade_execution_gateway import VnpyTradeExecutionGateway
from .infrastructure.logging.logging_utils import setup_strategy_logger
from .infrastructure.monitoring.strategy_monitor import StrategyMonitor
from .infrastructure.persistence.auto_save_service import AutoSaveService
from .infrastructure.persistence.history_data_repository import HistoryDataRepository
from .infrastructure.persistence.json_serializer import JsonSerializer
from .infrastructure.persistence.state_repository import StateRepository
from .infrastructure.reporting.feishu_handler import FeishuEventHandler
from .infrastructure.subscription.subscription_mode_engine import SubscriptionModeEngine


class StrategyEntry(StrategyTemplate):
    """
    商品波动率策略 (Pragmatic DDD)

    职责:
    1. VnPy 回调入口 (on_* 方法)
    2. 编排领域逻辑
    3. 组装依赖
    """

    author = "Hongxu Lai"

    # 标的合约列表 (期货)
    underlying_symbols: list = []

    # 飞书通知
    feishu_webhook: str = ""

    # 仓位管理
    max_positions: int = 5
    position_ratio: float = 0.1

    # 期权选择
    strike_level: int = 3

    parameters = [
        "feishu_webhook",
        "max_positions",
        "position_ratio",
        "strike_level",
    ]

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        strategy_name: str,
        vt_symbols: list,
        setting: dict,
    ) -> None:
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        # ── 日志 ──
        log_dir_setting = str(setting.get("log_dir", "") or "")
        log_filename = "strategy"
        if log_dir_setting:
            normalized_log_dir = log_dir_setting.replace("\\", "/")
            marker = "logs/runner"
            relative_log_dir = ""
            marker_index = normalized_log_dir.lower().find(marker)
            if marker_index != -1:
                relative_log_dir = normalized_log_dir[marker_index + len(marker) :].strip("/")
            if relative_log_dir:
                log_filename = os.path.join(*relative_log_dir.split("/"), "strategy")
        self.logger = setup_strategy_logger(self.strategy_name, log_filename)

        # ── 基础设施: 历史数据仓库 ──
        self.history_repo = HistoryDataRepository(self.logger)

        # ── 运行模式标志 ──
        self.paper_trading = setting.get("paper_trading", False)
        self.backtesting = setting.get("backtesting", False)
        self.warmup_days: int = int(setting.get("warmup_days", 5 if self.backtesting else 30))

        # ── 领域聚合根 (在 on_init 中初始化) ──
        self.target_aggregate: Optional[InstrumentManager] = None
        self.position_aggregate: Optional[PositionAggregate] = None
        self.combination_aggregate: Optional["CombinationAggregate"] = None

        # ── 领域服务 (在 on_init 中初始化) ──
        self.indicator_service: Optional[IndicatorService] = None
        self.signal_service: Optional[SignalService] = None
        self.position_sizing_service: Optional[PositionSizingService] = None
        self.future_selection_service: Optional[FutureSelectionService] = None
        self.option_selector_service: Optional[OptionSelectorService] = None
        self.greeks_calculator: Optional[GreeksCalculator] = None
        self.pricing_engine: Optional[PricingEngine] = None
        self.portfolio_risk_aggregator: Optional[PortfolioRiskAggregator] = None
        self.smart_order_executor: Optional[SmartOrderExecutor] = None
        self.risk_thresholds: RiskThresholds = RiskThresholds()
        self.risk_free_rate: float = 0.02
        self.strategy_contracts: Dict[str, Any] = {}
        self.service_activation: Dict[str, bool] = {}
        self.observability_config: Dict[str, Any] = {}
        self.decision_journal: List[Dict[str, Any]] = []
        self.decision_journal_limit: int = 200

        # ── 基础设施网关 (在 on_init 中初始化) ──
        self.market_gateway: Optional[VnpyMarketDataGateway] = None
        self.account_gateway: Optional[VnpyAccountGateway] = None
        self.order_gateway: Optional[VnpyOrderGateway] = None
        self.exec_gateway: Optional[VnpyTradeExecutionGateway] = None

        # ── 基础设施: 监控与持久化 (在 on_init 中初始化) ──
        self.monitor: Optional[StrategyMonitor] = None
        self.state_repository: Optional[StateRepository] = None
        self.auto_save_service: Optional[AutoSaveService] = None
        self.json_serializer: Optional[JsonSerializer] = None

        # ── 飞书 ──
        self.feishu_handler: Optional[FeishuEventHandler] = None

        # ── K线合成管道 ──
        self.bar_pipeline: Optional[BarPipeline] = None

        # ── 配置上下文 ──
        self.target_products: List[str] = []
        self.base_configured_vt_symbols: Set[str] = set(vt_symbols or [])

        # ── 订阅模式配置 ──
        self.subscription_config: Dict[str, Any] = {}
        self.subscription_engine: Optional[SubscriptionModeEngine] = None
        self.subscription_enabled: bool = False
        self.subscription_trigger_events: Set[str] = set()
        self.subscription_refresh_sec: int = 15
        self.subscribed_symbols: Set[str] = set(vt_symbols or [])
        self._stale_unsubscribe_since: Dict[str, float] = {}
        self._signal_temp_symbols: Dict[str, float] = {}
        self._last_subscription_refresh_ts: float = 0.0

        # ── 运行时状态 ──
        self.rollover_check_done: bool = False
        self.universe_check_interval: int = 0
        self.universe_check_threshold: int = 60
        self.last_bars: Dict[str, BarData] = {}
        self.warming_up: bool = False
        self.current_dt: datetime = datetime.now()
        self.last_decision_trace: Optional[DecisionTrace] = None

        # ── 应用层切片 ──
        self.lifecycle_workflow = LifecycleWorkflow(self)
        self.market_workflow = MarketWorkflow(self)
        self.subscription_workflow = SubscriptionWorkflow(self)
        self.state_workflow = StateWorkflow(self)
        self.event_bridge = EventBridge(self)

    # ═══════════════════════════════════════════════════════════════════
    #  VnPy 生命周期回调
    # ═══════════════════════════════════════════════════════════════════

    def on_init(self) -> None:
        self.lifecycle_workflow.on_init()

    def on_start(self) -> None:
        self.lifecycle_workflow.on_start()

    def on_stop(self) -> None:
        self.lifecycle_workflow.on_stop()

    # ═══════════════════════════════════════════════════════════════════
    #  VnPy 数据回调
    # ═══════════════════════════════════════════════════════════════════

    def on_tick(self, tick: TickData) -> None:
        self.market_workflow.on_tick(tick)

    def on_bars(self, bars: Dict[str, BarData]) -> None:
        self.market_workflow.on_bars(bars)

    def on_order(self, order: OrderData) -> None:
        self.event_bridge.on_order(order)

    def on_trade(self, trade: TradeData) -> None:
        self.event_bridge.on_trade(trade)

    def process_position_event(self, event: Event) -> None:
        self.event_bridge.process_position_event(event)

    def on_position(self, position: PositionData) -> None:
        self.event_bridge.on_position(position)

    # ═══════════════════════════════════════════════════════════════════
    #  核心编排逻辑委托
    # ═══════════════════════════════════════════════════════════════════

    def _process_bars(self, bars: Dict[str, BarData]) -> None:
        self.market_workflow.process_bars(bars)

    def _validate_universe(self) -> None:
        self.market_workflow.validate_universe()

    def _build_future_market_data(self, contracts: List[Any]) -> Dict[str, SelectionMarketData]:
        return self.market_workflow.build_future_market_data(contracts)

    # ═══════════════════════════════════════════════════════════════════
    #  订阅管理委托
    # ═══════════════════════════════════════════════════════════════════

    def _init_subscription_management(self) -> None:
        self.subscription_workflow.init_subscription_management()

    def _should_trigger_subscription(self, trigger: str) -> bool:
        return self.subscription_workflow.should_trigger_subscription(trigger)

    def _register_signal_temporary_symbol(self, vt_symbol: str) -> None:
        self.subscription_workflow.register_signal_temporary_symbol(vt_symbol)

    def _collect_active_signal_symbols(self, now_ts: float) -> Set[str]:
        return self.subscription_workflow.collect_active_signal_symbols(now_ts)

    def _collect_position_symbols(self) -> Set[str]:
        return self.subscription_workflow.collect_position_symbols()

    def _collect_pending_order_symbols(self) -> Set[str]:
        return self.subscription_workflow.collect_pending_order_symbols()

    def _get_active_contract_map(self) -> Dict[str, str]:
        return self.subscription_workflow.get_active_contract_map()

    def _get_last_price(self, vt_symbol: str) -> float:
        return self.subscription_workflow.get_last_price(vt_symbol)

    def _subscribe_symbol(self, vt_symbol: str) -> bool:
        return self.subscription_workflow.subscribe_symbol(vt_symbol)

    def _unsubscribe_symbol(self, vt_symbol: str) -> bool:
        return self.subscription_workflow.unsubscribe_symbol(vt_symbol)

    def _reconcile_subscriptions(self, trigger: str) -> None:
        self.subscription_workflow.reconcile_subscriptions(trigger)

    # ═══════════════════════════════════════════════════════════════════
    #  状态持久化委托
    # ═══════════════════════════════════════════════════════════════════

    def _create_snapshot(self) -> Dict[str, Any]:
        return self.state_workflow.create_snapshot()

    def _record_snapshot(self) -> None:
        self.state_workflow.record_snapshot()

    # ═══════════════════════════════════════════════════════════════════
    #  事件桥接委托
    # ═══════════════════════════════════════════════════════════════════

    def _publish_domain_events(self) -> None:
        self.event_bridge.publish_domain_events()

    def _sync_combination_status_on_position_closed(
        self,
        domain_event: PositionClosedEvent,
        event_engine: Optional[Any],
    ) -> None:
        self.event_bridge.sync_combination_status_on_position_closed(domain_event, event_engine)
