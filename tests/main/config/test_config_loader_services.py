from __future__ import annotations

from pathlib import Path

from src.main.config.config_loader import ConfigLoader


def test_load_strategy_config_merges_shared_service_sections(tmp_path: Path) -> None:
    base = tmp_path / "base.toml"
    override = tmp_path / "override.toml"
    base.write_text(
        """
        [service_activation]
        option_selector = false

        [observability]
        decision_journal_maxlen = 50

        [[strategies]]
        class_name = "StrategyEntry"
        strategy_name = "demo"

        [strategies.setting]
        max_positions = 3
        """,
        encoding="utf-8",
    )
    override.write_text(
        """
        [service_activation]
        option_selector = true

        [observability]
        decision_journal_maxlen = 99

        [timeframe]
        name = "15m"
        bar_window = 15
        bar_interval = "MINUTE"
        """,
        encoding="utf-8",
    )

    merged = ConfigLoader.load_strategy_config(str(base), str(override))

    assert merged["service_activation"]["option_selector"] is True
    assert merged["observability"]["decision_journal_maxlen"] == 99
    assert merged["strategies"][0]["strategy_name"] == "demo_15m"
    assert merged["strategies"][0]["setting"]["bar_window"] == 15


def test_import_from_string_supports_colon_and_dot() -> None:
    assert ConfigLoader.import_from_string("pathlib:Path") is Path
    assert ConfigLoader.import_from_string("pathlib.Path") is Path


def test_extract_shared_strategy_settings_returns_contracts_and_observability() -> None:
    config = {
        "strategy_contracts": {"indicator_service": "pkg.mod:Cls"},
        "service_activation": {"option_chain": True},
        "observability": {"decision_journal_maxlen": 123},
    }

    shared = ConfigLoader.extract_shared_strategy_settings(config)

    assert shared["strategy_contracts"]["indicator_service"] == "pkg.mod:Cls"
    assert shared["service_activation"]["option_chain"] is True
    assert shared["observability"]["decision_journal_maxlen"] == 123
