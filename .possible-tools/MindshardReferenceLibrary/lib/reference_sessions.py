from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from lib.reference_utils import canonical_json, ensure_directory, utc_now


class AttachmentStore:
    def __init__(self, project_path: str) -> None:
        self.project_path = Path(project_path).expanduser().resolve()
        self.state_path = self.project_path / ".mindshard" / "state" / "reference_library_attachments.json"

    def _base_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "project_path": str(self.project_path),
            "updated_at": utc_now(),
            "attachments": {},
        }

    def load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._base_payload()
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        ensure_directory(self.state_path.parent)
        payload["updated_at"] = utc_now()
        self.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    def attach(self, node_id: str, attachment_context: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self.load()
        payload["attachments"][node_id] = {
            "attached_at": utc_now(),
            "attachment_context": attachment_context or {},
        }
        return self.save(payload)

    def detach(self, node_id: str) -> dict[str, Any]:
        payload = self.load()
        payload["attachments"].pop(node_id, None)
        return self.save(payload)

    def list_root_ids(self) -> list[str]:
        return sorted(self.load().get("attachments", {}).keys())

    def get_attachment_context(self, node_id: str) -> dict[str, Any]:
        return self.load().get("attachments", {}).get(node_id, {}).get("attachment_context", {})


class SessionRecorder:
    def __init__(self, session_db_path: str) -> None:
        self.db_path = Path(session_db_path).expanduser().resolve()
        ensure_directory(self.db_path.parent)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS library_usage (
                    operation_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    section_id TEXT,
                    project_path TEXT,
                    attachment_context_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS library_excerpt_cache (
                    operation_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    section_id TEXT,
                    excerpt_hash TEXT NOT NULL,
                    excerpt_text TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def record_usage(
        self,
        operation_id: str,
        session_id: str,
        node_id: str,
        revision_id: str,
        section_id: str | None,
        project_path: str | None,
        attachment_context: dict[str, Any] | None,
    ) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO library_usage (
                    operation_id, session_id, node_id, revision_id, section_id,
                    project_path, attachment_context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    session_id,
                    node_id,
                    revision_id,
                    section_id,
                    project_path or "",
                    canonical_json(attachment_context or {}),
                    utc_now(),
                ),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def cache_excerpt(
        self,
        operation_id: str,
        session_id: str,
        node_id: str,
        revision_id: str,
        section_id: str | None,
        excerpt_hash: str,
        excerpt_text: str,
        provenance: dict[str, Any],
    ) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO library_excerpt_cache (
                    operation_id, session_id, node_id, revision_id, section_id,
                    excerpt_hash, excerpt_text, provenance_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    session_id,
                    node_id,
                    revision_id,
                    section_id,
                    excerpt_hash,
                    excerpt_text,
                    canonical_json(provenance),
                    utc_now(),
                ),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


class EvidenceShelf:
    def __init__(self, evidence_root: Path) -> None:
        self.evidence_root = ensure_directory(evidence_root)
        self.db_path = self.evidence_root / "evidence.sqlite3"
        self.log_path = self.evidence_root / "reference_excerpt.jsonl"
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_records (
                    operation_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    section_id TEXT,
                    excerpt_hash TEXT NOT NULL,
                    excerpt_text TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def mirror_reference_excerpt(
        self,
        operation_id: str,
        excerpt_hash: str,
        excerpt_text: str,
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        record = {
            "operation_id": operation_id,
            "kind": "reference_excerpt",
            "node_id": provenance["node_id"],
            "revision_id": provenance["revision_id"],
            "section_id": provenance.get("section_id"),
            "excerpt_hash": excerpt_hash,
            "excerpt_text": excerpt_text,
            "provenance": provenance,
            "created_at": utc_now(),
        }
        conn = self._connect()
        inserted = False
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO evidence_records (
                    operation_id, kind, node_id, revision_id, section_id,
                    excerpt_hash, excerpt_text, provenance_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["operation_id"],
                    record["kind"],
                    record["node_id"],
                    record["revision_id"],
                    record["section_id"],
                    record["excerpt_hash"],
                    record["excerpt_text"],
                    canonical_json(record["provenance"]),
                    record["created_at"],
                ),
            )
            conn.commit()
            inserted = cursor.rowcount > 0
        finally:
            conn.close()

        if inserted:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

        return {
            "inserted": inserted,
            "db_path": str(self.db_path),
            "log_path": str(self.log_path),
            "operation_id": operation_id,
        }
