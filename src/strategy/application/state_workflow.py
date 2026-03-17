"""绛栫暐鍏ュ彛鐨勭姸鎬佹寔涔呭寲涓庣洃鎺у伐浣滄祦銆?"""

from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategy.strategy_entry import StrategyEntry


class StateWorkflow:
    """澶勭悊鐘舵€佸揩鐓т笌鐩戞帶璁板綍銆?"""

    def __init__(self, entry: "StrategyEntry") -> None:
        self.entry = entry

    def create_snapshot(self) -> Dict[str, Any]:
        """鍒涘缓鐢ㄤ簬鎸佷箙鍖栫殑鑱氬悎蹇収銆?"""
        snapshot = {
            "target_aggregate": self.entry.target_aggregate.to_snapshot(),
            "position_aggregate": self.entry.position_aggregate.to_snapshot(),
            "current_dt": self.entry.current_dt,
        }
        if self.entry.combination_aggregate:
            snapshot["combination_aggregate"] = self.entry.combination_aggregate.to_snapshot()
        return snapshot

    def record_snapshot(self) -> None:
        """灏嗚繍琛屾椂蹇収鍐欏叆 runtime snapshot sinks銆?"""
        runtime = getattr(self.entry, "runtime", None)
        state_roles = getattr(runtime, "state", None)
        snapshot_sinks = tuple(getattr(state_roles, "snapshot_sinks", ()) or ())
        if not snapshot_sinks or not self.entry.target_aggregate:
            return

        for sink in snapshot_sinks:
            try:
                sink(
                    self.entry.target_aggregate,
                    self.entry.position_aggregate,
                    self.entry,
                )
            except Exception as e:
                self.entry.logger.error(f"璁板綍蹇収澶辫触: {e}")
