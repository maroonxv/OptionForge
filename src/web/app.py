from __future__ import annotations

import os
import select
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from flask import Flask, current_app, jsonify, render_template, request
from flask_socketio import SocketIO, join_room, leave_room

from src.main.utils.logging_setup import setup_logging
from src.strategy.infrastructure.monitoring.notification_protocol import (
    MONITOR_DECISION_TRACE_UPDATES_CHANNEL,
    MONITOR_SNAPSHOT_UPDATES_CHANNEL,
    decode_notification_payload,
)
from src.web.reader import PostgresSnapshotReader, StrategyStateReader


load_dotenv()

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")


def configure_monitor_logging() -> None:
    setup_logging("INFO", os.getenv("MONITOR_LOG_DIR", "logs/monitor"), "monitor")


def _build_state_reader() -> StrategyStateReader:
    return StrategyStateReader(
        {
            "host": os.getenv("VNPY_DATABASE_HOST", ""),
            "port": int(os.getenv("VNPY_DATABASE_PORT", "5432") or 5432),
            "user": os.getenv("VNPY_DATABASE_USER", ""),
            "password": os.getenv("VNPY_DATABASE_PASSWORD", ""),
            "database": os.getenv("VNPY_DATABASE_DATABASE", ""),
        }
    )


def _normalize_limit(limit_value: str, default: int, maximum: int) -> int:
    try:
        limit = int(limit_value)
    except Exception:
        limit = default
    if limit <= 0:
        return default
    return min(limit, maximum)


class MonitorRuntime:
    def __init__(
        self,
        snapshot_reader: PostgresSnapshotReader,
        state_reader: StrategyStateReader,
        socketio_server: SocketIO,
        heartbeat_sec: int,
    ) -> None:
        self.snapshot_reader = snapshot_reader
        self.state_reader = state_reader
        self.socketio = socketio_server
        self.heartbeat_sec = max(int(heartbeat_sec or 5), 1)
        self._sid_variants: Dict[str, str] = {}
        self._lock = Lock()
        self._background_tasks_started = False

    @staticmethod
    def variant_room(variant: str) -> str:
        return f"variant:{variant}"

    def start_background_tasks(self) -> None:
        if self._background_tasks_started:
            return
        self._background_tasks_started = True
        try:
            self.snapshot_reader.ensure_tables()
        except Exception:
            pass
        self.socketio.start_background_task(self._listen_notifications_loop)
        self.socketio.start_background_task(self._heartbeat_loop)

    def list_strategies(self) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        try:
            for row in self.state_reader.list_available_strategies():
                variant = str(row.get("variant", "") or "")
                if variant:
                    merged[variant] = dict(row)
        except Exception:
            pass
        try:
            for row in self.snapshot_reader.list_available_strategies():
                variant = str(row.get("variant", "") or "")
                if not variant:
                    continue
                previous = merged.get(variant) or {}
                merged[variant] = {
                    "variant": variant,
                    "last_update": row.get("last_update") or previous.get("last_update", ""),
                    "file_size": row.get("file_size"),
                }
        except Exception:
            pass
        return [merged[key] for key in sorted(merged.keys())]

    def get_snapshot(self, variant: str) -> Optional[Dict[str, Any]]:
        if not variant:
            return None
        try:
            snapshot = self.snapshot_reader.get_strategy_data(variant)
            if snapshot:
                return snapshot
        except Exception:
            pass
        try:
            snapshot = self.state_reader.get_strategy_data(variant)
            if snapshot:
                return snapshot
        except Exception:
            pass
        return None

    def get_decisions(self, variant: str, vt_symbol: str, limit: int) -> Dict[str, Any]:
        if variant and self.snapshot_reader._db_available():
            events = self.snapshot_reader.get_events(
                variant=variant,
                vt_symbol=vt_symbol,
                event_type="decision_trace",
                limit=limit,
            )
            if events:
                return {"items": events, "source": "events"}
        snapshot = self.get_snapshot(variant) or {}
        decisions = list(snapshot.get("recent_decisions", []) or [])
        if vt_symbol:
            decisions = [
                item for item in decisions if str(item.get("vt_symbol", "") or "") == vt_symbol
            ]
        return {"items": decisions[:limit], "source": "snapshot"}

    def subscribe(self, sid: str, variant: str) -> Dict[str, Any]:
        variant_name = str(variant or "")
        old_variant = ""
        with self._lock:
            old_variant = self._sid_variants.get(sid, "")
            if variant_name:
                self._sid_variants[sid] = variant_name
            else:
                self._sid_variants.pop(sid, None)
        if old_variant and old_variant != variant_name:
            leave_room(self.variant_room(old_variant), sid=sid)
        if variant_name:
            join_room(self.variant_room(variant_name), sid=sid)
            return {"variant": variant_name, "subscribed": True}
        return {"variant": "", "subscribed": False}

    def unsubscribe(self, sid: str) -> Dict[str, Any]:
        with self._lock:
            variant = self._sid_variants.pop(sid, "")
        if variant:
            leave_room(self.variant_room(variant), sid=sid)
        return {"variant": variant, "subscribed": False}

    def disconnect(self, sid: str) -> None:
        with self._lock:
            variant = self._sid_variants.pop(sid, "")
        if variant:
            try:
                leave_room(self.variant_room(variant), sid=sid)
            except Exception:
                pass

    def process_notification(self, channel: str, payload: Dict[str, Any]) -> None:
        if channel == MONITOR_SNAPSHOT_UPDATES_CHANNEL:
            variant = str(payload.get("variant", "") or "")
            if not variant:
                return
            snapshot = self.snapshot_reader.get_strategy_data(variant)
            if snapshot:
                self.socketio.emit(
                    "snapshot_update",
                    snapshot,
                    room=self.variant_room(variant),
                )
            return

        if channel != MONITOR_DECISION_TRACE_UPDATES_CHANNEL:
            return
        if str(payload.get("event_type", "") or "") != "decision_trace":
            return
        event = self.snapshot_reader.get_event_by_id(payload.get("event_id", 0))
        if not event:
            return
        variant = str(event.get("variant", "") or "")
        if not variant:
            return
        self.socketio.emit(
            "event_new",
            event,
            room=self.variant_room(variant),
        )

    def _listen_notifications_loop(self) -> None:
        while True:
            conn = self.snapshot_reader._connect_listener()
            if conn is None:
                self.socketio.sleep(1.0)
                continue
            try:
                cursor = conn.cursor()
                cursor.execute(f"LISTEN {MONITOR_SNAPSHOT_UPDATES_CHANNEL};")
                cursor.execute(f"LISTEN {MONITOR_DECISION_TRACE_UPDATES_CHANNEL};")
                while True:
                    ready, _, _ = select.select([conn], [], [], float(self.heartbeat_sec))
                    if not ready:
                        continue
                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        self.process_notification(
                            getattr(notify, "channel", ""),
                            decode_notification_payload(getattr(notify, "payload", "")),
                        )
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            self.socketio.sleep(1.0)

    def _heartbeat_loop(self) -> None:
        while True:
            self.socketio.emit(
                "heartbeat",
                {"server_time": datetime.now().isoformat()},
            )
            self.socketio.sleep(float(self.heartbeat_sec))


