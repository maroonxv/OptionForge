from __future__ import annotations

from pathlib import Path
import importlib.util
from typing import Any

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "generate_workflow_docs.py"
)


def load_script_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "visualizing_strategy_workflows.generate_workflow_docs",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_discover_workflow_files_honors_explicit_application_dir(tmp_path: Path) -> None:
    explicit_app_dir = tmp_path / "src" / "custom_application"
    fallback_app_dir = tmp_path / "src" / "strategy" / "application"
    explicit_app_dir.mkdir(parents=True)
    fallback_app_dir.mkdir(parents=True)

    explicit_workflow = explicit_app_dir / "alpha_workflow.py"
    explicit_workflow.write_text("class AlphaWorkflow:\n    pass\n", encoding="utf-8")
    (explicit_app_dir / "helper.py").write_text("pass\n", encoding="utf-8")
    (explicit_app_dir / "event_bridge.py").write_text("pass\n", encoding="utf-8")
    fallback_workflow = fallback_app_dir / "beta_workflow.py"
    fallback_workflow.write_text("class BetaWorkflow:\n    pass\n", encoding="utf-8")

    module = load_script_module()

    discovered = module.discover_workflow_files(
        project_root=tmp_path,
        application_dir=explicit_app_dir,
        workflow_pattern="*_workflow.py",
    )

    assert discovered == [explicit_workflow]


def test_scaffold_outputs_use_standardized_names(tmp_path: Path) -> None:
    application_dir = tmp_path / "src" / "strategy" / "application"
    application_dir.mkdir(parents=True)
    workflow_file = application_dir / "market_workflow.py"
    workflow_file.write_text(
        (
            "class MarketWorkflow:\n"
            "    def on_tick(self, tick):\n"
            "        return None\n\n"
            "    def _run_open_pipeline(self):\n"
            "        return None\n\n"
            "    def _run_close_pipeline(self):\n"
            "        return None\n\n"
            "    def timer_refresh(self):\n"
            "        return None\n"
        ),
        encoding="utf-8",
    )

    module = load_script_module()

    generated = module.scaffold_workflow_docs(
        project_root=tmp_path,
        docs_root=tmp_path / "docs",
        workflow_files=[workflow_file],
    )

    assert len(generated) == 1
    outputs = generated[0]
    assert outputs.slug == "market-workflow"
    assert outputs.markdown_path == tmp_path / "docs" / "workflows" / "market-workflow.md"
    assert outputs.diagram_paths["architecture"] == tmp_path / "docs" / "plantuml" / "code" / "market-workflow-architecture.puml"
    assert outputs.diagram_paths["activity"] == tmp_path / "docs" / "plantuml" / "code" / "market-workflow-activity.puml"
    assert outputs.diagram_paths["branch-decision"] == tmp_path / "docs" / "plantuml" / "code" / "market-workflow-branch-decision.puml"
    assert outputs.diagram_paths["data-lineage"] == tmp_path / "docs" / "plantuml" / "code" / "market-workflow-data-lineage.puml"
    assert outputs.diagram_paths["sequence"] == tmp_path / "docs" / "plantuml" / "code" / "market-workflow-sequence.puml"
    assert outputs.diagram_paths["open-activity"] == tmp_path / "docs" / "plantuml" / "code" / "market-workflow-open-activity.puml"
    assert outputs.diagram_paths["close-activity"] == tmp_path / "docs" / "plantuml" / "code" / "market-workflow-close-activity.puml"
    assert outputs.diagram_paths["timing"] == tmp_path / "docs" / "plantuml" / "code" / "market-workflow-timing.puml"
    assert outputs.chart_paths["activity"] == tmp_path / "docs" / "plantuml" / "chart" / "market-workflow-activity.svg"
    assert outputs.chart_paths["open-activity"] == tmp_path / "docs" / "plantuml" / "chart" / "market-workflow-open-activity.svg"
    assert outputs.chart_paths["timing"] == tmp_path / "docs" / "plantuml" / "chart" / "market-workflow-timing.svg"

    assert outputs.markdown_path.exists()
    assert outputs.diagram_paths["architecture"].exists()
    assert outputs.diagram_paths["activity"].exists()
    assert outputs.diagram_paths["branch-decision"].exists()
    assert outputs.diagram_paths["data-lineage"].exists()
    assert outputs.diagram_paths["sequence"].exists()
    assert outputs.diagram_paths["open-activity"].exists()
    assert outputs.diagram_paths["close-activity"].exists()
    assert outputs.diagram_paths["timing"].exists()


def test_markdown_scaffold_uses_first_public_method_when_no_on_hook_exists(tmp_path: Path) -> None:
    application_dir = tmp_path / "src" / "strategy" / "application"
    application_dir.mkdir(parents=True)
    workflow_file = application_dir / "subscription_workflow.py"
    workflow_file.write_text(
        (
            "class SubscriptionWorkflow:\n"
            "    def __init__(self, entry):\n"
            "        self.entry = entry\n\n"
            "    def init_subscription_management(self):\n"
            "        return None\n"
        ),
        encoding="utf-8",
    )

    module = load_script_module()
    generated = module.scaffold_workflow_docs(
        project_root=tmp_path,
        docs_root=tmp_path / "docs",
        workflow_files=[workflow_file],
    )

    markdown = generated[0].markdown_path.read_text(encoding="utf-8")
    assert "- 主入口: `SubscriptionWorkflow.init_subscription_management`" in markdown
    assert "## 职责说明" in markdown
    assert "## 活动图" in markdown
    assert "## 分支判定图" in markdown
    assert "## 数据血缘图" in markdown
    assert "## 顺序图" in markdown


