from __future__ import annotations

from pathlib import Path

from src.main.main import build_parser
from src.main.scaffold.config_params import DEFAULT_RUNTIME_CONFIG


def test_runtime_defaults_use_logs_runner() -> None:
    args = build_parser().parse_args([])

    assert args.log_dir == "logs/runner"
    assert DEFAULT_RUNTIME_CONFIG["log_dir"] == "logs/runner"


def test_docker_compose_and_env_example_define_split_log_mounts() -> None:
    compose = Path("deploy/docker-compose.yml").read_text(encoding="utf-8")
    env_example = Path("deploy/.env.example").read_text(encoding="utf-8")

    assert "HOST_LOGS_DIR" in env_example
    assert "APP_LOG_DIR=/app/logs/runner" in env_example
    assert "MONITOR_LOG_DIR=/app/logs/monitor" in env_example
    assert "VNPY_LOG_DIR=/app/logs/vnpy" in env_example

    assert "${HOST_LOGS_DIR:-../logs}/runner:/app/logs/runner" in compose
    assert "${HOST_LOGS_DIR:-../logs}/monitor:/app/logs/monitor" in compose
    assert "${HOST_LOGS_DIR:-../logs}/postgresql:/var/log/postgresql" in compose
    assert "logging_collector=on" in compose
