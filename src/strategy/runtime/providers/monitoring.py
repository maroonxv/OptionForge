from __future__ import annotations

from typing import Any

from ..models import CapabilityContribution, LifecycleRoles, ObservabilityRoles, StateRoles


class _MonitoringProvider:
    def build(
        self,
        entry: Any,
        full_config: dict[str, Any],
        kernel: Any,
    ) -> CapabilityContribution:
        monitor = getattr(entry, "monitor", None)
        if monitor is None:
            return CapabilityContribution()

        cleanup_hooks = ()
        if callable(getattr(monitor, "shutdown", None)):
            cleanup_hooks = (monitor.shutdown,)
        elif callable(getattr(monitor, "close", None)):
            cleanup_hooks = (monitor.close,)

        return CapabilityContribution(
            lifecycle=LifecycleRoles(cleanup_hooks=cleanup_hooks),
            state=StateRoles(
                snapshot_sinks=(
                    lambda target_aggregate, position_aggregate, runtime_entry: monitor.record_snapshot(
                        target_aggregate,
                        position_aggregate,
                        runtime_entry,
                    ),
                ),
            ),
            observability=ObservabilityRoles(
                trace_sinks=(lambda payload: monitor.record_decision_trace(payload),),
            ),
        )


PROVIDER = _MonitoringProvider()
