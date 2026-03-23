from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys

from vnpy.trader.logger import format as VNPY_LOG_FORMAT
from vnpy.trader.logger import level as DEFAULT_VNPY_LOG_LEVEL
from vnpy.trader.logger import logger as vnpy_logger
from vnpy.trader.setting import SETTINGS


def resolve_vnpy_log_dir(log_dir: str | None = None) -> Path:
    raw_dir = log_dir or os.getenv("VNPY_LOG_DIR") or "logs/vnpy"
    return Path(raw_dir)


def build_vnpy_log_path(
    log_dir: str | Path,
    *,
    current_date: date | None = None,
) -> Path:
    current_date = current_date or date.today()
    return Path(log_dir) / f"vt_{current_date.strftime('%Y%m%d')}.log"


def configure_vnpy_logging(
    log_dir: str | None = None,
    *,
    current_date: date | None = None,
) -> Path:
    target_dir = resolve_vnpy_log_dir(log_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = build_vnpy_log_path(target_dir, current_date=current_date)

    SETTINGS["log.console"] = True
    SETTINGS["log.file"] = True

    vnpy_logger.remove()
    vnpy_logger.add(
        sink=sys.stdout,
        level=DEFAULT_VNPY_LOG_LEVEL,
        format=VNPY_LOG_FORMAT,
    )
    vnpy_logger.add(
        sink=file_path,
        level=DEFAULT_VNPY_LOG_LEVEL,
        format=VNPY_LOG_FORMAT,
    )

    return file_path
