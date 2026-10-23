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


def check_sentence(value, *, plan_id: str, chunk_id: str, has_translation: bool, code: str) -> dict:
    """Validate a rendered sentence selection and bind its Plan/Chunk identity."""
    if not isinstance(value, dict) or set(value) != {"layer", "range", "quote"}:
        raise WorkspaceError(code, "Sentence locator is invalid")
    layer, span, quote = value["layer"], value["range"], value["quote"]
    if layer not in ("source", "translation") or (layer == "translation" and not has_translation):
        raise WorkspaceError(code, "Sentence layer is unavailable")
    if (not isinstance(span, dict) or set(span) != {"start", "end"}
            or any(type(span[k]) is not int for k in ("start", "end"))
            or not 0 <= span["start"] < span["end"] or span["end"] - span["start"] > 2000):
        raise WorkspaceError(code, "Sentence range is invalid")
    if (not isinstance(quote, dict) or set(quote) != {"exact", "prefix", "suffix"}
            or any(not isinstance(quote[k], str) for k in ("exact", "prefix", "suffix"))
            or not 1 <= len(quote["exact"]) <= 2000
            or len(quote["prefix"]) > 64 or len(quote["suffix"]) > 64):
        raise WorkspaceError(code, "Sentence quote is invalid")
    return {"planId": plan_id, "chunkId": chunk_id, "layer": layer,
            "range": {"start": span["start"], "end": span["end"]},
            "quote": {key: quote[key] for key in ("exact", "prefix", "suffix")}}


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

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, name: str) -> None:
        if name not in {"placement", "sentence"}:
            raise ValueError("Unsupported note column")
        if name not in {row["name"] for row in db.execute("PRAGMA table_info(notes)")}:
            db.execute(f"ALTER TABLE notes ADD COLUMN {name} TEXT")

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
        self._ensure_column(db, "placement")
        db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, digest TEXT, "
                   "result TEXT, cancelled INTEGER NOT NULL DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS clears (id TEXT PRIMARY KEY)")
        self._ensure_column(db, "sentence")
        db.execute("CREATE TABLE IF NOT EXISTS highlights (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, "
                   "bundle TEXT NOT NULL, plan_id TEXT NOT NULL, chunk_id TEXT NOT NULL, "
                   "source_start INTEGER NOT NULL, source_end INTEGER NOT NULL, layer TEXT NOT NULL, "
                   "range_start INTEGER NOT NULL, range_end INTEGER NOT NULL, quote TEXT NOT NULL, "
                   "deleted INTEGER NOT NULL, undo TEXT)")
        return db

    def generation(self, source_id: str) -> int:
        with _LOCK, closing(self._connect(source_id)) as db:
            return db.execute("SELECT count(*) FROM clears").fetchone()[0]

    @staticmethod
    def _check_annotation_overlap(db: sqlite3.Connection, bundle: str, locator: dict,
                                  entity: str, exclude_id: str | None = None) -> None:
        """Check occupancy inside the caller's write transaction, across both entities.

        An exact range can carry one highlight and one sentence note. Any other
        intersection is ambiguous, and must not redirect a new write to an old note.
        """
        candidates = [("highlight", row["id"],
                       {"planId": row["plan_id"], "chunkId": row["chunk_id"],
                        "layer": row["layer"],
                        "range": {"start": row["range_start"], "end": row["range_end"]}})
                      for row in db.execute("SELECT * FROM highlights WHERE deleted=0 AND bundle=?", (bundle,))]
        candidates.extend(("note", row["id"], json.loads(row["sentence"]))
                          for row in db.execute("SELECT id, bundle, sentence FROM notes "
                                                "WHERE deleted=0 AND sentence IS NOT NULL AND bundle=?", (bundle,)))
        start, end = locator["range"]["start"], locator["range"]["end"]
        for other_entity, other_id, other in candidates:
            if other_entity == entity and other_id == exclude_id:
                continue
            if any(other[key] != locator[key] for key in ("planId", "chunkId", "layer")):
                continue
            other_start, other_end = other["range"]["start"], other["range"]["end"]
            if start >= other_end or end <= other_start:
                continue
            if entity != other_entity and (start, end) == (other_start, other_end):
                continue
            code = "highlight_overlap" if entity == "highlight" else "note_sentence_overlap"
            raise WorkspaceError(code, "The sentence range is already occupied; select it again")

    def clear(self, source_id: str, *, request_id: str) -> None:
        """Erase notes and recovery payloads, retaining only revoked request IDs."""
        self._check_request(request_id)
        with _LOCK, closing(self._connect(source_id)) as db, db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM clears WHERE id=?", (request_id,)).fetchone():
                return
            db.execute("DELETE FROM notes")
            db.execute("DELETE FROM highlights")
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

    def _placement(self, source_id: str, version: str, placement: dict | None) -> str | None:
        if placement is None:
            return None
        if not isinstance(placement, dict) or set(placement) != {"sourceId", "bundle", "sourceLines"}:
            raise WorkspaceError("note_placement_invalid", "Note display placement is invalid")
        try:
            return self._anchor(source_id, version, placement)
        except WorkspaceError as error:
            raise WorkspaceError("note_placement_invalid", "Note display placement is invalid") from error

    def _public(self, row: sqlite3.Row, source_id: str, current_bundle: str) -> dict:
        anchor = json.loads(row["anchor"]) if row["anchor"] else None
        placement = json.loads(row["placement"]) if row["placement"] else None
        updated = bool((anchor or placement) and row["bundle"] != current_bundle)
        archive = self._root(source_id) / "reading" / "bundles" / row["bundle"]
        historical = bool(updated and archive.is_dir() and bundle_fingerprint(archive) == row["bundle"])
        return {"noteId": row["id"], "sourceId": source_id, "revision": row["revision"],
                "content": row["content"], "kind": row["kind"], "origin": row["origin"],
                "bundle": row["bundle"], "anchor": anchor, "placement": placement,
                "evidenceRole": row["evidence_role"],
                "sentence": json.loads(row["sentence"]) if row["sentence"] else None,
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
             anchor: dict | None = None, placement: dict | None = None,
             sentence: dict | None = None,
             expected_generation: int | None = None) -> dict:
        """Commit a candidate only with the Host's bound explicit user intent."""
        self._check_request(request_id)
        self._check_request(intent_id)
        if not isinstance(content, str) or not content.strip() or len(content) > 8000 or kind not in _KINDS or origin not in _ORIGINS or evidence_role not in _EVIDENCE_ROLES:
            raise WorkspaceError("note_invalid", "Note candidate is invalid")
        if evidence_role == "source_claim" and anchor is None:
            raise WorkspaceError("note_anchor_required", "A Source claim requires a Source anchor")
        if sentence is not None and anchor is None:
            raise WorkspaceError("note_sentence_invalid", "A sentence note requires a Source anchor")
        payload = {"sourceId": source_id, "bundle": bundle, "intentId": intent_id,
                   "content": content, "kind": kind, "origin": origin,
                   "evidenceRole": evidence_role, "anchor": anchor}
        # Absent optional fields retain the identity of pre-annotation request receipts.
        if placement is not None:
            payload["placement"] = placement
        if sentence is not None:
            payload["sentence"] = sentence
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
            encoded_placement = self._placement(source_id, bundle, placement)
            if sentence is not None:
                self._check_annotation_overlap(db, bundle, sentence, "note")
            note_id = uuid.uuid4().hex
            db.execute("INSERT INTO notes(id, revision, content, kind, origin, bundle, anchor, "
                       "evidence_role, deleted, undo, sentence, placement) VALUES(?, 1, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
                       (note_id, content.strip(), kind, origin, bundle, encoded_anchor, evidence_role,
                        json.dumps({"operation": "create"}),
                        json.dumps(sentence, ensure_ascii=False, sort_keys=True) if sentence is not None else None,
                        encoded_placement))
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
                   "operation": operation, "content": content}
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
                        if not saved["deleted"] and row["sentence"]:
                            self._check_annotation_overlap(db, saved["bundle"],
                                                           json.loads(row["sentence"]), "note", note_id)
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


from .workspace_lifecycle import guard_workspace_class
SourceNotes = guard_workspace_class(SourceNotes)
