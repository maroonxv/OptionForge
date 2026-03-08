"""策略入口的行情编排工作流。"""

from __future__ import annotations

from datetime import date
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from vnpy.trader.object import BarData, TickData

from ..domain.value_object.market.option_chain import OptionChainSnapshot
from ..domain.value_object.pricing.greeks import GreeksInput, GreeksResult
from ..domain.value_object.pricing.pricing import ExerciseStyle, PricingInput
from ..domain.value_object.risk import PortfolioGreeks
from ..domain.value_object.selection.selection import MarketData as SelectionMarketData
from ..domain.value_object.signal.strategy_contract import (
    DecisionTrace,
    IndicatorComputationResult,
    IndicatorContext,
    OptionSelectionPreference,
    SignalContext,
    SignalDecision,
)
from ..infrastructure.parsing.contract_helper import ContractHelper

if TYPE_CHECKING:
    from src.strategy.strategy_entry import StrategyEntry


class MarketWorkflow:
    """协调行情回调与 K 线处理流程。"""

    def __init__(self, entry: "StrategyEntry") -> None:
        self.entry = entry

    def on_tick(self, tick: TickData) -> None:
        """处理逐笔行情推送，启用管道时转发给 K 线管道。"""
        if self.entry.bar_pipeline:
            self.entry.bar_pipeline.handle_tick(tick)

    def on_bars(self, bars: Dict[str, BarData]) -> None:
        """处理 K 线回调，包含换月检查与主流程分发。"""
        self.entry.last_bars.update(bars)

        if self.entry.target_aggregate and not self.entry.warming_up:
            first_bar = next(iter(bars.values()))
            current_dt = first_bar.datetime
            rollover_changed = False

            if (
                current_dt.hour == 14
                and current_dt.minute == 50
                and self.entry.future_selection_service is not None
            ):
                if not self.entry.rollover_check_done:
                    self.entry.logger.info(f"触发每日换月检查: {current_dt}")
                    if self.entry.target_aggregate and self.entry.market_gateway:
                        for product in self.entry.target_products:
                            try:
                                current_vt = self.entry.target_aggregate.get_active_contract(product)
                                if not current_vt:
                                    continue

                                all_contracts = self.entry.market_gateway.get_all_contracts()
                                product_contracts = [
                                    c for c in all_contracts
                                    if ContractHelper.is_contract_of_product(c, product)
                                ]
                                if not product_contracts:
                                    continue

                                market_data = self.build_future_market_data(product_contracts)
                                dominant = self.entry.future_selection_service.select_dominant_contract(
                                    product_contracts,
                                    current_dt.date(),
                                    market_data=market_data,
                                    log_func=self.entry.logger.info,
                                )
                                if dominant and dominant.vt_symbol != current_vt:
                                    new_vt = dominant.vt_symbol
                                    self.entry.logger.info(f"品种 {product} 换月: {current_vt} -> {new_vt}")
                                    self.entry.target_aggregate.set_active_contract(product, new_vt)
                                    self.entry.target_aggregate.get_or_create_instrument(new_vt)
                                    self.entry._subscribe_symbol(new_vt)
                                    rollover_changed = True
                            except Exception as e:
                                self.entry.logger.error(f"品种 {product} 换月检查失败: {e}")
                    self.entry.rollover_check_done = True
            else:
                self.entry.rollover_check_done = False

            self.entry.universe_check_interval += 1
            if self.entry.universe_check_interval >= self.entry.universe_check_threshold:
                self.entry.universe_check_interval = 0
                self.entry._validate_universe()

            if rollover_changed:
                self.entry._reconcile_subscriptions("on_rollover")

        if self.entry.bar_pipeline:
            self.entry.bar_pipeline.handle_bars(bars)
        else:
            self.entry._process_bars(bars)

        if self.entry.auto_save_service and not self.entry.warming_up:
            self.entry.auto_save_service.maybe_save(self.entry._create_snapshot)

        if not self.entry.warming_up:
            now_ts = time.time()
            if now_ts - self.entry._last_subscription_refresh_ts >= self.entry.subscription_refresh_sec:
                self.entry._last_subscription_refresh_ts = now_ts
                self.entry._reconcile_subscriptions("timer")

    def process_bars(self, bars: Dict[str, BarData]) -> None:
        """将行情处理为一条可扩展的决策流水线骨架。"""
        if not self.entry.target_aggregate:
            return

        for vt_symbol, bar in bars.items():
            bar_data = {
                "datetime": bar.datetime,
                "open": bar.open_price,
                "high": bar.high_price,
                "low": bar.low_price,
                "close": bar.close_price,
                "volume": bar.volume,
            }
            self.entry.current_dt = bar.datetime

            try:
                instrument = self.entry.target_aggregate.update_bar(vt_symbol, bar_data)
                option_chain = self._build_option_chain_snapshot(vt_symbol, instrument.latest_close, bar_data["datetime"])
                indicator_context = self._build_indicator_context(vt_symbol, instrument, bar_data, option_chain)
                indicator_result = self._run_indicator_stage(instrument, bar_data, indicator_context)

                open_trace = self._run_open_pipeline(
                    vt_symbol=vt_symbol,
                    instrument=instrument,
                    bar_data=bar_data,
                    indicator_result=indicator_result,
                    option_chain=option_chain,
                )
                self._publish_trace(open_trace)

                if self.entry.position_aggregate:
                    positions = self.entry.position_aggregate.get_positions_by_underlying(vt_symbol)
                else:
                    positions = []
                for position in positions:
                    close_trace = self._run_close_pipeline(
                        vt_symbol=vt_symbol,
                        instrument=instrument,
                        position=position,
                        bar_data=bar_data,
                        indicator_result=indicator_result,
                        option_chain=option_chain,
                    )
                    self._publish_trace(close_trace)

            except Exception as e:
                self.entry.logger.error(f"处理 K 线更新失败 [{vt_symbol}]: {e}")

        self.entry._record_snapshot()

    def _run_indicator_stage(
        self,
        instrument: Any,
        bar_data: Dict[str, Any],
        context: IndicatorContext,
    ) -> IndicatorComputationResult:
        if not self.entry.indicator_service:
            return IndicatorComputationResult.noop(summary="未装配指标服务")
        try:
            result = self.entry.indicator_service.calculate_bar(instrument, bar_data, context=context)
            if result is None:
                return IndicatorComputationResult.noop(summary="指标服务返回空结果")
            return result
        except Exception as e:
            self.entry.logger.error(f"指标计算失败 [{context.vt_symbol}]: {e}")
            return IndicatorComputationResult.noop(summary=f"指标计算异常: {e}")

    def _run_open_pipeline(
        self,
        vt_symbol: str,
        instrument: Any,
        bar_data: Dict[str, Any],
        indicator_result: IndicatorComputationResult,
        option_chain: Optional[OptionChainSnapshot],
    ) -> DecisionTrace:
        trace = DecisionTrace(
            vt_symbol=vt_symbol,
            bar_dt=bar_data["datetime"],
            trace_type="open_pipeline",
            metadata={"underlying_price": instrument.latest_close},
        )
        trace.append_stage(
            "indicator",
            "ok",
            indicator_result.summary or "指标阶段完成",
            {
                "updated_indicator_keys": list(indicator_result.updated_indicator_keys),
                "values": dict(indicator_result.values),
            },
        )

        signal_context = SignalContext(
            vt_symbol=vt_symbol,
            timestamp=bar_data["datetime"],
            underlying_price=instrument.latest_close,
            option_chain=option_chain,
            indicator_result=indicator_result,
        )
        open_signal = self._normalize_signal_decision(
            self.entry.signal_service.check_open_signal(instrument, context=signal_context)
            if self.entry.signal_service
            else None,
            default_action="open",
        )
        if open_signal is None:
            trace.append_stage("signal", "noop", "未触发开仓信号")
            return trace

        trace.signal_name = open_signal.signal_name
        trace.append_stage(
            "signal",
            "ok",
            open_signal.rationale or open_signal.signal_name,
            {
                "action": open_signal.action,
                "confidence": open_signal.confidence,
                "metadata": dict(open_signal.metadata),
            },
        )
        self.entry._register_signal_temporary_symbol(vt_symbol)

        if option_chain is None or option_chain.is_empty:
            trace.append_stage("option_chain", "skipped", "未获取到有效期权链")
            return trace
        trace.append_stage(
            "option_chain",
            "ok",
            f"期权链构建完成，共 {len(option_chain.entries)} 个候选",
            {"candidate_count": len(option_chain.entries)},
        )

        selected_contract = self._select_contract_for_signal(open_signal, option_chain)
        if selected_contract is None:
            trace.append_stage("selection", "rejected", "未找到符合偏好的候选合约")
            return trace
        trace.append_stage(
            "selection",
            "ok",
            f"选中候选合约 {selected_contract.vt_symbol}",
            {
                "vt_symbol": selected_contract.vt_symbol,
                "option_type": selected_contract.option_type,
                "strike_price": selected_contract.strike_price,
                "days_to_expiry": selected_contract.days_to_expiry,
            },
        )

        pricing_payload, greeks_result = self._build_pricing_payload(option_chain, selected_contract)
        if pricing_payload is None:
            trace.append_stage("pricing", "skipped", "未启用定价能力或缺少隐波数据")
        else:
            trace.append_stage("pricing", "ok", "完成价格/Greeks 快照计算", pricing_payload)

        sizing_payload = self._build_sizing_payload(option_chain, selected_contract, greeks_result)
        if sizing_payload is None:
            trace.append_stage("sizing", "skipped", "未启用仓位能力或缺少必要账户数据")
        else:
            trace.append_stage(
                "sizing",
                "ok" if sizing_payload.get("passed", False) else "rejected",
                sizing_payload.get("summary", "仓位评估完成"),
                sizing_payload,
            )

        trace.append_stage(
            "execution_plan",
            "planned",
            "生成执行计划骨架（不直接下单）",
            {
                "vt_symbol": selected_contract.vt_symbol,
                "signal_name": open_signal.signal_name,
                "planned_action": "open",
                "suggested_volume": sizing_payload.get("final_volume") if sizing_payload else None,
            },
        )
        return trace

    def _run_close_pipeline(
        self,
        vt_symbol: str,
        instrument: Any,
        position: Any,
        bar_data: Dict[str, Any],
        indicator_result: IndicatorComputationResult,
        option_chain: Optional[OptionChainSnapshot],
    ) -> DecisionTrace:
        trace = DecisionTrace(
            vt_symbol=getattr(position, "vt_symbol", vt_symbol),
            bar_dt=bar_data["datetime"],
            trace_type="close_pipeline",
            metadata={"underlying_vt_symbol": vt_symbol},
        )
        trace.append_stage("indicator", "ok", indicator_result.summary or "沿用本 bar 指标结果")

        signal_context = SignalContext(
            vt_symbol=vt_symbol,
            timestamp=bar_data["datetime"],
            underlying_price=instrument.latest_close,
            option_chain=option_chain,
            indicator_result=indicator_result,
        )
        close_signal = self._normalize_signal_decision(
            self.entry.signal_service.check_close_signal(instrument, position, context=signal_context)
            if self.entry.signal_service
            else None,
            default_action="close",
        )
        if close_signal is None:
            trace.append_stage("signal", "noop", "未触发平仓信号")
            return trace

        trace.signal_name = close_signal.signal_name
        trace.append_stage(
            "signal",
            "ok",
            close_signal.rationale or close_signal.signal_name,
            {"position_vt_symbol": getattr(position, "vt_symbol", "")},
        )

        close_payload = self._build_close_plan_payload(position)
        if close_payload is None:
            trace.append_stage("execution_plan", "skipped", "未启用平仓计划能力")
        else:
            trace.append_stage("execution_plan", "planned", "生成平仓计划骨架", close_payload)
        return trace

    def _build_indicator_context(
        self,
        vt_symbol: str,
        instrument: Any,
        bar_data: Dict[str, Any],
        option_chain: Optional[OptionChainSnapshot],
    ) -> IndicatorContext:
        return IndicatorContext(
            vt_symbol=vt_symbol,
            timestamp=bar_data["datetime"],
            bar=bar_data,
            underlying_price=instrument.latest_close,
            option_chain=option_chain,
        )

    def _normalize_signal_decision(
        self,
        raw_signal: Any,
        default_action: str,
    ) -> Optional[SignalDecision]:
        if raw_signal is None:
            return None
        if isinstance(raw_signal, SignalDecision):
            return raw_signal
        text = str(raw_signal).strip()
        if not text:
            return None
        return SignalDecision(
            action=default_action,
            signal_name=text,
            rationale="兼容旧版字符串信号",
        )

    def _build_option_chain_snapshot(
        self,
        underlying_vt_symbol: str,
        underlying_price: float,
        as_of: Any,
    ) -> Optional[OptionChainSnapshot]:
        if not self.entry.service_activation.get("option_chain", True):
            return None
        if not self.entry.market_gateway:
            return None
        contracts = self.entry.market_gateway.get_all_contracts()
        if not contracts:
            return None
        return OptionChainSnapshot.from_contracts(
            underlying_vt_symbol=underlying_vt_symbol,
            underlying_price=underlying_price,
            contracts=contracts,
            get_tick=self.entry.market_gateway.get_tick,
            as_of=as_of,
        )

    def _select_contract_for_signal(
        self,
        signal: SignalDecision,
        option_chain: OptionChainSnapshot,
    ) -> Optional[Any]:
        if not self.entry.option_selector_service:
            return None
        preference = signal.selection_preference or OptionSelectionPreference(
            option_type="call",
            strike_level=self.entry.strike_level,
        )

        if preference.combination_type:
            self.entry.logger.info(
                f"组合偏好 {preference.combination_type} 已识别，当前骨架仅记录偏好，不固化多腿执行"
            )
            return None

        option_type = preference.option_type or "call"
        if preference.target_delta is not None:
            greeks_map = self._build_chain_greeks_map(option_chain)
            if greeks_map:
                return self.entry.option_selector_service.select_by_delta_from_chain(
                    option_chain,
                    option_type=option_type,
                    target_delta=preference.target_delta,
                    greeks_data=greeks_map,
                    log_func=self.entry.logger.info,
                )

        return self.entry.option_selector_service.select_option_from_chain(
            option_chain,
            option_type=option_type,
            strike_level=preference.strike_level or self.entry.strike_level,
            log_func=self.entry.logger.info,
        )

    def _build_chain_greeks_map(
        self,
        option_chain: OptionChainSnapshot,
    ) -> Dict[str, GreeksResult]:
        if not self.entry.greeks_calculator:
            return {}
        risk_free_rate = float(getattr(self.entry, "risk_free_rate", 0.02) or 0.02)
        result: Dict[str, GreeksResult] = {}
        for entry in option_chain.entries:
            iv = entry.quote.implied_volatility
            if iv is None or iv <= 0 or entry.contract.days_to_expiry <= 0:
                continue
            greeks = self.entry.greeks_calculator.calculate_greeks(
                GreeksInput(
                    spot_price=option_chain.underlying_price,
                    strike_price=entry.contract.strike_price,
                    time_to_expiry=entry.contract.days_to_expiry / 365.0,
                    risk_free_rate=risk_free_rate,
                    volatility=iv,
                    option_type=entry.contract.option_type,
                )
            )
            if greeks.success:
                result[entry.contract.vt_symbol] = greeks
        return result

    def _build_pricing_payload(
        self,
        option_chain: OptionChainSnapshot,
        selected_contract: Any,
    ) -> tuple[Optional[Dict[str, Any]], Optional[GreeksResult]]:
        chain_entry = next(
            (item for item in option_chain.entries if item.contract.vt_symbol == selected_contract.vt_symbol),
            None,
        )
        if chain_entry is None:
            return None, None

        greeks_result = None
        if self.entry.greeks_calculator and chain_entry.quote.implied_volatility:
            greeks_result = self.entry.greeks_calculator.calculate_greeks(
                GreeksInput(
                    spot_price=option_chain.underlying_price,
                    strike_price=chain_entry.contract.strike_price,
                    time_to_expiry=max(chain_entry.contract.days_to_expiry, 1) / 365.0,
                    risk_free_rate=float(getattr(self.entry, "risk_free_rate", 0.02) or 0.02),
                    volatility=chain_entry.quote.implied_volatility,
                    option_type=chain_entry.contract.option_type,
                )
            )

        pricing_result = None
        if self.entry.pricing_engine and chain_entry.quote.implied_volatility:
            pricing_result = self.entry.pricing_engine.price(
                PricingInput(
                    spot_price=option_chain.underlying_price,
                    strike_price=chain_entry.contract.strike_price,
                    time_to_expiry=max(chain_entry.contract.days_to_expiry, 1) / 365.0,
                    risk_free_rate=float(getattr(self.entry, "risk_free_rate", 0.02) or 0.02),
                    volatility=chain_entry.quote.implied_volatility,
                    option_type=chain_entry.contract.option_type,
                    exercise_style=ExerciseStyle.AMERICAN,
                )
            )

        if greeks_result is None and pricing_result is None:
            return None, None

        return (
            {
                "quote_last_price": chain_entry.quote.last_price,
                "quote_bid_price": chain_entry.quote.bid_price,
                "quote_ask_price": chain_entry.quote.ask_price,
                "implied_volatility": chain_entry.quote.implied_volatility,
                "theoretical_price": getattr(pricing_result, "price", None),
                "pricing_model": getattr(pricing_result, "model_used", ""),
                "delta": getattr(greeks_result, "delta", None),
                "gamma": getattr(greeks_result, "gamma", None),
                "theta": getattr(greeks_result, "theta", None),
                "vega": getattr(greeks_result, "vega", None),
            },
            greeks_result,
        )

    def _build_sizing_payload(
        self,
        option_chain: OptionChainSnapshot,
        selected_contract: Any,
        greeks_result: Optional[GreeksResult],
    ) -> Optional[Dict[str, Any]]:
        if not self.entry.position_sizing_service or not self.entry.account_gateway or greeks_result is None:
            return None
        account = self.entry.account_gateway.get_account_snapshot()
        if account is None:
            return None

        contract = self.entry.market_gateway.get_contract(selected_contract.vt_symbol) if self.entry.market_gateway else None
        multiplier = float(getattr(contract, "size", 1) or 1)
        price = max(float(getattr(selected_contract, "bid_price", 0.0) or 0.0), float(getattr(selected_contract, "ask_price", 0.0) or 0.0), 0.0)
        if price <= 0:
            price = float(getattr(selected_contract, "ask_price", 0.0) or 0.0)
        if price <= 0:
            return None

        sizing = self.entry.position_sizing_service.compute_sizing(
            account_balance=float(account.available),
            total_equity=float(account.balance),
            used_margin=max(float(account.balance) - float(account.available), 0.0),
            contract_price=price,
            underlying_price=option_chain.underlying_price,
            strike_price=selected_contract.strike_price,
            option_type=selected_contract.option_type,
            multiplier=multiplier,
            greeks=greeks_result,
            portfolio_greeks=PortfolioGreeks(),
            risk_thresholds=getattr(self.entry, "risk_thresholds", None),
        )
        return {
            "passed": sizing.passed,
            "final_volume": sizing.final_volume,
            "margin_volume": sizing.margin_volume,
            "usage_volume": sizing.usage_volume,
            "greeks_volume": sizing.greeks_volume,
            "reject_reason": sizing.reject_reason,
            "summary": "仓位评估通过" if sizing.passed else (sizing.reject_reason or "仓位评估拒绝"),
        }

    def _build_close_plan_payload(self, position: Any) -> Optional[Dict[str, Any]]:
        if not self.entry.position_sizing_service:
            return None
        close_price = 0.0
        if self.entry.market_gateway:
            tick = self.entry.market_gateway.get_tick(getattr(position, "vt_symbol", ""))
            close_price = float(getattr(tick, "last_price", 0.0) or 0.0) if tick else 0.0
        if close_price <= 0:
            close_price = float(getattr(position, "open_price", 0.0) or 0.0)
        instruction = self.entry.position_sizing_service.calculate_close_volume(
            position=position,
            close_price=close_price,
            signal="close_pipeline_plan",
        )
        if instruction is None:
            return None
        return {
            "vt_symbol": instruction.vt_symbol,
            "direction": instruction.direction.value,
            "offset": instruction.offset.value,
            "volume": instruction.volume,
            "price": instruction.price,
        }

    def _publish_trace(self, trace: DecisionTrace) -> None:
        emit_noop = bool(self.entry.observability_config.get("emit_noop_decisions", False))
        has_effective_stage = any(item.status not in {"noop", "skipped"} for item in trace.stages)
        if not emit_noop and not has_effective_stage:
            return

        payload = trace.to_payload()
        self.entry.last_decision_trace = trace
        if self.entry.service_activation.get("decision_observability", True):
            self.entry.decision_journal.append(payload)
            maxlen = max(int(getattr(self.entry, "decision_journal_limit", 200) or 200), 1)
            if len(self.entry.decision_journal) > maxlen:
                self.entry.decision_journal = self.entry.decision_journal[-maxlen:]
            if self.entry.monitor:
                self.entry.monitor.record_decision_trace(payload)

    def validate_universe(self) -> None:
        """确保每个配置品种都有可用主力合约。"""
        if (
            not self.entry.target_aggregate
            or not self.entry.market_gateway
            or self.entry.future_selection_service is None
        ):
            return

        for product in self.entry.target_products:
            existing = self.entry.target_aggregate.get_active_contract(product)
            if existing:
                continue

            try:
                all_contracts = self.entry.market_gateway.get_all_contracts()
                product_contracts = [
                    c for c in all_contracts
                    if ContractHelper.is_contract_of_product(c, product)
                ]
                if not product_contracts:
                    self.entry.logger.warning(f"品种 {product} 未找到可用合约")
                    continue

                market_data = self.build_future_market_data(product_contracts)
                dominant = self.entry.future_selection_service.select_dominant_contract(
                    product_contracts, date.today(), market_data=market_data, log_func=self.entry.logger.info
                )
                if dominant:
                    vt_symbol = dominant.vt_symbol
                    self.entry.target_aggregate.set_active_contract(product, vt_symbol)
                    self.entry.target_aggregate.get_or_create_instrument(vt_symbol)
                    self.entry._subscribe_symbol(vt_symbol)
                    self.entry.logger.info(f"品种 {product} 主力合约: {vt_symbol}")
            except Exception as e:
                self.entry.logger.error(f"品种 {product} 主力合约初始化失败: {e}")

    def build_future_market_data(self, contracts: List[Any]) -> Dict[str, SelectionMarketData]:
        """基于行情网关逐笔数据构建主力选择所需行情映射。"""
        if not self.entry.market_gateway:
            return {}

        data: Dict[str, SelectionMarketData] = {}
        for contract in contracts:
            vt_symbol = getattr(contract, "vt_symbol", "")
            if not vt_symbol:
                continue

            tick = self.entry.market_gateway.get_tick(vt_symbol)
            if tick is None:
                continue

            try:
                volume = float(getattr(tick, "volume", 0) or 0)
                open_interest = float(getattr(tick, "open_interest", 0) or 0)
            except (TypeError, ValueError):
                continue

            if volume != volume or open_interest != open_interest:
                continue

            data[vt_symbol] = SelectionMarketData(
                vt_symbol=vt_symbol,
                volume=int(volume),
                open_interest=open_interest,
            )

        return data
