from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.web import app as web_app


def test_create_app_initializes_monitor_file_logging(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MONITOR_LOG_DIR", str(tmp_path))

    with patch.object(web_app, "setup_logging") as setup_logging_mock:
        web_app.create_app(
            start_background_services=False,
            snapshot_reader=MagicMock(),
            state_reader=MagicMock(),
        )

    setup_logging_mock.assert_called_once_with("INFO", str(tmp_path), "monitor")
