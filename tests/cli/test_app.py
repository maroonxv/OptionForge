"""统一 CLI 测试。"""

from __future__ import annotations

from pathlib import Path
import tomllib
from unittest.mock import patch

import click

import src.cli.app as app_module
from typer.testing import CliRunner

from src import __version__
from src.cli.app import app

runner = CliRunner()


def test_version_flag_outputs_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert f"option-scaffold {__version__}" in result.stdout


def test_help_lists_phase_two_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "create" in result.stdout
    assert "validate" in result.stdout
    assert "doctor" in result.stdout
    assert "examples" in result.stdout


def test_root_command_without_args_shows_help_in_non_interactive_mode() -> None:
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert "主菜单" not in result.stdout


def test_root_command_without_args_opens_main_menu_in_interactive_mode(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_supports_main_menu", lambda: True)

    def fake_prompt(text: str, **_: object) -> int:
        assert text == "请选择操作"
        return 4

    monkeypatch.setattr(click, "prompt", fake_prompt)

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "主菜单：" in result.stdout
    assert "1. 创建策略工作区" in result.stdout
    assert "4. 退出" in result.stdout


def test_root_command_without_args_uses_create_as_default_menu_action(monkeypatch) -> None:
    called = {"create": False}

    monkeypatch.setattr(app_module, "_supports_main_menu", lambda: True)
    monkeypatch.setattr(click, "prompt", lambda *_args, **_kwargs: 1)

    def fake_create_command(**_: object) -> None:
        called["create"] = True

    monkeypatch.setattr(app_module, "create_command", fake_create_command)

    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert called["create"] is True


def test_run_main_menu_action_routes_examples_and_doctor_to_underlying_commands(monkeypatch) -> None:
    called = {"examples": None, "doctor": None}

    def fake_examples_command(**kwargs: object) -> None:
        called["examples"] = kwargs

    def fake_doctor_command(**kwargs: object) -> None:
        called["doctor"] = kwargs

    monkeypatch.setattr(app_module, "examples_command", fake_examples_command)
    monkeypatch.setattr(app_module, "doctor_command", fake_doctor_command)

    app_module._run_main_menu_action(2)
    app_module._run_main_menu_action(3)

    assert called["examples"] == {"name": None}
    assert called["doctor"] == {"strict": "", "check_db": ""}


def test_create_help_uses_refined_copy() -> None:
    result = runner.invoke(app, ["create", "--help"])

    assert result.exit_code == 0
    assert "支持交互式向导，也支持通过 flags 一次性生成" in result.stdout
    assert "常用示例：" in result.stdout
    assert "交互创建" in result.stdout
    assert "默认快速创建" in result.stdout
    assert "预设模板" in result.stdout
    assert "精细能力控制" in result.stdout
    assert "option-scaffold create alpha_lab" in result.stdout
    assert "option-scaffold create alpha_lab -y" in result.stdout
    assert "option-scaffold create alpha_lab --preset ema-cross -d .\\projects" in result.stdout
    assert "项目输出父目录；最终会生成到 <destination>/<name>/。" in result.stdout
    assert "按能力组显式开启功能，可重复传入；适合非交互模式精确控制。" in result.stdout
    assert "按二级子能力显式关闭，可重复传入；用于更细粒度裁剪。" in result.stdout
    assert "跳过目录覆盖类操作的二次确认；仅在确认目标目录可被修改时使用。" in result.stdout


def test_init_command_generates_strategy_scaffold(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["init", "ema_breakout", "--destination", str(tmp_path)],
    )

    created_dir = tmp_path / "ema_breakout"

    assert result.exit_code == 0
    assert created_dir.exists()
    assert (created_dir / "strategy_contract.toml").exists()
    assert (created_dir / "tests" / "test_contracts.py").exists()


def test_create_command_generates_project_workspace(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["create", "alpha_lab", "--destination", str(tmp_path), "-y"],
    )

    created_dir = tmp_path / "alpha_lab"
    config = tomllib.loads((created_dir / "config" / "strategy_config.toml").read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert created_dir.exists()
    assert (created_dir / "src" / "strategies" / "alpha_lab" / "indicator_service.py").exists()
    assert (created_dir / "tests" / "strategies" / "alpha_lab" / "test_contracts.py").exists()
    assert config["strategy_contracts"]["indicator_service"] == (
        "src.strategies.alpha_lab.indicator_service:AlphaLabIndicatorService"
    )
    assert "项目脚手架已生成完成。" in result.stdout
    assert f"- 项目根目录：{created_dir}" in result.stdout
    assert "- 策略包：src/strategies/alpha_lab" in result.stdout
    assert "- 主配置：" in result.stdout
    assert "cd alpha_lab" in result.stdout
    assert "option-scaffold validate --config config/strategy_config.toml" in result.stdout
    assert "option-scaffold run --config config/strategy_config.toml" in result.stdout

    readme = (created_dir / "README.md").read_text(encoding="utf-8")
    assert "cd alpha_lab" in readme
    assert "option-scaffold validate --config config/strategy_config.toml" in readme
    assert "option-scaffold run --config config/strategy_config.toml" in readme


def test_create_command_uses_alpha_lab_as_default_name_when_omitted(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["create", "--destination", str(tmp_path), "-y"],
    )

    created_dir = tmp_path / "alpha_lab"

    assert result.exit_code == 0
    assert created_dir.exists()
    assert "cd alpha_lab" in result.stdout


def test_create_command_supports_nested_option_flags(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "create",
            "option_lab",
            "--destination",
            str(tmp_path),
            "--preset",
            "custom",
            "--with",
            "greeks-risk",
            "--with",
            "hedging",
            "--with-option",
            "vega-hedging",
            "--without-option",
            "delta-hedging",
            "--no-interactive",
        ],
    )

    created_dir = tmp_path / "option_lab"
    config = tomllib.loads((created_dir / "config" / "strategy_config.toml").read_text(encoding="utf-8"))

    assert result.exit_code == 0
    assert config["service_activation"]["vega_hedging"] is True
    assert config["service_activation"]["delta_hedging"] is False


def test_create_command_rejects_missing_nested_option_dependencies(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "create",
            "bad_dependency",
            "--destination",
            str(tmp_path),
            "--preset",
            "custom",
            "--with-option",
            "vega-hedging",
            "--no-interactive",
        ],
    )

    assert result.exit_code == 2
    assert "依赖" in result.stdout or "依赖" in result.stderr
    assert "建议" in result.stdout or "建议" in result.stderr
    assert "--with-option greeks-calculator" in result.stdout or "--with-option greeks-calculator" in result.stderr


