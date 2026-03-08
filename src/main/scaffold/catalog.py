"""整仓库脚手架目录与预设定义。"""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

from .models import (
    CapabilityKey,
    CapabilityOptionKey,
    CreateOptions,
    DirectoryConflictPolicy,
    ScaffoldPlan,
    ScaffoldPreset,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOT = REPO_ROOT / "src" / "main" / "scaffold" / "templates" / "presets"
DEFAULT_PROJECT_NAME = "option_strategy_project"
DEFAULT_PRESET_KEY = "custom"

CAPABILITY_ORDER: tuple[CapabilityKey, ...] = (
    CapabilityKey.SELECTION,
    CapabilityKey.POSITION_SIZING,
    CapabilityKey.PRICING,
    CapabilityKey.GREEKS_RISK,
    CapabilityKey.EXECUTION,
    CapabilityKey.HEDGING,
    CapabilityKey.MONITORING,
    CapabilityKey.OBSERVABILITY,
)

CAPABILITY_LABELS: dict[CapabilityKey, str] = {
    CapabilityKey.SELECTION: "标的选择",
    CapabilityKey.POSITION_SIZING: "仓位控制",
    CapabilityKey.PRICING: "定价引擎",
    CapabilityKey.GREEKS_RISK: "Greeks 风控",
    CapabilityKey.EXECUTION: "执行增强",
    CapabilityKey.HEDGING: "对冲能力",
    CapabilityKey.MONITORING: "监控上报",
    CapabilityKey.OBSERVABILITY: "决策可观测性",
}

CAPABILITY_OPTION_ORDER: tuple[CapabilityOptionKey, ...] = (
    CapabilityOptionKey.FUTURE_SELECTION,
    CapabilityOptionKey.OPTION_CHAIN,
    CapabilityOptionKey.OPTION_SELECTOR,
    CapabilityOptionKey.POSITION_SIZING,
    CapabilityOptionKey.PRICING_ENGINE,
    CapabilityOptionKey.GREEKS_CALCULATOR,
    CapabilityOptionKey.PORTFOLIO_RISK,
    CapabilityOptionKey.SMART_ORDER_EXECUTOR,
    CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER,
    CapabilityOptionKey.DELTA_HEDGING,
    CapabilityOptionKey.VEGA_HEDGING,
    CapabilityOptionKey.MONITORING,
    CapabilityOptionKey.DECISION_OBSERVABILITY,
)

CAPABILITY_OPTION_LABELS: dict[CapabilityOptionKey, str] = {
    CapabilityOptionKey.FUTURE_SELECTION: "期货主力选择",
    CapabilityOptionKey.OPTION_CHAIN: "期权链加载",
    CapabilityOptionKey.OPTION_SELECTOR: "期权合约选择",
    CapabilityOptionKey.POSITION_SIZING: "仓位 sizing",
    CapabilityOptionKey.PRICING_ENGINE: "定价引擎",
    CapabilityOptionKey.GREEKS_CALCULATOR: "Greeks 计算",
    CapabilityOptionKey.PORTFOLIO_RISK: "组合 Greeks 风控",
    CapabilityOptionKey.SMART_ORDER_EXECUTOR: "智能执行器",
    CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER: "高级订单调度",
    CapabilityOptionKey.DELTA_HEDGING: "Delta 对冲",
    CapabilityOptionKey.VEGA_HEDGING: "Vega 对冲",
    CapabilityOptionKey.MONITORING: "策略监控",
    CapabilityOptionKey.DECISION_OBSERVABILITY: "决策日志",
}

CAPABILITY_GROUP_OPTIONS: dict[CapabilityKey, tuple[CapabilityOptionKey, ...]] = {
    CapabilityKey.SELECTION: (
        CapabilityOptionKey.FUTURE_SELECTION,
        CapabilityOptionKey.OPTION_CHAIN,
        CapabilityOptionKey.OPTION_SELECTOR,
    ),
    CapabilityKey.POSITION_SIZING: (CapabilityOptionKey.POSITION_SIZING,),
    CapabilityKey.PRICING: (CapabilityOptionKey.PRICING_ENGINE,),
    CapabilityKey.GREEKS_RISK: (
        CapabilityOptionKey.GREEKS_CALCULATOR,
        CapabilityOptionKey.PORTFOLIO_RISK,
    ),
    CapabilityKey.EXECUTION: (
        CapabilityOptionKey.SMART_ORDER_EXECUTOR,
        CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER,
    ),
    CapabilityKey.HEDGING: (
        CapabilityOptionKey.DELTA_HEDGING,
        CapabilityOptionKey.VEGA_HEDGING,
    ),
    CapabilityKey.MONITORING: (CapabilityOptionKey.MONITORING,),
    CapabilityKey.OBSERVABILITY: (CapabilityOptionKey.DECISION_OBSERVABILITY,),
}

CAPABILITY_OPTION_TO_SERVICE_KEY: dict[CapabilityOptionKey, str] = {
    CapabilityOptionKey.FUTURE_SELECTION: "future_selection",
    CapabilityOptionKey.OPTION_CHAIN: "option_chain",
    CapabilityOptionKey.OPTION_SELECTOR: "option_selector",
    CapabilityOptionKey.POSITION_SIZING: "position_sizing",
    CapabilityOptionKey.PRICING_ENGINE: "pricing_engine",
    CapabilityOptionKey.GREEKS_CALCULATOR: "greeks_calculator",
    CapabilityOptionKey.PORTFOLIO_RISK: "portfolio_risk",
    CapabilityOptionKey.SMART_ORDER_EXECUTOR: "smart_order_executor",
    CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER: "advanced_order_scheduler",
    CapabilityOptionKey.DELTA_HEDGING: "delta_hedging",
    CapabilityOptionKey.VEGA_HEDGING: "vega_hedging",
    CapabilityOptionKey.MONITORING: "monitoring",
    CapabilityOptionKey.DECISION_OBSERVABILITY: "decision_observability",
}

CAPABILITY_OPTION_DEPENDENCIES: dict[CapabilityOptionKey, tuple[CapabilityOptionKey, ...]] = {
    CapabilityOptionKey.OPTION_SELECTOR: (CapabilityOptionKey.OPTION_CHAIN,),
    CapabilityOptionKey.PORTFOLIO_RISK: (CapabilityOptionKey.GREEKS_CALCULATOR,),
    CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER: (CapabilityOptionKey.SMART_ORDER_EXECUTOR,),
    CapabilityOptionKey.DELTA_HEDGING: (CapabilityOptionKey.GREEKS_CALCULATOR,),
    CapabilityOptionKey.VEGA_HEDGING: (CapabilityOptionKey.GREEKS_CALCULATOR,),
}

CAPABILITY_OPTION_MUTEX_RULES: tuple[
    tuple[tuple[CapabilityOptionKey, CapabilityOptionKey], str],
    ...,
] = (
    (
        (CapabilityOptionKey.DELTA_HEDGING, CapabilityOptionKey.VEGA_HEDGING),
        "当前脚手架未提供 Delta/Vega 双对冲的优先级与协同编排，同时启用会造成语义冲突。",
    ),
    (
        (CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER, CapabilityOptionKey.DELTA_HEDGING),
        "当前脚手架未提供调度单与 Delta 对冲单的仲裁逻辑，不能同时启用。",
    ),
    (
        (CapabilityOptionKey.ADVANCED_ORDER_SCHEDULER, CapabilityOptionKey.VEGA_HEDGING),
        "当前脚手架未提供调度单与 Vega 对冲单的仲裁逻辑，不能同时启用。",
    ),
)

PRESET_OPTION_BLOCKLISTS: dict[str, dict[CapabilityOptionKey, str]] = {
    "delta-neutral": {
        CapabilityOptionKey.OPTION_SELECTOR: "`delta-neutral` 预设输出的是组合偏好，不走单腿选权链路，因此不能启用 `option-selector`。",
    },
}

SERVICE_ACTIVATION_KEYS: tuple[str, ...] = (
    "future_selection",
    "option_chain",
    "option_selector",
    "position_sizing",
    "pricing_engine",
    "greeks_calculator",
    "portfolio_risk",
    "smart_order_executor",
    "advanced_order_scheduler",
    "delta_hedging",
    "vega_hedging",
    "monitoring",
    "decision_observability",
)

BASE_COPY_PATHS: tuple[str, ...] = (
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "LICENSE",
    "requirements.txt",
    "deploy",
    "doc",
    "src",
    "config/domain_service",
    "config/general",
    "config/logging",
    "config/subscription",
    "config/timeframe",
    "config/pytest.ini",
)


def slugify(name: str) -> str:
    """将项目名称标准化为目录/模块 slug。"""
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", (name or "strategy").strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug.lower() or "strategy"


def classify(name: str) -> str:
    """将 slug 标准化为类名前缀。"""
    slug = slugify(name)
    return "".join(part.capitalize() for part in slug.split("_")) or "Strategy"


def _extract_summary(readme_text: str, fallback: str) -> str:
    for raw_line in readme_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        return line
    return fallback


def _load_template_contract(template_dir: Path) -> tuple[dict[str, object], dict[str, object], str, str]:
    contract_path = template_dir / "strategy_contract.toml"
    payload = tomllib.loads(contract_path.read_text(encoding="utf-8"))
    contracts = dict(payload.get("strategy_contracts") or {})
    indicator_import = str(contracts.get("indicator_service", "indicator_service:IndicatorService"))
    signal_import = str(contracts.get("signal_service", "signal_service:SignalService"))
    indicator_class = indicator_import.split(":", 1)[-1]
    signal_class = signal_import.split(":", 1)[-1]
    indicator_kwargs = dict(contracts.get("indicator_kwargs") or {})
    signal_kwargs = dict(contracts.get("signal_kwargs") or {})
    return indicator_kwargs, signal_kwargs, indicator_class, signal_class


def _build_example_preset(key: str, display_name: str, fallback_description: str) -> ScaffoldPreset:
    template_dir = TEMPLATE_ROOT / key
    indicator_kwargs, signal_kwargs, indicator_class, signal_class = _load_template_contract(template_dir)
    readme_path = template_dir / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    description = _extract_summary(readme_text, fallback_description)
    default_options = (
        CapabilityOptionKey.FUTURE_SELECTION,
        CapabilityOptionKey.OPTION_CHAIN,
        CapabilityOptionKey.MONITORING,
        CapabilityOptionKey.DECISION_OBSERVABILITY,
    )
    if key != "delta-neutral":
        default_options = (
            CapabilityOptionKey.FUTURE_SELECTION,
            CapabilityOptionKey.OPTION_CHAIN,
            CapabilityOptionKey.OPTION_SELECTOR,
            CapabilityOptionKey.MONITORING,
            CapabilityOptionKey.DECISION_OBSERVABILITY,
        )
    return ScaffoldPreset(
        key=key,
        display_name=display_name,
        description=description,
        template_dir=template_dir,
        default_options=default_options,
        indicator_class_template=indicator_class,
        signal_class_template=signal_class,
        indicator_kwargs=indicator_kwargs,
        signal_kwargs=signal_kwargs,
    )


def build_preset_catalog() -> dict[str, ScaffoldPreset]:
    """构建可用预设目录。"""
    return {
        DEFAULT_PRESET_KEY: ScaffoldPreset(
            key=DEFAULT_PRESET_KEY,
            display_name="Custom",
            description="生成最小自定义策略骨架，按能力逐步补齐。",
            template_dir=None,
            default_options=(
                CapabilityOptionKey.FUTURE_SELECTION,
                CapabilityOptionKey.OPTION_CHAIN,
                CapabilityOptionKey.OPTION_SELECTOR,
                CapabilityOptionKey.MONITORING,
                CapabilityOptionKey.DECISION_OBSERVABILITY,
            ),
            indicator_class_template="{class_prefix}IndicatorService",
            signal_class_template="{class_prefix}SignalService",
            indicator_kwargs={},
            signal_kwargs={},
        ),
        "ema-cross": _build_example_preset("ema-cross", "EMA Cross", "EMA 快慢线交叉策略模板。"),
        "iv-rank": _build_example_preset("iv-rank", "IV Rank", "基于 IV Rank 的波动率策略模板。"),
        "delta-neutral": _build_example_preset("delta-neutral", "Delta Neutral", "以组合偏好驱动的 Delta Neutral 模板。"),
    }


def get_preset_keys() -> tuple[str, ...]:
    """返回预设键列表。"""
    return tuple(build_preset_catalog().keys())


def get_preset(key: str) -> ScaffoldPreset:
    """获取预设定义。"""
    catalog = build_preset_catalog()
    preset = catalog.get((key or "").strip().lower())
    if preset is None:
        available = ", ".join(catalog.keys())
        raise ValueError(f"未知预设: {key}。可用预设: {available}")
    return preset


def capability_label(capability: CapabilityKey) -> str:
    """返回能力显示名称。"""
    return CAPABILITY_LABELS[capability]


def capability_option_label(option: CapabilityOptionKey) -> str:
    """返回二级子选项显示名称。"""
    return CAPABILITY_OPTION_LABELS[option]


def _option_flag(option: CapabilityOptionKey) -> str:
    return f"--with-option {option.value}"


def _without_option_flag(option: CapabilityOptionKey) -> str:
    return f"--without-option {option.value}"


def _with_flag(capability: CapabilityKey) -> str:
    return f"--with {capability.value}"


def _without_flag(capability: CapabilityKey) -> str:
    return f"--without {capability.value}"


def _raise_validation_error(error: str, suggestion: str) -> None:
    raise ValueError(f"{error} 建议：{suggestion}")


def validate_enabled_options(
    enabled_options: tuple[CapabilityOptionKey, ...],
    *,
    preset_key: str | None = None,
) -> tuple[CapabilityOptionKey, ...]:
    """校验二级子选项之间的依赖与互斥关系。"""
    enabled_set = set(enabled_options)

    for option, dependencies in CAPABILITY_OPTION_DEPENDENCIES.items():
        if option not in enabled_set:
            continue
        missing = tuple(dependency for dependency in dependencies if dependency not in enabled_set)
        if missing:
            dependency_names = "、".join(capability_option_label(item) for item in missing)
            dependency_flags = " ".join(_option_flag(item) for item in missing)
            _raise_validation_error(
                f"子选项 `{option.value}` 依赖 {dependency_names}。",
                f"补上 {dependency_flags}，或删除 {_option_flag(option)}。",
            )

    for (left, right), reason in CAPABILITY_OPTION_MUTEX_RULES:
        if left in enabled_set and right in enabled_set:
            _raise_validation_error(
                f"子选项 `{left.value}` 与 `{right.value}` 不能同时启用：{reason}",
                f"保留其中一个，删除 {_option_flag(left)} 或 {_option_flag(right)}。",
            )

    preset_rules = PRESET_OPTION_BLOCKLISTS.get(preset_key or "", {})
    for option, reason in preset_rules.items():
        if option in enabled_set:
            alternative_presets = [key for key in build_preset_catalog().keys() if key != (preset_key or "")]
            suggested_preset = alternative_presets[0] if alternative_presets else DEFAULT_PRESET_KEY
            _raise_validation_error(
                f"子选项 `{option.value}` 与预设 `{preset_key}` 不兼容：{reason}",
                f"删除 {_option_flag(option)}，或改用 `--preset {suggested_preset}`。",
            )

    return enabled_options


def get_capability_options(capability: CapabilityKey) -> tuple[CapabilityOptionKey, ...]:
    """返回能力组下的二级子选项。"""
    return CAPABILITY_GROUP_OPTIONS[capability]


def derive_capabilities(enabled_options: tuple[CapabilityOptionKey, ...]) -> tuple[CapabilityKey, ...]:
    """从二级子选项反推启用的顶层能力组。"""
    option_set = set(enabled_options)
    return tuple(
        capability
        for capability in CAPABILITY_ORDER
        if any(option in option_set for option in CAPABILITY_GROUP_OPTIONS[capability])
    )


def resolve_capability_options(
    preset: ScaffoldPreset,
    include_capabilities: tuple[CapabilityKey, ...],
    exclude_capabilities: tuple[CapabilityKey, ...],
    include_options: tuple[CapabilityOptionKey, ...],
    exclude_options: tuple[CapabilityOptionKey, ...],
) -> tuple[CapabilityOptionKey, ...]:
    """基于预设、能力组和子选项覆盖计算最终启用子选项。"""
    include_set = set(include_capabilities)
    exclude_set = set(exclude_capabilities)
    overlap = include_set & exclude_set
    if overlap:
        names = ", ".join(sorted(item.value for item in overlap))
        capability = sorted(overlap, key=lambda item: item.value)[0]
        _raise_validation_error(
            f"同一能力不能同时出现在 --with 和 --without 中: {names}。",
            f"保留 {_with_flag(capability)} 或 {_without_flag(capability)} 其中一个。",
        )

    include_option_set = set(include_options)
    exclude_option_set = set(exclude_options)
    option_overlap = include_option_set & exclude_option_set
    if option_overlap:
        names = ", ".join(sorted(item.value for item in option_overlap))
        option = sorted(option_overlap, key=lambda item: item.value)[0]
        _raise_validation_error(
            f"同一子选项不能同时出现在 --with-option 和 --without-option 中: {names}。",
            f"保留 {_option_flag(option)} 或 {_without_option_flag(option)} 其中一个。",
        )

    resolved = set(preset.default_options)
    for capability in include_capabilities:
        resolved.update(CAPABILITY_GROUP_OPTIONS[capability])
    for capability in exclude_capabilities:
        resolved.difference_update(CAPABILITY_GROUP_OPTIONS[capability])

    resolved.update(include_option_set)
    resolved.difference_update(exclude_option_set)
    resolved_options = tuple(item for item in CAPABILITY_OPTION_ORDER if item in resolved)
    return validate_enabled_options(resolved_options, preset_key=preset.key)


def build_service_activation(enabled_options: tuple[CapabilityOptionKey, ...]) -> dict[str, bool]:
    """将二级子选项转换为运行时 `service_activation`。"""
    activation = {key: False for key in SERVICE_ACTIVATION_KEYS}
    for option in enabled_options:
        activation[CAPABILITY_OPTION_TO_SERVICE_KEY[option]] = True
    return activation


def build_scaffold_plan(options: CreateOptions) -> ScaffoldPlan:
    """将 create 参数解析为稳定的渲染计划。"""
    if not options.name:
        raise ValueError("项目名称不能为空。请传入名称，或使用交互模式补齐。")
    if options.clear and options.overwrite:
        raise ValueError("`--clear` 与 `--overwrite` 不能同时使用。")

    preset = get_preset(options.preset or DEFAULT_PRESET_KEY)
    project_name = options.name.strip() or DEFAULT_PROJECT_NAME
    project_slug = slugify(project_name)
    class_prefix = classify(project_slug)
    enabled_options = resolve_capability_options(
        preset,
        options.include_capabilities,
        options.exclude_capabilities,
        options.include_options,
        options.exclude_options,
    )
    capabilities = derive_capabilities(enabled_options)
    service_activation = build_service_activation(enabled_options)
    conflict_policy = DirectoryConflictPolicy.ABORT
    if options.clear:
        conflict_policy = DirectoryConflictPolicy.CLEAR
    elif options.overwrite:
        conflict_policy = DirectoryConflictPolicy.OVERWRITE

    indicator_class_name = preset.indicator_class_template.format(
        class_prefix=class_prefix,
        strategy_slug=project_slug,
    )
    signal_class_name = preset.signal_class_template.format(
        class_prefix=class_prefix,
        strategy_slug=project_slug,
    )
    project_root = Path(options.destination) / project_slug

    return ScaffoldPlan(
        project_name=project_name,
        project_slug=project_slug,
        project_root=project_root,
        strategy_slug=project_slug,
        preset=preset,
        capabilities=capabilities,
        enabled_options=enabled_options,
        service_activation=service_activation,
        conflict_policy=conflict_policy,
        indicator_class_name=indicator_class_name,
        signal_class_name=signal_class_name,
        base_copy_paths=BASE_COPY_PATHS,
    )
