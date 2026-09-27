"""Shared Reading Application for preparation and navigation.

Runtime returns candidates; only ReadingCore commits reading assets. Host
starts a task and projects its status without owning the business sequence.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Protocol

from .article_blog import bundle_fingerprint
from .reading_workspace import (
    WorkspaceCore, WorkspaceError, _identifier, _needs_translation,
    _read_chunk_records, _read_document, _read_glossary, _read_reading_record,
    _reading_plan_records, _source_heading_paths, _protected_source_ranges, _validate_parser_bundle, _write_document,
    validate_source_id,
)
from .source_library import SourceLibrary
from .reading_progress import enqueue

METHOD_VERSION = "focus-reading-v0.2"
_LOCK = threading.RLock()


def _reference_heading(heading: str) -> bool:
    return re.fullmatch(r"(?:\d+(?:\.\d+)*[.)、]?\s*)?(?:references|bibliography|参考文献|参考资料|参考来源)",
                        heading.strip(), re.I) is not None


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ReadingRuntime(Protocol):
    """Produce candidates without writing Workspace assets."""

    def context(self, *, source_id: str, ranges: list[dict], previous: dict | None) -> dict: ...
    def plan(self, *, source_id: str, ranges: list[dict], context: dict) -> dict: ...
    def translate(self, *, source_id: str, chunk: dict, context: dict,
                  glossary: list[dict], neighbors: list[dict], issue: str | None) -> str: ...
    def check(self, *, source_id: str, chunks: list[dict],
              context: dict, glossary: list[dict]) -> dict: ...
    def cancel(self, source_id: str | None = None) -> None: ...


class ReadingCore:
    """The write boundary for a single Source's candidate preparation."""

    def __init__(self, workspace: Path, *, writer_id: str):
        self.workspace = Path(workspace).resolve()
        self.writer_id = writer_id
        self.core = WorkspaceCore(self.workspace)

    def _root(self, source_id: str) -> Path:
        source_id = validate_source_id(source_id)
        SourceLibrary(self.workspace).get(source_id)
        return self.workspace / "sources" / source_id

    def _path(self, source_id: str) -> Path:
        return self._root(source_id) / "reading" / "preparation.json"

    def _bundle_version(self, source_id: str) -> str:
        bundle = self._root(source_id) / "parser-bundle"
        _validate_parser_bundle(bundle)
        return bundle_fingerprint(bundle)

    def _read(self, source_id: str) -> dict | None:
        path = self._path(source_id)
        return _read_document(path) if path.is_file() else None

    def _write(self, source_id: str, run: dict) -> None:
        _write_document(self._path(source_id), run)

    @staticmethod
    def _request_input(entry: dict) -> dict:
        return entry.get("input", entry)

    def request_result(self, source_id: str, request_id: str) -> dict | None:
        run = self._read(source_id)
        entry = (run or {}).get("requests", {}).get(request_id)
        return entry.get("result") if isinstance(entry, dict) else None

    def _guard(self, source_id: str, run_id: str, attempt: str, bundle: str) -> dict:
        run = self._read(source_id)
        if not run or run["run_id"] != run_id or run["attempt"] != attempt:
            raise WorkspaceError("reading_attempt_changed", "Preparation attempt is stale")
        if run["status"] != "running":
            raise WorkspaceError("reading_attempt_closed", "Preparation cannot commit")
        if run["writer_id"] != self.writer_id:
            raise WorkspaceError("reading_writer_changed", "Another writer owns preparation")
        if run["bundle"] != bundle or self._bundle_version(source_id) != bundle:
            raise WorkspaceError("reading_bundle_changed", "Parser Bundle changed")
        if run.get("plan_id") and run.get("plan_revision"):
            root = self._root(source_id) / "reading" / "plans" / run["plan_id"]
            if _digest(_read_chunk_records(root / "chunks.jsonl")) != run["plan_revision"]:
                raise WorkspaceError("reading_plan_changed", "Candidate Reading Plan changed")
            if run.get("glossary_revision") and _digest(_read_glossary(root / "glossary.tsv")) != run["glossary_revision"]:
                raise WorkspaceError("reading_glossary_changed", "Plan Glossary changed")
        return run

    def _guard_candidate(self, source_id: str, run_id: str, attempt: str, bundle: str,
                         step: str, candidate: Any) -> dict:
        try:
            return self._guard(source_id, run_id, attempt, bundle)
        except WorkspaceError as exc:
            if exc.error_id in ("reading_bundle_changed", "reading_plan_changed", "reading_glossary_changed"):
                path = self._root(source_id) / "reading" / "conflicts" / f"{run_id}-{uuid.uuid4().hex}.json"
                _write_document(path, {"source_id": source_id, "run_id": run_id, "attempt": attempt,
                                       "bundle": bundle, "step": step, "candidate": candidate,
                                       "reason": exc.error_id})
            raise

    def begin(self, source_id: str, *, request_id: str, rebuild: bool = False,
              runtime: dict | None = None) -> dict:
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,80}", request_id):
            raise WorkspaceError("reading_request_invalid", "Unique request ID required")
        with _LOCK:
            bundle = self._bundle_version(source_id)
            old = self._read(source_id)
            request_payload = {"operation": "rebuild" if rebuild else "begin", "source_id": source_id}
            requests = dict(old.get("requests", {})) if old else {}
            if request_id in requests:
                if self._request_input(requests[request_id]) != request_payload:
                    raise WorkspaceError("reading_request_reused", "Request ID has different reading input")
                return old
            if old and old["bundle"] == bundle:
                if old["status"] in ("running", "ready") and not rebuild:
                    if old["status"] == "running" and old["writer_id"] != self.writer_id:
                        raise WorkspaceError("reading_writer_changed", "Another writer owns preparation")
                    if old["status"] == "ready" and not self._check_valid(source_id, old):
                        raise WorkspaceError("reading_ready_invalid", "Ready content has changed; rebuild explicitly")
                    old.setdefault("requests", {})[request_id] = {"input": request_payload,
                        "result": {"operation": "begin", "run_id": old["run_id"],
                                   "status": "reused", "source_id": source_id}}
                    self._write(source_id, old)
                    return old
                if old["status"] == "running":
                    raise WorkspaceError("reading_busy", "Preparation already running")
            state = _read_document(self.workspace / "state.json")
            selected = state["sources"][source_id]
            plan_id = None if rebuild or (old and old["bundle"] != bundle) else selected.get("current_plan_id")
            if plan_id and not (self._root(source_id) / "reading" / "plans" / plan_id / "chunks.jsonl").is_file():
                plan_id = None
            run = {
                "run_id": uuid.uuid4().hex, "request_id": request_id,
                "attempt": uuid.uuid4().hex, "writer_id": self.writer_id,
                "source_id": source_id, "bundle": bundle, "plan_id": plan_id,
                "method": METHOD_VERSION, "runtime": runtime, "status": "running",
                "step": "context", "context": None, "context_revision": None,
                "glossary_revision": None, "plan_revision": None, "check": None, "repair_rounds": 0,
                "transport_retries": 0, "error": None, "rebuild": rebuild,
                "ready_plans": dict(old.get("ready_plans", {})) if old else {},
                "requests": {**requests, request_id: {"input": request_payload,
                    "result": {"operation": request_payload["operation"], "run_id": None,
                               "status": "started", "source_id": source_id}}},
            }
            run["requests"][request_id]["result"]["run_id"] = run["run_id"]
            self._write(source_id, run)
            return run

    def status(self, source_id: str) -> dict | None:
        with _LOCK:
            run = self._read(source_id)
            if run is None:
                return None
            selected = _read_document(self.workspace / "state.json")["sources"][source_id]
            selected_id = selected.get("current_plan_id")
            selected_ready = bool(selected_id and self._plan_ready(source_id, selected_id))
            if run["bundle"] != self._bundle_version(source_id):
                return {**run, "status": "bundle_changed", "ready": False,
                        "selected_plan_id": selected_id, "selected_ready": selected_ready,
                        "candidate": False}
            progress = self._plan_status(source_id, run["plan_id"]) if run["plan_id"] else {
                "total": 0, "completed": 0, "pending": []}
            return {**run, **progress,
                    "ready": run["status"] == "ready" and self._check_valid(source_id, run),
                    "selected_plan_id": selected_id, "selected_ready": selected_ready,
                    "candidate": bool(selected_id and run["plan_id"] != selected_id)}

    def open_ready(self, source_id: str, *, request_id: str) -> dict:
        """Activate the first ready Plan, or reopen the already selected Plan."""
        with _LOCK:
            if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,80}", request_id):
                raise WorkspaceError("reading_request_invalid", "Unique request ID required")
            state_path = self.workspace / "state.json"
            state = _read_document(state_path)
            previous = state.get("reading_requests", {}).get(request_id)
            if previous:
                if previous.get("input") != {"operation": "open", "source_id": source_id}:
                    raise WorkspaceError("reading_request_reused", "Request ID has different reading input")
                return previous["result"]
            selected = state["sources"][source_id]
            ready = self.status(source_id)
            selected_plan = selected.get("current_plan_id")
            if selected_plan:
                if not self._plan_ready(source_id, selected_plan):
                    raise WorkspaceError("reading_not_ready", "Selected Plan is not ready for this Bundle")
                plan_id = selected_plan
            elif ready and ready["ready"]:
                plan_id = ready["plan_id"]
            else:
                raise WorkspaceError("reading_not_ready", "Reading Plan is not ready")
            changed = state.get("current_source_id") != source_id or not selected.get("reading_started", False)
            if selected_plan is None:
                chunks = _read_chunk_records(self._root(source_id) / "reading" / "plans" / plan_id / "chunks.jsonl")
                selected.update(current_plan_id=plan_id, current_chunk_id=chunks[0]["chunk_id"])
                changed = True
                selected['reading_pass'] = 1
            elif selected.get('reading_pass') is None:
                selected['reading_pass'] = 1
            selected["reading_started"] = True
            state["current_source_id"] = source_id
            if changed:
                state["reading_revision"] = int(state.get("reading_revision", 0)) + 1
            result = {"operation": "open", "source_id": source_id, "plan_id": plan_id,
                      "chunk_id": selected["current_chunk_id"],
                      "reading_revision": int(state.get("reading_revision", 0))}
            state.setdefault("reading_requests", {})[request_id] = {
                "input": {"operation": "open", "source_id": source_id}, "result": result}
            _write_document(state_path, state)
            return result

    def activate_candidate(self, source_id: str, *, plan_id: str, reading_revision: int,
                           request_id: str) -> dict:
        source_id = validate_source_id(source_id)
        plan_id = _identifier(plan_id, "plan_id")
        if type(reading_revision) is not int or reading_revision < 0:
            raise WorkspaceError("reading_receipt_invalid", "Expected reading revision is required")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,80}", request_id):
            raise WorkspaceError("reading_request_invalid", "Unique request ID required")
        payload = {"operation": "activate", "source_id": source_id,
                   "plan_id": plan_id, "reading_revision": reading_revision}
        with _LOCK:
            path = self.workspace / "state.json"
            state = _read_document(path)
            old = state.get("reading_requests", {}).get(request_id)
            if old:
                if old["input"] != payload:
                    raise WorkspaceError("reading_request_reused", "Request ID has different reading input")
                return old["result"]
            if int(state.get("reading_revision", 0)) != reading_revision:
                raise WorkspaceError("cursor_changed", "阅读位置已改变，请刷新后重试。")
            run = self.status(source_id)
            if not run or not run["ready"] or run["plan_id"] != plan_id or not run["candidate"]:
                raise WorkspaceError("reading_candidate_not_ready", "Candidate Plan is not ready")
            chunks = _read_chunk_records(self._root(source_id) / "reading" / "plans" / plan_id / "chunks.jsonl")
            state["sources"][source_id].update(current_plan_id=plan_id,
                current_chunk_id=chunks[0]["chunk_id"], reading_started=True, reading_pass=1)
            state["current_source_id"] = source_id
            state["reading_revision"] = reading_revision + 1
            result = {"operation": "activate", "source_id": source_id, "plan_id": plan_id,
                      "chunk_id": chunks[0]["chunk_id"], "reading_revision": state["reading_revision"]}
            state.setdefault("reading_requests", {})[request_id] = {"input": payload, "result": result}
            _write_document(path, state)
            return result

    def revise_candidate_glossary(self, source_id: str, *, plan_id: str,
                                  expected_glossary_revision: str, terms: list[dict],
                                  request_id: str) -> dict:
        """Explicitly revise only an unselected candidate and recheck it."""
        source_id = validate_source_id(source_id)
        plan_id = _identifier(plan_id, "plan_id")
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,80}", request_id):
            raise WorkspaceError("reading_request_invalid", "Unique request ID required")
        if not isinstance(terms, list) or any(not isinstance(t, dict) or set(t) != {"source", "translation"}
                or any(not isinstance(t[k], str) or not t[k].strip() or any(c in t[k] for c in "\t\r\n")
                       for k in ("source", "translation")) for t in terms):
            raise WorkspaceError("reading_glossary_invalid", "Glossary terms are invalid")
        if len({t["source"].casefold() for t in terms}) != len(terms):
            raise WorkspaceError("reading_glossary_invalid", "Glossary terms are duplicated")
        payload = {"operation": "revise_glossary", "source_id": source_id, "plan_id": plan_id,
                   "expected_glossary_revision": expected_glossary_revision, "terms": terms}
        with _LOCK:
            run = self._read(source_id)
            if not run or run.get("plan_id") != plan_id or not run.get("rebuild"):
                raise WorkspaceError("reading_candidate_missing", "No rebuild candidate exists")
            prior = run.get("requests", {}).get(request_id)
            if prior:
                if self._request_input(prior) != payload:
                    raise WorkspaceError("reading_request_reused", "Request ID has different reading input")
                return run
            selected = _read_document(self.workspace / "state.json")["sources"][source_id]
            if selected.get("current_plan_id") == plan_id:
                raise WorkspaceError("reading_candidate_selected", "Selected Plan cannot be edited")
            if run["writer_id"] != self.writer_id or run["status"] == "running":
                raise WorkspaceError("reading_busy", "Candidate must be idle before glossary revision")
            if run["bundle"] != self._bundle_version(source_id) or run.get("glossary_revision") != expected_glossary_revision:
                raise WorkspaceError("reading_glossary_changed", "Candidate glossary version changed")
            root = self._root(source_id) / "reading" / "plans" / plan_id
            old_terms = _read_glossary(root / "glossary.tsv")
            old_map = {t["source"].casefold(): t["translation"] for t in old_terms}
            new_map = {t["source"].casefold(): t["translation"] for t in terms}
            changed = {term for term in old_map.keys() | new_map.keys() if old_map.get(term) != new_map.get(term)}
            lines = (self._root(source_id) / "parser-bundle" / "content.md").read_text(encoding="utf-8").splitlines()
            affected = []
            for chunk in _read_chunk_records(root / "chunks.jsonl"):
                start, end = chunk["source_lines"]
                source_text = "\n".join(lines[start - 1:end]).casefold()
                if any(term in source_text for term in changed):
                    affected.append(chunk["chunk_id"])
            (root / "glossary.tsv").write_text("".join(f'{t["source"]}\t{t["translation"]}\n' for t in terms), encoding="utf-8")
            for chunk_id in affected:
                path = root / "records" / f"{chunk_id}.json"
                record = _read_reading_record(path, chunk_id)
                record["translation"] = None
                record.pop("translation_meta", None)
                _write_document(path, record)
            run["glossary_revision"] = _digest(_read_glossary(root / "glossary.tsv"))
            run["check"] = None
            run["status"] = "running"
            run["step"] = "translate" if affected else "check"
            run["attempt"] = uuid.uuid4().hex
            run["request_id"] = request_id
            run["error"] = None
            run.setdefault("ready_plans", {}).pop(plan_id, None)
            run.setdefault("requests", {})[request_id] = {"input": payload, "result": {
                "operation": "revise_glossary", "source_id": source_id, "plan_id": plan_id,
                "affected": affected, "status": "started", "run_id": run["run_id"]}}
            self._write(source_id, run)
            return run

    def _plan_ready(self, source_id: str, plan_id: str) -> bool:
        run = self._read(source_id) or {}
        certificate = run.get("ready_plans", {}).get(plan_id)
        if certificate is None and run.get("status") == "ready" and run.get("plan_id") == plan_id:
            certificate = run
        if not certificate or certificate.get("bundle") != self._bundle_version(source_id):
            return False
        try:
            root = self._root(source_id) / "reading" / "plans" / plan_id
            return (certificate.get("plan_revision") == _digest(_read_chunk_records(root / "chunks.jsonl"))
                    and certificate.get("glossary_revision") == _digest(_read_glossary(root / "glossary.tsv"))
                    and not self._plan_status(source_id, plan_id)["pending"]
                    and certificate.get("content_revision") == self._content_revision(source_id, certificate))
        except WorkspaceError:
            return False

    def _navigation(self, operation: str, *, source_id: str, plan_id: str, chunk_id: str | None,
                    reading_revision: int, request_id: str) -> dict:
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,80}", request_id):
            raise WorkspaceError("reading_request_invalid", "Unique request ID required")
        if type(reading_revision) is not int or reading_revision < 0:
            raise WorkspaceError("reading_receipt_invalid", "Reading revision is required")
        source_id = validate_source_id(source_id)
        plan_id = _identifier(plan_id, "plan_id")
        chunk_id = _identifier(chunk_id, "chunk_id") if chunk_id is not None else None
        payload = {"operation": operation, "source_id": source_id, "plan_id": plan_id,
                   "chunk_id": chunk_id, "reading_revision": reading_revision}
        with _LOCK:
            state_path = self.workspace / "state.json"
            state = _read_document(state_path)
            previous = state.get("reading_requests", {}).get(request_id)
            if previous:
                if previous.get("input") != payload:
                    raise WorkspaceError("reading_request_reused", "Request ID has different reading input")
                return previous["result"]
            selected = state["sources"].get(source_id)
            if (state.get("current_source_id") != source_id or not selected
                or selected.get("current_plan_id") != plan_id
                or selected.get("current_chunk_id") != chunk_id
                or int(state.get("reading_revision", 0)) != reading_revision):
                raise WorkspaceError("cursor_changed", "阅读位置已改变，请刷新后重试。")
            if not selected.get("reading_started") or not self._plan_ready(source_id, plan_id):
                raise WorkspaceError("reading_not_ready", "Reading Plan is not ready")
            chunks = _read_chunk_records(self._root(source_id) / "reading" / "plans" / plan_id / "chunks.jsonl")
            ids = [chunk["chunk_id"] for chunk in chunks]
            if operation == "continue":
                if chunk_id not in ids or chunk_id == ids[-1]:
                    raise WorkspaceError("reading_last_requires_finish", "Use Finish on the final Chunk")
                next_chunk = ids[ids.index(chunk_id) + 1]
            elif operation == "finish":
                if chunk_id != ids[-1]:
                    raise WorkspaceError("reading_finish_early", "Only the final Chunk may finish the Source")
                next_chunk = None
            elif operation == "reread":
                next_chunk = ids[0]
            else:
                raise WorkspaceError("reading_operation_invalid", "Unknown Reading operation")
            selected["current_chunk_id"] = next_chunk
            reading_pass = int(selected.get('reading_pass', 1))
            if operation == 'reread':
                selected['reading_pass'] = reading_pass + 1
            else:
                enqueue(state, request_id=request_id, operation=operation,
                        source_id=source_id, bundle=self._bundle_version(source_id),
                        plan_id=plan_id, chunk_id=chunk_id, reading_pass=reading_pass)
            state["reading_revision"] = reading_revision + 1
            result = {"operation": operation, "source_id": source_id, "plan_id": plan_id,
                      "previous_chunk_id": chunk_id, "chunk_id": next_chunk,
                      "reading_revision": state["reading_revision"],
                      "reading_pass": reading_pass + 1 if operation == 'reread' else reading_pass}
            if operation != 'reread':
                result['progress_id'] = request_id
            state.setdefault("reading_requests", {})[request_id] = {"input": payload, "result": result}
            _write_document(state_path, state)
            return result

    def continue_reading(self, **kwargs) -> dict:
        return self._navigation("continue", **kwargs)

    def finish_reading(self, **kwargs) -> dict:
        return self._navigation("finish", **kwargs)

    def reread(self, **kwargs) -> dict:
        return self._navigation("reread", **kwargs)

    def review(self, *, source_id: str, plan_id: str, chunk_id: str) -> dict:
        """Return an already read Chunk without storing a second Cursor."""
        with _LOCK:
            state = _read_document(self.workspace / "state.json")
            selected = state["sources"].get(source_id)
            if state.get("current_source_id") != source_id or not selected or selected.get("current_plan_id") != plan_id:
                raise WorkspaceError("cursor_changed", "阅读位置已改变，请刷新后重试。")
            chunks = _read_chunk_records(self._root(source_id) / "reading" / "plans" / plan_id / "chunks.jsonl")
            ids = [chunk["chunk_id"] for chunk in chunks]
            current = selected.get("current_chunk_id")
            if chunk_id not in ids or (current is not None and ids.index(chunk_id) >= ids.index(current)):
                raise WorkspaceError("reading_review_unread", "Only already read Chunks may be reviewed")
            return self.core.preparation_chunk(source_id=source_id, plan_id=plan_id, chunk_id=chunk_id)

    def _plan_status(self, source_id: str, plan_id: str) -> dict:
        root = self._root(source_id) / "reading" / "plans" / _identifier(plan_id, "plan_id")
        metadata = _validate_parser_bundle(self._root(source_id) / "parser-bundle")
        chunks = _read_chunk_records(root / "chunks.jsonl")
        pending = []
        for chunk in chunks:
            record = _read_reading_record(root / "records" / f"{chunk['chunk_id']}.json", chunk["chunk_id"])
            if _needs_translation(metadata, chunk) and not record["translation"]:
                pending.append(chunk["chunk_id"])
            if not _needs_translation(metadata, chunk) and record["translation"] is not None:
                raise WorkspaceError("reading_record_invalid", "Chinese content must not have a translation")
        return {"total": len(chunks), "completed": len(chunks) - len(pending), "pending": pending}

    def _content_revision(self, source_id: str, run: dict) -> str:
        root = self._root(source_id) / "reading" / "plans" / run["plan_id"]
        chunks = _read_chunk_records(root / "chunks.jsonl")
        records = [self._record_revision(root, c["chunk_id"]) for c in chunks]
        return _digest([run["bundle"], run["plan_id"], run["context_revision"],
                        run["glossary_revision"], chunks, records])

    @staticmethod
    def _record_revision(root: Path, chunk_id: str) -> dict:
        record = _read_reading_record(root / "records" / f"{chunk_id}.json", chunk_id)
        return {"translation": record["translation"], "translation_meta": record.get("translation_meta")}

    def _check_valid(self, source_id: str, run: dict) -> bool:
        root = self._root(source_id) / "reading" / "plans" / run["plan_id"]
        if run.get("plan_revision") != _digest(_read_chunk_records(root / "chunks.jsonl")):
            return False
        if run.get("glossary_revision") != _digest(_read_glossary(root / "glossary.tsv")):
            return False
        return bool(run["check"] and run["check"].get("passed") is True
                    and not self._plan_status(source_id, run["plan_id"])["pending"]
                    and run["check"].get("content_revision") == self._content_revision(source_id, run))

    def resume(self, source_id: str, *, request_id: str) -> dict:
        with _LOCK:
            run = self._read(source_id)
            if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,80}", request_id):
                raise WorkspaceError("reading_request_invalid", "Unique request ID required")
            request_payload = {"operation": "resume", "source_id": source_id}
            if run and request_id in run.get("requests", {}):
                if self._request_input(run["requests"][request_id]) != request_payload:
                    raise WorkspaceError("reading_request_reused", "Request ID has different reading input")
                return run
            if run is None or run["status"] not in ("failed", "cancelled", "interrupted"):
                raise WorkspaceError("reading_resume_invalid", "No interrupted preparation")
            if run["writer_id"] != self.writer_id:
                raise WorkspaceError("reading_writer_changed", "Another writer owns preparation")
            if run["bundle"] != self._bundle_version(source_id):
                raise WorkspaceError("reading_bundle_changed", "Parser Bundle changed")
            if run["request_id"] == request_id:
                raise WorkspaceError("reading_request_reused", "Resume requires a new request ID")
            run.setdefault("attempt_history", []).append({
                "attempt": run["attempt"], "status": run["status"],
                "repair_rounds": run["repair_rounds"], "error": run.get("error")})
            run.update(request_id=request_id, attempt=uuid.uuid4().hex, writer_id=self.writer_id,
                       status="running", error=None, repair_rounds=0, transport_retries=0)
            run.setdefault("requests", {})[request_id] = {"input": request_payload,
                "result": {"operation": "resume", "source_id": source_id,
                           "run_id": run["run_id"], "attempt": run["attempt"], "status": "started"}}
            self._write(source_id, run)
            return run

    def interrupt_running(self) -> None:
        with _LOCK:
            for path in (self.workspace / "sources").glob("*/reading/preparation.json"):
                run = _read_document(path)
                if run.get("status") == "running" and run.get("writer_id") == self.writer_id:
                    run.update(status="interrupted", error="Host restarted; resume explicitly")
                    _write_document(path, run)

    def cancel(self, source_id: str, *, request_id: str) -> dict:
        with _LOCK:
            if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,80}", request_id):
                raise WorkspaceError("reading_request_invalid", "Unique request ID required")
            run = self._read(source_id)
            if run is None:
                raise WorkspaceError("reading_run_missing", "No preparation task")
            if run["writer_id"] != self.writer_id:
                raise WorkspaceError("reading_writer_changed", "Another writer owns preparation")
            input_value = {"operation": "cancel", "source_id": source_id}
            old_request = run.get("requests", {}).get(request_id)
            if old_request:
                if self._request_input(old_request) != input_value:
                    raise WorkspaceError("reading_request_reused", "Request ID has different reading input")
                return run
            if run["status"] == "running":
                run.update(status="cancelled", error="Cancelled by reader")
            run.setdefault("requests", {})[request_id] = {"input": input_value,
                "result": {"operation": "cancel", "source_id": source_id, "run_id": run["run_id"],
                           "status": run["status"]}}
            self._write(source_id, run)
            return run

    def fail(self, source_id: str, run_id: str, attempt: str, bundle: str, message: str) -> None:
        with _LOCK:
            try:
                run = self._guard(source_id, run_id, attempt, bundle)
            except WorkspaceError as exc:
                if exc.error_id not in ("reading_bundle_changed", "reading_plan_changed", "reading_glossary_changed"):
                    return
                run = self._read(source_id)
                if not run or run["run_id"] != run_id or run["attempt"] != attempt or run["status"] != "running" or run["writer_id"] != self.writer_id:
                    return
                run.update(status="commit_conflict", error=f"{exc.error_id}: {str(exc)}")
                self._write(source_id, run)
                return
            run.update(status="failed", error=message[:500])
            self._write(source_id, run)

    def commit_context(self, source_id: str, run_id: str, attempt: str, bundle: str,
                       context: dict, coverage: list[list[int]]) -> dict:
        with _LOCK:
            run = self._guard_candidate(source_id, run_id, attempt, bundle, "context", {"context": context, "coverage": coverage})
            total = len((self._root(source_id) / "parser-bundle" / "content.md").read_text(encoding="utf-8").splitlines())
            if not isinstance(context, dict) or not context.get("structure") or not isinstance(context.get("terms"), list) \
                    or not isinstance(context.get("symbols"), list) or not isinstance(context.get("references"), list):
                raise WorkspaceError("reading_context_invalid", "Whole-source context is incomplete")
            if not coverage or coverage[0][0] != 1 or coverage[-1][1] != total \
                    or any(a[1] + 1 != b[0] for a, b in zip(coverage, coverage[1:])):
                raise WorkspaceError("reading_context_coverage", "Whole-source context did not cover the Bundle")
            run.update(context={**context, "coverage": coverage}, context_revision=_digest([context, coverage]),
                       step="plan")
            self._write(source_id, run)
            return run

    def commit_plan(self, source_id: str, run_id: str, attempt: str, bundle: str, draft: dict) -> dict:
        with _LOCK:
            run = self._guard_candidate(source_id, run_id, attempt, bundle, "plan", draft)
            if run["context"] is None or run["plan_id"] is not None:
                raise WorkspaceError("reading_plan_conflict", "A Plan already exists or context is absent")
            source_root = self._root(source_id)
            excluded = draft.get("excluded_ranges", []) if isinstance(draft, dict) else None
            if not isinstance(excluded, list) or any(not isinstance(item, list) or len(item) != 2
                or any(type(number) is not int for number in item) for item in excluded):
                raise WorkspaceError("reading_plan_invalid", "Excluded reference ranges are invalid")
            records, glossary = _reading_plan_records(source_root / "parser-bundle", draft,
                                                      excluded_ranges=excluded)
            lines = (source_root / "parser-bundle" / "content.md").read_text(encoding="utf-8").splitlines()
            heading_paths = _source_heading_paths(lines)
            claimed = set()
            for start, end in excluded:
                if start < 1 or end < start or end > len(lines):
                    raise WorkspaceError("reading_plan_invalid", "Excluded reference range is outside source")
                if any(not any(_reference_heading(heading)
                               for heading in heading_paths[number - 1]) for number in range(start, end + 1)):
                    raise WorkspaceError("reading_plan_invalid", "Only reference lists may be excluded")
                if any(re.search(r"!\[[^\]]*\]\(", lines[number - 1]) for number in range(start, end + 1)):
                    raise WorkspaceError("reading_plan_invalid", "Reference exclusions cannot hide figures or appendices")
                claimed.update(range(start, end + 1))
            reference_entries = {number for number, line in enumerate(lines, 1)
                if re.match(r"^\s*(?:\[\d+\]|\d+[.)]|[-+*])\s+\S", line)
                and any(_reference_heading(heading)
                        for heading in heading_paths[number - 1])}
            if not reference_entries.issubset(claimed):
                raise WorkspaceError("reading_plan_invalid", "Exclude bibliography entries from reading chunks; keep following appendices")
            for item in records:
                start, end = item["source_lines"]
                if claimed.intersection(range(start, end + 1)):
                    raise WorkspaceError("reading_plan_invalid", "Reading Chunks overlap exclusions")
                claimed.update(range(start, end + 1))
            if claimed != set(range(1, len(lines) + 1)):
                raise WorkspaceError("reading_plan_invalid", "Reading Plan omits source lines")
            plans = source_root / "reading" / "plans"
            numbers = [int(m.group(1)) for p in plans.glob("plan-*") if p.is_dir()
                       if (m := re.fullmatch(r"plan-(\d+)", p.name))]
            plan_id = f"plan-{max(numbers, default=0) + 1:03d}"
            root = plans / plan_id
            archive = source_root / "reading" / "bundles" / bundle
            if not archive.is_dir():
                shutil.copytree(source_root / "parser-bundle", archive)
            root.mkdir(parents=True)
            try:
                (root / "chunks.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in records),
                                                   encoding="utf-8")
                (root / "glossary.tsv").write_text("".join(f"{a}\t{b}\n" for a, b in glossary), encoding="utf-8")
                for c in records:
                    _write_document(root / "records" / f"{c['chunk_id']}.json",
                                    {"chunk_id": c["chunk_id"], "translation": None, "notes": []})
                _write_document(root / "provenance.json",
                                {"source_id": source_id, "bundle": bundle, "method": METHOD_VERSION,
                                 "context_revision": run["context_revision"], "runtime": run["runtime"],
                                 "excluded_ranges": excluded})
                run.update(plan_id=plan_id, plan_revision=_digest(_read_chunk_records(root / "chunks.jsonl")),
                           glossary_revision=_digest(_read_glossary(root / "glossary.tsv")), step="translate")
                self._write(source_id, run)
            except Exception:
                shutil.rmtree(root, ignore_errors=True)
                raise
            return run

    def commit_translation(self, source_id: str, run_id: str, attempt: str, bundle: str,
                           chunk_id: str, translation: str, *, repair: bool = False) -> dict:
        with _LOCK:
            run = self._guard_candidate(source_id, run_id, attempt, bundle, "translation",
                                        {"chunk_id": chunk_id, "translation": translation, "repair": repair})
            if not run["plan_id"] or not run["context_revision"]:
                raise WorkspaceError("reading_preparation_order", "Plan and context are required")
            chunk = self.core.preparation_chunk(source_id=source_id, plan_id=run["plan_id"], chunk_id=chunk_id)
            if chunk["status"] == "source_ready":
                raise WorkspaceError("translation_not_applicable", "Chinese content does not need translation")
            if not isinstance(translation, str) or not translation.strip():
                raise WorkspaceError("translation_invalid", "Translation is empty")
            if chunk["translation"] and not repair:
                return run
            if repair and (run["check"] is None or chunk_id not in run["check"].get("issues", {})):
                raise WorkspaceError("reading_repair_invalid", "Only an affected candidate may be repaired")
            record_path = self._root(source_id) / "reading" / "plans" / run["plan_id"] / "records" / f"{chunk_id}.json"
            record = _read_reading_record(record_path, chunk_id)
            record["translation"] = translation.strip()
            record["translation_meta"] = {
                "source_id": source_id, "bundle": bundle, "plan_id": run["plan_id"],
                "chunk_id": chunk_id, "source_lines": chunk["source_lines"],
                "source_hash": _digest(chunk["source_text"]),
                "context_revision": run["context_revision"],
                "glossary_revision": run["glossary_revision"],
                "method": run["method"], "runtime": run["runtime"],
                "revision": uuid.uuid4().hex,
            }
            _write_document(record_path, record)
            run.update(step="translate", check=None if not repair else run["check"])
            self._write(source_id, run)
            return run

    def commit_check(self, source_id: str, run_id: str, attempt: str, bundle: str, report: dict) -> dict:
        with _LOCK:
            run = self._guard_candidate(source_id, run_id, attempt, bundle, "check", report)
            if self._plan_status(source_id, run["plan_id"])["pending"]:
                raise WorkspaceError("reading_translation_missing", "Required translations are missing")
            if not isinstance(report, dict) or type(report.get("passed")) is not bool \
                    or not isinstance(report.get("issues"), dict):
                raise WorkspaceError("reading_check_invalid", "Consistency report is invalid")
            ids = {c["chunk_id"] for c in _read_chunk_records(
                self._root(source_id) / "reading" / "plans" / run["plan_id"] / "chunks.jsonl")}
            coverage = report.get("coverage")
            if not isinstance(coverage, list) or set(coverage) != ids or len(coverage) != len(ids):
                raise WorkspaceError("reading_check_invalid", "Consistency check did not cover every Chunk")
            if any(k not in ids or not isinstance(v, str) or not v for k, v in report["issues"].items()):
                raise WorkspaceError("reading_check_invalid", "Consistency issue locations are invalid")
            if report["passed"] and report["issues"]:
                raise WorkspaceError("reading_check_invalid", "Passing report contains issues")
            run["check"] = {**report, "content_revision": self._content_revision(source_id, run)}
            run["status"] = "ready" if report["passed"] else "running"
            run["step"] = "ready" if report["passed"] else "repair"
            if report["passed"]:
                provenance = self._root(source_id) / "reading" / "plans" / run["plan_id"] / "provenance.json"
                if not provenance.is_file():
                    _write_document(provenance, {"source_id": source_id, "bundle": bundle,
                        "method": run["method"], "context_revision": run["context_revision"],
                        "runtime": run["runtime"]})
                archive = self._root(source_id) / "reading" / "bundles" / bundle
                if not archive.is_dir():
                    shutil.copytree(self._root(source_id) / "parser-bundle", archive)
                run.setdefault("ready_plans", {})[run["plan_id"]] = {
                    "bundle": run["bundle"], "plan_id": run["plan_id"],
                    "plan_revision": run["plan_revision"],
                    "glossary_revision": run["glossary_revision"],
                    "context_revision": run["context_revision"],
                    "content_revision": run["check"]["content_revision"]}
            self._write(source_id, run)
            return run

    def mark_repair_round(self, source_id: str, run_id: str, attempt: str, bundle: str) -> int:
        with _LOCK:
            run = self._guard(source_id, run_id, attempt, bundle)
            run["repair_rounds"] += 1
            if run["repair_rounds"] > 2:
                run.update(status="failed", error="Consistency check still fails after two repair rounds")
            self._write(source_id, run)
            return run["repair_rounds"]

    def mark_transport_retry(self, source_id: str, run_id: str, attempt: str, bundle: str) -> int:
        with _LOCK:
            run = self._guard(source_id, run_id, attempt, bundle)
            run["transport_retries"] += 1
            self._write(source_id, run)
            return run["transport_retries"]