def test_create_command_rejects_semantic_mutex_options(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "create",
            "bad_mutex",
            "--destination",
            str(tmp_path),
            "--preset",
            "custom",
            "--with-option",
            "greeks-calculator",
            "--with-option",
            "delta-hedging",
            "--with-option",
            "vega-hedging",
            "--no-interactive",
        ],
    )

    assert result.exit_code == 2
    assert "不能同时启用" in result.stdout or "不能同时启用" in result.stderr
    assert "建议" in result.stdout or "建议" in result.stderr


def test_create_command_rejects_delta_neutral_option_selector_combo(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "create",
            "bad_delta_neutral",
            "--destination",
            str(tmp_path),
            "--preset",
            "delta-neutral",
            "--with-option",
            "option-selector",
            "--no-interactive",
        ],
    )

    assert result.exit_code == 2
    assert "不兼容" in result.stdout or "不兼容" in result.stderr
    assert "建议" in result.stdout or "建议" in result.stderr
    assert "--preset custom" in result.stdout or "--preset custom" in result.stderr


def test_run_command_forwards_arguments_to_legacy_main() -> None:
    config_path = str(Path("config/strategy_config.toml"))
    override_path = str(Path("config/timeframe/5m.toml"))
    log_dir = str(Path("data/logs/demo"))

    with patch("src.main.main.main", return_value=0) as mock_main:
        result = runner.invoke(
            app,
            [
                "run",
                "--mode",
                "daemon",
                "--config",
                "config/strategy_config.toml",
                "--override-config",
                "config/timeframe/5m.toml",
                "--log-level",
                "DEBUG",
                "--log-dir",
                "data/logs/demo",
                "--no-ui",
                "--paper",
            ],
        )

    assert result.exit_code == 0
    mock_main.assert_called_once_with(
        [
            "--mode",
            "daemon",
            "--config",
            config_path,
            "--override-config",
            override_path,
            "--log-level",
            "DEBUG",
            "--log-dir",
            log_dir,
            "--no-ui",
            "--paper",
        ]
    )


def test_backtest_command_forwards_arguments_to_legacy_main() -> None:
    config_path = str(Path("config/strategy_config.toml"))

    with patch("src.backtesting.cli.main", return_value=0) as mock_main:
        result = runner.invoke(
            app,
            [
                "backtest",
                "--config",
                "config/strategy_config.toml",
                "--start",
                "2025-01-01",
                "--end",
                "2025-03-01",
                "--capital",
                "500000",
                "--rate",
                "0.0001",
                "--slippage",
                "0.5",
                "--size",
                "100",
                "--pricetick",
                "0.1",
                "--no-chart",
            ],
        )

    assert result.exit_code == 0
    mock_main.assert_called_once_with(
        [
            "--config",
            config_path,
            "--start",
            "2025-01-01",
            "--end",
            "2025-03-01",
            "--capital",
            "500000",
            "--rate",
            "0.0001",
            "--slippage",
            "0.5",
            "--size",
            "100",
            "--pricetick",
            "0.1",
            "--no-chart",
        ]
    )


def test_validate_command_reports_success_for_default_config() -> None:
    result = runner.invoke(app, ["validate"])

    assert result.exit_code == 0
    assert "校验通过" in result.stdout
    assert "[OK] 策略配置文件" in result.stdout


def test_validate_command_rejects_inverted_date_range() -> None:
    result = runner.invoke(
        app,
        ["validate", "--start", "2025-03-01", "--end", "2025-01-01"],
    )

    assert result.exit_code == 2
    assert "开始日期 2025-03-01 晚于结束日期 2025-01-01" in result.stdout


def test_examples_command_lists_available_examples() -> None:
    result = runner.invoke(app, ["examples"])

    assert result.exit_code == 0
    assert "ema_cross_example" in result.stdout
    assert "iv_rank_example" in result.stdout


def test_examples_command_shows_selected_example_details() -> None:
    result = runner.invoke(app, ["examples", "ema_cross_example"])

    assert result.exit_code == 0
    assert "示例: ema_cross_example" in result.stdout
    assert "strategy_contract.toml" in result.stdout


def test_doctor_command_reports_summary() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "诊断完成" in result.stdout
    assert "[OK] Python" in result.stdout
