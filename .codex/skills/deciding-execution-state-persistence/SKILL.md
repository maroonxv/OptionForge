---
name: deciding-execution-state-persistence
description: Use when adding or revising execution-state persistence, restart recovery, snapshot contents, idempotency markers, or OMS-based execution restoration for strategies built on this scaffold.
---

# Deciding Execution State Persistence

## Overview

Use this skill to decide whether strategy execution state should persist at all, and if so, what the minimum safe subset is. The default stance is conservative: do not persist recomputable execution state.

**Violating the letter of these rules is violating the spirit of these rules.**

## Workflow

Follow this sequence before proposing or implementing any execution-state persistence:

1. Inventory every candidate field or state bundle under consideration.
2. Classify each item as exactly one of:
   - recomputable from OMS, positions, trades, or bar replay
   - non-recomputable and safety-critical
   - observability/debug-only
3. Default to **do not persist** for recomputable and observability-only items.
4. If persistence is still needed, persist only the minimum non-recomputable, safety-critical subset.
5. State all of the following before code changes:
   - what is being persisted
   - why it cannot be rebuilt safely
   - where it is stored
   - how restart recovery works with and without the persisted data
   - which tests prove the decision is safe

## Hard Gates

- Do not persist full execution-state snapshots by default.
- Do not persist live `WORKING`, `CANCEL_PENDING`, or `PARTIAL_FILLED` phases unless the strategy proves OMS reconstruction is insufficient.
- Do not add strategy-specific persistence directly into shared aggregates when runtime restore hooks are sufficient.
- Do not treat persisted order presence as a substitute for business phase.
- Do not finish the change without restart and idempotency tests.

## Required Checks

Always inspect the repository touchpoints in [references/repo-touchpoints.md](references/repo-touchpoints.md) before making a recommendation.

Always apply the classification and examples in [references/decision-matrix.md](references/decision-matrix.md).

Always produce both reasoning paths when persistence is proposed:

- Why the default `do not persist` path is insufficient
- Why the chosen persisted subset is the minimum safe exception

## Output Contract

Present the decision memo in the current conversation language using this structure:

```markdown
Persistence Decision

Candidate state list
- ...

Classification per field
- field: recomputable | non-recomputable and safety-critical | observability/debug-only

Default decision
- persist nothing | persist minimum subset

Persisted minimum subset
- ...

Recovery path
- without persistence: ...
- with persistence: ...

Test plan
- ...
```

## Red Flags

- "Persist the whole execution state just in case."
- "Snapshot everything, then optimize later."
- "This phase might be useful for debugging."
- "The order exists, so the business phase must still hold."
- "It is safer to store more."

All of these mean stop and re-run the classification.

## Pressure Scenarios

Use these scenarios when validating the skill:

1. "Persist execution state for restart safety" and check whether the agent over-persists the full state.
2. "Add restart support for a strategy-owned scheduler" and check whether the agent separates OMS-reconstructible state from true scheduler cursors.
3. "Persist today already rolled once" and check whether the agent stores the one-time marker instead of unrelated live execution phases.

If subagents are unavailable in the current environment, explicitly note that full pressure-testing could not be completed and still run repository validation plus a manual checklist review against these scenarios.

## Common Mistakes

- Treating restart convenience as correctness.
- Mixing trace payloads with safety-critical control markers.
- Expanding shared aggregate snapshots instead of using runtime hooks for strategy-specific data.
- Persisting transient phases without proving reconstruction gaps.
