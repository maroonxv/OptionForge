---
name: visualizing-strategy-workflows
description: Use when Claude Code needs to analyze Python application-layer orchestration files such as `*_workflow.py`, extract collaborators, data flow, and call order, and generate visual workflow docs with PlantUML and SVG artifacts.
argument-hint: "[--application-dir path] [docs-root]"
---

# Visualizing Strategy Workflows

Turn workflow orchestration code into short markdown docs backed by PlantUML. Keep the diagrams concrete and the prose brief.

## Load Order

1. Resolve the application directory: explicit override first, then `src/application`, then `src/strategy/application`.
2. Read [markdown-template.md](references/markdown-template.md) before editing workflow docs.
3. Read [diagram-conventions.md](references/diagram-conventions.md) before writing PlantUML.
4. Read [diagram-selection.md](references/diagram-selection.md) only when deciding whether an extra diagram, especially a state diagram, is justified.

## Workflow

1. Scan only `*_workflow.py` files. Treat bridge-like helper files as optional secondary artifacts.
2. Run the scaffold script:

```bash
python .claude/skills/visualizing-strategy-workflows/scripts/generate_workflow_docs.py --project-root <repo> --application-dir <optional-app-dir> --docs-root docs --render
```

3. Treat generated markdown and `.puml` files as scaffolding only. Read the real workflow source and replace placeholders with actual collaborators, branch points, data lineage, and call order.
4. Keep architecture, data flow, and sequence coverage for every workflow. Add state, timing, exception-path, or object-structure diagrams only when the code actually shows those behaviors.
5. Keep outputs in:
   - `docs/workflows/<workflow-slug>.md`
   - `docs/plantuml/code/`
   - `docs/plantuml/chart/`
6. If rendering is blocked because `plantuml` or Java is unavailable, keep the `.puml` sources, report the blocker, and do not fake SVG output.

## Output Rules

- Keep prose short: responsibility, source path, primary entrypoint, collaborators, inputs, and outputs.
- Use diagrams to explain orchestration. Do not repeat the code line by line.
- Ignore non-workflow files unless a diagram needs them as collaborators.
- Treat repository-specific workflow names as examples, not hardcoded assumptions.
