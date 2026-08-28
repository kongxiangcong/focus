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
CHUNK_KEYS = {
    "chunk_id",
    "index",
    "section_path",
    "source_lines",
    "images",
}
READING_RECORD_KEYS = {"chunk_id", "translation", "notes"}
NOTE_KINDS = {"thought", "emphasis", "question", "clarification"}
NOTE_ORIGINS = {"user", "dialogue"}


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
    state: dict[str, Any],
    *,
    paper_id: str,
    initialize_pointer: bool,
) -> None:
    topic_papers = topic.get("papers")
    if not isinstance(topic_papers, list):
        raise WorkspaceError("topic_invalid", "Topic is invalid")
    if paper_id not in topic_papers:
        topic_papers.append(paper_id)
    paper_states = state.get("papers")
    if not isinstance(paper_states, dict):
        raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
    empty_state = {"current_plan_id": None, "current_chunk_id": None}
    if initialize_pointer:
        paper_states[paper_id] = empty_state
    else:
        paper_states.setdefault(paper_id, empty_state)
    state["current_paper_id"] = paper_id


def _current_paper_state(
    workspace: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], str, Path]:
    state_path = workspace / "state.json"
    state = _read_document(state_path)
    paper_id = state.get("current_paper_id")
    paper_states = state.get("papers")
    if not isinstance(paper_id, str) or not isinstance(paper_states, dict):
        raise WorkspaceError("paper_missing", "No current Paper is selected")
    paper_id = _identifier(paper_id, "paper_id")
    paper_state = paper_states.get(paper_id)
    if not isinstance(paper_state, dict) or set(paper_state) != {
        "current_plan_id",
        "current_chunk_id",
    }:
        raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
    return state_path, state, paper_state, paper_id, workspace / "papers" / paper_id


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


def validate_paper_id(value: str) -> str:
    """Validate and return one public Paper ID."""
    return _identifier(value, "paper_id")


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
        if not MARKDOWN_IMAGE_RE.search(line):
            continue
        if number < len(lines) and _looks_like_caption(lines[number]):
            ranges.append((number, number + 1))
        if number > 1 and _looks_like_caption(lines[number - 2]):
            ranges.append((number - 1, number))
    return ranges


def _source_heading_paths(lines: list[str]) -> list[tuple[str, ...]]:
    headings: dict[int, str] = {}
    paths: list[tuple[str, ...]] = []
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            level = len(match.group(1))
            headings = {key: value for key, value in headings.items() if key < level}
            headings[level] = match.group(2).strip()
        paths.append(tuple(headings[key] for key in sorted(headings)))
    return paths


def _reading_plan_records(bundle: Path, draft: dict[str, Any]) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    chunks = draft.get("chunks")
    glossary = draft.get("glossary", [])
    if not isinstance(chunks, list) or not chunks or not isinstance(glossary, list):
        raise WorkspaceError("reading_plan_invalid", "Reading Plan draft is invalid")
    lines = (bundle / "paper.md").read_text(encoding="utf-8", errors="replace").splitlines()
    protected = _protected_source_ranges(lines)
    heading_paths = _source_heading_paths(lines)
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
        if tuple(section_path) not in set(heading_paths[start - 1 : end]):
            raise WorkspaceError("reading_plan_invalid", "Reading Chunk section path is not anchored to source headings")
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
            if not isinstance(value, dict) or set(value) != CHUNK_KEYS:
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


def _validate_anchor(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict) or not value or not set(value).issubset({"source_lines", "quote"}):
        return False
    source_lines = value.get("source_lines")
    quote = value.get("quote")
    return (
        (source_lines is None or (
            isinstance(source_lines, list)
            and len(source_lines) == 2
            and all(isinstance(item, int) and not isinstance(item, bool) for item in source_lines)
            and 1 <= source_lines[0] <= source_lines[1]
        ))
        and (quote is None or isinstance(quote, str) and bool(quote.strip()))
    )


