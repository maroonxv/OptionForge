from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys


SKILL_ROOT = Path(__file__).resolve().parents[1]


def test_skill_bundle_contains_required_files() -> None:
    required_paths = [
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "agents" / "openai.yaml",
        SKILL_ROOT / "references" / "discovery-checklist.md",
        SKILL_ROOT / "references" / "schema-design-rules.md",
        SKILL_ROOT / "references" / "schema-doc-template.md",
        SKILL_ROOT / "references" / "peewee-mapping.md",
        SKILL_ROOT / "references" / "example-prompts.md",
        SKILL_ROOT / "scripts" / "render_er_diagram.py",
        SKILL_ROOT / "scripts" / "update_schema_doc.py",
    ]

    missing = [path for path in required_paths if not path.exists()]
    assert missing == []


def test_skill_markdown_mentions_plan_mode_and_phase_gates() -> None:
    content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "Plan Mode" in content
    assert "等待用户审阅" in content
    assert "Peewee" in content
    assert "docs/design/schema/<strategy-slug>.md" in content
    assert "docs/plantuml/code/E-R/<strategy-slug>-er.puml" in content


def test_references_cover_required_domain_and_doc_sections() -> None:
    checklist = (SKILL_ROOT / "references" / "discovery-checklist.md").read_text(encoding="utf-8")
    template = (SKILL_ROOT / "references" / "schema-doc-template.md").read_text(encoding="utf-8")
    mapping = (SKILL_ROOT / "references" / "peewee-mapping.md").read_text(encoding="utf-8")

    assert "执行与生命周期" in checklist
    assert "账户与风控" in checklist
    assert "新增实体候选" in checklist

    assert "## E-R 图" in template
    assert "## 实体字典" in template
    assert "## 范式设计说明" in template
    assert "## 待确认项与 Peewee 映射准备" in template

    assert "不生成 DDL" in mapping
    assert "Peewee Model" in mapping


def test_skill_bundle_passes_quick_validate() -> None:
    script_path = (
        Path.home()
        / ".codex"
        / "skills"
        / ".system"
        / "skill-creator"
        / "scripts"
        / "quick_validate.py"
    )
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    completed = subprocess.run(
        [sys.executable, str(script_path), str(SKILL_ROOT)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