def _get_runtime() -> MonitorRuntime:
    return current_app.extensions["monitor_runtime"]


@socketio.on("subscribe")
def handle_subscribe(data):
    runtime = _get_runtime()
    variant = ""
    if isinstance(data, dict):
        variant = str(data.get("variant", "") or "")
    payload = runtime.subscribe(request.sid, variant)
    socketio.emit("subscription_state", payload, to=request.sid)


@socketio.on("unsubscribe")
def handle_unsubscribe():
    runtime = _get_runtime()
    payload = runtime.unsubscribe(request.sid)
    socketio.emit("subscription_state", payload, to=request.sid)


@socketio.on("disconnect")
def handle_disconnect():
    _get_runtime().disconnect(request.sid)


def create_app(
    start_background_services: bool = True,
    *,
    snapshot_reader: Optional[PostgresSnapshotReader] = None,
    state_reader: Optional[StrategyStateReader] = None,
) -> Flask:
    configure_monitor_logging()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    socketio.init_app(app)

    heartbeat_sec = max(int(float(os.getenv("MONITOR_SOCKET_HEARTBEAT_SEC", "5") or 5)), 1)
    runtime = MonitorRuntime(
        snapshot_reader=snapshot_reader or PostgresSnapshotReader(),
        state_reader=state_reader or _build_state_reader(),
        socketio_server=socketio,
        heartbeat_sec=heartbeat_sec,
    )
    app.extensions["monitor_runtime"] = runtime

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            strategies=[item["variant"] for item in runtime.list_strategies()],
            heartbeat_sec=heartbeat_sec,
        )

    @app.route("/dashboard/<variant_name>")
    def dashboard(variant_name):
        return render_template(
            "index.html",
            strategies=[item["variant"] for item in runtime.list_strategies()],
            variant=variant_name,
            heartbeat_sec=heartbeat_sec,
        )

    @app.route("/api/strategies")
    def api_strategies():
        return jsonify([item["variant"] for item in runtime.list_strategies()])

    @app.route("/api/data/<variant_name>")
    def api_data(variant_name):
        data = runtime.get_snapshot(variant_name)
        if not data:
            return jsonify({"error": "Not found"}), 404
        return jsonify(data)

    @app.route("/api/snapshot/<variant_name>")
    def api_snapshot(variant_name):
        data = runtime.get_snapshot(variant_name)
        if not data:
            return jsonify({"error": "Not found"}), 404
        return jsonify(data)

    @app.route("/api/events/<variant_name>")
    def api_events(variant_name):
        if not runtime.snapshot_reader._db_available():
            return jsonify([])
        vt_symbol = request.args.get("vt_symbol", "")
        start = request.args.get("start", "")
        end = request.args.get("end", "")
        event_type = request.args.get("type", "")
        limit = _normalize_limit(request.args.get("limit", "2000"), 2000, 5000)
        events = runtime.snapshot_reader.get_events(
            variant=variant_name,
            vt_symbol=vt_symbol,
            start=start,
            end=end,
            event_type=event_type,
            limit=limit,
        )
        return jsonify(events)

    @app.route("/api/decisions/<variant_name>")
    def api_decisions(variant_name):
        vt_symbol = request.args.get("vt_symbol", "")
        limit = _normalize_limit(request.args.get("limit", "120"), 120, 500)
        return jsonify(runtime.get_decisions(variant_name, vt_symbol, limit))

    @app.route("/api/bars")
    def api_bars():
        if not runtime.snapshot_reader._db_available():
            return jsonify([])
        vt_symbol = request.args.get("vt_symbol", "")
        start = request.args.get("start", "")
        end = request.args.get("end", "")
        interval = request.args.get("interval", "1m")
        limit = _normalize_limit(request.args.get("limit", "5000"), 5000, 5000)
        bars = runtime.snapshot_reader.get_bars(
            vt_symbol=vt_symbol,
            start=start,
            end=end,
            interval=interval,
            limit=limit,
        )
        return jsonify(bars)

    if start_background_services:
        runtime.start_background_tasks()

    return app


app = create_app(start_background_services=False)


if __name__ == "__main__":
    runtime = app.extensions["monitor_runtime"]
    runtime.start_background_tasks()
    socketio.run(
        app,
        host="0.0.0.0",
        port=5007,
        debug=True,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
