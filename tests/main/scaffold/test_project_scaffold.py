from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from src.main.scaffold.models import CapabilityKey, CapabilityOptionKey, CreateOptions
from src.main.scaffold.project import create_project_scaffold


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_create_project_scaffold_generates_custom_workspace(tmp_path: Path) -> None:
    plan = create_project_scaffold(
        CreateOptions(
            name="alpha_lab",
            destination=tmp_path,
            use_default=True,
        )
    )

    project_root = tmp_path / "alpha_lab"
    config = _load_toml(project_root / "config" / "strategy_config.toml")

    assert plan.project_root == project_root
    assert (project_root / "README.md").exists()
    assert (project_root / "pyproject.toml").exists()
    assert (project_root / "src" / "strategies" / "alpha_lab" / "indicator_service.py").exists()
    assert (project_root / "src" / "strategies" / "alpha_lab" / "signal_service.py").exists()
    assert (project_root / "src" / "strategies" / "alpha_lab" / "strategy_contract.toml").exists()
    assert (project_root / "tests" / "strategies" / "alpha_lab" / "test_contracts.py").exists()
    assert not (project_root / "example").exists()
    assert config["strategies"][0]["strategy_name"] == "alpha_lab"
    assert config["strategy_contracts"]["signal_service"] == (
        "src.strategies.alpha_lab.signal_service:AlphaLabSignalService"
    )
    assert config["service_activation"]["future_selection"] is True
    assert config["service_activation"]["monitoring"] is True
    assert config["service_activation"]["pricing_engine"] is False


@pytest.mark.parametrize(
    ("preset", "indicator_class", "signal_class"),
    [
        ("custom", "PresetCustomIndicatorService", "PresetCustomSignalService"),
        ("ema-cross", "EmaCrossIndicatorService", "EmaCrossSignalService"),
        ("iv-rank", "IvRankIndicatorService", "IvRankSignalService"),
        ("delta-neutral", "DeltaNeutralIndicatorService", "DeltaNeutralSignalService"),
    ],
)
def test_create_project_scaffold_supports_all_presets(
    tmp_path: Path,
    preset: str,
    indicator_class: str,
    signal_class: str,
) -> None:
    project_name = "preset_custom" if preset == "custom" else f"preset_{preset}"
    plan = create_project_scaffold(
        CreateOptions(
            name=project_name,
            destination=tmp_path,
            preset=preset,
            no_interactive=True,
        )
    )

    contract = _load_toml(plan.project_root / "src" / "strategies" / plan.strategy_slug / "strategy_contract.toml")

    assert plan.project_root.exists()
    assert contract["strategy_contracts"]["indicator_service"].endswith(indicator_class)
    assert contract["strategy_contracts"]["signal_service"].endswith(signal_class)

    if preset == "delta-neutral":
        config = _load_toml(plan.project_root / "config" / "strategy_config.toml")
        assert config["service_activation"]["option_selector"] is False


def test_create_project_scaffold_applies_capability_overrides(tmp_path: Path) -> None:
    plan = create_project_scaffold(
        CreateOptions(
            name="risk_lab",
            destination=tmp_path,
            preset="ema-cross",
            include_capabilities=(CapabilityKey.PRICING, CapabilityKey.EXECUTION),
            exclude_capabilities=(CapabilityKey.MONITORING,),
            no_interactive=True,
        )
    )

    config_path = plan.project_root / "config" / "strategy_config.toml"
    config = _load_toml(config_path)
    raw_text = config_path.read_text(encoding="utf-8")

    assert config["service_activation"]["pricing_engine"] is True
    assert config["service_activation"]["smart_order_executor"] is True
    assert config["service_activation"]["advanced_order_scheduler"] is True
    assert config["service_activation"]["monitoring"] is False
    assert "[order_execution]" in raw_text
    assert "[advanced_orders]" in raw_text
    assert "[greeks_risk]" not in raw_text


def test_create_project_scaffold_supports_nested_option_overrides(tmp_path: Path) -> None:
    plan = create_project_scaffold(
        CreateOptions(
            name="nested_lab",
            destination=tmp_path,
            preset="custom",
            include_capabilities=(CapabilityKey.HEDGING,),
            include_options=(CapabilityOptionKey.VEGA_HEDGING, CapabilityOptionKey.GREEKS_CALCULATOR),
            exclude_options=(CapabilityOptionKey.DELTA_HEDGING,),
            no_interactive=True,
        )
    )

    config_path = plan.project_root / "config" / "strategy_config.toml"
    config = _load_toml(config_path)
    raw_text = config_path.read_text(encoding="utf-8")

    assert CapabilityKey.HEDGING in plan.capabilities
    assert CapabilityKey.GREEKS_RISK in plan.capabilities
    assert CapabilityOptionKey.VEGA_HEDGING in plan.enabled_options
    assert CapabilityOptionKey.GREEKS_CALCULATOR in plan.enabled_options
    assert CapabilityOptionKey.DELTA_HEDGING not in plan.enabled_options
    assert config["service_activation"]["vega_hedging"] is True
    assert config["service_activation"]["delta_hedging"] is False
    assert config["service_activation"]["greeks_calculator"] is True
    assert "[hedging.vega_hedging]" in raw_text


def test_create_project_scaffold_rejects_conflicting_nested_option_overrides(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_project_scaffold(
            CreateOptions(
                name="bad_nested",
                destination=tmp_path,
                preset="custom",
                include_options=(CapabilityOptionKey.VEGA_HEDGING,),
                exclude_options=(CapabilityOptionKey.VEGA_HEDGING,),
                no_interactive=True,
            )
        )


def test_create_project_scaffold_rejects_missing_option_dependencies(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="依赖"):
        create_project_scaffold(
            CreateOptions(
                name="bad_dependency",
                destination=tmp_path,
                preset="custom",
                include_options=(CapabilityOptionKey.VEGA_HEDGING,),
                exclude_options=(CapabilityOptionKey.DELTA_HEDGING,),
                no_interactive=True,
            )
        )


def test_create_project_scaffold_rejects_semantic_mutex_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="不能同时启用"):
        create_project_scaffold(
            CreateOptions(
                name="bad_mutex",
                destination=tmp_path,
                preset="custom",
                include_options=(
                    CapabilityOptionKey.GREEKS_CALCULATOR,
                    CapabilityOptionKey.DELTA_HEDGING,
                    CapabilityOptionKey.VEGA_HEDGING,
                ),
                no_interactive=True,
            )
        )


def test_create_project_scaffold_rejects_preset_specific_blocked_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="不兼容"):
        create_project_scaffold(
            CreateOptions(
                name="bad_delta_neutral",
                destination=tmp_path,
                preset="delta-neutral",
                include_options=(CapabilityOptionKey.OPTION_SELECTOR,),
                no_interactive=True,
            )
        )


def test_create_project_scaffold_requires_explicit_conflict_policy_in_non_interactive_mode(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "alpha_lab"
    project_root.mkdir(parents=True)
    (project_root / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        create_project_scaffold(
            CreateOptions(
                name="alpha_lab",
                destination=tmp_path,
                preset="custom",
                no_interactive=True,
            )
        )


def test_create_project_scaffold_clear_policy_removes_existing_files(tmp_path: Path) -> None:
    project_root = tmp_path / "alpha_lab"
    project_root.mkdir(parents=True)
    stale_file = project_root / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    create_project_scaffold(
        CreateOptions(
            name="alpha_lab",
            destination=tmp_path,
            preset="custom",
            clear=True,
            force=True,
            no_interactive=True,
        )
    )

    assert not stale_file.exists()
    assert (project_root / "README.md").exists()
