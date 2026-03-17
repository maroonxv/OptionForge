"""策略入口的生命周期编排工作流。"""

from __future__ import annotations

from pathlib import Path
import os
from typing import TYPE_CHECKING

from vnpy.trader.constant import Interval
from vnpy_portfoliostrategy import StrategyTemplate

from ..domain.aggregate.combination_aggregate import CombinationAggregate
from ..domain.aggregate.position_aggregate import PositionAggregate
from ..domain.aggregate.target_instrument_aggregate import InstrumentManager
from ..domain.event.event_types import EVENT_STRATEGY_ALERT
from ..domain.value_object.order_execution import OrderExecutionConfig
from ..domain.value_object.risk import RiskThresholds
from ..infrastructure.bar_pipeline import BarPipeline
from ..infrastructure.gateway.vnpy_account_gateway import VnpyAccountGateway
from ..infrastructure.gateway.vnpy_market_data_gateway import VnpyMarketDataGateway
from ..infrastructure.gateway.vnpy_order_gateway import VnpyOrderGateway
from ..infrastructure.gateway.vnpy_trade_execution_gateway import VnpyTradeExecutionGateway
from ..infrastructure.persistence.auto_save_service import AutoSaveService
from ..infrastructure.persistence.exceptions import CorruptionError
from ..infrastructure.persistence.json_serializer import JsonSerializer
from ..infrastructure.persistence.state_repository import ArchiveNotFound, StateRepository
from ..infrastructure.reporting.feishu_handler import FeishuEventHandler
from ..runtime import StrategyRuntimeBuilder
from src.main.bootstrap.database_factory import DatabaseFactory

if TYPE_CHECKING:
    from src.strategy.strategy_entry import StrategyEntry


def build_runtime(entry: "StrategyEntry", full_config: dict[str, object]):
    return StrategyRuntimeBuilder().build(entry, full_config)


