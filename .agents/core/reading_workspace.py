"""Single write seam for deterministic Reading Workspace registration state."""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
import urllib.parse
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any


MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\(([^)]+)\)")
SEQUENTIAL_IMAGE_RE = re.compile(r"^image-(\d{3})(\.[a-z0-9]+)$")


class WorkspaceError(RuntimeError):
    def __init__(self, error_id: str, message: str):
        super().__init__(message)
        self.error_id = error_id


@dataclass(frozen=True)
class ParserTask:
    batch_id: str
    paper_id: str
    title: str
    topic_id: str
    topic_title: str
    model: str
    language: str


def _read_document(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.is_file():
        if default is not None:
            return default
        raise WorkspaceError("workspace_object_missing", f"Required Workspace object is missing: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError("workspace_object_invalid", f"Workspace object is invalid: {path.name}") from exc
    if not isinstance(value, dict):
        raise WorkspaceError("workspace_object_invalid", f"Workspace object is invalid: {path.name}")
    return value


def _write_document(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _restore(path: Path, snapshot: bytes | None) -> None:
    if snapshot is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.restore")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(snapshot)
    temporary.replace(path)


def _prepare_membership(
    topic: dict[str, Any],
    pointers: dict[str, Any],
    *,
    paper_id: str,
    topic_id: str,
    initialize_pointer: bool,
) -> None:
    topic_papers = topic.get("papers")
    if not isinstance(topic_papers, list):
        raise WorkspaceError("topic_invalid", f"Topic is invalid: {topic_id}")
    if paper_id not in topic_papers:
        topic_papers.append(paper_id)
    pointer_entries = pointers.get("papers")
    if not isinstance(pointer_entries, dict):
        raise WorkspaceError("workspace_pointers_invalid", "Workspace pointers are invalid")
    empty_pointer = {
        "current_plan_id": None,
        "current_chunk_id": None,
        "current_explanation_id": None,
    }
    if initialize_pointer:
        pointer_entries[paper_id] = empty_pointer
    else:
        pointer_entries.setdefault(paper_id, empty_pointer)
    pointers["current_paper_id"] = paper_id


def _commit_documents(
    documents: dict[Path, dict[str, Any]],
    *,
    staged_bundle: tuple[Path, Path] | None = None,
) -> None:
    snapshots = {path: path.read_bytes() if path.is_file() else None for path in documents}
    installed = False
    try:
        if staged_bundle:
            staging, bundle = staged_bundle
            staging.replace(bundle)
            installed = True
        for path, value in documents.items():
            _write_document(path, value)
    except Exception:
        for path, snapshot in snapshots.items():
            _restore(path, snapshot)
        if installed and staged_bundle:
            staging, bundle = staged_bundle
            if bundle.exists():
                bundle.replace(staging)
        raise


def _slug(value: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    pieces: list[str] = []
    separating = False
    for character in normalized:
        if character.isalnum():
            pieces.append(character)
            separating = False
        elif pieces and not separating:
            pieces.append("-")
            separating = True
    result = "".join(pieces).strip("-")
    return result or fallback


def _identifier(value: str, kind: str) -> str:
    if not value or value != value.strip("-"):
        raise WorkspaceError(f"{kind}_invalid", f"{kind.replace('_', ' ').title()} is invalid")
    if any(not (character.isalnum() or character == "-") for character in value):
        raise WorkspaceError(f"{kind}_invalid", f"{kind.replace('_', ' ').title()} is invalid")
    return value


def _batch_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", value):
        raise WorkspaceError("parser_task_invalid", "MinerU batch reference is invalid")
    return value


def _split_image_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<"):
        closing = target.find(">")
        return target[1:closing] if closing >= 0 else target
    return target.split(maxsplit=1)[0] if target else target


def _validate_parser_bundle(bundle: Path) -> None:
    errors: list[str] = []
    source = bundle / "source.pdf"
    paper = bundle / "paper.md"
    images = bundle / "images"
    if not source.is_file():
        errors.append("source.pdf is missing")
    if not paper.is_file() or not paper.read_text(encoding="utf-8", errors="replace").strip():
        errors.append("paper.md is missing or empty")
    if not images.is_dir():
        errors.append("images directory is missing")
    metadata = _read_document(bundle / "metadata.json", {})
    if metadata.get("parser") != "mineru-precision-api":
        errors.append("metadata parser provenance is invalid")
    validation = _read_document(bundle / "validation.json", {})
    if validation.get("ok") is not True:
        errors.append("structural validation did not pass")
    if paper.is_file() and images.is_dir():
        linked: list[Path] = []
        for match in MARKDOWN_IMAGE_RE.finditer(paper.read_text(encoding="utf-8", errors="replace")):
            target = _split_image_target(match.group(1))
            parsed = urllib.parse.urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith("#"):
                continue
            relative = PurePosixPath(urllib.parse.unquote(parsed.path).replace("\\", "/"))
            candidate = (bundle / Path(*relative.parts)).resolve()
            if not candidate.is_relative_to(bundle.resolve()) or not candidate.is_file():
                errors.append("referenced local images do not resolve")
                break
            if candidate not in linked:
                linked.append(candidate)
        actual = sorted(path.resolve() for path in images.glob("*") if path.is_file())
        if set(linked) != set(actual):
            errors.append("referenced local images do not resolve")
        numbers = []
        for path in linked:
            match = SEQUENTIAL_IMAGE_RE.fullmatch(path.name.lower())
            if not match:
                errors.append("referenced images are not sequentially named")
                break
            numbers.append(int(match.group(1)))
        if numbers != list(range(1, len(numbers) + 1)):
            errors.append("referenced images are not sequentially named")
    if errors:
        raise WorkspaceError("parser_bundle_invalid", "; ".join(dict.fromkeys(errors)))


class WorkspaceCore:
    """Own identifiers, parser tasks, bundle installation, membership, and pointers."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir():
            raise WorkspaceError("workspace_missing", "Workspace does not exist")

    def _task_root(self, batch_id: str) -> Path:
        return self.workspace / "parser-tasks" / _batch_id(batch_id)

    def _registered_and_reserved_paper_ids(self) -> set[str]:
        result = {
            path.parent.name
            for path in (self.workspace / "papers").glob("*/paper.yaml")
            if path.is_file()
        }
        for task_path in (self.workspace / "parser-tasks").glob("*/task.json"):
            try:
                task = _read_document(task_path)
                paper_id = str(task.get("paper_id", ""))
                result.add(_identifier(paper_id, "paper_id"))
            except WorkspaceError:
                continue
        return result

    def _allocate_paper_id(self, title: str) -> str:
        base = _slug(title, "paper")
        used = self._registered_and_reserved_paper_ids()
        if base not in used:
            return base
        suffix = 2
        while f"{base}-{suffix:03d}" in used:
            suffix += 1
        return f"{base}-{suffix:03d}"

    def create_parser_task(
        self,
        batch_id: str,
        source: Path,
        *,
        title: str,
        topic_title: str,
        topic_id: str | None,
        model: str,
        language: str,
    ) -> ParserTask:
        batch_id = _batch_id(batch_id)
        resolved_source = source.resolve()
        if not resolved_source.is_file() or resolved_source.suffix.lower() != ".pdf":
            raise WorkspaceError("source_pdf_missing", "Source must be an existing PDF file")
        resolved_topic_id = _identifier(topic_id, "topic_id") if topic_id else _slug(topic_title, "topic")
        task = ParserTask(
            batch_id=batch_id,
            paper_id=self._allocate_paper_id(title),
            title=title,
            topic_id=resolved_topic_id,
            topic_title=topic_title,
            model=model,
            language=language,
        )
        task_root = self._task_root(batch_id)
        if task_root.exists():
            raise WorkspaceError("parser_task_exists", f"Parser task already exists: {batch_id}")
        task_root.mkdir(parents=True)
        try:
            source_copy = task_root / "source.pdf"
            temporary_source = task_root / ".source.pdf.tmp"
            shutil.copy2(resolved_source, temporary_source)
            temporary_source.replace(source_copy)
            _write_document(task_root / "task.json", asdict(task))
        except Exception:
            shutil.rmtree(task_root, ignore_errors=True)
            raise
        return task

    def load_parser_task(self, batch_id: str) -> ParserTask:
        task_root = self._task_root(batch_id)
        task_path = task_root / "task.json"
        if not task_path.is_file():
            raise WorkspaceError("parser_task_missing", f"Parser task does not exist: {batch_id}")
        value = _read_document(task_path)
        required = {field.name for field in ParserTask.__dataclass_fields__.values()}
        if set(value) != required or value.get("batch_id") != batch_id:
            raise WorkspaceError("parser_task_invalid", "Parser task reference is invalid")
        try:
            task = ParserTask(**value)
        except TypeError as exc:
            raise WorkspaceError("parser_task_invalid", "Parser task reference is invalid") from exc
        _identifier(task.paper_id, "paper_id")
        _identifier(task.topic_id, "topic_id")
        if task.model not in {"vlm", "pipeline"} or not (task_root / "source.pdf").is_file():
            raise WorkspaceError("parser_task_invalid", "Parser task reference is invalid")
        return task

    def parser_task_source(self, task: ParserTask) -> Path:
        return self._task_root(task.batch_id) / "source.pdf"

    def prepare_parser_bundle(self, task: ParserTask) -> Path:
        paper_root = self.workspace / "papers" / task.paper_id
        bundle = paper_root / "parser-bundle"
        if bundle.exists():
            raise WorkspaceError("parser_bundle_exists", "The Paper already has an immutable Parser Bundle")
        staging = paper_root / ".parser-bundle-staging"
        if staging.exists():
            shutil.rmtree(staging)
        paper_root.mkdir(parents=True, exist_ok=True)
        return staging

    def discard_parser_bundle(self, task: ParserTask) -> None:
        paper_root = self.workspace / "papers" / task.paper_id
        staging = paper_root / ".parser-bundle-staging"
        if staging.exists():
            shutil.rmtree(staging)
        if paper_root.exists() and not any(paper_root.iterdir()):
            paper_root.rmdir()

    def install_parser_bundle(self, task: ParserTask, staging: Path) -> None:
        _validate_parser_bundle(staging)
        paper_root = self.workspace / "papers" / task.paper_id
        bundle = paper_root / "parser-bundle"
        paper_path = paper_root / "paper.yaml"
        topic_path = self.workspace / "topics" / task.topic_id / "topic.yaml"
        pointers_path = self.workspace / "pointers.yaml"
        if bundle.exists() or paper_path.exists():
            raise WorkspaceError("parser_bundle_exists", "The Paper is already registered")

        topic = _read_document(
            topic_path,
            {"topic_id": task.topic_id, "title": task.topic_title, "description": "", "papers": []},
        )
        pointers = _read_document(pointers_path, {"current_paper_id": None, "papers": {}})
        _prepare_membership(
            topic,
            pointers,
            paper_id=task.paper_id,
            topic_id=task.topic_id,
            initialize_pointer=True,
        )
        paper = {"paper_id": task.paper_id, "title": task.title, "topics": [task.topic_id]}
        _commit_documents(
            {paper_path: paper, topic_path: topic, pointers_path: pointers},
            staged_bundle=(staging, bundle),
        )
        shutil.rmtree(self._task_root(task.batch_id), ignore_errors=True)

    def reuse_paper(
        self,
        paper_id: str,
        *,
        topic_title: str | None = None,
        topic_id: str | None = None,
        existing_topic_id: str | None = None,
    ) -> str:
        paper_id = _identifier(paper_id, "paper_id")
        paper_root = self.workspace / "papers" / paper_id
        paper_path = paper_root / "paper.yaml"
        if not paper_path.is_file():
            raise WorkspaceError("paper_missing", f"Paper does not exist: {paper_id}")
        bundle = paper_root / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {paper_id}")
        _validate_parser_bundle(bundle)
        paper = _read_document(paper_path)
        paper_topics = paper.get("topics")
        if not isinstance(paper_topics, list):
            raise WorkspaceError("paper_invalid", f"Paper is invalid: {paper_id}")

        if existing_topic_id:
            resolved_topic_id = _identifier(existing_topic_id, "topic_id")
            topic_path = self.workspace / "topics" / resolved_topic_id / "topic.yaml"
            if not topic_path.is_file():
                raise WorkspaceError("topic_missing", f"Topic does not exist: {resolved_topic_id}")
            topic = _read_document(topic_path)
        else:
            if topic_title is None:
                raise WorkspaceError("topic_missing", "A Topic title or existing Topic ID is required")
            resolved_topic_id = _identifier(topic_id, "topic_id") if topic_id else _slug(topic_title, "topic")
            topic_path = self.workspace / "topics" / resolved_topic_id / "topic.yaml"
            topic = _read_document(
                topic_path,
                {"topic_id": resolved_topic_id, "title": topic_title, "description": "", "papers": []},
            )
        if resolved_topic_id not in paper_topics:
            paper_topics.append(resolved_topic_id)
        pointers_path = self.workspace / "pointers.yaml"
        pointers = _read_document(pointers_path, {"current_paper_id": None, "papers": {}})
        _prepare_membership(
            topic,
            pointers,
            paper_id=paper_id,
            topic_id=resolved_topic_id,
            initialize_pointer=False,
        )
        _commit_documents({paper_path: paper, topic_path: topic, pointers_path: pointers})
        return resolved_topic_id
