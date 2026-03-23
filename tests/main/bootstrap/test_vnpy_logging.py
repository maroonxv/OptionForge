from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import Mock, patch

from src.main.bootstrap import vnpy_logging


def test_build_vnpy_log_path_uses_daily_filename(tmp_path) -> None:
    path = vnpy_logging.build_vnpy_log_path(tmp_path, current_date=date(2026, 3, 23))

    assert path == tmp_path / "vt_20260323.log"


def test_configure_vnpy_logging_writes_to_requested_directory() -> None:
    fake_logger = SimpleNamespace(remove=Mock(), add=Mock())

    with (
        patch.object(vnpy_logging, "vnpy_logger", fake_logger),
        patch.object(vnpy_logging, "VNPY_LOG_FORMAT", "format"),
        patch.object(vnpy_logging, "DEFAULT_VNPY_LOG_LEVEL", 20),
    ):
        log_path = vnpy_logging.configure_vnpy_logging(
            log_dir="logs/vnpy",
            current_date=date(2026, 3, 23),
        )

    sinks = [call.kwargs["sink"] for call in fake_logger.add.call_args_list]

    assert log_path == Path("logs/vnpy") / "vt_20260323.log"
    assert sys.stdout in sinks
    assert Path("logs/vnpy") / "vt_20260323.log" in sinks
