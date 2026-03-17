from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    key: str
    provider_import_path: str
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    single_roles: tuple[str, ...] = ()
    multi_roles: tuple[str, ...] = ()


CAPABILITY_REGISTRY: dict[str, CapabilitySpec] = {
    "future_selection": CapabilitySpec(
        key="future_selection",
        provider_import_path="src.strategy.runtime.providers.future_selection",
        single_roles=("universe.initializer", "universe.rollover_checker"),
    ),
    "option_chain": CapabilitySpec(
        key="option_chain",
        provider_import_path="src.strategy.runtime.providers.option_chain",
        single_roles=("open_pipeline.option_chain_loader",),
    ),
    "option_selector": CapabilitySpec(
        key="option_selector",
        provider_import_path="src.strategy.runtime.providers.option_selector",
        requires=("option_chain",),
        single_roles=("open_pipeline.contract_selector",),
    ),
    "position_sizing": CapabilitySpec(
        key="position_sizing",
        provider_import_path="src.strategy.runtime.providers.position_sizing",
        single_roles=(
            "open_pipeline.sizing_evaluator",
            "close_pipeline.close_volume_planner",
        ),
    ),
    "pricing_engine": CapabilitySpec(
        key="pricing_engine",
        provider_import_path="src.strategy.runtime.providers.pricing_engine",
        single_roles=("open_pipeline.pricing_enricher",),
    ),
    "greeks_calculator": CapabilitySpec(
        key="greeks_calculator",
        provider_import_path="src.strategy.runtime.providers.greeks_calculator",
        single_roles=("open_pipeline.greeks_enricher",),
    ),
    "portfolio_risk": CapabilitySpec(
        key="portfolio_risk",
        provider_import_path="src.strategy.runtime.providers.portfolio_risk",
        requires=("greeks_calculator",),
        single_roles=(
            "open_pipeline.risk_evaluator",
            "close_pipeline.risk_evaluator",
        ),
    ),
    "smart_order_executor": CapabilitySpec(
        key="smart_order_executor",
        provider_import_path="src.strategy.runtime.providers.smart_order_executor",
        single_roles=(
            "open_pipeline.execution_planner",
            "close_pipeline.execution_planner",
        ),
    ),
    "advanced_order_scheduler": CapabilitySpec(
        key="advanced_order_scheduler",
        provider_import_path="src.strategy.runtime.providers.advanced_order_scheduler",
        requires=("smart_order_executor",),
        single_roles=(
            "open_pipeline.execution_scheduler",
            "close_pipeline.execution_scheduler",
        ),
    ),
    "delta_hedging": CapabilitySpec(
        key="delta_hedging",
        provider_import_path="src.strategy.runtime.providers.delta_hedging",
        requires=("greeks_calculator",),
        single_roles=("portfolio.rebalance_planner",),
    ),
    "vega_hedging": CapabilitySpec(
        key="vega_hedging",
        provider_import_path="src.strategy.runtime.providers.vega_hedging",
        requires=("greeks_calculator",),
        single_roles=("portfolio.rebalance_planner",),
    ),
    "monitoring": CapabilitySpec(
        key="monitoring",
        provider_import_path="src.strategy.runtime.providers.monitoring",
        multi_roles=(
            "state.snapshot_sinks",
            "observability.trace_sinks",
            "lifecycle.cleanup_hooks",
        ),
    ),
    "decision_observability": CapabilitySpec(
        key="decision_observability",
        provider_import_path="src.strategy.runtime.providers.decision_observability",
        multi_roles=("observability.trace_sinks",),
    ),
}

CAPABILITY_KEYS: tuple[str, ...] = tuple(CAPABILITY_REGISTRY.keys())
