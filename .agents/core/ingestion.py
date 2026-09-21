from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Any, Protocol

from .reading_workspace import (
    WorkspaceError,
    _read_document,
    _validate_parser_bundle,
    _write_document,
    validate_topic_id,
)
from .source_library import SourceLibrary


class CandidateParser(Protocol):
    def parse(self, source: Path, candidate: Path, *, checkpoint: Any | None = None) -> dict[str, Any]: ...


class CandidateRuntime(Protocol):
    def inspect(self, candidate: Path) -> dict[str, Any]: ...


class IngestionExternalError(RuntimeError):
    def __init__(
        self,
        error_id: str,
        message: str,
        *,
        transient: bool = False,
        acceptance_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_id = error_id
        self.transient = transient
        self.acceptance_unknown = acceptance_unknown


class IngestionCore:
    """Guarded Core commits for ingestion candidates and Topic membership."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.path = workspace / "ingestion" / "core.json"

    def _state(self) -> dict[str, Any]:
        return _read_document(self.path, {"version": 0, "writer_id": None, "requests": {}})

    @property
    def version(self) -> int:
        return int(self._state()["version"])

    def _authorize(self, state: dict[str, Any], writer_id: str) -> None:
        owner = state.get("writer_id")
        if owner not in {None, writer_id}:
            raise WorkspaceError("writer_conflict", "Another writer owns this Workspace")
        state["writer_id"] = writer_id

    def publish(
        self,
        candidate: Path,
        *,
        expected_version: int,
        request_id: str,
        writer_id: str,
        title: str,
        short_name: str,
        identity: str,
        item_path: Path,
        attempt_id: str,
    ) -> dict[str, Any]:
        _validate_parser_bundle(candidate)
        item = _read_document(item_path)
        attempts = item.get("run", {}).get("steps", {}).get("parse", {}).get("attempts", [])
        selected = next((entry for entry in attempts if entry.get("attempt_id") == attempt_id), None)
        if not isinstance(selected, dict) or selected.get("commit_allowed") is not True:
            raise WorkspaceError("attempt_cancelled", "This parser attempt is not allowed to commit")
        state = self._state()
        self._authorize(state, writer_id)
        requests = state.setdefault("requests", {})
        if request_id in requests:
            return dict(requests[request_id])
        if state["version"] != expected_version:
            return {"status": "version_conflict", "version": state["version"]}
        result = SourceLibrary(self.workspace).register(
            candidate,
            source_kind="paper_pdf",
            title=title,
            short_name=short_name,
            identity=identity,
        )
        state["version"] += 1
        committed = {"status": "published", "source_id": result["source_id"], "version": state["version"]}
        requests[request_id] = committed
        _write_document(self.path, state)
        return committed

    def attach(
        self,
        source_id: str,
        *,
        topic_title: str | None,
        topic_id: str | None,
        expected_version: int,
        request_id: str,
        writer_id: str,
    ) -> dict[str, Any]:
        state = self._state()
        self._authorize(state, writer_id)
        requests = state.setdefault("requests", {})
        if request_id in requests:
            return dict(requests[request_id])
        if state["version"] != expected_version:
            return {"status": "version_conflict", "version": state["version"]}
        resolved = SourceLibrary(self.workspace).attach(
            source_id, topic_title=topic_title, topic_id=topic_id
        )
        state["version"] += 1
        committed = {"status": "attached", "topic_id": resolved, "version": state["version"]}
        requests[request_id] = committed
        _write_document(self.path, state)
        return committed


class IngestionApplication:
    """Persistent single-document Inbox and ingestion application boundary."""

    def __init__(
        self,
        workspace: Path,
        *,
        parser: CandidateParser,
        writer_id: str,
        runtime: CandidateRuntime | None = None,
    ):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise WorkspaceError("workspace_missing", "Workspace does not exist")
        if not isinstance(writer_id, str) or not writer_id.strip():
            raise WorkspaceError("writer_invalid", "Writer identity is required")
        self.parser = parser
        self.runtime = runtime
        self.writer_id = writer_id.strip()
        self.core = IngestionCore(self.workspace)
        self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        for path in (self.workspace / "inbox").glob("*/item.json"):
            item = _read_document(path)
            if item.get("status") != "processing":
                continue
            item["status"] = "interrupted"
            attempts = item.get("run", {}).get("steps", {}).get("parse", {}).get("attempts", [])
            for attempt in attempts:
                if attempt.get("status") == "running":
                    attempt["status"] = "interrupted"
                    attempt["commit_allowed"] = False
            _write_document(path, item)

    def _root(self, item_id: str) -> Path:
        if not isinstance(item_id, str) or not item_id or any(c not in "0123456789abcdef" for c in item_id):
            raise WorkspaceError("inbox_item_invalid", "Inbox item id is invalid")
        return self.workspace / "inbox" / item_id

    @staticmethod
    def _fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
        return digest.hexdigest()

    def _read(self, item_id: str) -> dict[str, Any]:
        value = _read_document(self._root(item_id) / "item.json")
        if value.get("item_id") != item_id:
            raise WorkspaceError("inbox_item_invalid", "Inbox item is invalid")
        return value

    @staticmethod
    def _public(item: dict[str, Any]) -> dict[str, Any]:
        return dict(item)

    def stage_pdf(
        self,
        source: Path,
        *,
        topic_title: str | None = None,
        topic_id: str | None = None,
    ) -> dict[str, Any]:
        source = Path(source).resolve()
        if not source.is_file() or source.suffix.lower() != ".pdf" or source.read_bytes()[:4] != b"%PDF":
            raise WorkspaceError("source_pdf_invalid", "Source must be an existing PDF file")
        if topic_title is not None and (not isinstance(topic_title, str) or not topic_title.strip()):
            raise WorkspaceError("topic_invalid", "Topic title is empty or invalid")
        if topic_id is not None:
            validate_topic_id(topic_id)
        item_id = uuid.uuid4().hex
        root = self._root(item_id)
        root.mkdir(parents=True)
        stored = root / "source.pdf"
        shutil.copy2(source, stored)
        item = {
            "item_id": item_id,
            "file_name": source.name,
            "fingerprint": self._fingerprint(stored),
            "topic_title": topic_title.strip() if topic_title else None,
            "topic_id": topic_id,
            "status": "awaiting_confirmation",
            "confirmation": None,
            "run": None,
            "source_id": None,
            "document_status": "not_started",
            "topic_status": "not_started",
        }
        _write_document(root / "item.json", item)
        return self._public(item)

    def get(self, item_id: str) -> dict[str, Any]:
        return self._public(self._read(item_id))

    def list_inbox(self) -> list[dict[str, Any]]:
        return [
            self._public(_read_document(path))
            for path in sorted((self.workspace / "inbox").glob("*/item.json"))
        ]

    def update_staged(
        self,
        item_id: str,
        *,
        source: Path | None = None,
        topic_title: str | None = None,
        topic_id: str | None = None,
    ) -> dict[str, Any]:
        item = self._read(item_id)
        root = self._root(item_id)
        if source is not None:
            source = Path(source).resolve()
            if not source.is_file() or source.suffix.lower() != ".pdf" or source.read_bytes()[:4] != b"%PDF":
                raise WorkspaceError("source_pdf_invalid", "Source must be an existing PDF file")
            shutil.copy2(source, root / "source.pdf")
            item["file_name"] = source.name
            item["fingerprint"] = self._fingerprint(root / "source.pdf")
        if topic_title is not None:
            if not topic_title.strip():
                raise WorkspaceError("topic_invalid", "Topic title is empty or invalid")
            item["topic_title"] = topic_title.strip()
            item["topic_id"] = None
        if topic_id is not None:
            item["topic_id"] = validate_topic_id(topic_id)
            item["topic_title"] = None
        item["confirmation"] = None
        item["status"] = "awaiting_confirmation"
        _write_document(root / "item.json", item)
        return self._public(item)

    def confirm(
        self,
        item_id: str,
        *,
        services: list[str],
        purpose: str,
        scope: str,
    ) -> dict[str, Any]:
        item = self._read(item_id)
        expected_services = ["mineru"] + (["codex"] if self.runtime is not None else [])
        if scope != "ingestion" or not purpose.strip() or services != expected_services:
            raise WorkspaceError(
                "confirmation_scope_invalid",
                "Confirmation services do not match this ingestion workflow",
            )
        item["confirmation"] = {
            "fingerprint": item["fingerprint"],
            "topic_title": item["topic_title"],
            "topic_id": item["topic_id"],
            "services": list(services),
            "purpose": purpose.strip(),
            "scope": scope,
            "expected_version": self.core.version,
        }
        item["status"] = "confirmed"
        _write_document(self._root(item_id) / "item.json", item)
        return self._public(item)

    def process(self, item_id: str, *, request_id: str) -> dict[str, Any]:
        item = self._read(item_id)
        confirmation = item.get("confirmation")
        if not isinstance(confirmation, dict) or confirmation.get("fingerprint") != item.get("fingerprint"):
            raise WorkspaceError("confirmation_required", "A current ingestion confirmation is required")
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise WorkspaceError("request_id_invalid", "Request id is invalid")
        if item.get("request_id") == request_id and item.get("status") == "completed":
            return self._public(item)
        root = self._root(item_id)
        source = root / "source.pdf"
        run = item.get("run") or {
            "run_id": uuid.uuid4().hex,
            "steps": {
                "parse": {"status": "pending", "attempts": []},
                "runtime": {"status": "pending", "attempts": []},
                "publish": {"status": "pending", "attempts": []},
                "attach": {"status": "pending", "attempts": []},
            },
        }
        item["run"] = run
        item["request_id"] = request_id
        item["status"] = "processing"
        _write_document(root / "item.json", item)

        existing = SourceLibrary(self.workspace).find_original(source, source_kind="paper_pdf")
        if existing is None:
            candidate = root / "candidate"
            parse_step = run["steps"]["parse"]
            parsed = None
            for automatic_index in range(3):
                if candidate.exists():
                    shutil.rmtree(candidate)
                attempt = {
                    "attempt_id": uuid.uuid4().hex,
                    "status": "running",
                    "commit_allowed": True,
                }
                parse_step["attempts"].append(attempt)
                parse_step["status"] = "running"
                item["status"] = "processing"
                _write_document(root / "item.json", item)

                def save_checkpoint(value):
                    if not isinstance(value, dict) or not value.get("reference_id"):
                        raise WorkspaceError("parser_checkpoint_invalid", "Parser checkpoint is invalid")
                    parse_step["checkpoint"] = dict(value)
                    _write_document(root / "item.json", item)

                try:
                    checkpoint = parse_step.get("checkpoint")
                    if checkpoint is not None and hasattr(self.parser, "resume"):
                        parsed = self.parser.resume(source, candidate, checkpoint=checkpoint)
                    else:
                        parsed = self.parser.parse(source, candidate, checkpoint=save_checkpoint)
                    if not isinstance(parsed, dict):
                        raise WorkspaceError("parser_result_invalid", "Parser result is invalid")
                    _validate_parser_bundle(candidate)
                    attempt["status"] = "completed"
                    item.pop("error", None)
                    break
                except Exception as exc:
                    attempt["status"] = "failed"
                    attempt["error_id"] = getattr(exc, "error_id", "parser_failed")
                    item["error"] = {"error_id": attempt["error_id"], "message": str(exc)}
                    if getattr(exc, "acceptance_unknown", False):
                        parse_step["status"] = "status_check_required"
                        item["status"] = "status_check_required"
                        _write_document(root / "item.json", item)
                        return self._public(item)
                    if getattr(exc, "transient", False):
                        if automatic_index < 2:
                            continue
                        parse_step["status"] = "retry_waiting"
                        item["status"] = "retry_waiting"
                        _write_document(root / "item.json", item)
                        return self._public(item)
                    parse_step["status"] = "failed"
                    item["status"] = "failed"
                    item["document_status"] = "candidate_rejected"
                    _write_document(root / "item.json", item)
                    return self._public(item)
            assert parsed is not None
            run["steps"]["parse"]["status"] = "completed"
            if self.runtime is not None:
                runtime_attempt = {"attempt_id": uuid.uuid4().hex, "status": "running"}
                run["steps"]["runtime"]["attempts"].append(runtime_attempt)
                run["steps"]["runtime"]["status"] = "running"
                _write_document(root / "item.json", item)
                try:
                    runtime_result = self.runtime.inspect(candidate)
                    if (
                        not isinstance(runtime_result, dict)
                        or runtime_result.get("title_matches") is not True
                        or runtime_result.get("image_observed") is not True
                    ):
                        raise WorkspaceError("runtime_result_invalid", "Runtime inspection did not validate the candidate")
                except Exception as exc:
                    runtime_attempt["status"] = "failed"
                    run["steps"]["runtime"]["status"] = "failed"
                    item["status"] = "failed"
                    item["document_status"] = "candidate_retained"
                    item["error"] = {
                        "error_id": getattr(exc, "error_id", "runtime_failed"),
                        "message": str(exc),
                    }
                    _write_document(root / "item.json", item)
                    return self._public(item)
                runtime_attempt["status"] = "completed"
                run["steps"]["runtime"]["status"] = "completed"
                item["runtime_result"] = runtime_result
            else:
                run["steps"]["runtime"]["status"] = "skipped"
            try:
                published = self.core.publish(
                    candidate,
                    expected_version=int(confirmation["expected_version"]),
                    request_id=request_id + ":publish",
                    writer_id=self.writer_id,
                    title=str(parsed.get("title") or ""),
                    short_name=str(parsed.get("short_name") or ""),
                    identity="paper-original:" + item["fingerprint"],
                    item_path=root / "item.json",
                    attempt_id=attempt["attempt_id"],
                )
            except WorkspaceError as exc:
                if exc.error_id != "attempt_cancelled":
                    raise
                cancelled = self._read(item_id)
                cancelled["document_status"] = "candidate_retained"
                cancelled["run"]["steps"]["publish"]["status"] = "rejected"
                _write_document(root / "item.json", cancelled)
                return self._public(cancelled)
            if published["status"] == "version_conflict":
                item["status"] = "commit_conflict"
                item["document_status"] = "candidate_retained"
                run["steps"]["publish"]["status"] = "conflict"
                _write_document(root / "item.json", item)
                return self._public(item)
            source_id = published["source_id"]
            item["document_status"] = "published"
            run["steps"]["publish"]["status"] = "completed"
            version = int(published["version"])
        else:
            source_id = existing["source_id"]
            item["document_status"] = "reused"
            run["steps"]["parse"]["status"] = "skipped"
            run["steps"]["runtime"]["status"] = "skipped"
            run["steps"]["publish"]["status"] = "skipped"
            version = self.core.version
        item["source_id"] = source_id
        _write_document(root / "item.json", item)

        if item.get("topic_title") is not None or item.get("topic_id") is not None:
            try:
                attached = self.core.attach(
                    source_id,
                    topic_title=item.get("topic_title"),
                    topic_id=item.get("topic_id"),
                    expected_version=version,
                    request_id=request_id + ":attach",
                    writer_id=self.writer_id,
                )
                if attached["status"] == "version_conflict":
                    raise WorkspaceError("version_conflict", "Topic attachment version changed")
                item["topic_status"] = "attached"
                item["resolved_topic_id"] = attached["topic_id"]
                run["steps"]["attach"]["status"] = "completed"
            except WorkspaceError as exc:
                item["topic_status"] = "pending_recovery"
                item["topic_error"] = {"error_id": exc.error_id, "message": str(exc)}
                item["status"] = "topic_attachment_pending"
                run["steps"]["attach"]["status"] = "failed"
                _write_document(root / "item.json", item)
                return self._public(item)
        else:
            item["topic_status"] = "not_requested"
            run["steps"]["attach"]["status"] = "skipped"
        item["status"] = "completed"
        _write_document(root / "item.json", item)
        return self._public(item)

    def continue_run(self, item_id: str, *, request_id: str) -> dict[str, Any]:
        item = self._read(item_id)
        if item.get("status") not in {
            "retry_waiting",
            "failed",
            "commit_conflict",
            "topic_attachment_pending",
            "cancelled",
            "interrupted",
        }:
            raise WorkspaceError("ingestion_not_resumable", "Ingestion is not waiting for continuation")
        return self.process(item_id, request_id=request_id)

    def cancel(self, item_id: str) -> dict[str, Any]:
        item = self._read(item_id)
        run = item.get("run")
        if not isinstance(run, dict):
            raise WorkspaceError("ingestion_not_cancellable", "Ingestion has not started")
        parse_step = run.get("steps", {}).get("parse", {})
        attempts = parse_step.get("attempts", [])
        active = next((entry for entry in reversed(attempts) if entry.get("commit_allowed") is True), None)
        if active is not None:
            active["commit_allowed"] = False
            active["status"] = "cancelled"
        item["status"] = "cancelled"
        item["remote_status"] = "not_started"
        checkpoint = parse_step.get("checkpoint")
        if checkpoint is not None:
            item["remote_status"] = "stop_requested"
        _write_document(self._root(item_id) / "item.json", item)
        if checkpoint is not None and hasattr(self.parser, "cancel"):
            try:
                stopped = self.parser.cancel(checkpoint)
                item["remote_status"] = "stop_requested" if stopped else "still_running"
            except Exception as exc:
                item["remote_status"] = "stop_unknown"
                item["cancel_error"] = {
                    "error_id": getattr(exc, "error_id", "cancel_failed"),
                    "message": str(exc),
                }
            _write_document(self._root(item_id) / "item.json", item)
        runtime_step = run.get("steps", {}).get("runtime", {})
        if runtime_step.get("status") == "running" and self.runtime is not None and hasattr(self.runtime, "cancel"):
            item["runtime_status"] = "stop_requested" if self.runtime.cancel() else "stop_unknown"
            _write_document(self._root(item_id) / "item.json", item)
        return self._public(item)