class LifecycleWorkflow:
    """协调策略入口生命周期回调。"""

    def __init__(self, entry: "StrategyEntry") -> None:
        self.entry = entry

    def on_init(self) -> None:
        """完成依赖初始化、预热与告警注册。"""
        self.entry.logger.info("策略初始化...")

        # ______________________________  1. 加载交易品种配置  ______________________________

        from src.main.config.config_loader import ConfigLoader
        self.entry.target_products = ConfigLoader.load_target_products()
        if not self.entry.target_products:
            self.entry.logger.error("未配置任何交易品种，请先检查并配置 trading_target.toml")
            raise RuntimeError("策略初始化失败：未配置交易品种")
        self.entry.logger.info(f"已加载配置的标的: {len(self.entry.target_products)} 个品种")

        # ______________________________  2. 创建领域服务  ______________________________

        project_root = Path(__file__).resolve().parents[3]

        full_config = dict(self.entry.setting.get("strategy_full_config") or {})
        if not full_config:
            try:
                strategy_config_path = str(project_root / "config" / "strategy_config.toml")
                full_config = ConfigLoader.load_toml(strategy_config_path)
            except Exception:
                full_config = {}

        self.entry.strategy_contracts = dict(full_config.get("strategy_contracts") or {})
        self.entry.service_activation = ConfigLoader.resolve_service_activation(full_config)
        self.entry.observability_config = dict(full_config.get("observability") or {})
        self.entry.decision_journal_limit = max(
            10,
            int(self.entry.observability_config.get("decision_journal_maxlen", 200) or 200),
        )

        try:
            subscription_config_path = project_root / "config" / "subscription" / "subscription.toml"
            if subscription_config_path.exists():
                self.entry.subscription_config = ConfigLoader.load_toml(str(subscription_config_path))
            else:
                self.entry.subscription_config = {"enabled": False}
        except Exception as e:
            self.entry.logger.warning(f"加载订阅配置失败，将禁用订阅模式引擎: {e}")
            self.entry.subscription_config = {"enabled": False}
        self.entry._init_subscription_management()

        indicator_service_path = self.entry.strategy_contracts.get(
            "indicator_service",
            "src.strategy.domain.domain_service.signal.indicator_service:IndicatorService",
        )
        signal_service_path = self.entry.strategy_contracts.get(
            "signal_service",
            "src.strategy.domain.domain_service.signal.signal_service:SignalService",
        )
        indicator_kwargs = dict(self.entry.strategy_contracts.get("indicator_kwargs") or {})
        signal_kwargs = dict(self.entry.strategy_contracts.get("signal_kwargs") or {})

        indicator_cls = ConfigLoader.import_from_string(indicator_service_path)
        signal_cls = ConfigLoader.import_from_string(signal_service_path)
        self.entry.indicator_service = indicator_cls(**indicator_kwargs)
        self.entry.signal_service = signal_cls(**signal_kwargs)

        # ── 从 TOML 配置与 YAML 覆盖加载领域服务配置 ──
        from src.main.config.domain_service_config_loader import (
            load_position_sizing_config,
            load_pricing_engine_config,
            load_future_selector_config,
            load_option_selector_config,
        )

        position_sizing_cls = ConfigLoader.import_from_string(
            "src.strategy.domain.domain_service.risk.position_sizing_service:PositionSizingService"
        )
        future_selection_cls = ConfigLoader.import_from_string(
            "src.strategy.domain.domain_service.selection.future_selection_service:FutureSelectionService"
        )
        option_selector_cls = ConfigLoader.import_from_string(
            "src.strategy.domain.domain_service.selection.option_selector_service:OptionSelectorService"
        )
        pricing_engine_cls = ConfigLoader.import_from_string(
            "src.strategy.domain.domain_service.pricing.pricing_engine:PricingEngine"
        )
        greeks_calculator_cls = ConfigLoader.import_from_string(
            "src.strategy.domain.domain_service.pricing:GreeksCalculator"
        )
        portfolio_risk_cls = ConfigLoader.import_from_string(
            "src.strategy.domain.domain_service.risk.portfolio_risk_aggregator:PortfolioRiskAggregator"
        )
        smart_order_executor_cls = ConfigLoader.import_from_string(
            "src.strategy.domain.domain_service.execution.smart_order_executor:SmartOrderExecutor"
        )

        ps_cfg = full_config.get("position_sizing", {})
        ps_overrides = {**ps_cfg, "max_positions": self.entry.max_positions}
        self.entry.position_sizing_service = None
        if self.entry.service_activation.get("position_sizing"):
            self.entry.position_sizing_service = position_sizing_cls(
                config=load_position_sizing_config(overrides=ps_overrides)
            )

        self.entry.future_selection_service = None
        if self.entry.service_activation.get("future_selection", True):
            self.entry.future_selection_service = future_selection_cls(
                config=load_future_selector_config()
            )

        self.entry.option_selector_service = None
        if self.entry.service_activation.get("option_selector", True):
            self.entry.option_selector_service = option_selector_cls(
                config=load_option_selector_config(
                    overrides={"strike_level": self.entry.strike_level}
                )
            )

        self.entry.pricing_engine = None
        if self.entry.service_activation.get("pricing_engine"):
            self.entry.pricing_engine = pricing_engine_cls(
                config=load_pricing_engine_config(
                    overrides=full_config.get("pricing_engine", {})
                )
            )

        # ── 希腊值风控与订单执行增强 ──

        greeks_risk_cfg = full_config.get("greeks_risk", {})
        position_limits = greeks_risk_cfg.get("position_limits", {})
        portfolio_limits = greeks_risk_cfg.get("portfolio_limits", {})

        risk_thresholds = RiskThresholds(
            position_delta_limit=position_limits.get("delta", 0.8),
            position_gamma_limit=position_limits.get("gamma", 0.1),
            position_vega_limit=position_limits.get("vega", 50.0),
            portfolio_delta_limit=portfolio_limits.get("delta", 5.0),
            portfolio_gamma_limit=portfolio_limits.get("gamma", 1.0),
            portfolio_vega_limit=portfolio_limits.get("vega", 500.0),
        )
        self.entry.risk_thresholds = risk_thresholds
        self.entry.risk_free_rate = float(greeks_risk_cfg.get("risk_free_rate", 0.02) or 0.02)

        order_exec_cfg = full_config.get("order_execution", {})
        order_config = OrderExecutionConfig(
            timeout_seconds=order_exec_cfg.get("timeout_seconds", 30),
            max_retries=order_exec_cfg.get("max_retries", 3),
            slippage_ticks=order_exec_cfg.get("slippage_ticks", 2),
        )

        self.entry.greeks_calculator = greeks_calculator_cls() if self.entry.service_activation.get("greeks_calculator") else None
        self.entry.portfolio_risk_aggregator = (
            portfolio_risk_cls(risk_thresholds)
            if self.entry.service_activation.get("portfolio_risk")
            else None
        )
        self.entry.smart_order_executor = (
            smart_order_executor_cls(order_config)
            if self.entry.service_activation.get("smart_order_executor")
            else None
        )
        if self.entry.greeks_calculator or self.entry.portfolio_risk_aggregator:
            self.entry.logger.info(
                f"Greeks 风控能力已装配: position_limits={position_limits}, portfolio_limits={portfolio_limits}"
            )
        if self.entry.smart_order_executor:
            self.entry.logger.info(
                f"订单执行增强已装配: timeout={order_config.timeout_seconds}s, max_retries={order_config.max_retries}"
            )

        # ______________________________  3. 创建领域聚合根  ______________________________

        self.entry.target_aggregate = InstrumentManager()
        self.entry.position_aggregate = PositionAggregate()
        self.entry.combination_aggregate = CombinationAggregate()

        # ______________________________  4. 创建基础设施组件  ______________________________

        self.entry.market_gateway = VnpyMarketDataGateway(self.entry)
        self.entry.account_gateway = VnpyAccountGateway(self.entry)
        self.entry.order_gateway = VnpyOrderGateway(self.entry)
        self.entry.exec_gateway = VnpyTradeExecutionGateway(self.entry)

        variant_name = self.entry.strategy_name

        monitor_db_config = {
            "host": os.getenv("VNPY_DATABASE_HOST", "") or "",
            "port": int(os.getenv("VNPY_DATABASE_PORT", "5432") or 5432),
            "user": os.getenv("VNPY_DATABASE_USER", "") or "",
            "password": os.getenv("VNPY_DATABASE_PASSWORD", "") or "",
            "database": os.getenv("VNPY_DATABASE_DATABASE", "") or "",
        }
        self.entry.monitor = None
        if self.entry.service_activation.get("monitoring", True):
            monitor_cls = ConfigLoader.import_from_string(
                "src.strategy.infrastructure.monitoring.strategy_monitor:StrategyMonitor"
            )
            self.entry.monitor = monitor_cls(
                variant_name=variant_name,
                monitor_instance_id=os.getenv("MONITOR_INSTANCE_ID", "default") or "default",
                monitor_db_config=monitor_db_config,
                logger=self.entry.logger
            )

        # 创建 `JsonSerializer` 实例，供 `StateRepository` 与 `AutoSaveService` 共享
        self.entry.json_serializer = JsonSerializer()

        self.entry.state_repository = StateRepository(
            serializer=self.entry.json_serializer,
            database_factory=DatabaseFactory.get_instance(),
            logger=self.entry.logger,
        )

        # `AutoSaveService` 仅在非回测模式下创建
        if not self.entry.backtesting:
            self.entry.auto_save_service = AutoSaveService(
                state_repository=self.entry.state_repository,
                strategy_name=self.entry.strategy_name,
                serializer=self.entry.json_serializer,
                interval_seconds=60.0,
                cleanup_interval_hours=24.0,
                keep_days=7,
                logger=self.entry.logger,
            )

        # 初始快照
        self.entry.runtime = build_runtime(self.entry, full_config)
        for hook in self.entry.runtime.lifecycle.init_hooks:
            hook()

        self.entry._record_snapshot()

        # ______________________________  5. 初始化K线合成管道  ______________________________

        bar_window = int(self.entry.setting.get("bar_window", 0))
        if bar_window > 0:
            bar_interval_str = self.entry.setting.get("bar_interval", "MINUTE")
            interval_map = {
                "MINUTE": Interval.MINUTE,
                "HOUR": Interval.HOUR,
                "DAILY": Interval.DAILY,
            }
            interval = interval_map.get(bar_interval_str, Interval.MINUTE)
            self.entry.bar_pipeline = BarPipeline(
                bar_callback=self.entry._process_bars,
                window=bar_window,
                interval=interval,
            )
            self.entry.logger.info(f"K线合成管道已启用: {bar_window}{bar_interval_str}")
        else:
            self.entry.logger.info("未配置K线合成，使用直通模式")

        # ______________________________  6. 预热  ______________________________

        original_trading = getattr(self.entry, "trading", True)

        if self.entry.backtesting:
            self.entry.logger.info("当前处于回测模式，跳过状态恢复，直接加载历史数据进行初始化")
            self.entry.warming_up = True
            setattr(self.entry, "trading", False)
            try:
                self.entry.load_bars(self.entry.warmup_days)
            except Exception:
                self.entry.logger.error("回测 warmup 失败", exc_info=True)
                raise
            finally:
                setattr(self.entry, "trading", original_trading)
                self.entry.warming_up = False
        else:
            # 实盘预热: 加载状态 + 标的补漏 + Postgres 回放
            try:
                result = self.entry.state_repository.load(self.entry.strategy_name)
                if isinstance(result, ArchiveNotFound):
                    self.entry.logger.info(f"首次启动，无历史状态: {self.entry.strategy_name}")
                else:
                    # 从快照恢复聚合根
                    if "target_aggregate" in result:
                        self.entry.target_aggregate = InstrumentManager.from_snapshot(result["target_aggregate"])
                    if "position_aggregate" in result:
                        self.entry.position_aggregate = PositionAggregate.from_snapshot(result["position_aggregate"])
                    if "combination_aggregate" in result:
                        self.entry.combination_aggregate = CombinationAggregate.from_snapshot(result["combination_aggregate"])
                    if "current_dt" in result:
                        self.entry.current_dt = result["current_dt"]
                    self.entry.logger.info(f"策略状态已恢复: {self.entry.strategy_name}")
            except CorruptionError as e:
                self.entry.logger.error(f"策略状态损坏，拒绝启动: {e}")
                raise
            except Exception:
                self.entry.logger.error(f"加载策略状态失败: {self.entry.strategy_name}", exc_info=True)
                raise

            self._sync_live_oms_snapshot()

            try:
                self.entry._validate_universe()
            except Exception:
                self.entry.logger.error("实盘补漏/主力合约初始化失败", exc_info=True)
                raise

            active_contracts = list(self.entry.target_aggregate.get_all_active_contracts() or [])
            if isinstance(getattr(self.entry, "vt_symbols", None), list):
                for vt_symbol in active_contracts:
                    if vt_symbol and vt_symbol not in self.entry.vt_symbols:
                        self.entry.vt_symbols.append(vt_symbol)

            self.entry.warming_up = True
            setattr(self.entry, "trading", False)
            try:
                vt_symbols = list(self.entry.target_aggregate.get_all_active_contracts() or [])
                if not vt_symbols and isinstance(getattr(self.entry, "vt_symbols", None), list):
                    vt_symbols = list(self.entry.vt_symbols)

                ok = self.entry.history_repo.replay_bars_from_database(
                    vt_symbols=vt_symbols,
                    days=self.entry.warmup_days,
                    on_bars_callback=self.entry.on_bars,  # on_bars 内部根据 bar_pipeline 分支
                )
                if not ok:
                    self.entry.logger.error("实盘 warmup 失败: Postgres 中未能回放到有效 K 线")
                    raise RuntimeError("实盘 warmup 失败")
            except Exception:
                self.entry.logger.error("实盘 warmup 执行失败（可能是 BarPipeline 处理异常）", exc_info=True)
                raise
            finally:
                setattr(self.entry, "trading", original_trading)
                self.entry.warming_up = False

        # ______________________________  7. 注册飞书告警  ______________________________

        if self.entry.feishu_webhook:
            self.entry.feishu_handler = FeishuEventHandler(
                webhook_url=self.entry.feishu_webhook,
                strategy_name=self.entry.strategy_name
            )
            if hasattr(self.entry, "strategy_engine") and hasattr(self.entry.strategy_engine, "event_engine"):
                self.entry.strategy_engine.event_engine.register(
                    EVENT_STRATEGY_ALERT,
                    self.entry.feishu_handler.handle_alert_event
                )
                self.entry.logger.info("飞书通知已启用")

        self.entry.logger.info("策略初始化完成")

    def _sync_live_oms_snapshot(self) -> None:
        """在启用交易前将券商侧 OMS 状态灌回聚合根。"""
        positions = list(self.entry.account_gateway.get_all_positions() or [])
        active_orders = list(self.entry.order_gateway.get_all_active_orders() or [])
        trades = list(self.entry.order_gateway.get_all_trades() or [])

        if not positions and not active_orders and not trades:
            self.entry.logger.warning("实盘 OMS 回补为空，继续沿用持久化快照")
            return

        for position in positions:
            self.entry.event_bridge.on_position(position)
        for order in active_orders:
            self.entry.event_bridge.on_order(order)
        for trade in trades:
            self.entry.event_bridge.on_trade(trade)

        self.entry.logger.info(
            "实盘 OMS 回补完成: positions=%s active_orders=%s trades=%s",
            len(positions),
            len(active_orders),
            len(trades),
        )

    def on_start(self) -> None:
        """执行启动钩子并初始化订阅状态。"""
        try:
            StrategyTemplate.on_start(self.entry)
        except Exception:
            pass
        self.entry.logger.info("策略启动")
        self.entry._validate_universe()
        self.entry._reconcile_subscriptions("on_init")

    def on_stop(self) -> None:
        """执行停止钩子、落盘状态并清理处理器。"""
        try:
            StrategyTemplate.on_stop(self.entry)
        except Exception:
            pass
        self.entry.logger.info("策略停止")

        # 保存状态并关闭线程池 - 仅在非回测模式下
        if self.entry.auto_save_service:
            self.entry.auto_save_service.force_save(self.entry._create_snapshot)
            self.entry.auto_save_service.shutdown()

        # 注销飞书处理器
        if self.entry.feishu_handler:
            if hasattr(self.entry, "strategy_engine") and hasattr(self.entry.strategy_engine, "event_engine"):
                try:
                    self.entry.strategy_engine.event_engine.unregister(
                        EVENT_STRATEGY_ALERT,
                        self.entry.feishu_handler.handle_alert_event
                    )
                except Exception:
                    pass
