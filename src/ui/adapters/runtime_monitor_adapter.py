from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_GROUP_ORDER = ("requests", "workspace", "execution", "inference", "memory", "other")


@dataclass(frozen=True, slots=True)
class MonitorEventRecord:
    event_id: int
    dispatched_at: str
    group: str
    action: str
    sender: str
    target: str
    summary: str
    payload: dict[str, Any]
    response: dict[str, Any]
    is_error: bool


@dataclass(frozen=True, slots=True)
class MonitorRegistryEntry:
    group: str
    recent_count: int
    last_action: str
    last_timestamp: str


@dataclass(frozen=True, slots=True)
class MonitorSnapshot:
    total_event_count: int
    latest_event_id: int | None
    registry: list[MonitorRegistryEntry]
    events_by_group: dict[str, list[MonitorEventRecord]]
    log_tail: list[str]


class RuntimeMonitorAdapter:
    """Reads the runtime event ledger and log tail for the operator monitor."""

    def __init__(self, db_path: Path, log_path: Path) -> None:
        self._db_path = db_path
        self._log_path = log_path

    def fetch_snapshot(
        self,
        *,
        max_events: int = 250,
        limit_per_group: int = 20,
        log_line_count: int = 80,
    ) -> MonitorSnapshot:
        events_by_group: dict[str, list[MonitorEventRecord]] = {
            group: [] for group in _GROUP_ORDER
        }
        total_event_count = 0
        latest_event_id: int | None = None

        if self._db_path.exists():
            with closing(sqlite3.connect(self._db_path)) as connection:
                total_row = connection.execute(
                    "SELECT COUNT(*) FROM dispatch_events"
                ).fetchone()
                total_event_count = int(total_row[0]) if total_row else 0
                rows = connection.execute(
                    """
                    SELECT id, sender, target, action, payload_json, response_json, dispatched_at
                    FROM dispatch_events
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (max_events,),
                ).fetchall()

            for row in rows:
                event_id = int(row[0])
                if latest_event_id is None or event_id > latest_event_id:
                    latest_event_id = event_id
                payload = self._safe_load_json(str(row[4]))
                response = self._safe_load_json(str(row[5]))
                action = str(row[3])
                group = self._classify_group(action)
                if len(events_by_group[group]) >= limit_per_group:
                    continue
                events_by_group[group].append(
                    MonitorEventRecord(
                        event_id=event_id,
                        dispatched_at=str(row[6]),
                        group=group,
                        action=action,
                        sender=str(row[1]),
                        target=str(row[2]),
                        summary=self._build_summary(action=action, payload=payload, response=response),
                        payload=payload,
                        response=response,
                        is_error=self._is_error_response(response),
                    )
                )

        registry = [
            MonitorRegistryEntry(
                group=group,
                recent_count=len(events_by_group[group]),
                last_action=(events_by_group[group][0].action if events_by_group[group] else "idle"),
                last_timestamp=(
                    events_by_group[group][0].dispatched_at if events_by_group[group] else "-"
                ),
            )
            for group in _GROUP_ORDER
        ]
        return MonitorSnapshot(
            total_event_count=total_event_count,
            latest_event_id=latest_event_id,
            registry=registry,
            events_by_group=events_by_group,
            log_tail=self._read_log_tail(log_line_count),
        )

    def _classify_group(self, action: str) -> str:
        if action == "rpc.request":
            return "requests"
        if action.startswith(
            (
                "fs.",
                "project.",
                "archive.",
                "intake.",
                "parts.",
                "sandbox.",
                "ast.",
                "worker.",
                "sidecar.",
                "extension.",
            )
        ):
            return "workspace"
        if action.startswith(("python.", "sysops.")):
            return "execution"
        if action.startswith("ollama."):
            return "inference"
        if action.startswith(("journal.", "tasklist.")):
            return "memory"
        return "other"

    def _build_summary(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        response: dict[str, Any],
    ) -> str:
        if action == "rpc.request":
            request = payload.get("request", {})
            if isinstance(request, dict):
                method = str(request.get("method", "unknown"))
                if method == "tools/call":
                    params = request.get("params", {})
                    if isinstance(params, dict):
                        return f"tools/call {params.get('name', 'unknown')}"
                return method
            return "rpc.request"

        arguments = payload.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        structured = response.get("structured_content", {})
        if not isinstance(structured, dict):
            structured = {}

        if action.startswith("ollama."):
            model = str(arguments.get("model", structured.get("model", "unknown-model")))
            user_prompt = self._truncate(str(arguments.get("user", "")), 54)
            if user_prompt:
                return f"{model} | {user_prompt}"
            return model

        if action == "sidecar.export_bundle":
            target_dir = str(arguments.get("target_dir", "."))
            if structured.get("dry_run"):
                return f"preview {target_dir}"
            return f"install {target_dir}"

        for key in (
            "planned_change_count",
            "match_count",
            "files_scanned",
            "item_count",
            "count",
            "model_count",
            "copied_file_count",
        ):
            if key in structured:
                return f"{action} | {key}={structured[key]}"

        if "path" in arguments:
            return f"{action} | {arguments['path']}"
        if "target_dir" in arguments:
            return f"{action} | {arguments['target_dir']}"
        if "pattern" in arguments:
            return f"{action} | {self._truncate(str(arguments['pattern']), 48)}"
        return action

    def _is_error_response(self, response: dict[str, Any]) -> bool:
        if bool(response.get("is_error")):
            return True
        rpc_response = response.get("rpc_response")
        return isinstance(rpc_response, dict) and "error" in rpc_response

    def _read_log_tail(self, line_count: int) -> list[str]:
        if not self._log_path.exists():
            return []
        lines = self._log_path.read_text(encoding="utf-8").splitlines()
        if line_count <= 0:
            return []
        return lines[-line_count:]

    def _safe_load_json(self, raw_text: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return {"_raw": raw_text}
        return payload if isinstance(payload, dict) else {"_value": payload}

    def _truncate(self, text: str, limit: int) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: max(limit - 3, 0)] + "..."
