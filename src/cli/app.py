from __future__ import annotations

from pathlib import Path
import sys

import click
import typer.main as typer_main
import typer.testing as typer_testing

from src import __version__
from src.cli.commands.backtest import command as backtest_command
from src.cli.commands.create import (
    CREATE_CLEAR_HELP,
    CREATE_COMMAND_EXAMPLES,
    CREATE_COMMAND_HELP,
    CREATE_DEFAULT_HELP,
    CREATE_DESTINATION_HELP,
    CREATE_FORCE_HELP,
    CREATE_NO_INTERACTIVE_HELP,
    CREATE_OVERWRITE_HELP,
    CREATE_PRESET_HELP,
    CREATE_SET_HELP,
    CREATE_WITH_HELP,
    CREATE_WITH_OPTION_HELP,
    CREATE_WITHOUT_HELP,
    CREATE_WITHOUT_OPTION_HELP,
    command as create_command,
)
from src.cli.commands.doctor import command as doctor_command
from src.cli.commands.examples import command as examples_command
from src.cli.commands.forge import command as forge_command
from src.cli.commands.focus import (
    FOCUS_COMMAND_HELP,
    FOCUS_INIT_HELP,
    FOCUS_PACK_CHOICES,
    FOCUS_REFRESH_HELP,
    FOCUS_SHOW_HELP,
    FOCUS_TEST_HELP,
    init_command as focus_init_command,
    refresh_command as focus_refresh_command,
    show_command as focus_show_command,
    test_command as focus_test_command,
)
from src.cli.commands.init import command as init_command
from src.cli.commands.run import LogLevel, RunMode, command as run_command
from src.cli.commands.validate import command as validate_command


