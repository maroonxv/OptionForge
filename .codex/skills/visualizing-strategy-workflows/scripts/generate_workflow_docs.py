#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from pathlib import Path
import subprocess
import sys
from typing import Callable, Iterable, NamedTuple, Sequence


DEFAULT_APPLICATION_DIRS = (
    Path("src/application"),
    Path("src/strategy/application"),
)

CORE_WORKFLOW_DIAGRAMS = (
    "architecture",
    "activity",
    "branch-decision",
    "data-lineage",
    "sequence",
)

BRIDGE_DIAGRAMS = (
    "architecture",
    "activity",
    "data-lineage",
    "sequence",
)

DIAGRAM_SECTION_TITLES = {
    "architecture": "架构图",
    "activity": "活动图",
    "branch-decision": "分支判定图",
    "data-lineage": "数据血缘图",
    "sequence": "顺序图",
    "state": "状态图",
    "timing": "时间驱动图",
    "exception-path": "异常/降级路径图",
    "object-structure": "对象结构图",
    "open-activity": "开仓子流程活动图",
    "close-activity": "平仓子流程活动图",
    "symbol-sources": "目标合约来源汇聚图",
}


class WorkflowArtifacts(NamedTuple):
    source_path: Path
    slug: str
    kind: str
    markdown_path: Path
    diagram_paths: dict[str, Path]
    chart_paths: dict[str, Path]


def resolve_application_dir(project_root: Path, application_dir: Path | None = None) -> Path:
    if application_dir is not None:
        resolved = application_dir if application_dir.is_absolute() else project_root / application_dir
        if not resolved.exists():
            raise FileNotFoundError(f"Application directory not found: {resolved}")
        return resolved

    for candidate in DEFAULT_APPLICATION_DIRS:
        resolved = project_root / candidate
        if resolved.exists():
            return resolved

    searched = ", ".join(str(path) for path in DEFAULT_APPLICATION_DIRS)
    raise FileNotFoundError(f"Could not find an application directory under: {searched}")


def discover_workflow_files(
    project_root: Path,
    application_dir: Path | None = None,
    workflow_pattern: str = "*_workflow.py",
) -> list[Path]:
    resolved_dir = resolve_application_dir(project_root, application_dir)
    return sorted(
        path
        for path in resolved_dir.rglob(workflow_pattern)
        if path.is_file() and path.suffix == ".py"
    )


def discover_optional_bridge_files(
    project_root: Path,
    application_dir: Path | None = None,
) -> list[Path]:
    resolved_dir = resolve_application_dir(project_root, application_dir)
    return sorted(
        path
        for path in resolved_dir.rglob("*.py")
        if path.is_file()
        and "bridge" in path.stem.lower()
        and not path.stem.endswith("_workflow")
    )


def slugify_source(source_path: Path) -> str:
    return source_path.stem.replace("_", "-")


