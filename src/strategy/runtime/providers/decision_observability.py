from __future__ import annotations

from typing import Any

from ..models import CapabilityContribution, ObservabilityRoles


class _DecisionObservabilityProvider:
    def build(
        self,
        entry: Any,
        full_config: dict[str, Any],
        kernel: Any,
    ) -> CapabilityContribution:
        def append_trace(payload: dict[str, Any]) -> None:
            journal = getattr(entry, "decision_journal", None)
            if journal is None:
                journal = []
                entry.decision_journal = journal

            journal.append(payload)
            maxlen = max(int(getattr(entry, "decision_journal_limit", 200) or 200), 1)
            if len(journal) > maxlen:
                entry.decision_journal = journal[-maxlen:]

        return CapabilityContribution(
            observability=ObservabilityRoles(trace_sinks=(append_trace,))
        )


PROVIDER = _DecisionObservabilityProvider()
