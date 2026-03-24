# Repository Touchpoints

Inspect these files before recommending execution-state persistence.

## Core State Holders

### `src/strategy/domain/aggregate/position_aggregate.py`

- Holds leg-level execution state
- Defines how pending orders and leg phases evolve
- Relevant when deciding whether any leg-level field is genuinely non-recomputable

### `src/strategy/domain/aggregate/combination_aggregate.py`

- Holds combination-level execution intent and leg-phase convergence
- Relevant when deciding whether combination coordination data is restart-critical or reconstructible from leg state

### `src/strategy/domain/value_object/trading/execution_state.py`

- Defines execution-state types, phases, priorities, and action categories
- Inspect here to see whether the candidate data is core execution control state or only a transient phase

## Snapshot and Restore Boundaries

### `src/strategy/application/state_workflow.py`

- Builds the strategy snapshot
- Supports optional `snapshot_dumpers`
- Preferred insertion point when strategy-specific persistence must be added without polluting shared aggregate snapshots

### `src/strategy/application/lifecycle_workflow.py`

- Runs live OMS sync before restore hooks
- Supports optional `restore_hooks`
- Preferred restore boundary when strategy-specific persisted state must reconcile with OMS/positions/trades on startup

### `src/strategy/runtime/models.py`

- Defines runtime `StateRoles`
- Check whether the desired behavior belongs in shared snapshot logic or in strategy-provided dump/restore hooks

## Preferred Integration Rule

- Shared aggregate changes are appropriate only when the persisted state is generic scaffold behavior.
- Strategy-specific persistence should prefer runtime dump/restore hooks.
- OMS reconstruction should remain the default recovery path unless the strategy proves it is insufficient.
