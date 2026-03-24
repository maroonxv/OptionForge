# Execution State Decision Matrix

## Classification Matrix

| Class | Default | Persist? | Typical source of truth |
|---|---|---|---|
| Recomputable | Do not persist | No | OMS active orders, positions, trades, bar replay |
| Non-recomputable and safety-critical | Persist minimum subset | Yes, selectively | Strategy-owned control state |
| Observability/debug-only | Do not persist | No | Logs, traces, metrics, journals |

## Usually Persist

Persist only when the strategy truly depends on them after restart:

- `intent_id`
- idempotency keys
- one-time execution markers such as “already rolled today”
- manual confirmation tokens
- strategy-owned scheduler cursors
- preemption lineage only when it changes correctness after restart

## Usually Do Not Persist

- OMS-derived active order lists
- transient live phases such as `WORKING`, `SUBMITTING`, `CANCEL_PENDING`, `PARTIAL_FILLED`
- filled volume that can be rebuilt from trades
- snapshot-only trace annotations
- debugging notes, trace payloads, observability metadata

## Anti-Patterns

- Persisting the entire execution state because “storage is cheap”
- Using persisted order presence as a proxy for business phase
- Keeping observability fields in the same correctness-critical payload
- Expanding a shared aggregate snapshot with strategy-specific fields when hooks would isolate the change better

## Decision Heuristics

Ask these in order:

1. If the process restarts, can OMS, positions, trades, or replay rebuild this field safely?
2. If the field is lost, can the strategy repeat an action that must happen at most once?
3. Is this field required for correctness, or only for explanation and debugging?
4. Can the field be isolated into a strategy-specific runtime hook instead of shared aggregate state?

If the answer to 1 is yes, do not persist it.

If the answer to 2 is yes, persist only the minimal marker needed to preserve that one-time guarantee.

If the answer to 3 is “only explanation,” do not persist it.
