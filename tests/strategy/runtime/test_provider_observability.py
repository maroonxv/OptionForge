from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.strategy.application.state_workflow import StateWorkflow
from src.strategy.runtime.registry import CAPABILITY_REGISTRY


def _manifest(**overrides: bool) -> dict[str, bool]:
    manifest = {key: False for key in CAPABILITY_REGISTRY}
    manifest.update(overrides)
    return manifest


def test_state_workflow_writes_to_runtime_snapshot_sinks() -> None:
    sink = MagicMock()
    entry = SimpleNamespace(
        runtime=SimpleNamespace(state=SimpleNamespace(snapshot_sinks=[sink])),
        target_aggregate=MagicMock(),
        position_aggregate=MagicMock(),
        logger=MagicMock(),
    )

    StateWorkflow(entry).record_snapshot()

    sink.assert_called_once_with(
        entry.target_aggregate,
        entry.position_aggregate,
        entry,
    )


def test_monitoring_provider_contributes_snapshot_and_trace_sinks() -> None:
    from src.strategy.runtime.providers.monitoring import PROVIDER

    monitor = MagicMock()
    entry = SimpleNamespace(monitor=monitor, logger=MagicMock())
    contribution = PROVIDER.build(
        entry,
        {"service_activation": _manifest(monitoring=True)},
        kernel=SimpleNamespace(),
    )

    snapshot_sink = contribution.state.snapshot_sinks[0]
    trace_sink = contribution.observability.trace_sinks[0]

    snapshot_sink("targets", "positions", entry)
    trace_sink({"trace": "payload"})

    monitor.record_snapshot.assert_called_once_with("targets", "positions", entry)
    monitor.record_decision_trace.assert_called_once_with({"trace": "payload"})


def test_decision_observability_provider_appends_trace_payloads() -> None:
    from src.strategy.runtime.providers.decision_observability import PROVIDER

    entry = SimpleNamespace(
        decision_journal=[],
        decision_journal_limit=1,
        logger=MagicMock(),
    )

    contribution = PROVIDER.build(
        entry,
        {"service_activation": _manifest(decision_observability=True)},
        kernel=SimpleNamespace(),
    )

    sink = contribution.observability.trace_sinks[0]
    sink({"trace": 1})
    sink({"trace": 2})

    assert entry.decision_journal == [{"trace": 2}]