def test_scaffold_repository_overview_creates_chinese_index_and_overview_diagrams(tmp_path: Path) -> None:
    application_dir = tmp_path / "src" / "strategy" / "application"
    application_dir.mkdir(parents=True)
    lifecycle = application_dir / "lifecycle_workflow.py"
    market = application_dir / "market_workflow.py"
    lifecycle.write_text("class LifecycleWorkflow:\n    def on_init(self):\n        return None\n", encoding="utf-8")
    market.write_text("class MarketWorkflow:\n    def on_tick(self, tick):\n        return None\n", encoding="utf-8")

    module = load_script_module()
    workflows = [lifecycle, market]
    module.scaffold_repository_overview(
        project_root=tmp_path,
        docs_root=tmp_path / "docs",
        workflow_files=workflows,
        bridge_files=[],
    )

    index_path = tmp_path / "docs" / "workflows" / "index.md"
    overview_path = tmp_path / "docs" / "plantuml" / "code" / "workflow-global-collaboration.puml"
    dispatch_path = tmp_path / "docs" / "plantuml" / "code" / "workflow-event-dispatch.puml"
    object_map_path = tmp_path / "docs" / "plantuml" / "code" / "workflow-object-infrastructure-map.puml"

    assert index_path.exists()
    assert overview_path.exists()
    assert dispatch_path.exists()
    assert object_map_path.exists()

    index_content = index_path.read_text(encoding="utf-8")
    assert "# Workflow 可视化总览" in index_content
    assert "## 仓库级总览图" in index_content
    assert "## Workflow 文档" in index_content
    assert "全局协作图" in index_content
    assert "事件入口分发图" in index_content
    assert "核心对象与基础设施映射图" in index_content


def test_optional_bridge_file_is_scaffolded_when_present(tmp_path: Path) -> None:
    application_dir = tmp_path / "src" / "strategy" / "application"
    application_dir.mkdir(parents=True)
    bridge_file = application_dir / "event_bridge.py"
    bridge_file.write_text(
        (
            "class EventBridge:\n"
            "    def on_order(self, order):\n"
            "        return None\n"
        ),
        encoding="utf-8",
    )

    module = load_script_module()
    bridge_files = module.discover_optional_bridge_files(
        project_root=tmp_path,
        application_dir=application_dir,
    )
    assert bridge_files == [bridge_file]

    generated = module.scaffold_bridge_docs(
        project_root=tmp_path,
        docs_root=tmp_path / "docs",
        bridge_files=bridge_files,
    )
    assert len(generated) == 1
    assert generated[0].markdown_path == tmp_path / "docs" / "workflows" / "event-bridge.md"
    assert generated[0].diagram_paths["activity"] == tmp_path / "docs" / "plantuml" / "code" / "event-bridge-activity.puml"
    assert generated[0].diagram_paths["data-lineage"] == tmp_path / "docs" / "plantuml" / "code" / "event-bridge-data-lineage.puml"
    markdown = generated[0].markdown_path.read_text(encoding="utf-8")
    assert "# 桥接编排：event_bridge" in markdown
    assert "## 职责说明" in markdown


def test_state_workflow_keeps_lightweight_diagram_bundle(tmp_path: Path) -> None:
    application_dir = tmp_path / "src" / "strategy" / "application"
    application_dir.mkdir(parents=True)
    workflow_file = application_dir / "state_workflow.py"
    workflow_file.write_text(
        (
            "class StateWorkflow:\n"
            "    def create_snapshot(self):\n"
            "        return {'target': 'snapshot'}\n\n"
            "    def record_snapshot(self):\n"
            "        return None\n"
        ),
        encoding="utf-8",
    )

    module = load_script_module()
    generated = module.scaffold_workflow_docs(
        project_root=tmp_path,
        docs_root=tmp_path / "docs",
        workflow_files=[workflow_file],
    )

    diagrams = set(generated[0].diagram_paths)
    assert diagrams == {
        "architecture",
        "activity",
        "branch-decision",
        "data-lineage",
        "sequence",
        "object-structure",
    }


def test_render_generated_diagrams_calls_plantuml_with_output_dir(tmp_path: Path) -> None:
    code_dir = tmp_path / "docs" / "plantuml" / "code"
    chart_dir = tmp_path / "docs" / "plantuml" / "chart"
    code_dir.mkdir(parents=True)
    chart_dir.mkdir(parents=True)

    first = code_dir / "lifecycle-workflow-architecture.puml"
    second = code_dir / "lifecycle-workflow-sequence.puml"
    first.write_text("@startuml\n@enduml\n", encoding="utf-8")
    second.write_text("@startuml\n@enduml\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_runner(command: list[str], **_: Any) -> None:
        calls.append(command)

    module = load_script_module()
    module.render_plantuml_sources(
        source_files=[first, second],
        chart_dir=chart_dir,
        runner=fake_runner,
    )

    assert calls == [
        ["plantuml", "-tsvg", "-o", str(chart_dir), str(first)],
        ["plantuml", "-tsvg", "-o", str(chart_dir), str(second)],
    ]
