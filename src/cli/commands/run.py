from __future__ import annotations

from enum import Enum
from pathlib import Path

import typer

from src.cli.common import (
    EXIT_CODE_FAILURE,
    EXIT_CODE_VALIDATION,
    NdjsonEmitter,
    abort,
    append_flag,
    append_option,
    flag_enabled,
    invoke_legacy_main,
)


class RunMode(str, Enum):
    standalone = "standalone"
    daemon = "daemon"


class LogLevel(str, Enum):
    debug = "DEBUG"
    info = "INFO"
    warning = "WARNING"
    error = "ERROR"


def _build_argv(
    *,
    mode: RunMode,
    config: Path,
    override_config: Path | None,
    log_level: LogLevel,
    log_dir: Path,
    no_ui: str,
    paper: str,
) -> list[str]:
    argv: list[str] = []
    append_option(argv, "--mode", mode.value)
    append_option(argv, "--config", config)
    append_option(argv, "--override-config", override_config)
    append_option(argv, "--log-level", log_level.value)
    append_option(argv, "--log-dir", log_dir)
    append_flag(argv, "--no-ui", flag_enabled(no_ui))
    append_flag(argv, "--paper", flag_enabled(paper))
    return argv


def command(
    mode: RunMode = typer.Option(RunMode.standalone, "--mode", help="运行模式，standalone 或 daemon。"),
    config: Path = typer.Option(Path("config/strategy_config.toml"), "--config", help="策略配置文件路径。"),
    override_config: Path | None = typer.Option(None, "--override-config", help="覆盖配置文件路径。"),
    log_level: LogLevel = typer.Option(LogLevel.info, "--log-level", help="日志级别。"),
    log_dir: Path = typer.Option(Path("logs/runner"), "--log-dir", help="日志目录。"),
    no_ui: str = typer.Option("", "--no-ui", flag_value="1", show_default=False, help="无界面模式运行。"),
    paper: str = typer.Option("", "--paper", flag_value="1", show_default=False, help="启用模拟交易模式。"),
    json_output: bool = False,
) -> None:
    argv = _build_argv(
        mode=mode,
        config=config,
        override_config=override_config,
        log_level=log_level,
        log_dir=log_dir,
        no_ui=no_ui,
        paper=paper,
    )

    if not json_output:
        try:
            from src.main.main import main as legacy_main

            exit_code = invoke_legacy_main(legacy_main, argv)
        except ModuleNotFoundError as exc:
            abort(
                f"运行命令缺少依赖: {exc.name}。请先执行 `pip install -r requirements.txt`，然后运行 `pip install -e .`。",
                exit_code=EXIT_CODE_FAILURE,
            )
        except FileNotFoundError as exc:
            missing_path = exc.filename or str(exc)
            abort(f"运行命令找不到文件: {missing_path}", exit_code=EXIT_CODE_VALIDATION)
        except ValueError as exc:
            abort(str(exc), exit_code=EXIT_CODE_VALIDATION)
        except Exception as exc:
            abort(f"运行命令执行失败: {exc}", exit_code=EXIT_CODE_FAILURE)

        if exit_code:
            raise typer.Exit(code=exit_code)
        return

    emitter = NdjsonEmitter("run")
    emitter.start(
        mode=mode.value,
        config=str(config),
        override_config=str(override_config) if override_config else None,
        log_level=log_level.value,
        log_dir=str(log_dir),
        no_ui=flag_enabled(no_ui),
        paper=flag_enabled(paper),
    )
    emitter.phase(name="execute", status="start")
    emitter.artifact(path=log_dir, label="log-dir", kind="directory")
    try:
        from src.main.main import main as legacy_main

        exit_code = invoke_legacy_main(legacy_main, argv)
        emitter.phase(name="execute", status="complete", exit_code=exit_code)
        emitter.result(ok=exit_code == 0, exit_code=exit_code, log_dir=str(log_dir))
        if exit_code:
            raise typer.Exit(code=exit_code)
    except ModuleNotFoundError as exc:
        emitter.error(message=f"Missing dependency: {exc.name}", error_type="module_not_found")
        emitter.result(ok=False, exit_code=EXIT_CODE_FAILURE)
        raise typer.Exit(code=EXIT_CODE_FAILURE)
    except FileNotFoundError as exc:
        emitter.error(message=exc.filename or str(exc), error_type="file_not_found")
        emitter.result(ok=False, exit_code=EXIT_CODE_VALIDATION)
        raise typer.Exit(code=EXIT_CODE_VALIDATION)
    except ValueError as exc:
        emitter.error(message=str(exc), error_type="validation")
        emitter.result(ok=False, exit_code=EXIT_CODE_VALIDATION)
        raise typer.Exit(code=EXIT_CODE_VALIDATION)
    except typer.Exit:
        raise
    except Exception as exc:
        emitter.error(message=str(exc), error_type="exception")
        emitter.result(ok=False, exit_code=EXIT_CODE_FAILURE)
        raise typer.Exit(code=EXIT_CODE_FAILURE)
