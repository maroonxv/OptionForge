from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from difflib import get_close_matches
from enum import Enum

from .models import CapabilityOptionKey, ConfigOverride, ScaffoldPreset


class ConfigValueType(str, Enum):
    BOOL = "bool"
    CHOICE = "choice"
    FLOAT = "float"
    INT = "int"
    STR = "str"


@dataclass(frozen=True)
class ConfigParamSchema:
    key: str
    label: str
    group: str
    section_label: str
    value_type: ConfigValueType
    description: str = ""
    choices: tuple[str, ...] = ()
    required_options: tuple[CapabilityOptionKey, ...] = ()


DEFAULT_STRATEGY_SETTINGS: dict[str, object] = {
    "max_positions": 5,
    "position_ratio": 0.1,
    "strike_level": 3,
    "bar_window": 1,
    "bar_interval": "MINUTE",
}

DEFAULT_RUNTIME_CONFIG: dict[str, object] = {
    "log_level": "INFO",
    "log_dir": "logs/runner",
    "heartbeat_interval": 60,
    "max_restart_count": 10,
    "restart_delay": 5.0,
}

DEFAULT_OBSERVABILITY_CONFIG: dict[str, object] = {
    "decision_journal_maxlen": 200,
    "emit_noop_decisions": False,
}

DEFAULT_POSITION_SIZING_CONFIG: dict[str, object] = {
    "margin_ratio": 0.12,
    "min_margin_ratio": 0.07,
    "margin_usage_limit": 0.6,
    "max_volume_per_order": 10,
}

DEFAULT_GREEKS_RISK_CONFIG: dict[str, object] = {
    "risk_free_rate": 0.02,
    "position_limits": {
        "delta": 0.8,
        "gamma": 0.1,
        "vega": 50.0,
    },
    "portfolio_limits": {
        "delta": 5.0,
        "gamma": 1.0,
        "vega": 500.0,
    },
}

DEFAULT_ORDER_EXECUTION_CONFIG: dict[str, object] = {
    "timeout_seconds": 30,
    "max_retries": 3,
    "slippage_ticks": 2,
    "trading_periods": [
        {"start": "08:40", "end": "11:30"},
        {"start": "13:00", "end": "15:30"},
    ],
}

DEFAULT_ADVANCED_ORDERS_CONFIG: dict[str, object] = {
    "default_iceberg_batch_size": 5,
    "default_twap_slices": 10,
    "default_time_window_seconds": 300,
}

DEFAULT_HEDGING_CONFIG: dict[str, object] = {
    "delta_hedging": {
        "target_delta": 0.0,
        "hedging_band": 0.5,
        "hedge_instrument_vt_symbol": "",
        "hedge_instrument_delta": 1.0,
        "hedge_instrument_multiplier": 10.0,
    },
    "vega_hedging": {
        "target_vega": 0.0,
        "hedging_band": 50.0,
        "hedge_instrument_vt_symbol": "",
        "hedge_instrument_vega": 0.1,
        "hedge_instrument_delta": 0.5,
        "hedge_instrument_gamma": 0.01,
        "hedge_instrument_theta": -0.05,
        "hedge_instrument_multiplier": 10.0,
    },
}

CONFIG_GROUP_TITLES: dict[str, str] = {
    "core": "核心策略设置",
    "runtime": "运行时配置",
    "module": "已启用模块配置",
    "preset": "Preset 参数",
}

