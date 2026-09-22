from __future__ import annotations

import hashlib
import shutil
import threading
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


INGESTION_METHOD_VERSION = "focus-ingestion-v1"
CANDIDATE_RESULT_NAME = "ingestion-result.json"


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _component_config(component: object) -> dict[str, Any]:
    config: dict[str, Any] = {
        "adapter": f"{type(component).__module__}.{type(component).__qualname__}",
    }
    for name in ("model", "language", "ocr"):
        value = getattr(component, name, None)
        if isinstance(value, (str, bool, int, float)):
            config[name] = value
    return config


def persist_candidate_result(candidate: Path, result: dict[str, Any]) -> None:
    if not isinstance(result.get("title"), str) or not isinstance(result.get("short_name"), str):
        raise WorkspaceError("parser_result_invalid", "Parser result requires title and short name")
    _write_document(candidate / CANDIDATE_RESULT_NAME, result)


def _read_candidate_result(candidate: Path) -> dict[str, Any]:
    result = _read_document(candidate / CANDIDATE_RESULT_NAME)
    if not isinstance(result.get("title"), str) or not isinstance(result.get("short_name"), str):
        raise WorkspaceError("parser_result_invalid", "Persisted parser result is invalid")
    return result


class CandidateParser(Protocol):
    """Create a valid candidate and persist its exact result before returning."""

    def parse(self, source: Path, candidate: Path, *, checkpoint: Any | None = None) -> dict[str, Any]: ...


INGESTION_SERVICES = ["mineru"]


