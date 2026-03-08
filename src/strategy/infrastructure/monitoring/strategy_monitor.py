import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from peewee import PostgresqlDatabase

from ...domain.aggregate.instrument_manager import InstrumentManager
from ...domain.aggregate.position_aggregate import PositionAggregate
from ..persistence.json_serializer import JsonSerializer
from src.strategy.infrastructure.monitoring.model.monitor_signal_event_po import (
    MonitorSignalEventPO,
)
from src.strategy.infrastructure.monitoring.model.monitor_signal_snapshot_po import (
    MonitorSignalSnapshotPO,
)


class StrategyMonitor:
    """
    负责策略的监控与快照逻辑。

    统一使用 Postgres 持久化，不再落地本地文件快照。
    """

    def __init__(
        self,
        variant_name: str,
        monitor_instance_id: str,
        monitor_db_config: Optional[Dict[str, Any]] = None,
        logger: Any = None,
    ):
        self.variant_name = variant_name
        self.monitor_instance_id = monitor_instance_id
        self._monitor_db_config = monitor_db_config or {}
        self.logger = logger

        self.monitor_db_enabled = str(os.getenv("MONITOR_DB_ENABLED", "1")).lower() not in (
            "0",
            "false",
            "no",
            "off",
            "",
        )
        if not self._monitor_db_config.get("host"):
            self.monitor_db_enabled = False

        self._monitor_tables_ensured = False
        self._monitor_db: Optional[PostgresqlDatabase] = None
        self._last_status_map: Dict[str, Dict[str, bool]] = {}
        self._json_serializer = JsonSerializer()

    def _serialize_payload(self, payload: Dict[str, Any]) -> str:
        """将监控 payload 序列化为 JSON 文本（不注入 schema_version）。"""
        return self._json_serializer.serialize(
            payload,
            inject_schema_version=False,
        )

    def _monitor_db_available(self) -> bool:
        if not self.monitor_db_enabled:
            return False
        cfg = self._monitor_db_config
        return bool(cfg.get("host") and cfg.get("user") and cfg.get("database"))

    def _monitor_db_connect(self) -> Optional[PostgresqlDatabase]:
        if not self._monitor_db_available():
            return None
        try:
            if self._monitor_db is None:
                self._monitor_db = PostgresqlDatabase(
                    self._monitor_db_config["database"],
                    user=self._monitor_db_config["user"],
                    password=self._monitor_db_config.get("password", ""),
                    host=self._monitor_db_config["host"],
                    port=int(self._monitor_db_config.get("port", 5432)),
                    autorollback=True,
                )
            self._monitor_db.connect(reuse_if_open=True)
            return self._monitor_db
        except Exception:
            return None

    @staticmethod
    def _bind_models(db: PostgresqlDatabase) -> None:
        MonitorSignalSnapshotPO._meta.database = db
        MonitorSignalEventPO._meta.database = db

    def _ensure_monitor_tables(self) -> None:
        if self._monitor_tables_ensured:
            return
        db = self._monitor_db_connect()
        if db is None:
            return

        try:
            self._bind_models(db)
            with db.connection_context():
                db.create_tables([MonitorSignalSnapshotPO, MonitorSignalEventPO], safe=True)
            self._monitor_tables_ensured = True
        except Exception:
            return

    def _upsert_monitor_snapshot(
        self,
        payload: Dict[str, Any],
        bar_dt: Optional[datetime],
        bar_interval: Optional[str],
        bar_window: Optional[int],
    ) -> None:
        self._ensure_monitor_tables()
        db = self._monitor_db_connect()
        if db is None:
            return

        now_dt = datetime.now()
        try:
            payload_text = self._serialize_payload(payload)
        except Exception:
            return

        try:
            self._bind_models(db)
            with db.connection_context():
                (
                    MonitorSignalSnapshotPO.insert(
                        variant=self.variant_name,
                        instance_id=self.monitor_instance_id,
                        updated_at=now_dt,
                        bar_dt=bar_dt,
                        bar_interval=bar_interval,
                        bar_window=bar_window,
                        payload_json=payload_text,
                    )
                    .on_conflict(
                        conflict_target=[
                            MonitorSignalSnapshotPO.variant,
                            MonitorSignalSnapshotPO.instance_id,
                        ],
                        update={
                            MonitorSignalSnapshotPO.updated_at: now_dt,
                            MonitorSignalSnapshotPO.bar_dt: bar_dt,
                            MonitorSignalSnapshotPO.bar_interval: bar_interval,
                            MonitorSignalSnapshotPO.bar_window: bar_window,
                            MonitorSignalSnapshotPO.payload_json: payload_text,
                        },
                    )
                    .execute()
                )
        except Exception:
            return

    def insert_monitor_event(
        self,
        event_type: str,
        event_key: str,
        payload: Dict[str, Any],
        vt_symbol: str,
        bar_dt: Optional[datetime],
        created_at: Optional[datetime] = None,
    ) -> None:
        self._ensure_monitor_tables()
        db = self._monitor_db_connect()
        if db is None:
            return

        if not created_at:
            created_at = datetime.now()

        try:
            payload_text = self._serialize_payload(payload)
        except Exception:
            return

    def record_decision_trace(self, payload: Dict[str, Any]) -> None:
        """记录决策流水线轨迹。"""
        vt_symbol = str(payload.get("vt_symbol", "") or "")
        bar_dt = self.parse_bar_dt(payload.get("bar_dt"))
        trace_id = str(payload.get("trace_id", "") or "")
        signal_name = str(payload.get("signal_name", "") or "")
        event_key = (
            f"{self.variant_name}|{self.monitor_instance_id}|{vt_symbol}|"
            f"{(bar_dt.isoformat() if bar_dt else '')}|decision|{trace_id}|{signal_name}"
        )
        self.insert_monitor_event(
            event_type="decision_trace",
            event_key=event_key,
            payload=payload,
            vt_symbol=vt_symbol,
            bar_dt=bar_dt,
        )

        try:
            self._bind_models(db)
            with db.connection_context():
                (
                    MonitorSignalEventPO.insert(
                        variant=self.variant_name,
                        instance_id=self.monitor_instance_id,
                        vt_symbol=vt_symbol or "",
                        bar_dt=bar_dt,
                        event_type=event_type,
                        event_key=event_key,
                        created_at=created_at,
                        payload_json=payload_text,
                    )
                    .on_conflict_ignore()
                    .execute()
                )
        except Exception:
            return

    def parse_bar_dt(self, bar_dt_value: Any) -> Optional[datetime]:
        if isinstance(bar_dt_value, datetime):
            return bar_dt_value
        if isinstance(bar_dt_value, str) and bar_dt_value:
            try:
                return datetime.fromisoformat(bar_dt_value)
            except Exception:
                try:
                    return datetime.strptime(bar_dt_value, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    return None
        return None

    def record_snapshot(
        self,
        target_aggregate: InstrumentManager,
        position_aggregate: PositionAggregate,
        strategy_context: Any,
    ) -> None:
        """
        生成并保存用于 Web 监控的快照数据（统一写入 Postgres）。
        """
        try:
            max_bars = 300
            instruments_data: Dict[str, Any] = {}
            snapshot_bar_dt: Optional[datetime] = None

            for vt_symbol in target_aggregate.get_all_symbols():
                instrument = target_aggregate.get_instrument(vt_symbol)
                if not instrument:
                    continue

                bars_df = getattr(instrument, "bars", None)
                dates: List[str] = []
                ohlc: List[List[Any]] = []
                volumes: List[Any] = []
                tail_df = None

                if bars_df is not None and not getattr(bars_df, "empty", True):
                    tail_df = bars_df.tail(max_bars).copy()

                if tail_df is not None:
                    for _, row in tail_df.iterrows():
                        dt = row.get("datetime")
                        if isinstance(dt, str):
                            dt_str = dt
                        else:
                            dt_str = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""

                        dates.append(dt_str)
                        low = row.get("low")
                        high = row.get("high")
                        ohlc.append([
                            row.get("open"),
                            row.get("close"),
                            low,
                            high,
                        ])
                        volumes.append(row.get("volume", 0))

                # 指标数据和状态由具体策略实现决定，此处仅记录基础 OHLCV
                status = {}

                tail_last_dt = None
                try:
                    if tail_df is not None and not tail_df.empty:
                        tail_last_dt = tail_df.iloc[-1].get("datetime")
                except Exception:
                    tail_last_dt = None
                tail_last_dt_parsed = self.parse_bar_dt(tail_last_dt)
                if tail_last_dt_parsed and (
                    snapshot_bar_dt is None or tail_last_dt_parsed > snapshot_bar_dt
                ):
                    snapshot_bar_dt = tail_last_dt_parsed
                instruments_data[vt_symbol] = {
                    "dates": dates,
                    "ohlc": ohlc,
                    "volumes": volumes,
                    "indicators": instrument.indicators if hasattr(instrument, "indicators") else {},
                    "status": status,
                    "last_price": float(getattr(instrument, "latest_close", 0.0) or 0.0),
                    "delivery_month": "Other",
                }

            positions_list: List[Dict[str, Any]] = []
            try:
                for pos in position_aggregate.get_all_positions():
                    positions_list.append(
                        {
                            "vt_symbol": getattr(pos, "vt_symbol", ""),
                            "direction": str(getattr(pos, "direction", "")),
                            "volume": getattr(pos, "volume", 0),
                            "price": getattr(pos, "open_price", 0),
                            "pnl": 0.0,
                        }
                    )
            except Exception:
                positions_list = []

            orders_list: List[Dict[str, Any]] = []
            try:
                if hasattr(position_aggregate, "get_all_pending_orders"):
                    orders = position_aggregate.get_all_pending_orders()
                else:
                    orders = getattr(position_aggregate, "_pending_orders", {}).values()
                for order in orders:
                    orders_list.append(
                        {
                            "vt_orderid": getattr(order, "vt_orderid", ""),
                            "vt_symbol": getattr(order, "vt_symbol", ""),
                            "direction": str(getattr(order, "direction", "")),
                            "offset": str(getattr(order, "offset", "")),
                            "volume": getattr(order, "volume", 0),
                            "price": getattr(order, "price", 0),
                            "status": str(getattr(order, "status", "Unknown")),
                        }
                    )
            except Exception:
                orders_list = []

            snapshot_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "variant": self.variant_name,
                "instruments": instruments_data,
                "positions": positions_list,
                "orders": orders_list,
                "recent_decisions": list(getattr(strategy_context, "decision_journal", []) or []),
            }

            bar_interval = str(getattr(strategy_context, "bar_interval", "") or "") or None
            bar_window_raw = getattr(strategy_context, "bar_window", None)
            try:
                bar_window = int(bar_window_raw) if bar_window_raw is not None else None
            except Exception:
                bar_window = None

            for vt_symbol, inst_data in instruments_data.items():
                prev = self._last_status_map.get(vt_symbol) or {}
                cur = (inst_data.get("status") or {}) if isinstance(inst_data, dict) else {}
                for state_name in cur.keys():
                    old_v = bool(prev.get(state_name, False))
                    new_v = bool(cur.get(state_name, False))
                    if old_v == new_v:
                        continue
                    state_event_key = (
                        f"{self.variant_name}|{self.monitor_instance_id}|{vt_symbol}|"
                        f"{(snapshot_bar_dt.isoformat() if snapshot_bar_dt else '')}|{state_name}|{old_v}->{new_v}"
                    )
                    self.insert_monitor_event(
                        event_type="state_change",
                        event_key=state_event_key,
                        payload={
                            "state_name": state_name,
                            "old_value": old_v,
                            "new_value": new_v,
                            "bar_dt": snapshot_bar_dt.isoformat() if snapshot_bar_dt else "",
                        },
                        vt_symbol=vt_symbol,
                        bar_dt=snapshot_bar_dt,
                    )
                self._last_status_map[vt_symbol] = {k: bool(cur.get(k, False)) for k in cur.keys()}

            self._upsert_monitor_snapshot(
                payload=snapshot_data,
                bar_dt=snapshot_bar_dt,
                bar_interval=bar_interval,
                bar_window=bar_window,
            )

            if self.logger:
                self.logger.debug(
                    f"监控快照已写入 Postgres: variant={self.variant_name}, instance={self.monitor_instance_id}"
                )

        except Exception as e:
            if self.logger:
                self.logger.error(f"保存监控快照失败: {str(e)}")
            pass