_CONFIG_PARAM_SCHEMAS: tuple[ConfigParamSchema, ...] = (
    ConfigParamSchema(
        key="setting.max_positions",
        label="最大持仓数",
        group="core",
        section_label="核心策略设置",
        value_type=ConfigValueType.INT,
        description="策略最多允许持有的合约数量。",
    ),
    ConfigParamSchema(
        key="setting.position_ratio",
        label="单次资金占比",
        group="core",
        section_label="核心策略设置",
        value_type=ConfigValueType.FLOAT,
        description="单次开仓使用的资金比例。",
    ),
    ConfigParamSchema(
        key="setting.strike_level",
        label="虚值档位",
        group="core",
        section_label="核心策略设置",
        value_type=ConfigValueType.INT,
        description="期权选合约时使用的虚值档位。",
    ),
    ConfigParamSchema(
        key="setting.bar_window",
        label="K线窗口",
        group="core",
        section_label="核心策略设置",
        value_type=ConfigValueType.INT,
        description="K线合成窗口大小。",
    ),
    ConfigParamSchema(
        key="setting.bar_interval",
        label="K线基础周期",
        group="core",
        section_label="核心策略设置",
        value_type=ConfigValueType.CHOICE,
        choices=("MINUTE", "HOUR", "DAILY"),
        description="K线合成的基础时间单位。",
    ),
    ConfigParamSchema(
        key="runtime.log_level",
        label="日志级别",
        group="runtime",
        section_label="运行时配置",
        value_type=ConfigValueType.CHOICE,
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        description="CLI 与运行时日志输出级别。",
    ),
    ConfigParamSchema(
        key="runtime.log_dir",
        label="日志目录",
        group="runtime",
        section_label="运行时配置",
        value_type=ConfigValueType.STR,
        description="日志目录，相对路径会写入工作区。",
    ),
    ConfigParamSchema(
        key="runtime.heartbeat_interval",
        label="心跳间隔",
        group="runtime",
        section_label="运行时配置",
        value_type=ConfigValueType.INT,
        description="心跳检查间隔（秒）。",
    ),
    ConfigParamSchema(
        key="runtime.max_restart_count",
        label="最大重启次数",
        group="runtime",
        section_label="运行时配置",
        value_type=ConfigValueType.INT,
        description="守护进程允许的最大重启次数。",
    ),
    ConfigParamSchema(
        key="runtime.restart_delay",
        label="重启延迟",
        group="runtime",
        section_label="运行时配置",
        value_type=ConfigValueType.FLOAT,
        description="守护进程每次重启前等待的秒数。",
    ),
    ConfigParamSchema(
        key="observability.decision_journal_maxlen",
        label="决策日志最大长度",
        group="module",
        section_label="可观测配置",
        value_type=ConfigValueType.INT,
        description="保留的决策日志条数上限。",
        required_options=(CapabilityOptionKey.DECISION_OBSERVABILITY,),
    ),
    ConfigParamSchema(
        key="observability.emit_noop_decisions",
        label="记录空决策",
        group="module",
        section_label="可观测配置",
        value_type=ConfigValueType.BOOL,
        description="是否记录无操作决策。",
        required_options=(CapabilityOptionKey.DECISION_OBSERVABILITY,),
    ),
    ConfigParamSchema(
        key="position_sizing.margin_ratio",
        label="保证金比例",
        group="module",
        section_label="仓位控制",
        value_type=ConfigValueType.FLOAT,
        description="动态仓位 sizing 使用的保证金比例。",
        required_options=(CapabilityOptionKey.POSITION_SIZING,),
    ),
    ConfigParamSchema(
        key="position_sizing.min_margin_ratio",
        label="最低保证金比例",
        group="module",
        section_label="仓位控制",
        value_type=ConfigValueType.FLOAT,
        description="最低保证金比例阈值。",
        required_options=(CapabilityOptionKey.POSITION_SIZING,),
    ),
    ConfigParamSchema(
        key="position_sizing.margin_usage_limit",
        label="保证金使用率上限",
        group="module",
        section_label="仓位控制",
        value_type=ConfigValueType.FLOAT,
        description="组合保证金使用率上限。",
        required_options=(CapabilityOptionKey.POSITION_SIZING,),
    ),
    ConfigParamSchema(
        key="position_sizing.max_volume_per_order",
        label="单笔最大手数",
        group="module",
        section_label="仓位控制",
        value_type=ConfigValueType.INT,
        description="每次下单允许的最大手数。",
        required_options=(CapabilityOptionKey.POSITION_SIZING,),
    ),
    ConfigParamSchema(
        key="greeks_risk.risk_free_rate",
        label="无风险利率",
        group="module",
        section_label="Greeks 风控",
        value_type=ConfigValueType.FLOAT,
        description="年化无风险利率。",
        required_options=(CapabilityOptionKey.GREEKS_CALCULATOR, CapabilityOptionKey.PORTFOLIO_RISK),
    ),
    ConfigParamSchema(
        key="greeks_risk.position_limits.delta",
        label="单持仓 Delta 上限",
        group="module",
        section_label="Greeks 风控",
        value_type=ConfigValueType.FLOAT,
        description="单持仓 Delta 阈值。",
        required_options=(CapabilityOptionKey.GREEKS_CALCULATOR, CapabilityOptionKey.PORTFOLIO_RISK),
    ),
    ConfigParamSchema(
        key="greeks_risk.position_limits.gamma",
        label="单持仓 Gamma 上限",
        group="module",
        section_label="Greeks 风控",
        value_type=ConfigValueType.FLOAT,
        description="单持仓 Gamma 阈值。",
        required_options=(CapabilityOptionKey.GREEKS_CALCULATOR, CapabilityOptionKey.PORTFOLIO_RISK),
    ),
    ConfigParamSchema(
        key="greeks_risk.position_limits.vega",
        label="单持仓 Vega 上限",
        group="module",
        section_label="Greeks 风控",
        value_type=ConfigValueType.FLOAT,
        description="单持仓 Vega 阈值。",
        required_options=(CapabilityOptionKey.GREEKS_CALCULATOR, CapabilityOptionKey.PORTFOLIO_RISK),
    ),
    ConfigParamSchema(
        key="greeks_risk.portfolio_limits.delta",
        label="组合 Delta 上限",
        group="module",
        section_label="Greeks 风控",
        value_type=ConfigValueType.FLOAT,
        description="组合 Delta 阈值。",
        required_options=(CapabilityOptionKey.GREEKS_CALCULATOR, CapabilityOptionKey.PORTFOLIO_RISK),
    ),
    ConfigParamSchema(
        key="greeks_risk.portfolio_limits.gamma",
        label="组合 Gamma 上限",
        group="module",
        section_label="Greeks 风控",
        value_type=ConfigValueType.FLOAT,
        description="组合 Gamma 阈值。",
        required_options=(CapabilityOptionKey.GREEKS_CALCULATOR, CapabilityOptionKey.PORTFOLIO_RISK),
    ),
    ConfigParamSchema(
        key="greeks_risk.portfolio_limits.vega",
        label="组合 Vega 上限",
        group="module",
        section_label="Greeks 风控",
        value_type=ConfigValueType.FLOAT,
        description="组合 Vega 阈值。",
        required_options=(CapabilityOptionKey.GREEKS_CALCULATOR, CapabilityOptionKey.PORTFOLIO_RISK),
    ),
    ConfigParamSchema(
        key="order_execution.timeout_seconds",
        label="订单超时秒数",
        group="module",
        section_label="执行增强",
        value_type=ConfigValueType.INT,
        description="限价单超时时间。",
        required_options=(CapabilityOptionKey.SMART_ORDER_EXECUTOR, CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER),
    ),
    ConfigParamSchema(
        key="order_execution.max_retries",
        label="最大重试次数",
        group="module",
        section_label="执行增强",
        value_type=ConfigValueType.INT,
        description="订单超时后的最大重试次数。",
        required_options=(CapabilityOptionKey.SMART_ORDER_EXECUTOR, CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER),
    ),
    ConfigParamSchema(
        key="order_execution.slippage_ticks",
        label="滑点档位",
        group="module",
        section_label="执行增强",
        value_type=ConfigValueType.INT,
        description="自适应价格滑点 tick 数。",
        required_options=(CapabilityOptionKey.SMART_ORDER_EXECUTOR, CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER),
    ),
    ConfigParamSchema(
        key="advanced_orders.default_iceberg_batch_size",
        label="冰山单默认批次",
        group="module",
        section_label="执行增强",
        value_type=ConfigValueType.INT,
        description="冰山单默认批次数量。",
        required_options=(CapabilityOptionKey.SMART_ORDER_EXECUTOR, CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER),
    ),
    ConfigParamSchema(
        key="advanced_orders.default_twap_slices",
        label="TWAP 默认切片数",
        group="module",
        section_label="执行增强",
        value_type=ConfigValueType.INT,
        description="TWAP 默认切片数。",
        required_options=(CapabilityOptionKey.SMART_ORDER_EXECUTOR, CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER),
    ),
    ConfigParamSchema(
        key="advanced_orders.default_time_window_seconds",
        label="默认时间窗口",
        group="module",
        section_label="执行增强",
        value_type=ConfigValueType.INT,
        description="高级订单默认时间窗口（秒）。",
        required_options=(CapabilityOptionKey.SMART_ORDER_EXECUTOR, CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER),
    ),
    ConfigParamSchema(
        key="hedging.delta_hedging.target_delta",
        label="目标 Delta",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="Delta 对冲目标值。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.delta_hedging.hedging_band",
        label="Delta 对冲带宽",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="Delta 超出多少后触发对冲。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.delta_hedging.hedge_instrument_vt_symbol",
        label="Delta 对冲标的",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.STR,
        description="Delta 对冲使用的 vt_symbol。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.delta_hedging.hedge_instrument_delta",
        label="Delta 对冲工具 Delta",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="对冲工具 Delta 值。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.delta_hedging.hedge_instrument_multiplier",
        label="Delta 对冲乘数",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="对冲工具合约乘数。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.vega_hedging.target_vega",
        label="目标 Vega",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="Vega 对冲目标值。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.vega_hedging.hedging_band",
        label="Vega 对冲带宽",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="Vega 超出多少后触发对冲。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.vega_hedging.hedge_instrument_vt_symbol",
        label="Vega 对冲标的",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.STR,
        description="Vega 对冲使用的 vt_symbol。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.vega_hedging.hedge_instrument_vega",
        label="Vega 对冲工具 Vega",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="对冲工具 Vega 值。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.vega_hedging.hedge_instrument_delta",
        label="Vega 对冲工具 Delta",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="对冲工具 Delta 值。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.vega_hedging.hedge_instrument_gamma",
        label="Vega 对冲工具 Gamma",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="对冲工具 Gamma 值。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.vega_hedging.hedge_instrument_theta",
        label="Vega 对冲工具 Theta",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="对冲工具 Theta 值。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
    ConfigParamSchema(
        key="hedging.vega_hedging.hedge_instrument_multiplier",
        label="Vega 对冲乘数",
        group="module",
        section_label="对冲配置",
        value_type=ConfigValueType.FLOAT,
        description="对冲工具合约乘数。",
        required_options=(CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
    ),
)


def _supports_schema(schema: ConfigParamSchema, enabled_options: tuple[CapabilityOptionKey, ...]) -> bool:
    if not schema.required_options:
        return True
    enabled = set(enabled_options)
    return any(option in enabled for option in schema.required_options)


def _infer_preset_value_type(key: str, value: object) -> ConfigValueType:
    if isinstance(value, bool):
        return ConfigValueType.BOOL
    if isinstance(value, int) and not isinstance(value, bool):
        return ConfigValueType.INT
    if isinstance(value, float):
        return ConfigValueType.FLOAT
    if isinstance(value, str):
        return ConfigValueType.STR
    raise ValueError(f"Preset 参数 `{key}` 仅支持标量默认值。")


def _build_preset_param_schemas(preset: ScaffoldPreset) -> tuple[ConfigParamSchema, ...]:
    schemas: list[ConfigParamSchema] = []
    for key, value in preset.indicator_kwargs.items():
        schemas.append(
            ConfigParamSchema(
                key=f"indicator_kwargs.{key}",
                label=f"指标参数 {key}",
                group="preset",
                section_label="Preset 指标参数",
                value_type=_infer_preset_value_type(key, value),
                description=f"来自 preset `{preset.key}` 的 indicator_kwargs 默认值。",
            )
        )
    for key, value in preset.signal_kwargs.items():
        schemas.append(
            ConfigParamSchema(
                key=f"signal_kwargs.{key}",
                label=f"信号参数 {key}",
                group="preset",
                section_label="Preset 信号参数",
                value_type=_infer_preset_value_type(key, value),
                description=f"来自 preset `{preset.key}` 的 signal_kwargs 默认值。",
            )
        )
    return tuple(schemas)


def build_all_config_param_schemas(preset: ScaffoldPreset) -> tuple[ConfigParamSchema, ...]:
    return _CONFIG_PARAM_SCHEMAS + _build_preset_param_schemas(preset)


def build_available_config_param_schemas(
    preset: ScaffoldPreset,
    enabled_options: tuple[CapabilityOptionKey, ...],
) -> tuple[ConfigParamSchema, ...]:
    return tuple(
        schema
        for schema in build_all_config_param_schemas(preset)
        if _supports_schema(schema, enabled_options)
    )


def build_default_config_payload(
    preset: ScaffoldPreset,
    enabled_options: tuple[CapabilityOptionKey, ...],
) -> dict[str, object]:
    enabled = set(enabled_options)
    execution_enabled = bool(
        enabled & {CapabilityOptionKey.SMART_ORDER_EXECUTOR, CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER}
    )
    hedging_enabled = bool(enabled & {CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING})
    greeks_enabled = bool(enabled & {CapabilityOptionKey.GREEKS_CALCULATOR, CapabilityOptionKey.PORTFOLIO_RISK})

    return {
        "setting": deepcopy(DEFAULT_STRATEGY_SETTINGS),
        "runtime": deepcopy(DEFAULT_RUNTIME_CONFIG),
        "observability": deepcopy(DEFAULT_OBSERVABILITY_CONFIG)
        if CapabilityOptionKey.DECISION_OBSERVABILITY in enabled
        else {},
        "position_sizing": deepcopy(DEFAULT_POSITION_SIZING_CONFIG)
        if CapabilityOptionKey.POSITION_SIZING in enabled
        else {},
        "greeks_risk": deepcopy(DEFAULT_GREEKS_RISK_CONFIG) if greeks_enabled else {},
        "order_execution": deepcopy(DEFAULT_ORDER_EXECUTION_CONFIG) if execution_enabled else {},
        "advanced_orders": deepcopy(DEFAULT_ADVANCED_ORDERS_CONFIG) if execution_enabled else {},
        "hedging": deepcopy(DEFAULT_HEDGING_CONFIG) if hedging_enabled else {},
        "indicator_kwargs": deepcopy(preset.indicator_kwargs),
        "signal_kwargs": deepcopy(preset.signal_kwargs),
    }


def _get_nested_value(payload: dict[str, object], key: str) -> object:
    current: object = payload
    for segment in key.split("."):
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(key)
        current = current[segment]
    return current


def _set_nested_value(payload: dict[str, object], key: str, value: object) -> None:
    current: dict[str, object] = payload
    segments = key.split(".")
    for segment in segments[:-1]:
        next_value = current.setdefault(segment, {})
        if not isinstance(next_value, dict):
            raise KeyError(key)
        current = next_value
    current[segments[-1]] = value


def get_config_value(payload: dict[str, object], key: str) -> object:
    return _get_nested_value(payload, key)


def apply_config_overrides(
    payload: dict[str, object],
    overrides: tuple[ConfigOverride, ...],
) -> dict[str, object]:
    merged = deepcopy(payload)
    for override in overrides:
        _set_nested_value(merged, override.key, override.value)
    return merged


def _available_keys_text(available_keys: tuple[str, ...]) -> str:
    return "、".join(available_keys)


def _unknown_key_error(key: str, available_keys: tuple[str, ...]) -> ValueError:
    suggestions = get_close_matches(key, available_keys, n=3)
    suggestion_text = ""
    if suggestions:
        suggestion_text = f" 你可以改用：{_available_keys_text(tuple(suggestions))}。"
    return ValueError(
        f"配置键 `{key}` 不受支持。当前可用键：{_available_keys_text(available_keys)}。{suggestion_text}".strip()
    )


def _unavailable_key_error(key: str, available_keys: tuple[str, ...]) -> ValueError:
    return ValueError(
        f"配置键 `{key}` 当前不可用，请先启用对应模块。当前可用键：{_available_keys_text(available_keys)}。"
    )


def _parse_bool(raw_value: str, key: str) -> bool:
    normalized = raw_value.strip().lower()
    mapping = {
        "1": True,
        "0": False,
        "true": True,
        "false": False,
        "yes": True,
        "no": False,
        "on": True,
        "off": False,
    }
    if normalized not in mapping:
        raise ValueError(f"配置键 `{key}` 需要布尔值，可用 true/false/yes/no/1/0。")
    return mapping[normalized]


def _parse_value(raw_value: str, schema: ConfigParamSchema) -> object:
    if schema.value_type == ConfigValueType.STR:
        return raw_value
    if schema.value_type == ConfigValueType.BOOL:
        return _parse_bool(raw_value, schema.key)
    if schema.value_type == ConfigValueType.INT:
        try:
            return int(raw_value)
        except ValueError as exc:
            raise ValueError(f"配置键 `{schema.key}` 需要整数值。") from exc
    if schema.value_type == ConfigValueType.FLOAT:
        try:
            return float(raw_value)
        except ValueError as exc:
            raise ValueError(f"配置键 `{schema.key}` 需要数字值。") from exc
    if schema.value_type == ConfigValueType.CHOICE:
        normalized = raw_value.strip().lower()
        for choice in schema.choices:
            if choice.lower() == normalized:
                return choice
        choices = " / ".join(schema.choices)
        raise ValueError(f"配置键 `{schema.key}` 只能取：{choices}。")
    raise ValueError(f"不支持的参数类型：{schema.value_type}")


def normalize_config_overrides(overrides: tuple[ConfigOverride, ...]) -> tuple[ConfigOverride, ...]:
    deduped: dict[str, ConfigOverride] = {}
    for override in overrides:
        deduped[override.key] = override
    return tuple(deduped.values())


def parse_config_assignments(
    assignments: tuple[str, ...],
    preset: ScaffoldPreset,
    enabled_options: tuple[CapabilityOptionKey, ...],
) -> tuple[ConfigOverride, ...]:
    all_schemas = build_all_config_param_schemas(preset)
    available_schemas = build_available_config_param_schemas(preset, enabled_options)
    all_by_key = {schema.key: schema for schema in all_schemas}
    available_by_key = {schema.key: schema for schema in available_schemas}
    available_keys = tuple(available_by_key)
    resolved: dict[str, ConfigOverride] = {}

    for assignment in assignments:
        if "=" not in assignment:
            raise ValueError(
                f"`--set` 必须使用 key=value 形式，例如 `--set setting.max_positions=8`。收到：{assignment}"
            )
        key, raw_value = assignment.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"`--set` 的键不能为空。收到：{assignment}")
        if key not in all_by_key:
            raise _unknown_key_error(key, available_keys)
        if key not in available_by_key:
            raise _unavailable_key_error(key, available_keys)
        value = _parse_value(raw_value, available_by_key[key])
        resolved[key] = ConfigOverride(key=key, value=value)

    return tuple(resolved.values())


def resolve_config_payload(
    preset: ScaffoldPreset,
    enabled_options: tuple[CapabilityOptionKey, ...],
    raw_assignments: tuple[str, ...] = (),
    overrides: tuple[ConfigOverride, ...] = (),
) -> tuple[dict[str, object], tuple[ConfigOverride, ...]]:
    parsed_overrides = parse_config_assignments(raw_assignments, preset, enabled_options) if raw_assignments else ()
    final_overrides = normalize_config_overrides(parsed_overrides + overrides)
    payload = build_default_config_payload(preset, enabled_options)
    return apply_config_overrides(payload, final_overrides), final_overrides


def format_config_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

