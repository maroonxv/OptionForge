"""整仓库脚手架创建命令。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import typer

from src.cli.common import EXIT_CODE_VALIDATION, abort, display_path, flag_enabled
from src.main.scaffold.models import CapabilityKey, CapabilityOptionKey, CreateOptions
from src.main.scaffold.project import create_project_scaffold


CREATE_COMMAND_HELP = "创建整仓库级期权策略项目脚手架；支持交互式向导，也支持通过 flags 一次性生成。"
CREATE_COMMAND_EXAMPLES = (
    "常用示例：\n"
    "  option-scaffold create alpha_lab\n"
    "  option-scaffold create alpha_lab -y\n"
    "  option-scaffold create alpha_lab --preset ema-cross -d .\\projects\n"
    "  option-scaffold create alpha_lab --preset custom --with hedging --with-option vega-hedging --no-interactive"
)
CREATE_NAME_HELP = "项目名称；省略时会进入交互式向导询问。"
CREATE_DESTINATION_HELP = "项目输出父目录；最终会生成到 <destination>/<name>/。"
CREATE_PRESET_HELP = "策略预设；可选 custom、ema-cross、iv-rank、delta-neutral。省略时可在向导中选择。"
CREATE_WITH_HELP = "按能力组显式开启功能，可重复传入；适合非交互模式精确控制。"
CREATE_WITHOUT_HELP = "按能力组显式关闭功能，可重复传入；适合在预设基础上做裁剪。"
CREATE_WITH_OPTION_HELP = "按二级子能力显式开启，可重复传入；用于更细粒度定制。"
CREATE_WITHOUT_OPTION_HELP = "按二级子能力显式关闭，可重复传入；用于更细粒度裁剪。"
CREATE_FORCE_HELP = "跳过目录覆盖类操作的二次确认；仅在确认目标目录可被修改时使用。"
CREATE_CLEAR_HELP = "目标目录非空时先清空再生成；会删除目录中的现有文件。"
CREATE_OVERWRITE_HELP = "目标目录非空时保留目录，仅覆盖本次生成的同名冲突文件。"
CREATE_DEFAULT_HELP = "跳过提问，直接使用默认预设与默认能力组合生成。"
CREATE_NO_INTERACTIVE_HELP = "禁用交互向导；仅按显式 flags 与默认规则执行。"


def _to_capabilities(values: Iterable[str]) -> tuple[CapabilityKey, ...]:
    return tuple(CapabilityKey(value) for value in values)


def _to_options(values: Iterable[str]) -> tuple[CapabilityOptionKey, ...]:
    return tuple(CapabilityOptionKey(value) for value in values)


def command(
    name: str | None = typer.Argument(None, help=CREATE_NAME_HELP),
    destination: Path = typer.Option(Path("."), "--destination", "-d", help=CREATE_DESTINATION_HELP),
    preset: str | None = typer.Option(None, "--preset", help=CREATE_PRESET_HELP),
    with_: tuple[str, ...] = typer.Option((), "--with", help=CREATE_WITH_HELP),
    without: tuple[str, ...] = typer.Option((), "--without", help=CREATE_WITHOUT_HELP),
    with_option: tuple[str, ...] = typer.Option((), "--with-option", help=CREATE_WITH_OPTION_HELP),
    without_option: tuple[str, ...] = typer.Option((), "--without-option", help=CREATE_WITHOUT_OPTION_HELP),
    force: str = typer.Option("", "--force", flag_value="1", show_default=False, help=CREATE_FORCE_HELP),
    clear: str = typer.Option("", "--clear", flag_value="1", show_default=False, help=CREATE_CLEAR_HELP),
    overwrite: str = typer.Option("", "--overwrite", flag_value="1", show_default=False, help=CREATE_OVERWRITE_HELP),
    use_default: str = typer.Option("", "-y", "--default", flag_value="1", show_default=False, help=CREATE_DEFAULT_HELP),
    no_interactive: str = typer.Option("", "--no-interactive", flag_value="1", show_default=False, help=CREATE_NO_INTERACTIVE_HELP),
) -> None:
    """创建整仓库级期权策略项目脚手架。"""
    try:
        plan = create_project_scaffold(
            CreateOptions(
                name=name,
                destination=destination,
                preset=preset,
                include_capabilities=_to_capabilities(with_),
                exclude_capabilities=_to_capabilities(without),
                include_options=_to_options(with_option),
                exclude_options=_to_options(without_option),
                use_default=flag_enabled(use_default),
                no_interactive=flag_enabled(no_interactive),
                force=flag_enabled(force),
                clear=flag_enabled(clear),
                overwrite=flag_enabled(overwrite),
            )
        )
    except (FileExistsError, ValueError) as exc:
        abort(str(exc), exit_code=EXIT_CODE_VALIDATION)

    typer.echo("项目脚手架已生成完成。")
    typer.echo(f"- 项目根目录：{display_path(plan.project_root)}")
    typer.echo(f"- 策略包：src/strategies/{plan.strategy_slug}")
    typer.echo(f"- 主配置：{display_path(plan.project_root / 'config' / 'strategy_config.toml')}")
    typer.echo("- 下一步：进入项目目录后，优先检查主配置并按需调整能力开关。")
