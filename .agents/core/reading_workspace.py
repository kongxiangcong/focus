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
MARKDOWN_IMAGE_DETAIL_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)]+)\)")
SEQUENTIAL_IMAGE_RE = re.compile(r"^image-(\d{3})(\.[a-z0-9]+)$")
CHUNK_RECORD_KEYS = {
    "chunk_id",
    "index",
    "section_path",
    "source_lines",
    "images",
    "translation",
    "notes",
}


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


def _replace_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


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


def _protected_source_ranges(lines: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    table_start: int | None = None
    for number, line in enumerate(lines, 1):
        if "|" in line:
            table_start = table_start or number
        elif table_start is not None:
            table = lines[table_start - 1 : number - 1]
            if len(table) >= 2 and any(re.fullmatch(r"\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*", row) for row in table):
                ranges.append((table_start, number - 1))
            table_start = None
    if table_start is not None:
        table = lines[table_start - 1 :]
        if len(table) >= 2 and any(re.fullmatch(r"\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*", row) for row in table):
            ranges.append((table_start, len(lines)))

    opening: tuple[str, int] | None = None
    for number, line in enumerate(lines, 1):
        marker = line.strip()
        if opening is None and (marker.startswith("```") or marker in {"$$", "\\["}):
            opening = ("```" if marker.startswith("```") else marker, number)
        elif opening is not None:
            token, start = opening
            closes = (token == "```" and marker.startswith("```")) or (token == "$$" and marker == "$$") or (token == "\\[" and marker == "\\]")
            if closes:
                ranges.append((start, number))
                opening = None
    if opening is not None:
        raise WorkspaceError("reading_plan_invalid", "Paper Markdown contains an unterminated protected block")

    for number, line in enumerate(lines, 1):
        if MARKDOWN_IMAGE_RE.search(line) and number < len(lines):
            caption = lines[number].strip()
            if re.match(r"^(figure|fig\.?|table)\s*\d", caption, flags=re.IGNORECASE):
                ranges.append((number, number + 1))
    return ranges


def _reading_plan_records(bundle: Path, draft: dict[str, Any]) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    chunks = draft.get("chunks")
    glossary = draft.get("glossary", [])
    if not isinstance(chunks, list) or not chunks or not isinstance(glossary, list):
        raise WorkspaceError("reading_plan_invalid", "Reading Plan draft is invalid")
    lines = (bundle / "paper.md").read_text(encoding="utf-8", errors="replace").splitlines()
    protected = _protected_source_ranges(lines)
    records: list[dict[str, Any]] = []
    previous_end: int | None = None
    for index, chunk in enumerate(chunks, 1):
        if not isinstance(chunk, dict) or set(chunk) != {"section_path", "source_lines", "images"}:
            raise WorkspaceError("reading_plan_invalid", "Reading Chunk draft is invalid")
        section_path = chunk["section_path"]
        source_lines = chunk["source_lines"]
        images = chunk["images"]
        if (
            not isinstance(section_path, list)
            or not section_path
            or any(not isinstance(part, str) or not part.strip() for part in section_path)
            or not isinstance(source_lines, list)
            or len(source_lines) != 2
            or any(not isinstance(value, int) or isinstance(value, bool) for value in source_lines)
            or not isinstance(images, list)
            or any(not isinstance(value, str) for value in images)
        ):
            raise WorkspaceError("reading_plan_invalid", "Reading Chunk draft is invalid")
        start, end = source_lines
        if start < 1 or end < start or end > len(lines) or (previous_end is not None and start != previous_end + 1):
            raise WorkspaceError("reading_plan_invalid", "Reading Chunk source ranges must be ordered and continuous")
        if any(unit_start <= end < unit_end for unit_start, unit_end in protected):
            raise WorkspaceError("reading_plan_invalid", "Reading Chunk boundary splits a protected source unit")
        referenced: list[str] = []
        for line in lines[start - 1 : end]:
            for match in MARKDOWN_IMAGE_RE.finditer(line):
                target = _split_image_target(match.group(1))
                parsed = urllib.parse.urlsplit(target)
                if not parsed.scheme and not parsed.netloc and not target.startswith("#"):
                    referenced.append(PurePosixPath(urllib.parse.unquote(parsed.path).replace("\\", "/")).as_posix())
        if images != list(dict.fromkeys(referenced)):
            raise WorkspaceError("reading_plan_invalid", "Reading Chunk image bindings do not match its source range")
        records.append(
            {
                "chunk_id": f"chunk-{index:03d}",
                "index": index,
                "section_path": section_path,
                "source_lines": [start, end],
                "images": images,
                "translation": None,
                "notes": [],
            }
        )
        previous_end = end

    normalized_glossary: list[tuple[str, str]] = []
    seen_terms: set[str] = set()
    for row in glossary:
        if (
            not isinstance(row, list)
            or len(row) != 2
            or any(not isinstance(value, str) or not value.strip() or "\t" in value or "\n" in value or "\r" in value for value in row)
            or row[0] in seen_terms
        ):
            raise WorkspaceError("reading_plan_invalid", "Plan Glossary is invalid")
        seen_terms.add(row[0])
        normalized_glossary.append((row[0], row[1]))
    return records, normalized_glossary


def _read_chunk_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise WorkspaceError("reading_plan_missing", f"Reading Plan does not exist: {path.parent.name}")
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            value = json.loads(line)
            if not isinstance(value, dict) or set(value) != CHUNK_RECORD_KEYS:
                raise ValueError
            records.append(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorkspaceError("reading_plan_invalid", f"Reading Plan is invalid: {path.parent.name}") from exc
    if not records or [record.get("index") for record in records] != list(range(1, len(records) + 1)):
        raise WorkspaceError("reading_plan_invalid", f"Reading Plan is invalid: {path.parent.name}")
    expected_ids = [f"chunk-{index:03d}" for index in range(1, len(records) + 1)]
    if [record.get("chunk_id") for record in records] != expected_ids:
        raise WorkspaceError("reading_plan_invalid", f"Reading Plan is invalid: {path.parent.name}")
    return records


def _read_glossary(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise WorkspaceError("reading_plan_invalid", f"Plan Glossary is missing: {path.parent.name}")
    rows: list[dict[str, str]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            source, translation = line.split("\t")
            if not source or not translation:
                raise ValueError
            rows.append({"source": source, "translation": translation})
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise WorkspaceError("reading_plan_invalid", f"Plan Glossary is invalid: {path.parent.name}") from exc
    return rows


def _bound_image_presentations(bundle: Path, source_lines: list[str], image_paths: list[str]) -> list[dict[str, str]]:
    presentations: list[dict[str, str]] = []
    for image_path in image_paths:
        caption = ""
        for offset, line in enumerate(source_lines):
            for match in MARKDOWN_IMAGE_DETAIL_RE.finditer(line):
                if PurePosixPath(_split_image_target(match.group(2)).replace("\\", "/")).as_posix() != image_path:
                    continue
                caption = match.group(1).strip()
                if offset + 1 < len(source_lines):
                    adjacent = source_lines[offset + 1].strip()
                    if re.match(r"^(figure|fig\.?|table)\s*\d", adjacent, flags=re.IGNORECASE):
                        caption = adjacent
                break
            if caption:
                break
        resolved = (bundle / Path(*PurePosixPath(image_path).parts)).resolve()
        if not resolved.is_relative_to(bundle.resolve()) or not resolved.is_file():
            raise WorkspaceError("reading_chunk_invalid", "Reading Chunk image binding is invalid")
        presentations.append({"path": str(resolved), "caption": caption})
    return presentations


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

    def map_reading_plan(
        self,
        paper_id: str,
        *,
        draft: dict[str, Any] | None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        paper_id = _identifier(paper_id, "paper_id")
        paper_root = self.workspace / "papers" / paper_id
        paper_path = paper_root / "paper.yaml"
        if not paper_path.is_file():
            raise WorkspaceError("paper_missing", f"Paper does not exist: {paper_id}")
        paper = _read_document(paper_path)
        if paper.get("paper_id") != paper_id:
            raise WorkspaceError("paper_invalid", f"Paper is invalid: {paper_id}")
        bundle = paper_root / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {paper_id}")
        _validate_parser_bundle(bundle)
        if scope is not None and (not isinstance(scope, str) or not scope.strip()):
            raise WorkspaceError("reading_scope_invalid", "Reading scope is invalid")

        pointers_path = self.workspace / "pointers.yaml"
        pointers = _read_document(pointers_path)
        pointer_entries = pointers.get("papers")
        if not isinstance(pointer_entries, dict) or not isinstance(pointer_entries.get(paper_id), dict):
            raise WorkspaceError("workspace_pointers_invalid", "Workspace pointers are invalid")
        paper_pointer = pointer_entries[paper_id]
        current_plan_id = paper_pointer.get("current_plan_id")
        current_chunk_id = paper_pointer.get("current_chunk_id")
        if current_plan_id is not None:
            _identifier(current_plan_id, "reading_plan")
            if not (paper_root / "reading" / "plans" / current_plan_id / "chunks.jsonl").is_file():
                raise WorkspaceError("reading_plan_missing", f"Reading Plan does not exist: {current_plan_id}")
            return {"ok": True, "paper_id": paper_id, "plan_id": current_plan_id, "chunk_id": current_chunk_id, "reused": True}
        if draft is None:
            raise WorkspaceError("reading_plan_input_missing", "A Reading Plan draft is required")
        records, glossary = _reading_plan_records(bundle, draft)

        plans_root = paper_root / "reading" / "plans"
        used_numbers = []
        for path in plans_root.glob("plan-*"):
            match = re.fullmatch(r"plan-(\d{3})", path.name)
            if path.is_dir() and match:
                used_numbers.append(int(match.group(1)))
        plan_id = f"plan-{(max(used_numbers, default=0) + 1):03d}"
        plan_root = plans_root / plan_id
        staging = plans_root / f".{plan_id}.{uuid.uuid4().hex}.staging"
        pointer_snapshot = pointers_path.read_bytes()
        installed = False
        try:
            staging.mkdir(parents=True)
            chunks_text = "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records)
            (staging / "chunks.jsonl").write_text(chunks_text, encoding="utf-8")
            glossary_text = "".join(f"{source}\t{translation}\n" for source, translation in glossary)
            (staging / "glossary.tsv").write_text(glossary_text, encoding="utf-8")
            staging.replace(plan_root)
            installed = True
            paper_pointer["current_plan_id"] = plan_id
            paper_pointer["current_chunk_id"] = records[0]["chunk_id"]
            _write_document(pointers_path, pointers)
        except Exception:
            _restore(pointers_path, pointer_snapshot)
            if installed:
                shutil.rmtree(plan_root, ignore_errors=True)
            shutil.rmtree(staging, ignore_errors=True)
            if plans_root.is_dir() and not any(plans_root.iterdir()):
                plans_root.rmdir()
            raise
        return {
            "ok": True,
            "paper_id": paper_id,
            "plan_id": plan_id,
            "chunk_id": records[0]["chunk_id"],
            "reused": False,
        }

    def present_current_chunk(self, *, translation: str | None = None) -> dict[str, Any]:
        pointers = _read_document(self.workspace / "pointers.yaml")
        paper_id = pointers.get("current_paper_id")
        pointer_entries = pointers.get("papers")
        if not isinstance(paper_id, str) or not isinstance(pointer_entries, dict):
            raise WorkspaceError("paper_missing", "No current Paper is selected")
        paper_id = _identifier(paper_id, "paper_id")
        paper_pointer = pointer_entries.get(paper_id)
        if not isinstance(paper_pointer, dict):
            raise WorkspaceError("workspace_pointers_invalid", "Workspace pointers are invalid")
        plan_id = paper_pointer.get("current_plan_id")
        chunk_id = paper_pointer.get("current_chunk_id")
        if plan_id is None:
            raise WorkspaceError("reading_plan_missing", f"Reading Plan does not exist: {paper_id}")
        plan_id = _identifier(plan_id, "reading_plan")
        if chunk_id is None:
            return {"ok": True, "status": "reading_completed", "paper_id": paper_id, "plan_id": plan_id, "chunk_id": None}
        chunk_id = _identifier(chunk_id, "reading_chunk")

        paper_root = self.workspace / "papers" / paper_id
        bundle = paper_root / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {paper_id}")
        _validate_parser_bundle(bundle)
        plan_root = paper_root / "reading" / "plans" / plan_id
        chunks_path = plan_root / "chunks.jsonl"
        records = _read_chunk_records(chunks_path)
        matches = [(index, record) for index, record in enumerate(records) if record.get("chunk_id") == chunk_id]
        if len(matches) != 1:
            raise WorkspaceError("reading_chunk_missing", f"Reading Chunk does not exist: {chunk_id}")
        record_index, record = matches[0]
        source_range = record.get("source_lines")
        images = record.get("images")
        section_path = record.get("section_path")
        cached_translation = record.get("translation")
        if (
            not isinstance(source_range, list)
            or len(source_range) != 2
            or any(not isinstance(value, int) for value in source_range)
            or not isinstance(images, list)
            or any(not isinstance(value, str) for value in images)
            or not isinstance(section_path, list)
            or not all(isinstance(value, str) for value in section_path)
            or (cached_translation is not None and not isinstance(cached_translation, str))
        ):
            raise WorkspaceError("reading_chunk_invalid", f"Reading Chunk is invalid: {chunk_id}")
        paper_lines = (bundle / "paper.md").read_text(encoding="utf-8", errors="replace").splitlines()
        start, end = source_range
        if start < 1 or end < start or end > len(paper_lines):
            raise WorkspaceError("reading_chunk_invalid", f"Reading Chunk is invalid: {chunk_id}")
        selected_lines = paper_lines[start - 1 : end]
        presentation = {
            "paper_id": paper_id,
            "plan_id": plan_id,
            "chunk_id": chunk_id,
            "section_path": section_path,
            "source_lines": source_range,
            "source_text": "\n".join(selected_lines),
            "images": _bound_image_presentations(bundle, selected_lines, images),
            "glossary": _read_glossary(plan_root / "glossary.tsv"),
        }
        if cached_translation is None and translation is None:
            return {"ok": True, "status": "translation_required", **presentation}
        cached = cached_translation is not None
        if not cached:
            if not isinstance(translation, str) or not translation.strip():
                raise WorkspaceError("translation_invalid", "Translation is empty or invalid")
            updated = dict(record)
            updated["translation"] = translation
            records[record_index] = updated
            content = "".join(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n" for value in records)
            try:
                _replace_text(chunks_path, content)
            except OSError as exc:
                raise WorkspaceError("reading_chunk_write_failed", "Translation could not be cached") from exc
            cached_translation = translation
        return {
            "ok": True,
            "status": "presented",
            **presentation,
            "translation": cached_translation,
            "cached": cached,
        }