class CandidateRuntime(Protocol):
    """Independent Runtime capability.

    It inspects a bounded candidate excerpt and its own tests verify it on this
    boundary. Default single-document ingestion never declares or calls it, so a
    Runtime result can neither gate nor replace Core validation.
    """

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
        candidate_fingerprint = _file_fingerprint(candidate / "source.pdf")
        inbox_fingerprint = _file_fingerprint(item_path.parent / "source.pdf")
        confirmation = item.get("confirmation", {})
        if not (
            candidate_fingerprint
            == inbox_fingerprint
            == item.get("fingerprint")
            == confirmation.get("fingerprint")
            == confirmation.get("input_version")
        ):
            raise WorkspaceError("candidate_original_mismatch", "Candidate original does not match the Inbox source")
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
        item_path: Path,
    ) -> dict[str, Any]:
        item = _read_document(item_path)
        if item.get("status") == "cancelled":
            raise WorkspaceError("attempt_cancelled", "This ingestion is cancelled")
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
    """Persistent single-document Inbox and ingestion application boundary.

    Default ingestion publishes a validated Parser Bundle without any AI review:
    it declares and calls only the Parser it actually uses (`mineru`). Runtime
    capabilities are verified on their own boundary and are not part of this flow.
    """

    def __init__(
        self,
        workspace: Path,
        *,
        parser: CandidateParser,
        writer_id: str,
    ):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise WorkspaceError("workspace_missing", "Workspace does not exist")
        if not isinstance(writer_id, str) or not writer_id.strip():
            raise WorkspaceError("writer_invalid", "Writer identity is required")
        self.parser = parser
        self.writer_id = writer_id.strip()
        self._state_lock = threading.RLock()
        self.core = IngestionCore(self.workspace)
        self._recover_interrupted()

    def _service_config(self) -> dict[str, dict[str, Any]]:
        return {"mineru": _component_config(self.parser)}

    def _attempt_binding(self, service: str, confirmation: dict[str, Any]) -> dict[str, Any]:
        return {
            "service": service,
            "configuration": dict(confirmation["service_config"][service]),
            "method_version": confirmation["method_version"],
            "input_version": confirmation["input_version"],
        }

    def _attempt_matches(
        self,
        attempt: dict[str, Any],
        service: str,
        confirmation: dict[str, Any],
    ) -> bool:
        expected = self._attempt_binding(service, confirmation)
        return all(attempt.get(key) == value for key, value in expected.items())

    def _recover_interrupted(self) -> None:
        for path in (self.workspace / "inbox").glob("*/item.json"):
            item = _read_document(path)
            if item.get("status") != "processing":
                continue
            item["status"] = "interrupted"
            steps = item.get("run", {}).get("steps", {})
            for step in steps.values():
                if step.get("status") == "running":
                    step["status"] = "interrupted"
                for attempt in step.get("attempts", []):
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
        return _file_fingerprint(path)

    def _read(self, item_id: str) -> dict[str, Any]:
        with self._state_lock:
            value = _read_document(self._root(item_id) / "item.json")
        if value.get("item_id") != item_id:
            raise WorkspaceError("inbox_item_invalid", "Inbox item is invalid")
        return value

    def _write(self, item_id: str, item: dict[str, Any]) -> bool:
        with self._state_lock:
            path = self._root(item_id) / "item.json"
            current = _read_document(path) if path.is_file() else None
            if isinstance(current, dict) and current.get("status") == "cancelled" and item.get("status") != "cancelled":
                return False
            _write_document(path, item)
            return True

    @staticmethod
    def _public(item: dict[str, Any]) -> dict[str, Any]:
        return dict(item)

    def _unfinished_original(self, fingerprint: str) -> dict[str, Any] | None:
        """The persisted Inbox task for this exact original, while it is still unfinished.

        Identity is the content fingerprint, so a renamed file and an application
        restart both resolve to the same task. Nothing is added to the item here:
        finding a task never continues, resubmits or retargets it.
        """
        matches: list[tuple[float, str, dict[str, Any]]] = []
        for path in (self.workspace / "inbox").glob("*/item.json"):
            item = _read_document(path, {})
            if item.get("fingerprint") != fingerprint or item.get("status") == "completed":
                continue
            matches.append((path.stat().st_mtime, str(path), item))
        return max(matches, key=lambda match: match[:2])[2] if matches else None

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
        fingerprint = self._fingerprint(source)
        with self._state_lock:
            existing = self._unfinished_original(fingerprint)
            if existing is not None:
                # Same original, unfinished task: return it with its own target and
                # progress. The requested target is reported back as the original one.
                return {**self._public(existing), "duplicate": True}
            item_id = uuid.uuid4().hex
            root = self._root(item_id)
            root.mkdir(parents=True)
            stored = root / "source.pdf"
            shutil.copy2(source, stored)
            item = {
                "item_id": item_id,
                "file_name": source.name,
                "fingerprint": fingerprint,
                "topic_title": topic_title.strip() if topic_title else None,
                "topic_id": topic_id,
                "services": list(INGESTION_SERVICES),
                "status": "awaiting_confirmation",
                "confirmation": None,
                "run": None,
                "source_id": None,
                "document_status": "not_started",
                "topic_status": "not_started",
            }
            self._write(item_id, item)
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
        with self._state_lock:
            item = self._read(item_id)
            if item.get("status") not in {"awaiting_confirmation", "confirmed"}:
                raise WorkspaceError("ingestion_not_editable", "Only a staged Inbox item can be edited")
            root = self._root(item_id)
            if source is not None:
                source = Path(source).resolve()
                if not source.is_file() or source.suffix.lower() != ".pdf" or source.read_bytes()[:4] != b"%PDF":
                    raise WorkspaceError("source_pdf_invalid", "Source must be an existing PDF file")
                # Editing may not sidestep identity reuse: the replacement original
                # must not belong to a different unfinished Inbox task.
                replacement_fingerprint = self._fingerprint(source)
                existing = self._unfinished_original(replacement_fingerprint)
                if existing is not None and existing.get("item_id") != item_id:
                    raise WorkspaceError(
                        "ingestion_duplicate_original",
                        "Another unfinished Inbox task already uses this original",
                    )
                shutil.copy2(source, root / "source.pdf")
                item["file_name"] = source.name
                item["fingerprint"] = replacement_fingerprint
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
            self._write(item_id, item)
            return self._public(item)

    def confirm(
        self,
        item_id: str,
        *,
        services: list[str],
        purpose: str,
        scope: str,
    ) -> dict[str, Any]:
        with self._state_lock:
            item = self._read(item_id)
            confirmable = {
                "awaiting_confirmation",
                "confirmed",
                "interrupted",
                "retry_waiting",
                "failed",
                "commit_conflict",
                "topic_attachment_pending",
                "cancelled",
                "status_check_required",
            }
            if item.get("status") not in confirmable:
                raise WorkspaceError(
                    "ingestion_not_confirmable",
                    "Only a staged or resumable Inbox item can be confirmed",
                )
            expected_services = list(INGESTION_SERVICES)
            if (
                scope != "ingestion"
                or not purpose.strip()
                or not isinstance(services, list)
                or services != expected_services
            ):
                raise WorkspaceError(
                    "confirmation_scope_invalid",
                    "Confirmation services do not match this ingestion workflow",
                )
            if self._fingerprint(self._root(item_id) / "source.pdf") != item.get("fingerprint"):
                raise WorkspaceError("confirmation_required", "Inbox source changed and must be staged again")
            new_confirmation = {
                "fingerprint": item["fingerprint"],
                "input_version": item["fingerprint"],
                "topic_title": item["topic_title"],
                "topic_id": item["topic_id"],
                "services": list(services),
                "service_config": self._service_config(),
                "method_version": INGESTION_METHOD_VERSION,
                "purpose": purpose.strip(),
                "scope": scope,
                "expected_version": self.core.version,
            }
            previous = item.get("confirmation")
            binding_keys = {
                "fingerprint",
                "input_version",
                "topic_title",
                "topic_id",
                "services",
                "service_config",
                "method_version",
                "scope",
            }
            binding_changed = isinstance(previous, dict) and any(
                previous.get(key) != new_confirmation.get(key) for key in binding_keys
            )
            if item.get("status") == "status_check_required" and not binding_changed:
                raise WorkspaceError(
                    "remote_status_check_required",
                    "The accepted remote task must be reconciled before it can be reconfirmed",
                )
            if binding_changed and item.get("document_status") not in {"published", "reused"}:
                shutil.rmtree(self._root(item_id) / "candidate", ignore_errors=True)
                item["run"] = None
                item["document_status"] = "not_started"
                item["topic_status"] = "not_started"
                for key in ("candidate_result", "request_id", "error"):
                    item.pop(key, None)
            item["confirmation"] = new_confirmation
            item["status"] = "confirmed"
            self._write(item_id, item)
            return self._public(item)

    def process(self, item_id: str, *, request_id: str) -> dict[str, Any]:
        with self._state_lock:
            item = self._read(item_id)
            confirmation = item.get("confirmation")
            expected_services = list(INGESTION_SERVICES)
            root = self._root(item_id)
            source = root / "source.pdf"
            if (
                not isinstance(confirmation, dict)
                or confirmation.get("fingerprint") != item.get("fingerprint")
                or confirmation.get("input_version") != item.get("fingerprint")
                or confirmation.get("topic_title") != item.get("topic_title")
                or confirmation.get("topic_id") != item.get("topic_id")
                or confirmation.get("services") != expected_services
                or confirmation.get("service_config") != self._service_config()
                or confirmation.get("method_version") != INGESTION_METHOD_VERSION
                or confirmation.get("scope") != "ingestion"
                or not source.is_file()
                or self._fingerprint(source) != item.get("fingerprint")
            ):
                raise WorkspaceError("confirmation_required", "A current ingestion confirmation is required")
            if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
                raise WorkspaceError("request_id_invalid", "Request id is invalid")
            if item.get("request_id") == request_id and item.get("status") == "completed":
                return self._public(item)
            if item.get("status") not in {
                "confirmed",
                "interrupted",
                "retry_waiting",
                "failed",
                "commit_conflict",
                "topic_attachment_pending",
                "status_check_required",
            }:
                raise WorkspaceError("ingestion_not_processable", "Inbox item is not ready to process")
            run = item.get("run") or {
                "run_id": uuid.uuid4().hex,
                "steps": {
                    "parse": {"status": "pending", "attempts": []},
                    "publish": {"status": "pending", "attempts": []},
                    "attach": {"status": "pending", "attempts": []},
                },
            }
            item["run"] = run
            item["request_id"] = request_id
            item["status"] = "processing"
            self._write(item_id, item)

        existing = SourceLibrary(self.workspace).find("paper-original:" + item["fingerprint"])
        if existing is None:
            candidate = root / "candidate"
            parse_step = run["steps"]["parse"]
            parsed = item.get("candidate_result")
            reusable_candidate = False
            may_recover_candidate = any(
                entry.get("status") in {"completed", "interrupted"}
                and self._attempt_matches(entry, "mineru", confirmation)
                for entry in parse_step.get("attempts", [])
            )
            if candidate.is_dir() and may_recover_candidate:
                try:
                    _validate_parser_bundle(candidate)
                    if _file_fingerprint(candidate / "source.pdf") != _file_fingerprint(source):
                        raise WorkspaceError(
                            "candidate_original_mismatch",
                            "Candidate original does not match the Inbox source",
                        )
                    if not isinstance(parsed, dict):
                        parsed = _read_candidate_result(candidate)
                    try:
                        attempt = next(
                            entry for entry in reversed(parse_step["attempts"])
                            if entry.get("status") == "completed" and entry.get("commit_allowed") is True
                            and self._attempt_matches(entry, "mineru", confirmation)
                        )
                    except StopIteration:
                        attempt = {
                            "attempt_id": uuid.uuid4().hex,
                            "status": "completed",
                            "commit_allowed": True,
                            "recovered_candidate": True,
                            **self._attempt_binding("mineru", confirmation),
                        }
                        parse_step["attempts"].append(attempt)
                    parse_step["status"] = "completed"
                    item["candidate_result"] = dict(parsed)
                    item.pop("error", None)
                    self._write(item_id, item)
                    reusable_candidate = True
                except WorkspaceError:
                    pass
            for automatic_index in range(0 if reusable_candidate else 3):
                if candidate.exists():
                    shutil.rmtree(candidate)
                attempt = {
                    "attempt_id": uuid.uuid4().hex,
                    "status": "running",
                    "commit_allowed": True,
                    **self._attempt_binding("mineru", confirmation),
                }
                parse_step["attempts"].append(attempt)
                parse_step["status"] = "running"
                item["status"] = "processing"
                if not self._write(item_id, item):
                    return self._public(self._read(item_id))

                def save_checkpoint(value):
                    if not isinstance(value, dict) or not value.get("reference_id"):
                        raise WorkspaceError("parser_checkpoint_invalid", "Parser checkpoint is invalid")
                    parse_step["checkpoint"] = dict(value)
                    current = self._read(item_id)
                    current_step = current["run"]["steps"]["parse"]
                    current_attempt = next(
                        entry for entry in current_step["attempts"]
                        if entry["attempt_id"] == attempt["attempt_id"]
                    )
                    if current_attempt.get("commit_allowed") is not True:
                        if hasattr(self.parser, "cancel"):
                            try:
                                self.parser.cancel(value)
                            except Exception:
                                pass
                        return
                    current_step["checkpoint"] = dict(value)
                    self._write(item_id, current)

                try:
                    checkpoint = parse_step.get("checkpoint")
                    if checkpoint is not None and hasattr(self.parser, "resume"):
                        parsed = self.parser.resume(source, candidate, checkpoint=checkpoint)
                    else:
                        parsed = self.parser.parse(source, candidate, checkpoint=save_checkpoint)
                    if not isinstance(parsed, dict):
                        raise WorkspaceError("parser_result_invalid", "Parser result is invalid")
                    _validate_parser_bundle(candidate)
                    if _read_candidate_result(candidate) != parsed:
                        raise WorkspaceError(
                            "parser_result_invalid",
                            "Parser result does not match its persisted candidate result",
                        )
                    item = self._read(item_id)
                    run = item["run"]
                    parse_step = run["steps"]["parse"]
                    attempt = next(
                        entry for entry in parse_step["attempts"]
                        if entry["attempt_id"] == attempt["attempt_id"]
                    )
                    if attempt.get("commit_allowed") is not True:
                        item["document_status"] = "candidate_retained"
                        run["steps"]["publish"]["status"] = "rejected"
                        self._write(item_id, item)
                        return self._public(item)
                    attempt["status"] = "completed"
                    item["candidate_result"] = dict(parsed)
                    item.pop("error", None)
                    break
                except Exception as exc:
                    current = self._read(item_id)
                    current_run = current["run"]
                    current_step = current_run["steps"]["parse"]
                    current_attempt = next(
                        entry for entry in current_step["attempts"]
                        if entry["attempt_id"] == attempt["attempt_id"]
                    )
                    if current_attempt.get("commit_allowed") is not True:
                        current["document_status"] = "candidate_retained" if candidate.exists() else "not_started"
                        current_run["steps"]["publish"]["status"] = "rejected"
                        self._write(item_id, current)
                        return self._public(current)
                    item, run, parse_step, attempt = current, current_run, current_step, current_attempt
                    attempt["status"] = "failed"
                    attempt["error_id"] = getattr(exc, "error_id", "parser_failed")
                    item["error"] = {"error_id": attempt["error_id"], "message": str(exc)}
                    if getattr(exc, "acceptance_unknown", False):
                        parse_step["status"] = "status_check_required"
                        item["status"] = "status_check_required"
                        self._write(item_id, item)
                        return self._public(item)
                    if getattr(exc, "transient", False):
                        if automatic_index < 2:
                            continue
                        parse_step["status"] = "retry_waiting"
                        item["status"] = "retry_waiting"
                        self._write(item_id, item)
                        return self._public(item)
                    parse_step["status"] = "failed"
                    item["status"] = "failed"
                    item["document_status"] = "candidate_rejected"
                    self._write(item_id, item)
                    return self._public(item)
            assert parsed is not None
            run["steps"]["parse"]["status"] = "completed"
            self._write(item_id, item)
            # Default ingestion publishes straight from the validated Parser Bundle:
            # no Runtime inspection runs, and no candidate may replace Core validation.
            try:
                with self._state_lock:
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
                    if exc.error_id == "writer_conflict":
                        raise
                    item = self._read(item_id)
                    item["status"] = "failed"
                    item["document_status"] = "candidate_rejected"
                    item["error"] = {"error_id": exc.error_id, "message": str(exc)}
                    item["run"]["steps"]["publish"]["status"] = "failed"
                    if exc.error_id == "candidate_original_mismatch":
                        item["run"]["steps"]["parse"]["status"] = "failed"
                        item.pop("candidate_result", None)
                        shutil.rmtree(candidate, ignore_errors=True)
                    self._write(item_id, item)
                    return self._public(item)
                cancelled = self._read(item_id)
                cancelled["document_status"] = "candidate_retained"
                cancelled["run"]["steps"]["publish"]["status"] = "rejected"
                self._write(item_id, cancelled)
                return self._public(cancelled)
            if published["status"] == "version_conflict":
                item["status"] = "commit_conflict"
                item["document_status"] = "candidate_retained"
                run["steps"]["publish"]["status"] = "conflict"
                self._write(item_id, item)
                return self._public(item)
            source_id = published["source_id"]
            item["document_status"] = "published"
            run["steps"]["publish"]["status"] = "completed"
            version = int(published["version"])
        else:
            with self._state_lock:
                item = self._read(item_id)
                if item.get("status") == "cancelled":
                    return self._public(item)
                run = item["run"]
                source_id = existing["source_id"]
                item["document_status"] = "reused"
                run["steps"]["parse"]["status"] = "skipped"
                run["steps"]["publish"]["status"] = "skipped"
                version = self.core.version
        item["source_id"] = source_id
        self._write(item_id, item)

        with self._state_lock:
            item = self._read(item_id)
            if item.get("status") == "cancelled":
                return self._public(item)
            run = item["run"]
            if item.get("topic_title") is not None or item.get("topic_id") is not None:
                try:
                    attached = self.core.attach(
                        source_id,
                        topic_title=item.get("topic_title"),
                        topic_id=item.get("topic_id"),
                        expected_version=version,
                        request_id=request_id + ":attach",
                        writer_id=self.writer_id,
                        item_path=root / "item.json",
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
                    self._write(item_id, item)
                    return self._public(item)
            else:
                item["topic_status"] = "not_requested"
                run["steps"]["attach"]["status"] = "skipped"
            item["status"] = "completed"
            self._write(item_id, item)
            return self._public(item)

    def continue_run(self, item_id: str, *, request_id: str) -> dict[str, Any]:
        item = self._read(item_id)
        if item.get("status") not in {
            "status_check_required",
            "retry_waiting",
            "failed",
            "commit_conflict",
            "topic_attachment_pending",
            "cancelled",
            "interrupted",
        }:
            raise WorkspaceError("ingestion_not_resumable", "Ingestion is not waiting for continuation")
        if item.get("status") == "status_check_required" and not item.get("run", {}).get("steps", {}).get("parse", {}).get("checkpoint"):
            raise WorkspaceError("remote_reference_missing", "Remote acceptance cannot be reconciled without a task reference")
        if item.get("status") == "cancelled":
            item["status"] = "confirmed"
            with self._state_lock:
                _write_document(self._root(item_id) / "item.json", item)
        if item.get("status") == "commit_conflict":
            item["confirmation"]["expected_version"] = self.core.version
            self._write(item_id, item)
        return self.process(item_id, request_id=request_id)

    def cancel(self, item_id: str) -> dict[str, Any]:
        with self._state_lock:
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
            self._write(item_id, item)
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
                self._write(item_id, item)
            return self._public(item)
