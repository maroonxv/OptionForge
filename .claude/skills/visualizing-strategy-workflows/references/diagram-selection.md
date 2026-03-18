# Diagram Selection

## Mandatory

Every workflow doc must include:

- Architecture diagram
- Data-flow diagram
- Sequence diagram

## Optional State Diagram

Add a state diagram only when the workflow has a meaningful state model, for example:

- explicit lifecycle phases
- mode toggles such as warmup vs live mode
- subscription state transitions
- timer-driven stale/active transitions
- guarded transitions with repeated checks

Do not add a state diagram just for symmetry. If the workflow is a simple one-shot orchestration without durable mode changes, skip it.

## Current Repo Guidance

In this repository:

- `market_workflow.py` should emphasize data flow and sequence depth.
- `lifecycle_workflow.py` often justifies a state or phase diagram because startup, warmup, live restore, and shutdown are distinct phases.
- `subscription_workflow.py` often justifies a state diagram because subscriptions become active, stale, or expired over time.
- `state_workflow.py` should usually stay simple.
