"""Source-owned Reading Highlights, sharing note transactions and clear fences."""
from __future__ import annotations

import json
import re
import uuid
from contextlib import closing

from .reading_workspace import WorkspaceError
from .source_notes import SourceNotes, _LOCK, _payload_identity


class SourceHighlights:
    def __init__(self, notes: SourceNotes):
        self.notes = notes
        self.workspace = notes.workspace
        self.writer_id = notes.writer_id

    @staticmethod
    def _public(row, source_id: str, current_bundle: str) -> dict:
        return {"highlightId": row["id"], "sourceId": source_id, "revision": row["revision"],
                "bundle": row["bundle"], "planId": row["plan_id"], "chunkId": row["chunk_id"],
                "sourceLines": [row["source_start"], row["source_end"]], "layer": row["layer"],
                "range": {"start": row["range_start"], "end": row["range_end"]},
                "quote": json.loads(row["quote"]), "deleted": bool(row["deleted"]),
                "canUndo": row["undo"] is not None, "sourceUpdated": row["bundle"] != current_bundle}

    def list(self, source_id: str, *, include_deleted: bool = False) -> list[dict]:
        current = self.notes.bundle_version(source_id)
        with _LOCK, closing(self.notes._connect(source_id)) as db, db:
            return [self._public(row, source_id, current)
                    for row in db.execute("SELECT * FROM highlights ORDER BY rowid")
                    if include_deleted or not row["deleted"]]

    def result(self, source_id: str, request_id: str) -> dict | None:
        return self.notes.result(source_id, request_id)

    def save(self, source_id: str, *, request_id: str, plan_bundle: str,
             chunk_lines, locator: dict, expected_generation: int | None = None) -> dict:
        self.notes._check_request(request_id)
        digest = _payload_identity({"entity": "highlight", "op": "create", "sourceId": source_id,
                                    "bundle": plan_bundle, "locator": locator})
        with _LOCK, closing(self.notes._connect(source_id)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if expected_generation is not None and expected_generation != db.execute("SELECT count(*) FROM clears").fetchone()[0]:
                raise WorkspaceError("discussion_cleared", "This discussion was cleared")
            prior = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if prior:
                if prior["cancelled"]:
                    raise WorkspaceError("note_cancelled", "Highlight request was cancelled")
                if prior["digest"] != digest:
                    raise WorkspaceError("highlight_request_conflict", "Request ID was used with different content")
                return json.loads(prior["result"])
            current = self.notes.bundle_version(source_id)
            if plan_bundle != current:
                raise WorkspaceError("highlight_bundle_changed", "Source Bundle changed")
            highlight_id = uuid.uuid4().hex
            db.execute("INSERT INTO highlights VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
                       (highlight_id, plan_bundle, locator["planId"], locator["chunkId"],
                        chunk_lines[0], chunk_lines[1], locator["layer"], locator["range"]["start"],
                        locator["range"]["end"], json.dumps(locator["quote"], ensure_ascii=False, sort_keys=True),
                        json.dumps({"operation": "create"})))
            row = db.execute("SELECT * FROM highlights WHERE id=?", (highlight_id,)).fetchone()
            result = {"status": "saved", "highlight": self._public(row, source_id, current)}
            db.execute("INSERT INTO requests VALUES (?, ?, ?, 0)",
                       (request_id, digest, json.dumps(result, ensure_ascii=False)))
            return result

    def change(self, source_id: str, *, highlight_id: str, request_id: str,
               expected_revision: int, operation: str) -> dict:
        self.notes._check_request(request_id)
        if (not isinstance(highlight_id, str) or not re.fullmatch(r"[0-9a-f]{32}", highlight_id)
                or type(expected_revision) is not int or expected_revision < 1
                or operation not in ("delete", "undo")):
            raise WorkspaceError("highlight_invalid", "Highlight change is invalid")
        digest = _payload_identity({"entity": "highlight", "op": operation, "sourceId": source_id,
                                    "highlightId": highlight_id, "expectedRevision": expected_revision})
        with _LOCK, closing(self.notes._connect(source_id)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
            if prior:
                if prior["cancelled"]:
                    raise WorkspaceError("note_cancelled", "Highlight request was cancelled")
                if prior["digest"] != digest:
                    raise WorkspaceError("highlight_request_conflict", "Request ID was used with different content")
                return json.loads(prior["result"])
            row = db.execute("SELECT * FROM highlights WHERE id=?", (highlight_id,)).fetchone()
            if row is None:
                raise WorkspaceError("highlight_not_found", "Highlight does not exist")
            current_bundle = self.notes.bundle_version(source_id)
            current = self._public(row, source_id, current_bundle)
            if (row["revision"] != expected_revision or (row["deleted"] and operation != "undo")
                    or (operation == "undo" and row["undo"] is None)):
                result = {"status": "conflict", "current": current}
            else:
                if operation == "delete":
                    deleted, undo = 1, json.dumps({"operation": "delete"})
                else:
                    deleted = int(json.loads(row["undo"])["operation"] == "create")
                    undo = None
                db.execute("UPDATE highlights SET revision=?, deleted=?, undo=? WHERE id=?",
                           (row["revision"] + 1, deleted, undo, highlight_id))
                updated = db.execute("SELECT * FROM highlights WHERE id=?", (highlight_id,)).fetchone()
                result = {"status": "changed", "operation": operation,
                          "highlight": self._public(updated, source_id, current_bundle)}
            db.execute("INSERT INTO requests VALUES (?, ?, ?, 0)",
                       (request_id, digest, json.dumps(result, ensure_ascii=False)))
            return result


from .workspace_lifecycle import guard_workspace_class
SourceHighlights = guard_workspace_class(SourceHighlights)
