from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_strategy_entry_no_longer_imports_optional_services() -> None:
    imports = _imports("src/strategy/strategy_entry.py")
    assert "src.strategy.domain.domain_service.selection.future_selection_service" not in imports
    assert "src.strategy.domain.domain_service.pricing.pricing_engine" not in imports


def test_lifecycle_workflow_no_longer_imports_optional_services() -> None:
    imports = _imports("src/strategy/application/lifecycle_workflow.py")
    assert "src.strategy.domain.domain_service.selection.future_selection_service" not in imports
    assert "src.strategy.domain.domain_service.pricing.pricing_engine" not in imports
