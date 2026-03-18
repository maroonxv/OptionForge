from __future__ import annotations

from pathlib import Path
import importlib.util
import subprocess
from typing import Any

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"


def load_script_module(script_name: str) -> Any:
    script_path = SCRIPTS_DIR / script_name
    spec = importlib.util.spec_from_file_location(
        f"option_schema_designer.{script_name.replace('.py', '')}",
        script_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_render_diagram_uses_java_pipe_and_writes_svg(tmp_path: Path) -> None:
    source_file = tmp_path / "docs" / "plantuml" / "code" / "E-R" / "covered-call-er.puml"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("@startchen\nentity \"策略\" as STRAT {}\n@endchen\n", encoding="utf-8")
    output_dir = tmp_path / "docs" / "plantuml" / "charts"
    jar_path = tmp_path / "tools" / "plantuml.jar"
    jar_path.parent.mkdir(parents=True)
    jar_path.write_text("fake-jar", encoding="utf-8")

    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="<svg>diagram</svg>",
            stderr="",
        )

    module = load_script_module("render_er_diagram.py")
    output_path = module.render_diagram(
        source_file=source_file,
        output_dir=output_dir,
        jar_path=jar_path,
        java_path="java",
        runner=fake_runner,
    )

    assert output_path == output_dir / "covered-call-er.svg"
    assert output_path.read_text(encoding="utf-8") == "<svg>diagram</svg>"
    assert calls == [
        (
            ["java", "-jar", str(jar_path), "-pipe", "-tsvg"],
            {
                "input": source_file.read_text(encoding="utf-8"),
                "capture_output": True,
                "text": True,
                "check": False,
            },
        )
    ]


def test_render_diagram_rejects_missing_plantuml_jar(tmp_path: Path) -> None:
    module = load_script_module("render_er_diagram.py")
    source_file = tmp_path / "docs" / "plantuml" / "code" / "E-R" / "wheel-er.puml"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("@startchen\n@endchen\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="PlantUML jar"):
        module.render_diagram(
            source_file=source_file,
            output_dir=tmp_path / "docs" / "plantuml" / "charts",
            jar_path=tmp_path / "missing" / "plantuml.jar",
            java_path="java",
        )


def test_render_diagram_reports_missing_java() -> None:
    module = load_script_module("render_er_diagram.py")

    with pytest.raises(RuntimeError, match="Java"):
        module.resolve_java_path(which=lambda _: None)


def test_update_schema_doc_adds_er_section_with_relative_image_path(tmp_path: Path) -> None:
    doc_path = tmp_path / "docs" / "design" / "schema" / "covered-call.md"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_text(
        "# Covered Call\n\n## 设计目标与上下文\n\n说明。\n",
        encoding="utf-8",
    )
    image_path = tmp_path / "docs" / "plantuml" / "charts" / "covered-call-er.svg"
    image_path.parent.mkdir(parents=True)
    image_path.write_text("<svg/>", encoding="utf-8")

    module = load_script_module("update_schema_doc.py")
    module.update_schema_doc(
        doc_path=doc_path,
        image_path=image_path,
        title="Covered Call 核心 E-R 图",
    )

    content = doc_path.read_text(encoding="utf-8")
    assert "## E-R 图" in content
    assert "![Covered Call 核心 E-R 图](../../plantuml/charts/covered-call-er.svg)" in content
    assert content.count("## E-R 图") == 1


def test_update_schema_doc_replaces_existing_block_without_duplication(tmp_path: Path) -> None:
    doc_path = tmp_path / "docs" / "design" / "schema" / "iron-condor.md"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_text(
        (
            "# Iron Condor\n\n"
            "## E-R 图\n\n"
            "<!-- option-schema-designer:er-diagram:start -->\n"
            "![旧图](../../plantuml/charts/old.svg)\n"
            "<!-- option-schema-designer:er-diagram:end -->\n\n"
            "## 实体字典\n\n"
            "内容。\n"
        ),
        encoding="utf-8",
    )
    image_path = tmp_path / "docs" / "plantuml" / "charts" / "iron-condor-er.svg"
    image_path.parent.mkdir(parents=True)
    image_path.write_text("<svg/>", encoding="utf-8")

    module = load_script_module("update_schema_doc.py")
    module.update_schema_doc(
        doc_path=doc_path,
        image_path=image_path,
        title="Iron Condor 主 E-R 图",
    )
    module.update_schema_doc(
        doc_path=doc_path,
        image_path=image_path,
        title="Iron Condor 主 E-R 图",
    )

    content = doc_path.read_text(encoding="utf-8")
    assert content.count("## E-R 图") == 1
    assert content.count("![Iron Condor 主 E-R 图]") == 1
    assert "old.svg" not in content