def _version_option_callback(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    del param
    if not value or ctx.resilient_parsing:
        return

    click.echo(f"OptionForge {__version__}")
    ctx.exit()


def _supports_main_menu() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _should_enter_main_menu(ctx: click.Context) -> bool:
    return ctx.invoked_subcommand is None and _supports_main_menu()


def _prompt_main_menu_choice() -> int:
    click.echo("欢迎使用 OptionForge。")
    click.echo("主菜单：")
    click.echo("1. 创建策略工作区")
    click.echo("2. 查看示例")
    click.echo("3. 环境诊断")
    click.echo("4. 退出")
    return click.prompt("请选择操作", type=click.IntRange(1, 4), default=1, show_default=True)


def _run_main_menu_action(choice: int) -> None:
    if choice == 1:
        create_command(
            name=None,
            destination=Path("."),
            preset=None,
            with_=(),
            without=(),
            with_option=(),
            without_option=(),
            set_values=(),
            force="",
            clear="",
            overwrite="",
            use_default="",
            no_interactive="",
        )
        return
    if choice == 2:
        examples_command(name=None)
        return
    if choice == 3:
        doctor_command(strict="", check_db="")
        return


@click.group(
    name="optionforge",
    help="OptionForge 的统一命令入口，推荐先使用 focus 聚焦当前策略。",
    invoke_without_command=True,
)
@click.option(
    "--version",
    "-V",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_version_option_callback,
    help="显示版本并退出。",
)
@click.pass_context
def app(ctx: click.Context) -> None:
    """统一暴露初始化、运行、回测、校验与诊断命令。"""
    if ctx.invoked_subcommand is not None:
        return

    if _should_enter_main_menu(ctx):
        _run_main_menu_action(_prompt_main_menu_choice())
        ctx.exit()

    click.echo(ctx.get_help())
    ctx.exit()


@app.group("focus", help=FOCUS_COMMAND_HELP)
def focus_group() -> None:
    """AI-first focus 工作流。"""


@focus_group.command("init", help=FOCUS_INIT_HELP)
@click.argument("name")
@click.option("--trading-target", default="option-universe", show_default=True, help="策略交易标的。")
@click.option("--strategy-type", default="custom", show_default=True, help="策略类型标签。")
@click.option("--run-mode", default="standalone", show_default=True, help="默认运行模式。")
@click.option(
    "--pack",
    multiple=True,
    type=click.Choice(list(FOCUS_PACK_CHOICES), case_sensitive=False),
    help="显式启用的 pack；省略时默认启用全家桶。",
)
@click.option(
    "--without-pack",
    multiple=True,
    type=click.Choice(list(FOCUS_PACK_CHOICES), case_sensitive=False),
    help="显式关闭的 pack。",
)
@click.option("--force", is_flag=True, help="Manifest 已存在时允许覆盖。")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON。")
def focus_init_click(
    name: str,
    trading_target: str,
    strategy_type: str,
    run_mode: str,
    pack: tuple[str, ...],
    without_pack: tuple[str, ...],
    force: bool,
    json_output: bool,
) -> None:
    focus_init_command(
        name=name,
        trading_target=trading_target,
        strategy_type=strategy_type,
        run_mode=run_mode,
        pack=tuple(pack),
        without_pack=tuple(without_pack),
        force="1" if force else "",
        json_output=json_output,
    )


@focus_group.command("refresh", help=FOCUS_REFRESH_HELP)
@click.option("--strategy", default=None, help="可选；刷新指定策略并将其设为当前焦点。")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON。")
def focus_refresh_click(strategy: str | None, json_output: bool) -> None:
    focus_refresh_command(strategy=strategy, json_output=json_output)


@focus_group.command("show", help=FOCUS_SHOW_HELP)
@click.option("--strategy", default=None, help="可选；展示指定策略的焦点上下文。")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON。")
def focus_show_click(strategy: str | None, json_output: bool) -> None:
    focus_show_command(strategy=strategy, json_output=json_output)


@focus_group.command(
    "test",
    help=FOCUS_TEST_HELP,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--strategy", default=None, help="可选；运行指定策略的焦点测试集合。")
@click.option("--full", "run_full", is_flag=True, help="运行完整焦点测试集合，不应用 smoke 过滤。")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON。")
@click.pass_context
def focus_test_click(ctx: click.Context, strategy: str | None, run_full: bool, json_output: bool) -> None:
    focus_test_command(strategy=strategy, extra_args=tuple(ctx.args), full=run_full, json_output=json_output)


@app.command("create", help=f"{CREATE_COMMAND_HELP}\n\n\b\n{CREATE_COMMAND_EXAMPLES}")
@click.argument("name", required=False)
@click.option(
    "--destination",
    "-d",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("."),
    show_default=True,
    help=CREATE_DESTINATION_HELP,
)
@click.option(
    "--preset",
    type=click.Choice(["custom", "ema-cross", "iv-rank", "delta-neutral"], case_sensitive=False),
    default=None,
    help=CREATE_PRESET_HELP,
)
@click.option(
    "--with",
    "with_",
    multiple=True,
    type=click.Choice(
        ["selection", "position-sizing", "pricing", "greeks-risk", "execution", "hedging", "monitoring", "observability"],
        case_sensitive=False,
    ),
    help=CREATE_WITH_HELP,
)
@click.option(
    "--without",
    multiple=True,
    type=click.Choice(
        ["selection", "position-sizing", "pricing", "greeks-risk", "execution", "hedging", "monitoring", "observability"],
        case_sensitive=False,
    ),
    help=CREATE_WITHOUT_HELP,
)
@click.option(
    "--with-option",
    "with_option",
    multiple=True,
    type=click.Choice(
        [
            "future-selection",
            "option-chain",
            "option-selector",
            "position-sizing",
            "pricing-engine",
            "greeks-calculator",
            "portfolio-risk",
            "smart-order-executor",
            "advanced-order-scheduler",
            "delta-hedging",
            "vega-hedging",
            "monitoring",
            "decision-observability",
        ],
        case_sensitive=False,
    ),
    help=CREATE_WITH_OPTION_HELP,
)
@click.option(
    "--without-option",
    "without_option",
    multiple=True,
    type=click.Choice(
        [
            "future-selection",
            "option-chain",
            "option-selector",
            "position-sizing",
            "pricing-engine",
            "greeks-calculator",
            "portfolio-risk",
            "smart-order-executor",
            "advanced-order-scheduler",
            "delta-hedging",
            "vega-hedging",
            "monitoring",
            "decision-observability",
        ],
        case_sensitive=False,
    ),
    help=CREATE_WITHOUT_OPTION_HELP,
)
@click.option("--set", "set_values", multiple=True, help=CREATE_SET_HELP)
@click.option("--force", is_flag=True, help=CREATE_FORCE_HELP)
@click.option("--clear", is_flag=True, help=CREATE_CLEAR_HELP)
@click.option("--overwrite", is_flag=True, help=CREATE_OVERWRITE_HELP)
@click.option("-y", "--default", "use_default", is_flag=True, help=CREATE_DEFAULT_HELP)
@click.option("--no-interactive", is_flag=True, help=CREATE_NO_INTERACTIVE_HELP)
@click.option("--json", "json_output", is_flag=True, help="输出 JSON。")
def create_click(
    name: str | None,
    destination: Path,
    preset: str | None,
    with_: tuple[str, ...],
    without: tuple[str, ...],
    with_option: tuple[str, ...],
    without_option: tuple[str, ...],
    set_values: tuple[str, ...],
    force: bool,
    clear: bool,
    overwrite: bool,
    use_default: bool,
    no_interactive: bool,
    json_output: bool,
) -> None:
    create_command(
        name=name,
        destination=destination,
        preset=preset,
        with_=tuple(with_),
        without=tuple(without),
        with_option=tuple(with_option),
        without_option=tuple(without_option),
        set_values=tuple(set_values),
        force="1" if force else "",
        clear="1" if clear else "",
        overwrite="1" if overwrite else "",
        use_default="1" if use_default else "",
        no_interactive="1" if no_interactive else "",
        json_output=json_output,
    )


@app.command("forge", help="基于 strategy_spec.toml 串起脚手架、focus、测试计划与验证流程。")
@click.argument("name", required=False)
@click.option("--spec", type=click.Path(path_type=Path, dir_okay=False), default=None, help="显式指定 strategy_spec.toml。")
@click.option(
    "--destination",
    "-d",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("."),
    show_default=True,
    help=CREATE_DESTINATION_HELP,
)
@click.option(
    "--preset",
    type=click.Choice(["custom", "ema-cross", "iv-rank", "delta-neutral"], case_sensitive=False),
    default=None,
    help=CREATE_PRESET_HELP,
)
@click.option(
    "--with",
    "with_",
    multiple=True,
    type=click.Choice(
        ["selection", "position-sizing", "pricing", "greeks-risk", "execution", "hedging", "monitoring", "observability"],
        case_sensitive=False,
    ),
    help=CREATE_WITH_HELP,
)
@click.option(
    "--without",
    multiple=True,
    type=click.Choice(
        ["selection", "position-sizing", "pricing", "greeks-risk", "execution", "hedging", "monitoring", "observability"],
        case_sensitive=False,
    ),
    help=CREATE_WITHOUT_HELP,
)
@click.option(
    "--with-option",
    "with_option",
    multiple=True,
    type=click.Choice(
        [
            "future-selection",
            "option-chain",
            "option-selector",
            "position-sizing",
            "pricing-engine",
            "greeks-calculator",
            "portfolio-risk",
            "smart-order-executor",
            "advanced-order-scheduler",
            "delta-hedging",
            "vega-hedging",
            "monitoring",
            "decision-observability",
        ],
        case_sensitive=False,
    ),
    help=CREATE_WITH_OPTION_HELP,
)
@click.option(
    "--without-option",
    "without_option",
    multiple=True,
    type=click.Choice(
        [
            "future-selection",
            "option-chain",
            "option-selector",
            "position-sizing",
            "pricing-engine",
            "greeks-calculator",
            "portfolio-risk",
            "smart-order-executor",
            "advanced-order-scheduler",
            "delta-hedging",
            "vega-hedging",
            "monitoring",
            "decision-observability",
        ],
        case_sensitive=False,
    ),
    help=CREATE_WITHOUT_OPTION_HELP,
)
@click.option("--set", "set_values", multiple=True, help=CREATE_SET_HELP)
@click.option("--force", is_flag=True, help=CREATE_FORCE_HELP)
@click.option("--clear", is_flag=True, help=CREATE_CLEAR_HELP)
@click.option("--overwrite", is_flag=True, help=CREATE_OVERWRITE_HELP)
@click.option("--no-interactive", is_flag=True, help=CREATE_NO_INTERACTIVE_HELP)
@click.option("--json", "json_output", is_flag=True, help="输出 NDJSON。")
def forge_click(
    name: str | None,
    spec: Path | None,
    destination: Path,
    preset: str | None,
    with_: tuple[str, ...],
    without: tuple[str, ...],
    with_option: tuple[str, ...],
    without_option: tuple[str, ...],
    set_values: tuple[str, ...],
    force: bool,
    clear: bool,
    overwrite: bool,
    no_interactive: bool,
    json_output: bool,
) -> None:
    forge_command(
        name=name,
        spec=spec,
        destination=destination,
        preset=preset,
        with_=tuple(with_),
        without=tuple(without),
        with_option=tuple(with_option),
        without_option=tuple(without_option),
        set_values=tuple(set_values),
        force="1" if force else "",
        clear="1" if clear else "",
        overwrite="1" if overwrite else "",
        no_interactive="1" if no_interactive else "",
        json_output=json_output,
    )


@app.command("init", help="生成单策略开发骨架。")
@click.argument("name")
@click.option(
    "--destination",
    "-d",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("example"),
    show_default=True,
    help="输出目录，默认写入根目录下的 example/。",
)
@click.option("--force", is_flag=True, help="目录已存在时允许覆盖文件。")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON。")
def init_click(name: str, destination: Path, force: bool, json_output: bool) -> None:
    init_command(name=name, destination=destination, force="1" if force else "", json_output=json_output)


@app.command("run", help="启动策略主程序。")
@click.option(
    "--mode",
    type=click.Choice([item.value for item in RunMode], case_sensitive=False),
    default=RunMode.standalone.value,
    show_default=True,
    help="运行模式，可选 standalone 或 daemon。",
)
@click.option(
    "--config",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("config/strategy_config.toml"),
    show_default=True,
    help="策略主配置文件路径。",
)
@click.option(
    "--override-config",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="覆盖配置文件路径。",
)
@click.option(
    "--log-level",
    type=click.Choice([item.value for item in LogLevel], case_sensitive=False),
    default=LogLevel.info.value,
    show_default=True,
    help="日志级别。",
)
@click.option(
    "--log-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("logs/runner"),
    show_default=True,
    help="日志目录。",
)
@click.option("--no-ui", is_flag=True, help="无界面模式运行。")
@click.option("--paper", is_flag=True, help="启用模拟交易模式。")
@click.option("--json", "json_output", is_flag=True, help="输出 NDJSON。")
def run_click(
    mode: str,
    config: Path,
    override_config: Path | None,
    log_level: str,
    log_dir: Path,
    no_ui: bool,
    paper: bool,
    json_output: bool,
) -> None:
    run_command(
        mode=RunMode(mode),
        config=config,
        override_config=override_config,
        log_level=LogLevel(log_level),
        log_dir=log_dir,
        no_ui="1" if no_ui else "",
        paper="1" if paper else "",
        json_output=json_output,
    )


@app.command("backtest", help="启动回测入口。")
@click.option("--config", type=click.Path(path_type=Path, dir_okay=False), default=None, help="策略配置文件路径。")
@click.option("--start", default=None, help="开始日期，格式 YYYY-MM-DD。")
@click.option("--end", default=None, help="结束日期，格式 YYYY-MM-DD。")
@click.option("--capital", type=int, default=None, help="初始资金。")
@click.option("--rate", type=float, default=None, help="手续费率。")
@click.option("--slippage", type=float, default=None, help="滑点。")
@click.option("--size", type=int, default=None, help="合约乘数。")
@click.option("--pricetick", type=float, default=None, help="最小价格变动。")
@click.option("--no-chart", is_flag=True, help="不显示图表。")
@click.option("--json", "json_output", is_flag=True, help="输出 NDJSON。")
def backtest_click(
    config: Path | None,
    start: str | None,
    end: str | None,
    capital: int | None,
    rate: float | None,
    slippage: float | None,
    size: int | None,
    pricetick: float | None,
    no_chart: bool,
    json_output: bool,
) -> None:
    backtest_command(
        config=config,
        start=start,
        end=end,
        capital=capital,
        rate=rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        no_chart="1" if no_chart else "",
        json_output=json_output,
    )


@app.command("validate", help="校验策略配置、契约绑定与可选回测参数。")
@click.option(
    "--config",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("config/strategy_config.toml"),
    show_default=True,
    help="策略主配置文件路径。",
)
@click.option(
    "--override-config",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="可选的覆盖配置文件路径。",
)
@click.option("--start", default=None, help="可选回测开始日期，格式 YYYY-MM-DD。")
@click.option("--end", default=None, help="可选回测结束日期，格式 YYYY-MM-DD。")
@click.option("--capital", type=int, default=None, help="可选回测初始资金。")
@click.option("--rate", type=float, default=None, help="可选回测手续费率。")
@click.option("--slippage", type=float, default=None, help="可选回测滑点。")
@click.option("--size", type=int, default=None, help="可选回测合约乘数。")
@click.option("--pricetick", type=float, default=None, help="可选回测最小价格变动。")
@click.option("--no-chart", is_flag=True, help="校验时按回测语义处理图表开关。")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON。")
def validate_click(
    config: Path,
    override_config: Path | None,
    start: str | None,
    end: str | None,
    capital: int | None,
    rate: float | None,
    slippage: float | None,
    size: int | None,
    pricetick: float | None,
    no_chart: bool,
    json_output: bool,
) -> None:
    validate_command(
        config=config,
        override_config=override_config,
        start=start,
        end=end,
        capital=capital,
        rate=rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        no_chart="1" if no_chart else "",
        json_output=json_output,
    )


@app.command("examples", help="查看内置示例。")
@click.argument("name", required=False)
@click.option("--json", "json_output", is_flag=True, help="输出 JSON。")
def examples_click(name: str | None, json_output: bool) -> None:
    examples_command(name=name, json_output=json_output)


@app.command("doctor", help="诊断本地 CLI 环境与依赖。")
@click.option("--strict", is_flag=True, help="将警告也视为失败。")
@click.option("--check-db", is_flag=True, help="额外尝试连接数据库并执行 SELECT 1。")
@click.option("--json", "json_output", is_flag=True, help="输出 JSON。")
def doctor_click(strict: bool, check_db: bool, json_output: bool) -> None:
    doctor_command(strict="1" if strict else "", check_db="1" if check_db else "", json_output=json_output)


_original_get_command = typer_main.get_command


def _patched_get_command(target: object):
    if isinstance(target, click.Command):
        return target
    return _original_get_command(target)


typer_main.get_command = _patched_get_command
typer_testing._get_command = _patched_get_command


def main() -> None:
    """模块执行入口。"""
    app()


if __name__ == "__main__":
    main()
