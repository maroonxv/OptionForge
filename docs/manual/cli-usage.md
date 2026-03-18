# CLI Usage Guide

This guide describes the current AGENT-first CLI workflow for the source-checkout entrypoint `python -m src.cli.app`.

It is intentionally aligned with `AGENTS_FOCUS.md`, `strategy_spec.toml`, `.focus/context.json`, and the generated acceptance assets.

## Recommended AGENT Entry Point

The recommended AGENT entry point is:

```powershell
python -m src.cli.app forge --json
```

Run commands from the repository root when working from source.
If the package is installed into the active environment, the equivalent short alias is `optionforge ...`.

Use `forge` when you need to:

- create a new AGENT-ready workspace
- refresh `strategy_spec.toml`
- regenerate focus navigation assets
- regenerate `tests/TEST.md`
- run the default AGENT verification loop

Lower-level commands still exist:

- `create`
- `focus init`
- `focus refresh`

Use them only when you need targeted low-level behavior rather than the default AGENT workflow.

## AGENT Asset Model

AGENTs should consume repository assets in this order:

1. `strategy_spec.toml`
2. `.focus/context.json`
3. `.focus/*.md`
4. `tests/TEST.md`
5. `artifacts/validate/latest.json`
6. `artifacts/backtest/latest.json`

Interpretation:

- `strategy_spec.toml` defines high-level intent
- `.focus/context.json` defines the current machine-readable working surface
- `.focus/*.md` are human-readable navigation companions
- `tests/TEST.md` records the test plan and latest acceptance summary
- `artifacts/*/latest.json` record the latest structured command outputs

## Structured Output Rules

Prefer structured output by default.

### JSON envelope

Use `--json` on single-response commands:

```powershell
python -m src.cli.app forge --json
python -m src.cli.app focus show --json
python -m src.cli.app validate --json
python -m src.cli.app doctor --json
python -m src.cli.app examples --json
```

### NDJSON streams

Use `--json` on long-running commands to receive NDJSON events:

```powershell
python -m src.cli.app run --json
python -m src.cli.app backtest --json
```

## Canonical AGENT Loop

The canonical AGENT loop is:

```powershell
python -m src.cli.app forge --json
python -m src.cli.app validate --json
python -m src.cli.app focus test --json
```

Add execution evidence only when needed:

```powershell
python -m src.cli.app backtest --json
python -m src.cli.app run --json
```

## Common Command Patterns

### Refresh AGENT assets

```powershell
python -m src.cli.app forge --json
```

### Inspect current context

```powershell
python -m src.cli.app focus show --json
```

### Validate current config

```powershell
python -m src.cli.app validate --config config/strategy_config.toml --json
```

### Run focus verification

```powershell
python -m src.cli.app focus test --json
```

### Run backtest evidence

```powershell
python -m src.cli.app backtest --config config/strategy_config.toml --start 2025-01-01 --end 2025-03-01 --no-chart --json
```

## Editing Boundary Rule

Before editing code:

1. inspect `.focus/context.json`
2. confirm the editable surface
3. avoid ad hoc repo traversal
4. widen scope only when the task cannot be completed inside the current editable surface

Do not treat `.focus/*.md` as the only AGENT-readable assets. They are companions to `.focus/context.json`, not replacements for it.

## Verification Rule

Default verification order:

1. `validate --json`
2. `focus test --json`
3. `backtest --json` only when behavior or parameter effects must be evidenced
4. `run --json` only for runtime workflows

## Notes For Human Operators

Plain-text output remains available, but AGENT workflows should prefer structured output. If documentation or generated AGENT assets drift, update the generator/source layer and rerun:

```powershell
python -m src.cli.app forge
```