def _validate_note(note: Any) -> bool:
    if not isinstance(note, dict) or set(note) not in (
        {"kind", "origin", "content"},
        {"kind", "origin", "content", "anchor"},
    ):
        return False
    return (
        note.get("kind") in NOTE_KINDS
        and note.get("origin") in NOTE_ORIGINS
        and isinstance(note.get("content"), str)
        and bool(note["content"].strip())
        and _validate_anchor(note.get("anchor"))
    )


def _read_reading_record(path: Path, chunk_id: str) -> dict[str, Any]:
    value = _read_document(path)
    if (
        set(value) != READING_RECORD_KEYS
        or value.get("chunk_id") != chunk_id
        or (
            value.get("translation") is not None
            and (
                not isinstance(value.get("translation"), str)
                or not value["translation"].strip()
            )
        )
        or not isinstance(value.get("notes"), list)
        or any(not _validate_note(note) for note in value["notes"])
    ):
        raise WorkspaceError("reading_record_invalid", f"Reading Record is invalid: {chunk_id}")
    return value


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


def _looks_like_caption(value: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:figure|fig\.?|table|algorithm|scheme|图|表|算法)\s*[-.:：]?[\s\d一二三四五六七八九十]+",
            value,
            flags=re.IGNORECASE,
        )
    )


def _bound_image_presentations(bundle: Path, source_lines: list[str], image_paths: list[str]) -> list[dict[str, str]]:
    presentations: list[dict[str, str]] = []
    for image_path in image_paths:
        caption = ""
        for offset, line in enumerate(source_lines):
            for match in MARKDOWN_IMAGE_DETAIL_RE.finditer(line):
                if PurePosixPath(_split_image_target(match.group(2)).replace("\\", "/")).as_posix() != image_path:
                    continue
                caption = match.group(1).strip()
                adjacent_candidates = []
                if offset + 1 < len(source_lines):
                    adjacent_candidates.append(source_lines[offset + 1].strip())
                if offset > 0:
                    adjacent_candidates.append(source_lines[offset - 1].strip())
                original_caption = next((value for value in adjacent_candidates if _looks_like_caption(value)), "")
                if original_caption:
                    caption = original_caption
                break
            if caption:
                break
        resolved = (bundle / Path(*PurePosixPath(image_path).parts)).resolve()
        if not resolved.is_relative_to(bundle.resolve()) or not resolved.is_file():
            raise WorkspaceError("reading_chunk_invalid", "Reading Chunk image binding is invalid")
        presentations.append({"path": str(resolved), "caption": caption})
    return presentations


def _chunk_presentation(
    bundle: Path,
    plan_root: Path,
    *,
    paper_id: str,
    plan_id: str,
    chunk: dict[str, Any],
    reading_record: dict[str, Any],
    total: int,
) -> dict[str, Any]:
    chunk_id = chunk.get("chunk_id")
    source_range = chunk.get("source_lines")
    images = chunk.get("images")
    section_path = chunk.get("section_path")
    if (
        not isinstance(chunk_id, str)
        or reading_record.get("chunk_id") != chunk_id
        or not isinstance(source_range, list)
        or len(source_range) != 2
        or any(not isinstance(value, int) or isinstance(value, bool) for value in source_range)
        or not isinstance(images, list)
        or any(not isinstance(value, str) for value in images)
        or not isinstance(section_path, list)
        or not all(isinstance(value, str) and value for value in section_path)
    ):
        raise WorkspaceError("reading_chunk_invalid", f"Reading Chunk is invalid: {chunk_id}")
    paper_lines = (bundle / "paper.md").read_text(encoding="utf-8", errors="replace").splitlines()
    start, end = source_range
    if start < 1 or end < start or end > len(paper_lines):
        raise WorkspaceError("reading_chunk_invalid", f"Reading Chunk is invalid: {chunk_id}")
    selected_lines = paper_lines[start - 1 : end]
    source_text = "\n".join(selected_lines)
    glossary = [
        row
        for row in _read_glossary(plan_root / "glossary.tsv")
        if row["source"].casefold() in source_text.casefold()
    ]
    return {
        "paper_id": paper_id,
        "plan_id": plan_id,
        "chunk_id": chunk_id,
        "index": chunk["index"],
        "total": total,
        "section_path": section_path,
        "source_lines": source_range,
        "source_text": source_text,
        "translation": reading_record["translation"],
        "images": _bound_image_presentations(bundle, selected_lines, images),
        "relevant_glossary": glossary,
    }


