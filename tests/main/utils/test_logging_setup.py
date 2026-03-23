from __future__ import annotations

from datetime import date
import logging

from src.main.utils.logging_setup import DailyFileHandler, build_daily_log_path, setup_logging


def test_build_daily_log_path_appends_date_and_log_suffix(tmp_path) -> None:
    path = build_daily_log_path(tmp_path, "runner", current_date=date(2026, 3, 23))
    nested = build_daily_log_path(tmp_path, "nested/strategy.log", current_date=date(2026, 3, 23))

    assert path == tmp_path / "runner_20260323.log"
    assert nested == tmp_path / "nested" / "strategy_20260323.log"


def test_daily_file_handler_switches_files_without_deleting_previous(tmp_path) -> None:
    current_date = [date(2026, 3, 23)]
    handler = DailyFileHandler(
        tmp_path,
        "runner",
        date_provider=lambda: current_date[0],
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("tests.daily_file_handler")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    logger.info("day-one")
    current_date[0] = date(2026, 3, 24)
    logger.info("day-two")

    handler.close()
    logger.handlers.clear()

    first_day = tmp_path / "runner_20260323.log"
    second_day = tmp_path / "runner_20260324.log"

    assert first_day.exists()
    assert second_day.exists()
    assert "day-one" in first_day.read_text(encoding="utf-8")
    assert "day-two" in second_day.read_text(encoding="utf-8")


def test_setup_logging_uses_daily_file_handler(tmp_path) -> None:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    try:
        setup_logging("INFO", str(tmp_path), "runner")
        assert any(isinstance(handler, DailyFileHandler) for handler in root.handlers)
    finally:
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        for handler in original_handlers:
            root.addHandler(handler)