def ensure_parent_dirs(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_source_text(source_path: Path) -> str:
    return source_path.read_text(encoding="utf-8")


def parse_module(source_path: Path) -> ast.Module:
    return ast.parse(read_source_text(source_path), filename=str(source_path))


def extract_method_names(source_path: Path) -> list[str]:
    tree = parse_module(source_path)
    class_nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if not class_nodes:
        return []
    methods: list[str] = []
    for node in class_nodes[0].body:
        if isinstance(node, ast.FunctionDef):
            methods.append(node.name)
    return methods


def extract_primary_entrypoint(source_path: Path) -> str:
    tree = parse_module(source_path)
    class_nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if not class_nodes:
        return source_path.stem

    container = class_nodes[0]
    for node in container.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("on_"):
            return f"{container.name}.{node.name}"
    for node in container.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            return f"{container.name}.{node.name}"
    return container.name


def choose_workflow_diagrams(source_path: Path) -> tuple[str, ...]:
    lower_source = read_source_text(source_path).lower()
    lower_stem = source_path.stem.lower()
    method_names = extract_method_names(source_path)
    diagrams = list(CORE_WORKFLOW_DIAGRAMS)

    has_stateful_markers = any(
        token in lower_source
        for token in (
            "warming_up",
            "backtesting",
            "subscription_enabled",
            "_stale_unsubscribe_since",
            "_signal_temp_symbols",
            "ttl",
            "rollover_check_done",
        )
    ) or any(name in {"on_start", "on_stop"} for name in method_names)
    if has_stateful_markers:
        diagrams.append("state")

    has_timing_markers = any(
        token in lower_source
        for token in ("time.", "datetime", "ttl", "timer", "refresh", "hour", "minute")
    )
    if has_timing_markers:
        diagrams.append("timing")

    try_count = sum(1 for node in ast.walk(parse_module(source_path)) if isinstance(node, ast.Try))
    has_exception_paths = "lifecycle" in lower_stem or try_count >= 3
    if has_exception_paths:
        diagrams.append("exception-path")

    has_object_structure = "state" in lower_stem or "create_snapshot" in lower_source or "to_snapshot" in lower_source
    if has_object_structure:
        diagrams.append("object-structure")

    if "_run_open_pipeline" in lower_source or "check_open_signal" in lower_source:
        diagrams.append("open-activity")
    if "_run_close_pipeline" in lower_source or "check_close_signal" in lower_source:
        diagrams.append("close-activity")

    symbol_collectors = [name for name in method_names if "collect" in name and "symbol" in name]
    if len(symbol_collectors) >= 2 or "signal_symbols" in lower_source:
        diagrams.append("symbol-sources")

    if "lifecycle" in lower_stem and "state" not in diagrams:
        diagrams.append("state")
    if "subscription" in lower_stem and "state" not in diagrams:
        diagrams.append("state")
    if "subscription" in lower_stem and "timing" not in diagrams:
        diagrams.append("timing")
    if "state" in lower_stem and "object-structure" not in diagrams:
        diagrams.append("object-structure")

    deduped: list[str] = []
    for diagram in diagrams:
        if diagram not in deduped:
            deduped.append(diagram)
    return tuple(deduped)


def choose_bridge_diagrams(_: Path) -> tuple[str, ...]:
    return BRIDGE_DIAGRAMS


def build_artifacts(
    source_path: Path,
    docs_root: Path,
    kind: str,
    diagram_kinds: Sequence[str],
) -> WorkflowArtifacts:
    slug = slugify_source(source_path)
    workflows_dir = docs_root / "workflows"
    code_dir = docs_root / "plantuml" / "code"
    chart_dir = docs_root / "plantuml" / "chart"
    diagram_paths = {
        diagram_kind: code_dir / f"{slug}-{diagram_kind}.puml"
        for diagram_kind in diagram_kinds
    }
    chart_paths = {
        diagram_kind: chart_dir / f"{slug}-{diagram_kind}.svg"
        for diagram_kind in diagram_kinds
    }
    return WorkflowArtifacts(
        source_path=source_path,
        slug=slug,
        kind=kind,
        markdown_path=workflows_dir / f"{slug}.md",
        diagram_paths=diagram_paths,
        chart_paths=chart_paths,
    )


def write_if_missing(path: Path, content: str) -> None:
    ensure_parent_dirs(path)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def render_doc_title(artifacts: WorkflowArtifacts) -> str:
    if artifacts.kind == "bridge":
        return f"桥接编排：{artifacts.source_path.stem}"
    return f"工作流：{artifacts.source_path.stem}"


def render_markdown_skeleton(project_root: Path, artifacts: WorkflowArtifacts) -> str:
    source_rel = artifacts.source_path.relative_to(project_root).as_posix()
    entrypoint = extract_primary_entrypoint(artifacts.source_path)
    lines = [
        f"# {render_doc_title(artifacts)}",
        "",
        f"- 源文件: `{source_rel}`",
        f"- 主入口: `{entrypoint}`",
        "",
        "## 职责说明",
        "",
        "TODO：用 2-4 句话概括这个编排文件负责的业务流程、边界和输出。",
        "",
    ]

    ordered_keys = list(artifacts.diagram_paths.keys())
    for diagram_key in ordered_keys:
        title = DIAGRAM_SECTION_TITLES[diagram_key]
        rel_chart = Path("..") / "plantuml" / "chart" / artifacts.chart_paths[diagram_key].name
        lines.extend(
            [
                f"## {title}",
                "",
                f"![{artifacts.source_path.stem} {title}]({rel_chart.as_posix()})",
                "",
            ]
        )

    lines.extend(
        [
            "## 关键结论",
            "",
            "- 关键协作者: TODO",
            "- 主要输入: TODO",
            "- 主要输出: TODO",
            "- 关键中间对象: TODO",
            "",
        ]
    )
    return "\n".join(lines)


def render_architecture_template(artifacts: WorkflowArtifacts) -> str:
    return f"""@startuml
title {artifacts.source_path.stem} - 架构图
skinparam shadowing false
skinparam componentStyle rectangle

package "编排入口" {{
  component "{artifacts.source_path.stem}" as workflow
}}

package "关键协作者" {{
  component "待补充协作者" as collaborator
}}

workflow --> collaborator : 调用 / 依赖
@enduml
"""


def render_activity_template(artifacts: WorkflowArtifacts, diagram_key: str) -> str:
    title = DIAGRAM_SECTION_TITLES[diagram_key]
    start_label = "进入编排"
    if diagram_key == "open-activity":
        start_label = "进入开仓子流程"
    elif diagram_key == "close-activity":
        start_label = "进入平仓子流程"
    return f"""@startuml
title {artifacts.source_path.stem} - {title}
start
:{start_label};
:读取上下文 / 输入;
:执行关键步骤;
if (是否继续?) then (是)
  :进入下一阶段;
else (否)
  :提前结束;
endif
stop
@enduml
"""


def render_branch_decision_template(artifacts: WorkflowArtifacts) -> str:
    return f"""@startuml
title {artifacts.source_path.stem} - 分支判定图
start
:进入判定阶段;
if (条件一成立?) then (是)
  :进入分支一;
elseif (条件二成立?)
  :进入分支二;
else
  :走默认分支 / 提前返回;
endif
stop
@enduml
"""


def render_data_lineage_template(artifacts: WorkflowArtifacts) -> str:
    return f"""@startuml
title {artifacts.source_path.stem} - 数据血缘图
skinparam shadowing false

rectangle "输入对象\\nTODO" as input
rectangle "{artifacts.source_path.stem}\\n编排处理" as workflow
rectangle "中间对象\\nTODO" as middle
rectangle "输出对象\\nTODO" as output

input --> workflow : 消费
workflow --> middle : 生成 / 变换
middle --> output : 输出
@enduml
"""


def render_sequence_template(artifacts: WorkflowArtifacts) -> str:
    return f"""@startuml
title {artifacts.source_path.stem} - 顺序图
autonumber

participant "调用方" as caller
participant "{artifacts.source_path.stem}" as workflow
participant "关键协作者" as collaborator

caller -> workflow : 调用主入口
workflow -> collaborator : 发起关键调用
collaborator --> workflow : 返回结果
workflow --> caller : 返回结果 / 结束
@enduml
"""


def render_state_template(artifacts: WorkflowArtifacts) -> str:
    return f"""@startuml
title {artifacts.source_path.stem} - 状态图
[*] --> 初始
初始 --> 处理中 : 进入流程
处理中 --> 等待 : 条件未满足 / 暂缓
处理中 --> 完成 : 流程结束
等待 --> 处理中 : 条件恢复
完成 --> [*]
@enduml
"""


def render_timing_template(artifacts: WorkflowArtifacts) -> str:
    return f"""@startuml
title {artifacts.source_path.stem} - 时间驱动图
robust "定时触发" as timer
robust "{artifacts.source_path.stem}" as workflow

@0
timer is 空闲
workflow is 等待

@1
timer is 触发
workflow is 刷新 / 重算

@2
timer is 空闲
workflow is 等待
@enduml
"""


def render_exception_path_template(artifacts: WorkflowArtifacts) -> str:
    return f"""@startuml
title {artifacts.source_path.stem} - 异常/降级路径图
start
:执行主路径;
if (发生异常?) then (是)
  :记录日志;
  :执行降级 / 跳过 / 回退;
else (否)
  :继续主路径;
endif
stop
@enduml
"""


def render_object_structure_template(artifacts: WorkflowArtifacts) -> str:
    return f"""@startuml
title {artifacts.source_path.stem} - 对象结构图
class "输入聚合快照" as input
class "{artifacts.source_path.stem}" as workflow
class "输出结构 / 持久化对象" as output

workflow --> input : 读取
workflow --> output : 组装
@enduml
"""


def render_symbol_sources_template(artifacts: WorkflowArtifacts) -> str:
    return f"""@startuml
title {artifacts.source_path.stem} - 目标合约来源汇聚图
skinparam shadowing false

rectangle "持仓来源" as position_source
rectangle "挂单来源" as order_source
rectangle "主力合约来源" as active_source
rectangle "临时信号来源" as temp_source
rectangle "{artifacts.source_path.stem}" as workflow
rectangle "目标订阅集合" as target_symbols

position_source --> workflow
order_source --> workflow
active_source --> workflow
temp_source --> workflow
workflow --> target_symbols : 汇聚 / 过滤 / 去重
@enduml
"""


def render_diagram_template(artifacts: WorkflowArtifacts, diagram_key: str) -> str:
    if diagram_key == "architecture":
        return render_architecture_template(artifacts)
    if diagram_key in {"activity", "open-activity", "close-activity"}:
        return render_activity_template(artifacts, diagram_key)
    if diagram_key == "branch-decision":
        return render_branch_decision_template(artifacts)
    if diagram_key == "data-lineage":
        return render_data_lineage_template(artifacts)
    if diagram_key == "sequence":
        return render_sequence_template(artifacts)
    if diagram_key == "state":
        return render_state_template(artifacts)
    if diagram_key == "timing":
        return render_timing_template(artifacts)
    if diagram_key == "exception-path":
        return render_exception_path_template(artifacts)
    if diagram_key == "object-structure":
        return render_object_structure_template(artifacts)
    if diagram_key == "symbol-sources":
        return render_symbol_sources_template(artifacts)
    raise ValueError(f"Unsupported diagram key: {diagram_key}")


def scaffold_artifacts(project_root: Path, artifacts: WorkflowArtifacts) -> WorkflowArtifacts:
    write_if_missing(artifacts.markdown_path, render_markdown_skeleton(project_root, artifacts))
    for diagram_key, diagram_path in artifacts.diagram_paths.items():
        write_if_missing(diagram_path, render_diagram_template(artifacts, diagram_key))
    return artifacts


def scaffold_workflow_docs(
    project_root: Path,
    docs_root: Path,
    workflow_files: Sequence[Path],
) -> list[WorkflowArtifacts]:
    resolved_docs_root = docs_root if docs_root.is_absolute() else project_root / docs_root
    generated: list[WorkflowArtifacts] = []
    for workflow_file in workflow_files:
        artifacts = build_artifacts(
            source_path=workflow_file,
            docs_root=resolved_docs_root,
            kind="workflow",
            diagram_kinds=choose_workflow_diagrams(workflow_file),
        )
        generated.append(scaffold_artifacts(project_root, artifacts))
    return generated


def scaffold_bridge_docs(
    project_root: Path,
    docs_root: Path,
    bridge_files: Sequence[Path],
) -> list[WorkflowArtifacts]:
    resolved_docs_root = docs_root if docs_root.is_absolute() else project_root / docs_root
    generated: list[WorkflowArtifacts] = []
    for bridge_file in bridge_files:
        artifacts = build_artifacts(
            source_path=bridge_file,
            docs_root=resolved_docs_root,
            kind="bridge",
            diagram_kinds=choose_bridge_diagrams(bridge_file),
        )
        generated.append(scaffold_artifacts(project_root, artifacts))
    return generated


def render_global_collaboration_template(
    workflow_files: Sequence[Path],
    bridge_files: Sequence[Path],
) -> str:
    workflow_nodes = "\n".join(
        f'component "{path.stem}" as {slugify_source(path).replace("-", "_")}'
        for path in workflow_files
    )
    bridge_nodes = "\n".join(
        f'component "{path.stem}" as {slugify_source(path).replace("-", "_")}'
        for path in bridge_files
    )
    workflow_links = "\n".join(
        f'StrategyEntry --> {slugify_source(path).replace("-", "_")}'
        for path in workflow_files
    )
    bridge_links = "\n".join(
        f'StrategyEntry --> {slugify_source(path).replace("-", "_")}'
        for path in bridge_files
    )
    return f"""@startuml
title Workflow 全局协作图
skinparam shadowing false
skinparam componentStyle rectangle

component "StrategyEntry" as StrategyEntry
{workflow_nodes}
{bridge_nodes}

{workflow_links}
{bridge_links}
@enduml
"""


def find_strategy_entry_file(project_root: Path) -> Path | None:
    candidates = (
        project_root / "src" / "strategy" / "strategy_entry.py",
        project_root / "src" / "strategy_entry.py",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def extract_dispatch_edges(strategy_entry_path: Path | None) -> list[tuple[str, str]]:
    if strategy_entry_path is None:
        return []
    tree = parse_module(strategy_entry_path)
    class_nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if not class_nodes:
        return []

    edges: list[tuple[str, str]] = []
    for node in class_nodes[0].body:
        if not isinstance(node, ast.FunctionDef):
            continue
        method_name = node.name
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                target = inner.func.value
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    edges.append((method_name, target.attr))
                    break
    return edges


def render_event_dispatch_template(project_root: Path) -> str:
    strategy_entry_path = find_strategy_entry_file(project_root)
    edges = extract_dispatch_edges(strategy_entry_path)
    if not edges:
        return """@startuml
title 事件入口分发图
skinparam shadowing false

rectangle "事件入口" as event_entry
rectangle "应用层编排" as workflow

event_entry --> workflow : 待补充分发关系
@enduml
"""

    nodes = "\n".join(
        f'rectangle "{target}" as {target}'
        for target in dict.fromkeys(target for _, target in edges)
    )
    links = "\n".join(
        f'rectangle "{source}" as {source}\n{source} --> {target}'
        for source, target in edges
    )
    return f"""@startuml
title 事件入口分发图
skinparam shadowing false

{nodes}
{links}
@enduml
"""


def render_object_infrastructure_map_template(
    workflow_files: Sequence[Path],
    bridge_files: Sequence[Path],
) -> str:
    nodes = []
    for label in ("aggregate", "gateway", "service", "monitor", "repository"):
        nodes.append(f'rectangle "{label}" as {label}')
    workflow_nodes = "\n".join(
        f'component "{path.stem}" as {slugify_source(path).replace("-", "_")}'
        for path in [*workflow_files, *bridge_files]
    )
    links = "\n".join(
        f'{slugify_source(path).replace("-", "_")} --> aggregate\n'
        f'{slugify_source(path).replace("-", "_")} --> gateway\n'
        f'{slugify_source(path).replace("-", "_")} --> service'
        for path in workflow_files
    )
    bridge_links = "\n".join(
        f'{slugify_source(path).replace("-", "_")} --> aggregate\n'
        f'{slugify_source(path).replace("-", "_")} --> gateway'
        for path in bridge_files
    )
    return f"""@startuml
title 核心对象与基础设施映射图
skinparam shadowing false
skinparam componentStyle rectangle

{workflow_nodes}
{chr(10).join(nodes)}
{links}
{bridge_links}
@enduml
"""


def scaffold_repository_overview(
    project_root: Path,
    docs_root: Path,
    workflow_files: Sequence[Path],
    bridge_files: Sequence[Path],
) -> None:
    resolved_docs_root = docs_root if docs_root.is_absolute() else project_root / docs_root
    workflows_dir = resolved_docs_root / "workflows"
    code_dir = resolved_docs_root / "plantuml" / "code"

    overview_specs = {
        "workflow-global-collaboration": render_global_collaboration_template(workflow_files, bridge_files),
        "workflow-event-dispatch": render_event_dispatch_template(project_root),
        "workflow-object-infrastructure-map": render_object_infrastructure_map_template(workflow_files, bridge_files),
    }
    for name, content in overview_specs.items():
        write_if_missing(code_dir / f"{name}.puml", content)

    lines = [
        "# Workflow 可视化总览",
        "",
        "本页汇总应用层 workflow 与可选桥接编排文件的全局图谱入口。",
        "",
        "## 仓库级总览图",
        "",
        "### 全局协作图",
        "",
        "![Workflow 全局协作图](../plantuml/chart/workflow-global-collaboration.svg)",
        "",
        "### 事件入口分发图",
        "",
        "![事件入口分发图](../plantuml/chart/workflow-event-dispatch.svg)",
        "",
        "### 核心对象与基础设施映射图",
        "",
        "![核心对象与基础设施映射图](../plantuml/chart/workflow-object-infrastructure-map.svg)",
        "",
        "## Workflow 文档",
        "",
    ]
    for workflow_file in workflow_files:
        slug = slugify_source(workflow_file)
        lines.append(f"- [{workflow_file.stem} 工作流](./{slug}.md)")

    if bridge_files:
        lines.extend(["", "## 可选桥接编排文档", ""])
        for bridge_file in bridge_files:
            slug = slugify_source(bridge_file)
            lines.append(f"- [{bridge_file.stem} 桥接编排](./{slug}.md)")

    write_if_missing(workflows_dir / "index.md", "\n".join(lines) + "\n")


def iter_renderable_sources(*artifact_groups: Iterable[WorkflowArtifacts], docs_root: Path | None = None) -> list[Path]:
    if docs_root is not None:
        resolved_root = docs_root if docs_root.is_absolute() else docs_root
        return sorted((resolved_root / "plantuml" / "code").glob("*.puml"))

    source_files: list[Path] = []
    for artifact_group in artifact_groups:
        for artifacts in artifact_group:
            source_files.extend(artifacts.diagram_paths.values())
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in source_files:
        if path not in seen:
            deduped.append(path)
            seen.add(path)
    return deduped


def render_plantuml_sources(
    source_files: Sequence[Path],
    chart_dir: Path,
    runner: Callable[..., object] | None = None,
) -> None:
    chart_dir.mkdir(parents=True, exist_ok=True)
    run = runner or subprocess.run
    for source_file in source_files:
        run(
            ["plantuml", "-tsvg", "-o", str(chart_dir), str(source_file)],
            check=True,
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold and optionally render workflow visualization docs.",
    )
    parser.add_argument("--project-root", required=True, help="Repository root")
    parser.add_argument("--application-dir", help="Explicit application directory override")
    parser.add_argument("--docs-root", default="docs", help="Documentation root relative to project root")
    parser.add_argument("--workflow-pattern", default="*_workflow.py", help="File glob used to detect workflow files")
    parser.add_argument("--render", action="store_true", help="Render discovered PlantUML sources to SVG")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()
    application_dir = Path(args.application_dir) if args.application_dir else None
    docs_root = Path(args.docs_root)

    workflow_files = discover_workflow_files(
        project_root=project_root,
        application_dir=application_dir,
        workflow_pattern=args.workflow_pattern,
    )
    if not workflow_files:
        raise FileNotFoundError("No workflow files matched the requested pattern.")

    bridge_files = discover_optional_bridge_files(
        project_root=project_root,
        application_dir=application_dir,
    )

    workflow_artifacts = scaffold_workflow_docs(
        project_root=project_root,
        docs_root=docs_root,
        workflow_files=workflow_files,
    )
    scaffold_bridge_docs(
        project_root=project_root,
        docs_root=docs_root,
        bridge_files=bridge_files,
    )
    scaffold_repository_overview(
        project_root=project_root,
        docs_root=docs_root,
        workflow_files=workflow_files,
        bridge_files=bridge_files,
    )

    if args.render:
        resolved_docs_root = docs_root if docs_root.is_absolute() else project_root / docs_root
        render_plantuml_sources(
            source_files=sorted((resolved_docs_root / "plantuml" / "code").glob("*.puml")),
            chart_dir=resolved_docs_root / "plantuml" / "chart",
        )

    print(
        "Generated workflow docs for "
        f"{len(workflow_artifacts)} workflow file(s) and {len(bridge_files)} bridge file(s)."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