class ReadingExternalError(RuntimeError):
    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class ReadingApplication:
    """One bounded, resumable sequence for a single Source."""

    def __init__(self, workspace: Path, *, runtime: ReadingRuntime, writer_id: str):
        self.core = ReadingCore(workspace, writer_id=writer_id)
        self.runtime = runtime

    def status(self, source_id: str) -> dict | None:
        return self.core.status(source_id)

    def continue_reading(self, **kwargs) -> dict:
        return self.core.continue_reading(**kwargs)

    def finish_reading(self, **kwargs) -> dict:
        return self.core.finish_reading(**kwargs)

    def reread(self, **kwargs) -> dict:
        return self.core.reread(**kwargs)

    def review(self, **kwargs) -> dict:
        return self.core.review(**kwargs)

    def begin(self, source_id: str, *, request_id: str, rebuild: bool = False) -> dict:
        runtime = getattr(self.runtime, "provenance", {"adapter": type(self.runtime).__name__})
        return self.core.begin(source_id, request_id=request_id, rebuild=rebuild, runtime=runtime)

    def resume(self, source_id: str, *, request_id: str) -> dict:
        return self.core.resume(source_id, request_id=request_id)

    def cancel(self, source_id: str, *, request_id: str) -> dict:
        result = self.core.cancel(source_id, request_id=request_id)
        if result["status"] == "cancelled":
            self.runtime.cancel(source_id)
        return result

    def _call(self, run: dict, operation, **kwargs):
        while True:
            try:
                return operation(**kwargs)
            except ReadingExternalError as exc:
                if not exc.transient:
                    raise
                count = self.core.mark_transport_retry(run["source_id"], run["run_id"],
                                                       run["attempt"], run["bundle"])
                if count > 2:
                    raise

    def _ranges(self, source_id: str) -> list[dict]:
        bundle = self.core._root(source_id) / "parser-bundle"
        lines = (bundle / "content.md").read_text(encoding="utf-8").splitlines()
        if not lines:
            raise WorkspaceError("reading_source_empty", "Source has no readable content")
        paths = _source_heading_paths(lines)
        protected = _protected_source_ranges(lines)
        return [{"source_lines": [start + 1, min(start + 500, len(lines))],
                 "source_text": "\n".join(lines[start:start + 500]),
                 "heading_paths": [{"line": i + 1, "path": list(paths[i])}
                                   for i in range(start, min(start + 500, len(lines)))
                                   if i == start or paths[i] != paths[i - 1]],
                 "protected_ranges": [list(unit) for unit in protected
                                      if unit[0] <= start + 500 and unit[1] > start]}
                for start in range(0, len(lines), 500)]

    def process(self, source_id: str, *, run_id: str, attempt: str, on_progress=None) -> dict:
        """Run without a long write lock; every result is fenced at Core commit."""
        run = self.core.status(source_id)
        if not run or run["run_id"] != run_id or run["attempt"] != attempt or run["status"] != "running":
            raise WorkspaceError("reading_attempt_changed", "Preparation attempt is stale")
        bundle = run["bundle"]
        def notify():
            if on_progress is not None:
                on_progress()
        try:
            ranges = self._ranges(source_id)
            if run["context"] is None:
                context = None
                for part in ranges:
                    context = self._call(run, self.runtime.context, source_id=source_id,
                                         ranges=[part], previous=context)
                coverage = [part["source_lines"] for part in ranges]
                run = self.core.commit_context(source_id, run_id, attempt, bundle, context, coverage)
                notify()
            if run["plan_id"] is None:
                planning_context = run["context"]
                for planning_attempt in range(3):
                    draft = self._call(run, self.runtime.plan, source_id=source_id, ranges=ranges,
                                       context=planning_context)
                    try:
                        run = self.core.commit_plan(source_id, run_id, attempt, bundle, draft)
                        break
                    except WorkspaceError as exc:
                        if exc.error_id != "reading_plan_invalid" or planning_attempt == 2:
                            raise
                        self.core._guard(source_id, run_id, attempt, bundle)
                        planning_context = {**run["context"], "plan_feedback": {
                            "rejected_candidate": draft, "validation_error": str(exc)}}
                notify()
            if run["glossary_revision"] is None:
                # Existing Plan, prepared before this workflow: preserve valid
                # saved translations while establishing a current context/check.
                root = self.core._root(source_id) / "reading" / "plans" / run["plan_id"]
                with _LOCK:
                    current = self.core._guard(source_id, run_id, attempt, bundle)
                    current["glossary_revision"] = _digest(_read_glossary(root / "glossary.tsv"))
                    current["plan_revision"] = _digest(_read_chunk_records(root / "chunks.jsonl"))
                    current["step"] = "translate"
                    self.core._write(source_id, current)
                    run = current
                notify()
            root = self.core._root(source_id) / "reading" / "plans" / run["plan_id"]
            chunks = _read_chunk_records(root / "chunks.jsonl")
            glossary = _read_glossary(root / "glossary.tsv")
            pending = self.core._plan_status(source_id, run["plan_id"])["pending"]
            for chunk_id in pending:
                chunk = self.core.core.preparation_chunk(source_id=source_id, plan_id=run["plan_id"],
                                                         chunk_id=chunk_id)
                index = next(i for i, c in enumerate(chunks) if c["chunk_id"] == chunk_id)
                neighbors = [self.core.core.preparation_chunk(source_id=source_id, plan_id=run["plan_id"],
                             chunk_id=c["chunk_id"]) for c in chunks[max(0, index - 1):index + 2]
                             if c["chunk_id"] != chunk_id]
                translation = self._call(run, self.runtime.translate, source_id=source_id, chunk=chunk,
                                         context=run["context"], glossary=glossary, neighbors=neighbors, issue=None)
                run = self.core.commit_translation(source_id, run_id, attempt, bundle, chunk_id, translation)
                notify()
            if self.core._check_valid(source_id, run):
                return self.core.status(source_id)
            while True:
                with _LOCK:
                    run = self.core._guard(source_id, run_id, attempt, bundle)
                    run["step"] = "check"
                    self.core._write(source_id, run)
                notify()
                prepared = [self.core.core.preparation_chunk(source_id=source_id, plan_id=run["plan_id"],
                            chunk_id=c["chunk_id"]) for c in chunks]
                report = self._call(run, self.runtime.check, source_id=source_id, chunks=prepared,
                                    context=run["context"], glossary=glossary)
                run = self.core.commit_check(source_id, run_id, attempt, bundle, report)
                notify()
                if run["status"] == "ready":
                    return self.core.status(source_id)
                if run["repair_rounds"] >= 2:
                    self.core.fail(source_id, run_id, attempt, bundle,
                                   "Consistency check still fails after two repair rounds")
                    return self.core.status(source_id)
                self.core.mark_repair_round(source_id, run_id, attempt, bundle)
                for chunk_id, issue in report["issues"].items():
                    chunk = self.core.core.preparation_chunk(source_id=source_id, plan_id=run["plan_id"],
                                                             chunk_id=chunk_id)
                    if chunk["status"] == "source_ready":
                        raise WorkspaceError("reading_check_invalid", "Chinese source cannot be repaired by translation")
                    index = next(i for i, c in enumerate(chunks) if c["chunk_id"] == chunk_id)
                    neighbors = [prepared[i] for i in range(max(0, index - 1), min(len(prepared), index + 2))
                                 if i != index]
                    translation = self._call(run, self.runtime.translate, source_id=source_id, chunk=chunk,
                                             context=run["context"], glossary=glossary,
                                             neighbors=neighbors, issue=issue)
                    run = self.core.commit_translation(source_id, run_id, attempt, bundle,
                                                       chunk_id, translation, repair=True)
                    notify()
        except Exception as exc:
            self.core.fail(source_id, run_id, attempt, bundle, str(exc))
            raise
