"""
logging_setup.py - 日志处理模块

负责配置全局日志系统，支持控制台和按天切分的文件输出。
"""

from __future__ import annotations

from datetime import date
import logging
from pathlib import Path
import sys
from typing import Callable, Optional

from src.main.config.logging_config_loader import get_logger_level_overrides


def _safe_level(level_name: str) -> int:
    return getattr(logging, str(level_name).strip().upper(), logging.INFO)


def normalize_log_name(log_name: str) -> Path:
    raw_name = str(log_name).strip() or "runner"
    path = Path(raw_name)
    stem = path.stem or path.name or "runner"
    return path.with_name(stem)


def build_daily_log_path(
    log_dir: str | Path,
    log_name: str,
    *,
    current_date: date | None = None,
) -> Path:
    current_date = current_date or date.today()
    normalized_name = normalize_log_name(log_name)
    filename = f"{normalized_name.name}_{current_date.strftime('%Y%m%d')}.log"
    return Path(log_dir) / normalized_name.parent / filename


class DailyFileHandler(logging.Handler):
    terminator = "\n"

    def __init__(
        self,
        log_dir: str | Path,
        log_name: str,
        *,
        encoding: str = "utf-8",
        date_provider: Callable[[], date] | None = None,
    ) -> None:
        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_name = log_name
        self.encoding = encoding
        self.date_provider = date_provider or date.today
        self.current_path: Path | None = None
        self.stream = None
        self.createLock()

    @property
    def baseFilename(self) -> str:
        return str(self.current_path or self._resolve_path())

    def _resolve_path(self) -> Path:
        return build_daily_log_path(
            self.log_dir,
            self.log_name,
            current_date=self.date_provider(),
        )

    def _ensure_stream(self) -> None:
        target_path = self._resolve_path()
        if self.stream and self.current_path == target_path:
            return

        if self.stream:
            self.stream.close()

        target_path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = target_path.open("a", encoding=self.encoding)
        self.current_path = target_path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            self.acquire()
            try:
                self._ensure_stream()
                self.stream.write(message + self.terminator)
                self.flush()
            finally:
                self.release()
        except Exception:
            self.handleError(record)

    def flush(self) -> None:
        if self.stream and not self.stream.closed:
            self.stream.flush()

    def close(self) -> None:
        self.acquire()
        try:
            try:
                self.flush()
            finally:
                if self.stream:
                    self.stream.close()
                    self.stream = None
                    self.current_path = None
        finally:
            self.release()
        super().close()


def _apply_logger_level_overrides(logger_level_overrides: dict[str, str]) -> None:
    for logger_name, level_name in logger_level_overrides.items():
        level = _safe_level(level_name)
        target = logging.getLogger() if logger_name.lower() == "root" else logging.getLogger(logger_name)
        target.setLevel(level)


def setup_logging(
    log_level: str,
    log_dir: str,
    log_name: str = "runner",
    logging_config_path: Optional[str] = None,
) -> None:
    """
    配置日志系统。

    Args:
        log_level: 日志级别
        log_dir: 日志目录
        log_name: 日志文件名前缀
    """

    root = logging.getLogger()
    if root.handlers:
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)

    effective_level = _safe_level(log_level)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = DailyFileHandler(log_dir, log_name, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(effective_level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(effective_level)

    root.setLevel(effective_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    overrides = get_logger_level_overrides(logging_config_path)
    if overrides:
        _apply_logger_level_overrides(overrides)