class WorkspaceCore:
    """Own Parser assets, fixed Reading Plans, Cursor State, and Reading Records."""

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
        state_path = self.workspace / "state.json"
        if bundle.exists() or paper_path.exists():
            raise WorkspaceError("parser_bundle_exists", "The Paper is already registered")

        topic = _read_document(
            topic_path,
            {"topic_id": task.topic_id, "title": task.topic_title, "description": "", "papers": []},
        )
        state = _read_document(state_path, {"current_paper_id": None, "papers": {}})
        _prepare_membership(
            topic,
            state,
            paper_id=task.paper_id,
            initialize_pointer=True,
        )
        paper = {"paper_id": task.paper_id, "title": task.title, "topics": [task.topic_id]}
        _commit_documents(
            {paper_path: paper, topic_path: topic, state_path: state},
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
        state_path = self.workspace / "state.json"
        state = _read_document(state_path, {"current_paper_id": None, "papers": {}})
        _prepare_membership(
            topic,
            state,
            paper_id=paper_id,
            initialize_pointer=False,
        )
        _commit_documents({paper_path: paper, topic_path: topic, state_path: state})
        return resolved_topic_id

    def map_reading_plan(
        self,
        paper_id: str,
        *,
        draft: dict[str, Any] | None,
        scope: str | None = None,
        reinitialize: bool = False,
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

        state_path = self.workspace / "state.json"
        state = _read_document(state_path)
        paper_states = state.get("papers")
        if not isinstance(paper_states, dict) or not isinstance(paper_states.get(paper_id), dict):
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        paper_state = paper_states[paper_id]
        if set(paper_state) != {"current_plan_id", "current_chunk_id"}:
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        current_plan_id = paper_state.get("current_plan_id")
        current_chunk_id = paper_state.get("current_chunk_id")
        if current_plan_id is not None:
            current_plan_id = _identifier(current_plan_id, "reading_plan")
            current_plan_root = paper_root / "reading" / "plans" / current_plan_id
            chunks = _read_chunk_records(current_plan_root / "chunks.jsonl")
            if current_chunk_id is not None:
                current_chunk_id = _identifier(current_chunk_id, "reading_chunk")
                if current_chunk_id not in {chunk["chunk_id"] for chunk in chunks}:
                    raise WorkspaceError(
                        "reading_chunk_missing", f"Reading Chunk does not exist: {current_chunk_id}"
                    )
            for chunk in chunks:
                _read_reading_record(
                    current_plan_root / "records" / f'{chunk["chunk_id"]}.json',
                    chunk["chunk_id"],
                )
            if not reinitialize:
                return {
                    "ok": True,
                    "paper_id": paper_id,
                    "plan_id": current_plan_id,
                    "chunk_id": current_chunk_id,
                    "reused": True,
                    "reinitialized": False,
                }
        elif reinitialize:
            raise WorkspaceError("reading_plan_missing", "No current Reading Plan exists to reinitialize")
        if draft is None:
            raise WorkspaceError("reading_plan_input_missing", "A Reading Plan draft is required")
        records, glossary = _reading_plan_records(bundle, draft)

        plans_root = paper_root / "reading" / "plans"
        used_numbers = []
        for path in plans_root.glob("plan-*"):
            match = re.fullmatch(r"plan-(\d+)", path.name)
            if path.is_dir() and match:
                used_numbers.append(int(match.group(1)))
        plan_id = f"plan-{(max(used_numbers, default=0) + 1):03d}"
        plan_root = plans_root / plan_id
        staging = plans_root / f".{plan_id}.{uuid.uuid4().hex}.staging"
        state_snapshot = state_path.read_bytes()
        installed = False
        try:
            staging.mkdir(parents=True)
            chunks_text = "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records)
            (staging / "chunks.jsonl").write_text(chunks_text, encoding="utf-8")
            glossary_text = "".join(f"{source}\t{translation}\n" for source, translation in glossary)
            (staging / "glossary.tsv").write_text(glossary_text, encoding="utf-8")
            records_root = staging / "records"
            records_root.mkdir()
            for record in records:
                _write_document(
                    records_root / f'{record["chunk_id"]}.json',
                    {"chunk_id": record["chunk_id"], "translation": None, "notes": []},
                )
            staging.replace(plan_root)
            installed = True
            paper_state["current_plan_id"] = plan_id
            paper_state["current_chunk_id"] = records[0]["chunk_id"]
            _write_document(state_path, state)
        except Exception:
            _restore(state_path, state_snapshot)
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
            "reinitialized": reinitialize,
        }

    def _current_reading_selection(
        self, *, require_chunk: bool
    ) -> tuple[Path, dict[str, Any], dict[str, Any], str, str, str | None]:
        state_path, state, paper_state, paper_id, _ = _current_paper_state(self.workspace)
        plan_id = paper_state.get("current_plan_id")
        chunk_id = paper_state.get("current_chunk_id")
        if plan_id is None:
            raise WorkspaceError("reading_plan_missing", f"Reading Plan does not exist: {paper_id}")
        plan_id = _identifier(plan_id, "reading_plan")
        if chunk_id is None:
            if require_chunk:
                raise WorkspaceError("reading_completed", "Reading Plan is complete")
        else:
            chunk_id = _identifier(chunk_id, "reading_chunk")
        return state_path, state, paper_state, paper_id, plan_id, chunk_id

    def _current_chunk_context(
        self,
    ) -> tuple[Path, dict[str, Any], dict[str, Any], str, str, str, Path, list[dict[str, Any]], int]:
        state_path, state, paper_state, paper_id, plan_id, chunk_id = self._current_reading_selection(
            require_chunk=True
        )
        assert chunk_id is not None
        plan_root = self.workspace / "papers" / paper_id / "reading" / "plans" / plan_id
        chunks = _read_chunk_records(plan_root / "chunks.jsonl")
        matches = [index for index, chunk in enumerate(chunks) if chunk.get("chunk_id") == chunk_id]
        if len(matches) != 1:
            raise WorkspaceError("reading_chunk_missing", f"Reading Chunk does not exist: {chunk_id}")
        return state_path, state, paper_state, paper_id, plan_id, chunk_id, plan_root, chunks, matches[0]

    def get_reading_state(self) -> dict[str, Any]:
        _, _, _, paper_id, plan_id, chunk_id = self._current_reading_selection(require_chunk=False)
        plan_root = self.workspace / "papers" / paper_id / "reading" / "plans" / plan_id
        chunks = _read_chunk_records(plan_root / "chunks.jsonl")
        if chunk_id is None:
            return {
                "ok": True,
                "status": "reading_completed",
                "paper_id": paper_id,
                "plan_id": plan_id,
                "chunk_id": None,
                "index": None,
                "total": len(chunks),
                "section_path": [],
            }
        matches = [chunk for chunk in chunks if chunk.get("chunk_id") == chunk_id]
        if len(matches) != 1:
            raise WorkspaceError("reading_chunk_missing", f"Reading Chunk does not exist: {chunk_id}")
        chunk = matches[0]
        return {
            "ok": True,
            "status": "reading",
            "paper_id": paper_id,
            "plan_id": plan_id,
            "chunk_id": chunk_id,
            "index": chunk["index"],
            "total": len(chunks),
            "section_path": chunk["section_path"],
        }

    def get_current_chunk(self) -> dict[str, Any]:
        try:
            _, _, _, paper_id, plan_id, chunk_id, plan_root, chunks, index = self._current_chunk_context()
        except WorkspaceError as exc:
            if exc.error_id == "reading_completed":
                return self.get_reading_state()
            raise
        bundle = self.workspace / "papers" / paper_id / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {paper_id}")
        _validate_parser_bundle(bundle)
        reading_record = _read_reading_record(plan_root / "records" / f"{chunk_id}.json", chunk_id)
        presentation = _chunk_presentation(
            bundle,
            plan_root,
            paper_id=paper_id,
            plan_id=plan_id,
            chunk=chunks[index],
            reading_record=reading_record,
            total=len(chunks),
        )
        return {
            "ok": True,
            "status": "translation_required" if reading_record["translation"] is None else "presented",
            **presentation,
        }

    def _cursor_changed(self) -> dict[str, Any]:
        return {**self.get_reading_state(), "status": "cursor_changed"}

    @staticmethod
    def _note(*, kind: str, origin: str, content: str, anchor: dict[str, Any] | None) -> dict[str, Any]:
        note: dict[str, Any] = {
            "kind": kind,
            "origin": origin,
            "content": content.strip() if isinstance(content, str) else content,
        }
        if anchor is not None:
            note["anchor"] = anchor
        if not _validate_note(note):
            error_id = "note_kind_invalid" if kind not in NOTE_KINDS else "note_invalid"
            raise WorkspaceError(error_id, "Note is invalid")
        return note

    def append_note(
        self,
        *,
        expected_plan_id: str,
        expected_chunk_id: str,
        kind: str,
        origin: str,
        content: str,
        anchor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _, _, _, paper_id, plan_id, chunk_id, plan_root, _, _ = self._current_chunk_context()
        if plan_id != expected_plan_id or chunk_id != expected_chunk_id:
            return self._cursor_changed()
        note = self._note(kind=kind, origin=origin, content=content, anchor=anchor)
        record_path = plan_root / "records" / f"{chunk_id}.json"
        record = _read_reading_record(record_path, chunk_id)
        if note in record["notes"]:
            status = "note_unchanged"
        else:
            record["notes"].append(note)
            try:
                _write_document(record_path, record)
            except OSError as exc:
                raise WorkspaceError("reading_record_write_failed", "Note could not be saved") from exc
            status = "note_saved"
        return {
            "ok": True,
            "status": status,
            "paper_id": paper_id,
            "plan_id": plan_id,
            "chunk_id": chunk_id,
            "note": note,
        }

    def list_notes(
        self,
        *,
        plan_id: str,
        chunk_id: str,
        kinds: list[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        _, _, _, paper_id, _, _ = self._current_reading_selection(require_chunk=False)
        plan_id = _identifier(plan_id, "reading_plan")
        chunk_id = _identifier(chunk_id, "reading_chunk")
        if kinds is not None and (not isinstance(kinds, list) or any(kind not in NOTE_KINDS for kind in kinds)):
            raise WorkspaceError("note_kind_invalid", "Note kind is invalid")
        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
            raise WorkspaceError("note_limit_invalid", "Note limit is invalid")
        plan_root = self.workspace / "papers" / paper_id / "reading" / "plans" / plan_id
        chunks = _read_chunk_records(plan_root / "chunks.jsonl")
        if chunk_id not in {chunk["chunk_id"] for chunk in chunks}:
            raise WorkspaceError("reading_chunk_missing", f"Reading Chunk does not exist: {chunk_id}")
        record = _read_reading_record(plan_root / "records" / f"{chunk_id}.json", chunk_id)
        notes = [note for note in record["notes"] if kinds is None or note["kind"] in kinds]
        if limit is not None:
            notes = notes[-limit:]
        return {
            "ok": True,
            "status": "notes_listed",
            "paper_id": paper_id,
            "plan_id": plan_id,
            "chunk_id": chunk_id,
            "notes": notes,
        }

    def update_glossary(self, *, expected_plan_id: str, source: str, translation: str) -> dict[str, Any]:
        if (
            not isinstance(source, str)
            or not source.strip()
            or not isinstance(translation, str)
            or not translation.strip()
            or any(character in source + translation for character in "\t\r\n")
        ):
            raise WorkspaceError("glossary_term_invalid", "Glossary term is empty or invalid")
        _, _, _, paper_id, plan_id, chunk_id = self._current_reading_selection(require_chunk=False)
        if plan_id != expected_plan_id:
            return self._cursor_changed()
        glossary_path = self.workspace / "papers" / paper_id / "reading" / "plans" / plan_id / "glossary.tsv"
        glossary = _read_glossary(glossary_path)
        for row in glossary:
            if row["source"] == source:
                row["translation"] = translation
                break
        else:
            glossary.append({"source": source, "translation": translation})
        serialized = "".join(f'{row["source"]}\t{row["translation"]}\n' for row in glossary)
        try:
            _replace_text(glossary_path, serialized)
        except OSError as exc:
            raise WorkspaceError("glossary_write_failed", "Plan Glossary could not be updated") from exc
        return {
            "ok": True,
            "status": "glossary_updated",
            "paper_id": paper_id,
            "plan_id": plan_id,
            "chunk_id": chunk_id,
            "term": {"source": source, "translation": translation},
        }

    def retranslate_current_chunk(
        self, *, expected_plan_id: str, expected_chunk_id: str, translation: str
    ) -> dict[str, Any]:
        if not isinstance(translation, str) or not translation.strip():
            raise WorkspaceError("translation_invalid", "Translation is empty or invalid")
        _, _, _, paper_id, plan_id, chunk_id, plan_root, _, _ = self._current_chunk_context()
        if plan_id != expected_plan_id or chunk_id != expected_chunk_id:
            return self._cursor_changed()
        record_path = plan_root / "records" / f"{chunk_id}.json"
        record = _read_reading_record(record_path, chunk_id)
        record["translation"] = translation
        try:
            _write_document(record_path, record)
        except OSError as exc:
            raise WorkspaceError("reading_record_write_failed", "Translation could not be replaced") from exc
        return {
            "ok": True,
            "status": "retranslated",
            "paper_id": paper_id,
            "plan_id": plan_id,
            "chunk_id": chunk_id,
            "translation": translation,
        }

    def continue_reading(
        self,
        *,
        expected_plan_id: str,
        expected_chunk_id: str,
        pending_notes: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        _, _, _, _, current_plan_id, current_chunk_id = self._current_reading_selection(
            require_chunk=False
        )
        if current_chunk_id is None:
            return self.get_reading_state()
        if current_plan_id != expected_plan_id or current_chunk_id != expected_chunk_id:
            return self._cursor_changed()
        state_path, state, paper_state, paper_id, plan_id, chunk_id, plan_root, chunks, index = self._current_chunk_context()
        if pending_notes is None:
            pending_notes = []
        if not isinstance(pending_notes, list):
            raise WorkspaceError("note_invalid", "Pending Notes are invalid")
        if any(not _validate_note(note) for note in pending_notes):
            raise WorkspaceError("note_invalid", "Pending Notes are invalid")
        normalized_notes = [
            self._note(
                kind=note["kind"],
                origin=note["origin"],
                content=note["content"],
                anchor=note.get("anchor"),
            )
            for note in pending_notes
        ]
        if normalized_notes:
            record_path = plan_root / "records" / f"{chunk_id}.json"
            record = _read_reading_record(record_path, chunk_id)
            changed = False
            for note in normalized_notes:
                if note not in record["notes"]:
                    record["notes"].append(note)
                    changed = True
            if changed:
                try:
                    _write_document(record_path, record)
                except OSError as exc:
                    raise WorkspaceError("reading_record_write_failed", "Pending Notes could not be saved") from exc
        next_chunk_id = chunks[index + 1]["chunk_id"] if index + 1 < len(chunks) else None
        paper_state["current_chunk_id"] = next_chunk_id
        try:
            _write_document(state_path, state)
        except OSError as exc:
            raise WorkspaceError("reading_cursor_write_failed", "Reading Cursor could not be updated") from exc
        if next_chunk_id is None:
            return self.get_reading_state()
        return {
            **self.get_reading_state(),
            "status": "continued",
        }

    def search_paper(self, *, query: str, limit: int = 5) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            raise WorkspaceError("paper_query_invalid", "Paper query is empty or invalid")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise WorkspaceError("paper_query_limit_invalid", "Paper query limit is invalid")
        _, _, _, paper_id, paper_root = _current_paper_state(self.workspace)
        bundle = paper_root / "parser-bundle"
        _validate_parser_bundle(bundle)
        lines = (bundle / "paper.md").read_text(encoding="utf-8", errors="replace").splitlines()
        paths = _source_heading_paths(lines)
        terms = [term.casefold() for term in re.findall(r"[\w]+", query) if len(term) > 1]
        terms = terms or [query.strip().casefold()]
        matches: list[dict[str, Any]] = []
        for index, line in enumerate(lines):
            if not any(term in line.casefold() for term in terms):
                continue
            start = max(0, index - 1)
            end = min(len(lines), index + 2)
            snippet = " ".join(part.strip() for part in lines[start:end] if part.strip())
            matches.append(
                {
                    "section_path": list(paths[index]),
                    "source_lines": [start + 1, end],
                    "snippet": snippet[:320],
                }
            )
            if len(matches) == limit:
                break
        return {
            "ok": True,
            "status": "paper_matches_found" if matches else "paper_matches_empty",
            "paper_id": paper_id,
            "query": query,
            "matches": matches,
        }

    def read_source_range(self, *, start: int, end: int) -> dict[str, Any]:
        if any(not isinstance(value, int) or isinstance(value, bool) for value in (start, end)):
            raise WorkspaceError("source_range_invalid", "Source range is invalid")
        _, _, _, paper_id, paper_root = _current_paper_state(self.workspace)
        bundle = paper_root / "parser-bundle"
        _validate_parser_bundle(bundle)
        lines = (bundle / "paper.md").read_text(encoding="utf-8", errors="replace").splitlines()
        if start < 1 or end < start or end > len(lines):
            raise WorkspaceError("source_range_invalid", "Source range is invalid")
        selected = lines[start - 1 : end]
        image_paths = [
            PurePosixPath(_split_image_target(match.group(2)).replace("\\", "/")).as_posix()
            for line in selected
            for match in MARKDOWN_IMAGE_DETAIL_RE.finditer(line)
        ]
        return {
            "ok": True,
            "status": "source_range_read",
            "paper_id": paper_id,
            "section_path": list(_source_heading_paths(lines)[start - 1]),
            "source_lines": [start, end],
            "source_text": "\n".join(selected),
            "images": _bound_image_presentations(bundle, selected, image_paths),
        }

    def switch_paper(self, paper_id: str) -> dict[str, Any]:
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
        state_path = self.workspace / "state.json"
        state = _read_document(state_path)
        paper_states = state.get("papers")
        if not isinstance(paper_states, dict) or not isinstance(paper_states.get(paper_id), dict):
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        paper_state = paper_states[paper_id]
        if set(paper_state) != {"current_plan_id", "current_chunk_id"}:
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        state["current_paper_id"] = paper_id
        try:
            _write_document(state_path, state)
        except OSError as exc:
            raise WorkspaceError("workspace_state_write_failed", "Current Paper could not be selected") from exc
        return {
            "ok": True,
            "status": "paper_selected",
            "paper_id": paper_id,
            "plan_id": paper_state.get("current_plan_id"),
            "chunk_id": paper_state.get("current_chunk_id"),
        }
