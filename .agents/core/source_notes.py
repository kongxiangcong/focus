"""Source-owned explicit notes and their durable, single-step recovery state.

One SQLite transaction contains the note, its recovery slot, and the request
receipt. The Host owns chat and never writes this database directly.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from .article_blog import bundle_fingerprint
from .reading_workspace import WorkspaceError, _validate_parser_bundle, validate_source_id
from .source_library import SourceLibrary


_LOCK = threading.RLock()
_REQUEST = re.compile(r"[A-Za-z0-9-]{8,80}\Z")
_KINDS = {"example", "conclusion", "question", "thought", "concept"}
_ORIGINS = {"user", "dialogue"}
_EVIDENCE_ROLES = {"source_claim", "explanation", "unresolved_question"}


def _payload_identity(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class SourceNotes:
    """Canonical note write and query boundary for one registered Source."""

    def __init__(self, workspace: Path, *, writer_id: str = "local-core"):
        self.workspace = Path(workspace).resolve()
        if not isinstance(writer_id, str) or not writer_id.strip():
            raise WorkspaceError("note_writer_invalid", "A current writer identity is required")
        self.writer_id = writer_id

    def _root(self, source_id: str) -> Path:
        source_id = validate_source_id(source_id)
        SourceLibrary(self.workspace).get(source_id)
        return self.workspace / "sources" / source_id

    def bundle_version(self, source_id: str) -> str:
        bundle = self._root(source_id) / "parser-bundle"
        _validate_parser_bundle(bundle)
        return bundle_fingerprint(bundle)

    def _connect(self, source_id: str) -> sqlite3.Connection:
        root = self._root(source_id) / "notes"
        root.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(root / "notes.sqlite3", timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, "
                   "content TEXT NOT NULL, kind TEXT NOT NULL, origin TEXT NOT NULL, "
                   "bundle TEXT NOT NULL, anchor TEXT, evidence_role TEXT NOT NULL, "
                   "deleted INTEGER NOT NULL, undo TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, digest TEXT, "
                   "result TEXT, cancelled INTEGER NOT NULL DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS clears (id TEXT PRIMARY KEY)")
        return db

    def generation(self, source_id: str) -> int:
        with _LOCK, closing(self._connect(source_id)) as db:
            return db.execute("SELECT count(*) FROM clears").fetchone()[0]

    def clear(self, source_id: str, *, request_id: str) -> None:
        """Erase notes and recovery payloads, retaining only revoked request IDs."""
        self._check_request(request_id)
        with _LOCK, closing(self._connect(source_id)) as db, db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM clears WHERE id=?", (request_id,)).fetchone():
                return
            db.execute("DELETE FROM notes")
            db.execute("UPDATE requests SET digest=NULL, result=NULL, cancelled=1")
            db.execute("INSERT INTO clears VALUES (?)", (request_id,))
        with closing(self._connect(source_id)) as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _anchor(self, source_id: str, version: str, anchor: dict | None) -> str | None:
        if anchor is None:
            return None
        if not isinstance(anchor, dict) or set(anchor) - {"sourceId", "bundle", "sourceLines", "quote"}:
            raise WorkspaceError("note_anchor_invalid", "Source anchor is invalid")
        if anchor.get("sourceId") != source_id or anchor.get("bundle") != version:
            raise WorkspaceError("note_anchor_changed", "Source anchor belongs to another Bundle")
        span = anchor.get("sourceLines")
        if not isinstance(span, list) or len(span) != 2 or any(type(n) is not int for n in span):
            raise WorkspaceError("note_anchor_invalid", "Source anchor lines are invalid")
        lines = (self._root(source_id) / "parser-bundle" / "content.md").read_text(encoding="utf-8").splitlines()
        start, end = span
        if start < 1 or end < start or end > len(lines):
            raise WorkspaceError("note_anchor_invalid", "Source anchor lines are outside the Bundle")
        quote = anchor.get("quote")
        if quote is not None and (not isinstance(quote, str) or not quote.strip() or quote not in "\n".join(lines[start - 1:end])):
            raise WorkspaceError("note_anchor_invalid", "Source anchor quote does not match")
        return json.dumps(anchor, ensure_ascii=False, sort_keys=True)

    def _public(self, row: sqlite3.Row, source_id: str, current_bundle: str) -> dict:
        anchor = json.loads(row["anchor"]) if row["anchor"] else None
        updated = bool(anchor and row["bundle"] != current_bundle)
        archive = self._root(source_id) / "reading" / "bundles" / row["bundle"]
        historical = bool(updated and archive.is_dir() and bundle_fingerprint(archive) == row["bundle"])
        return {"noteId": row["id"], "sourceId": source_id, "revision": row["revision"],
                "content": row["content"], "kind": row["kind"], "origin": row["origin"],
                "bundle": row["bundle"], "anchor": anchor, "evidenceRole": row["evidence_role"],
                "deleted": bool(row["deleted"]),
                "canUndo": row["undo"] is not None,
                "sourceUpdated": updated,
                "referenceStatus": "historical" if historical else "unavailable" if updated else "current"}

    def list(self, source_id: str, *, include_deleted: bool = False) -> list[dict]:
        version = self.bundle_version(source_id)
        with _LOCK, closing(self._connect(source_id)) as db, db:
            rows = db.execute("SELECT * FROM notes ORDER BY rowid").fetchall()
            return [self._public(row, source_id, version) for row in rows if include_deleted or not row["deleted"]]

    def result(self, source_id: str, request_id: str) -> dict | None:
        self._check_request(request_id)
        with _LOCK, closing(self._connect(source_id)) as db, db:
            row = db.execute("SELECT result, cancelled FROM requests WHERE id=?", (request_id,)).fetchone()
            return json.loads(row["result"]) if row and row["result"] else ({"status": "cancelled"} if row and row["cancelled"] else None)

    @staticmethod
    def _check_request(request_id: str) -> None:
        if not isinstance(request_id, str) or not _REQUEST.fullmatch(request_id):
            raise WorkspaceError("note_request_invalid", "A stable request ID is required")

    def cancel(self, source_id: str, request_id: str) -> dict:
        self._check_request(request_id)
        with _LOCK, closing(self._connect(source_id)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT result FROM requests WHERE id=?", (request_id,)).fetchone()
            if row and row["result"]:
                return json.loads(row["result"])
            db.execute("INSERT INTO requests(id, cancelled) VALUES(?, 1) "
                       "ON CONFLICT(id) DO UPDATE SET cancelled=1", (request_id,))
            return {"status": "cancelled"}

    def save(self, source_id: str, *, bundle: str, request_id: str, intent_id: str,
             content: str, kind: str, origin: str, evidence_role: str,
             anchor: dict | None = None, expected_generation: int | None = None) -> dict:
        """Commit a candidate only with the Host's bound explicit user intent."""
        self._check_request(request_id)
        self._check_request(intent_id)
        if not isinstance(content, str) or not content.strip() or len(content) > 8000 or kind not in _KINDS or origin not in _ORIGINS or evidence_role not in _EVIDENCE_ROLES:
            raise WorkspaceError("note_invalid", "Note candidate is invalid")
        if evidence_role == "source_claim" and anchor is None:
            raise WorkspaceError("note_anchor_required", "A Source claim requires a Source anchor")
        payload = {"sourceId": source_id, "bundle": bundle, "intentId": intent_id,
                   "writerId": self.writer_id,
                   "content": content, "kind": kind, "origin": origin,
                   "evidenceRole": evidence_role, "anchor": anchor}
        digest = _payload_identity(payload)
        with _LOCK, closing(self._connect(source_id)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if expected_generation is not None and expected_generation != db.execute("SELECT count(*) FROM clears").fetchone()[0]:
                raise WorkspaceError("discussion_cleared", "This discussion was cleared")
            prior = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if prior:
                if prior["cancelled"]:
                    raise WorkspaceError("note_cancelled", "Note request was cancelled")
                if prior["digest"] != digest:
                    raise WorkspaceError("note_request_conflict", "Request ID was used with different content")
                return json.loads(prior["result"])
            current = self.bundle_version(source_id)
            if bundle != current:
                raise WorkspaceError("note_bundle_changed", "Source Bundle changed")
            encoded_anchor = self._anchor(source_id, bundle, anchor)
            note_id = uuid.uuid4().hex
            db.execute("INSERT INTO notes VALUES(?, 1, ?, ?, ?, ?, ?, ?, 0, ?)",
                       (note_id, content.strip(), kind, origin, bundle, encoded_anchor, evidence_role,
                        json.dumps({"operation": "create"})))
            row = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
            result = {"status": "saved", "note": self._public(row, source_id, current)}
            db.execute("INSERT INTO requests VALUES(?, ?, ?, 0)", (request_id, digest, json.dumps(result, ensure_ascii=False)))
            return result

    def change(self, source_id: str, *, note_id: str, request_id: str,
               expected_revision: int, operation: str, content: str | None = None) -> dict:
        """Edit, delete, or consume the most recent recovery slot atomically."""
        self._check_request(request_id)
        if not isinstance(note_id, str) or not re.fullmatch(r"[0-9a-f]{32}", note_id):
            raise WorkspaceError("note_id_invalid", "Note ID is invalid")
        if type(expected_revision) is not int or expected_revision < 1 or operation not in {"edit", "delete", "undo"}:
            raise WorkspaceError("note_change_invalid", "Note change is invalid")
        if operation == "edit":
            if not isinstance(content, str) or not content.strip() or len(content) > 8000:
                raise WorkspaceError("note_invalid", "Edited note content is invalid")
        elif content is not None:
            raise WorkspaceError("note_change_invalid", "Unexpected note content")
        payload = {"sourceId": source_id, "noteId": note_id, "expectedRevision": expected_revision,
                   "writerId": self.writer_id, "operation": operation, "content": content}
        digest = _payload_identity(payload)
        with _LOCK, closing(self._connect(source_id)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if prior:
                if prior["cancelled"]:
                    raise WorkspaceError("note_cancelled", "Note change was cancelled")
                if prior["digest"] != digest:
                    raise WorkspaceError("note_request_conflict", "Request ID was used with different content")
                return json.loads(prior["result"])
            row = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
            if row is None:
                raise WorkspaceError("note_missing", "Note does not exist")
            current_bundle = self.bundle_version(source_id)
            current = self._public(row, source_id, current_bundle)
            if row["revision"] != expected_revision or (row["deleted"] and operation != "undo") or (operation == "undo" and row["undo"] is None):
                result = {"status": "conflict", "current": current, "attemptedContent": content}
            else:
                before = {field: row[field] for field in ("content", "kind", "origin", "bundle",
                                                          "anchor", "evidence_role", "deleted")}
                revision = row["revision"] + 1
                if operation == "edit":
                    db.execute("UPDATE notes SET revision=?, content=?, undo=? WHERE id=?",
                               (revision, content.strip(), json.dumps({"operation": "edit", "before": before}), note_id))
                elif operation == "delete":
                    db.execute("UPDATE notes SET revision=?, deleted=1, undo=? WHERE id=?",
                               (revision, json.dumps({"operation": "delete", "before": before}), note_id))
                else:
                    recovery = json.loads(row["undo"])
                    if recovery["operation"] == "create":
                        db.execute("UPDATE notes SET revision=?, deleted=1, undo=NULL WHERE id=?", (revision, note_id))
                    else:
                        saved = recovery["before"]
                        db.execute("UPDATE notes SET revision=?, content=?, kind=?, origin=?, bundle=?, anchor=?, "
                                   "evidence_role=?, deleted=?, undo=NULL WHERE id=?",
                                   (revision, saved["content"], saved["kind"], saved["origin"], saved["bundle"],
                                    saved["anchor"], saved["evidence_role"], saved["deleted"], note_id))
                updated = db.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
                result = {"status": "changed", "operation": operation,
                          "note": self._public(updated, source_id, current_bundle)}
            db.execute("INSERT INTO requests VALUES(?, ?, ?, 0)",
                       (request_id, digest, json.dumps(result, ensure_ascii=False)))
            return result
