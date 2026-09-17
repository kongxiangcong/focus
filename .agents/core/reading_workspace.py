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
    source_kind: str
    title: str
    fallback_title: str
    short_name: str
    identity: str
    topic_id: str | None
    topic_title: str | None
    published_at: str | None
    model: str
    language: str


@dataclass(frozen=True)
class ArticleParserTask:
    reference_id: str
    reference_kind: str
    source_kind: str
    title: str
    fallback_title: str
    short_name: str
    identity: str
    topic_id: str | None
    topic_title: str | None
    published_at: str | None
    model: str
    language: str
    source_url: str
    local_html: bool


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


def _current_source_state(
    workspace: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], str, Path]:
    state_path = workspace / "state.json"
    state = _read_document(state_path)
    source_id = state.get("current_source_id")
    source_states = state.get("sources")
    if not isinstance(source_id, str) or not isinstance(source_states, dict):
        raise WorkspaceError("source_missing", "No current Reading Source is selected")
    source_id = validate_source_id(source_id)
    source_state = source_states.get(source_id)
    if not isinstance(source_state, dict) or (set(source_state) - {"reading_started"}) != {
        "current_plan_id",
        "current_chunk_id",
    }:
        raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
    if "reading_started" in source_state and not isinstance(source_state["reading_started"], bool):
        raise WorkspaceError("workspace_state_invalid", "Reading start marker must be boolean")
    return state_path, state, source_state, source_id, workspace / "sources" / source_id


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


def validate_source_id(value: str) -> str:
    """Validate and return one public Source ID."""
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip(" .")
        or len(value) > 180
        or any(ord(character) < 32 or character in '<>:"/\\|?*' for character in value)
        or not (value.endswith("-paper") or value.endswith("-article"))
    ):
        raise WorkspaceError("source_id_invalid", "Source Id is invalid")
    return value


def validate_topic_id(value: str) -> str:
    """Validate and return one public Topic ID."""
    return _identifier(value, "topic_id")


def _batch_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", value):
        raise WorkspaceError("parser_task_invalid", "MinerU batch reference is invalid")
    return value


def _task_reference(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", value):
        raise WorkspaceError("parser_task_invalid", "MinerU task reference is invalid")
    return value


def _split_image_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<"):
        closing = target.find(">")
        return target[1:closing] if closing >= 0 else target
    return target.split(maxsplit=1)[0] if target else target


def _validate_parser_bundle(bundle: Path) -> dict[str, Any]:
    errors: list[str] = []
    metadata = _read_document(bundle / "metadata.json", {})
    source_kind = metadata.get("source_kind")
    original_name = {"paper_pdf": "source.pdf", "article_html": "source.html", "article_markdown": "source.md"}.get(source_kind)
    original = bundle / original_name if original_name else None
    content = bundle / "content.md"
    images = bundle / "images"
    if source_kind not in {"paper_pdf", "article_html", "article_markdown"}:
        errors.append("metadata source kind is invalid")
    elif original is None or not original.is_file():
        errors.append(f"{original_name} is missing")
    originals = {'source.pdf', 'source.html', 'source.md'}
    if any((bundle / name).exists() for name in originals - {original_name}):
        errors.append("Parser Bundle must contain exactly one source representation")
    if not content.is_file() or not content.read_text(encoding="utf-8", errors="replace").strip():
        errors.append("content.md is missing or empty")
    if not images.is_dir():
        errors.append("images directory is missing")
    if metadata.get("parser") not in {"paper-parser", "article-parser", "markdown-import"}:
        errors.append("metadata parser provenance is invalid")
    elif metadata.get("parser") != {"paper_pdf": "paper-parser", "article_html": "article-parser", "article_markdown": "markdown-import"}.get(source_kind):
        errors.append("metadata parser does not match source kind")
    if not isinstance(metadata.get("language"), str) or not metadata["language"].strip():
        errors.append("metadata language is invalid")
    if "source_url" in metadata and (
        not isinstance(metadata["source_url"], str) or not metadata["source_url"].strip()
    ):
        errors.append("metadata source URL is invalid")
    elif "source_url" in metadata:
        parsed_source_url = urllib.parse.urlsplit(metadata["source_url"])
        if parsed_source_url.scheme not in {"http", "https"} or not parsed_source_url.netloc:
            errors.append("metadata source URL is invalid")
    reference_keys = [key for key in ("task_id", "batch_id") if key in metadata]
    if len(reference_keys) != 1:
        errors.append("metadata task reference is invalid")
    elif not isinstance(metadata[reference_keys[0]], str) or not re.fullmatch(
        r"[A-Za-z0-9._-]{1,200}", metadata[reference_keys[0]]
    ):
        errors.append("metadata task reference is invalid")
    validation = _read_document(bundle / "validation.json", {})
    if validation.get("ok") is not True:
        errors.append("structural validation did not pass")
    warnings = validation.get("warnings", [])
    if not isinstance(warnings, list) or len(warnings) > 20 or any(not isinstance(item, str) for item in warnings):
        errors.append("structural validation warnings are invalid")
    if content.is_file() and images.is_dir():
        linked: list[Path] = []
        for match in MARKDOWN_IMAGE_RE.finditer(content.read_text(encoding="utf-8", errors="replace")):
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
    return metadata


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
        raise WorkspaceError("reading_plan_invalid", "Source Markdown contains an unterminated protected block")

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
    lines = (bundle / "content.md").read_text(encoding="utf-8", errors="replace").splitlines()
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
    source_id: str,
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
    content_lines = (bundle / "content.md").read_text(encoding="utf-8", errors="replace").splitlines()
    start, end = source_range
    if start < 1 or end < start or end > len(content_lines):
        raise WorkspaceError("reading_chunk_invalid", f"Reading Chunk is invalid: {chunk_id}")
    selected_lines = content_lines[start - 1 : end]
    source_text = "\n".join(selected_lines)
    glossary = [
        row
        for row in _read_glossary(plan_root / "glossary.tsv")
        if row["source"].casefold() in source_text.casefold()
    ]
    return {
        "source_id": source_id,
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

    def _task_root(self, reference_id: str) -> Path:
        return self.workspace / "parser-tasks" / _task_reference(reference_id)

    def create_parser_task(
        self,
        batch_id: str,
        source: Path,
        *,
        title: str,
        short_name: str,
        topic_title: str | None,
        topic_id: str | None,
        published_at: str | None,
        model: str,
        language: str,
    ) -> ParserTask:
        batch_id = _batch_id(batch_id)
        resolved_source = source.resolve()
        if not resolved_source.is_file() or resolved_source.suffix.lower() != ".pdf":
            raise WorkspaceError("source_pdf_missing", "Source must be an existing PDF file")
        resolved_topic_id = _identifier(topic_id, "topic_id") if topic_id else (
            _slug(topic_title, "topic") if topic_title else None
        )
        identity = f"paper-original:{resolved_source.name}:{resolved_source.stat().st_size}"
        task = ParserTask(
            batch_id=batch_id,
            source_kind="paper_pdf",
            title=title,
            fallback_title=resolved_source.stem,
            short_name=short_name,
            identity=identity,
            topic_id=resolved_topic_id,
            topic_title=topic_title,
            published_at=published_at,
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

    def create_article_parser_task(
        self,
        reference_id: str,
        reference_kind: str,
        *,
        title: str,
        short_name: str,
        topic_title: str | None,
        topic_id: str | None,
        published_at: str | None,
        source_url: str,
        local_html: Path | None,
    ) -> ArticleParserTask:
        reference_id = _task_reference(reference_id)
        if reference_kind not in {"task_id", "batch_id"}:
            raise WorkspaceError("parser_task_invalid", "MinerU task reference kind is invalid")
        if not isinstance(source_url, str):
            raise WorkspaceError("source_url_invalid", "Article source URL is invalid")
        resolved_html = local_html.resolve() if local_html is not None else None
        if resolved_html is not None and (not resolved_html.is_file() or resolved_html.suffix.lower() != ".html"):
            raise WorkspaceError("source_html_missing", "Source must be an existing .html file")
        resolved_topic_id = _identifier(topic_id, "topic_id") if topic_id else (
            _slug(topic_title, "topic") if topic_title else None
        )
        if source_url:
            from .source_library import canonical_article_url

            identity = "url:" + canonical_article_url(source_url)
        else:
            assert resolved_html is not None
            identity = f"article-original:{resolved_html.name}:{resolved_html.stat().st_size}"
        task = ArticleParserTask(
            reference_id=reference_id,
            reference_kind=reference_kind,
            source_kind="article_html",
            title=title,
            fallback_title=resolved_html.stem if resolved_html is not None else "",
            short_name=short_name,
            identity=identity,
            topic_id=resolved_topic_id,
            topic_title=topic_title,
            published_at=published_at,
            model="MinerU-HTML",
            language="zh",
            source_url=source_url,
            local_html=resolved_html is not None,
        )
        task_root = self._task_root(reference_id)
        if task_root.exists():
            raise WorkspaceError("parser_task_exists", f"Parser task already exists: {reference_id}")
        task_root.mkdir(parents=True)
        try:
            value = {field: getattr(task, field) for field in ArticleParserTask.__dataclass_fields__}
            value.pop("reference_id")
            value.pop("reference_kind")
            value[reference_kind] = reference_id
            _write_document(task_root / "task.json", value)
            if resolved_html is not None:
                shutil.copy2(resolved_html, task_root / "source.html")
        except Exception:
            shutil.rmtree(task_root, ignore_errors=True)
            raise
        return task

    def load_article_parser_task(self, reference_id: str) -> ArticleParserTask:
        reference_id = _task_reference(reference_id)
        task_root = self._task_root(reference_id)
        value = _read_document(task_root / "task.json")
        reference_keys = [key for key in ("task_id", "batch_id") if key in value]
        if len(reference_keys) != 1 or value[reference_keys[0]] != reference_id:
            raise WorkspaceError("parser_task_invalid", "MinerU task reference is invalid")
        reference_kind = reference_keys[0]
        value = dict(value)
        value.pop(reference_kind)
        try:
            task = ArticleParserTask(reference_id=reference_id, reference_kind=reference_kind, **value)
        except TypeError as exc:
            raise WorkspaceError("parser_task_invalid", "MinerU task reference is invalid") from exc
        if task.topic_id is not None:
            _identifier(task.topic_id, "topic_id")
        if task.source_kind != "article_html" or task.model != "MinerU-HTML" or task.language != "zh":
            raise WorkspaceError("parser_task_invalid", "MinerU task reference is invalid")
        if task.local_html != (task_root / "source.html").is_file():
            raise WorkspaceError("parser_task_invalid", "MinerU task reference is invalid")
        return task

    def article_task_source(self, task: ArticleParserTask) -> Path | None:
        path = self._task_root(task.reference_id) / "source.html"
        return path if task.local_html else None

    def discard_parser_task(self, task: ParserTask | ArticleParserTask) -> None:
        shutil.rmtree(self._task_root(self._reference_id(task)), ignore_errors=True)

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
        if task.topic_id is not None:
            _identifier(task.topic_id, "topic_id")
        if (
            task.source_kind != "paper_pdf"
            or task.model not in {"vlm", "pipeline"}
            or not (task_root / "source.pdf").is_file()
        ):
            raise WorkspaceError("parser_task_invalid", "Parser task reference is invalid")
        return task

    def parser_task_source(self, task: ParserTask) -> Path:
        return self._task_root(task.batch_id) / "source.pdf"

    @staticmethod
    def _reference_id(task: ParserTask | ArticleParserTask) -> str:
        return task.batch_id if isinstance(task, ParserTask) else task.reference_id

    def prepare_parser_bundle(self, task: ParserTask | ArticleParserTask) -> Path:
        task_root = self._task_root(self._reference_id(task))
        staging = task_root / ".parser-bundle-staging"
        if staging.exists():
            shutil.rmtree(staging)
        return staging

    def discard_parser_bundle(self, task: ParserTask | ArticleParserTask) -> None:
        staging = self._task_root(self._reference_id(task)) / ".parser-bundle-staging"
        if staging.exists():
            shutil.rmtree(staging)

    def install_parser_bundle(self, task: ParserTask | ArticleParserTask, staging: Path) -> dict[str, Any]:
        from .source_library import SourceLibrary, normalize_short_name

        content = (staging / "content.md").read_text(encoding="utf-8", errors="replace")
        heading = next(
            (match.group(1).strip() for line in content.splitlines() if (match := re.match(r"^#\s+(.+?)\s*$", line))),
            "",
        )
        title = task.title.strip() or heading or task.fallback_title.strip()
        if not title:
            raise WorkspaceError("source_title_missing", "A trustworthy Source Title could not be resolved")
        short_name = task.short_name.strip() if task.short_name else title
        if task.source_kind == "paper_pdf" and "deepstack" in title.casefold():
            short_name = task.short_name.strip() if task.short_name else "DeepStack"
        short_name = normalize_short_name(short_name)
        result = SourceLibrary(self.workspace).register(
            staging,
            source_kind=task.source_kind,
            title=title,
            short_name=short_name,
            identity=task.identity,
            published_at=task.published_at,
            topic_title=task.topic_title,
            topic_id=task.topic_id,
            source_url=task.source_url if isinstance(task, ArticleParserTask) and task.source_url else None,
        )
        shutil.rmtree(self._task_root(self._reference_id(task)), ignore_errors=True)
        return result

    def reuse_source(
        self,
        source_id: str,
        *,
        topic_title: str | None = None,
        topic_id: str | None = None,
        existing_topic_id: str | None = None,
    ) -> str:
        from .source_library import SourceLibrary

        return SourceLibrary(self.workspace).attach(
            source_id,
            topic_title=topic_title,
            topic_id=topic_id,
            existing_topic_id=existing_topic_id,
        )

    def map_reading_plan(
        self,
        source_id: str,
        *,
        draft: dict[str, Any] | None,
        scope: str | None = None,
        reinitialize: bool = False,
    ) -> dict[str, Any]:
        source_id = validate_source_id(source_id)
        source_root = self.workspace / "sources" / source_id
        from .source_library import SourceLibrary

        SourceLibrary(self.workspace).get(source_id)
        bundle = source_root / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {source_id}")
        _validate_parser_bundle(bundle)
        if scope is not None and (not isinstance(scope, str) or not scope.strip()):
            raise WorkspaceError("reading_scope_invalid", "Reading scope is invalid")

        state_path = self.workspace / "state.json"
        state = _read_document(state_path)
        source_states = state.get("sources")
        if not isinstance(source_states, dict) or not isinstance(source_states.get(source_id), dict):
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        source_state = source_states[source_id]
        if (set(source_state) - {"reading_started"}) != {"current_plan_id", "current_chunk_id"}:
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        current_plan_id = source_state.get("current_plan_id")
        current_chunk_id = source_state.get("current_chunk_id")
        if current_plan_id is not None:
            current_plan_id = _identifier(current_plan_id, "reading_plan")
            current_plan_root = source_root / "reading" / "plans" / current_plan_id
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
                    "source_id": source_id,
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

        plans_root = source_root / "reading" / "plans"
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
            source_state["current_plan_id"] = plan_id
            source_state["current_chunk_id"] = records[0]["chunk_id"]
            source_state["reading_started"] = False
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
            "source_id": source_id,
            "plan_id": plan_id,
            "chunk_id": records[0]["chunk_id"],
            "reused": False,
            "reinitialized": reinitialize,
        }

    def _current_reading_selection(
        self, *, require_chunk: bool
    ) -> tuple[Path, dict[str, Any], dict[str, Any], str, str, str | None]:
        state_path, state, source_state, source_id, _ = _current_source_state(self.workspace)
        plan_id = source_state.get("current_plan_id")
        chunk_id = source_state.get("current_chunk_id")
        if plan_id is None:
            raise WorkspaceError("reading_plan_missing", f"Reading Plan does not exist: {source_id}")
        plan_id = _identifier(plan_id, "reading_plan")
        if chunk_id is None:
            if require_chunk:
                raise WorkspaceError("reading_completed", "Reading Plan is complete")
        else:
            chunk_id = _identifier(chunk_id, "reading_chunk")
        return state_path, state, source_state, source_id, plan_id, chunk_id

    def _current_chunk_context(
        self,
    ) -> tuple[Path, dict[str, Any], dict[str, Any], str, str, str, Path, list[dict[str, Any]], int]:
        state_path, state, source_state, source_id, plan_id, chunk_id = self._current_reading_selection(
            require_chunk=True
        )
        assert chunk_id is not None
        plan_root = self.workspace / "sources" / source_id / "reading" / "plans" / plan_id
        chunks = _read_chunk_records(plan_root / "chunks.jsonl")
        matches = [index for index, chunk in enumerate(chunks) if chunk.get("chunk_id") == chunk_id]
        if len(matches) != 1:
            raise WorkspaceError("reading_chunk_missing", f"Reading Chunk does not exist: {chunk_id}")
        return state_path, state, source_state, source_id, plan_id, chunk_id, plan_root, chunks, matches[0]

    def get_reading_state(self) -> dict[str, Any]:
        _, state, _, source_id, plan_id, chunk_id = self._current_reading_selection(require_chunk=False)
        plan_root = self.workspace / "sources" / source_id / "reading" / "plans" / plan_id
        chunks = _read_chunk_records(plan_root / "chunks.jsonl")
        if chunk_id is None:
            return {
                "ok": True,
                "status": "reading_completed",
                "source_id": source_id,
                "topic_id": state.get("current_topic_id"),
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
            "source_id": source_id,
            "topic_id": state.get("current_topic_id"),
            "plan_id": plan_id,
            "chunk_id": chunk_id,
            "index": chunk["index"],
            "total": len(chunks),
            "section_path": chunk["section_path"],
        }

    def get_current_chunk(self) -> dict[str, Any]:
        try:
            _, _, _, source_id, plan_id, chunk_id, plan_root, chunks, index = self._current_chunk_context()
        except WorkspaceError as exc:
            if exc.error_id == "reading_completed":
                return self.get_reading_state()
            raise
        bundle = self.workspace / "sources" / source_id / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {source_id}")
        metadata = _validate_parser_bundle(bundle)
        reading_record = _read_reading_record(plan_root / "records" / f"{chunk_id}.json", chunk_id)
        direct_chinese = metadata["source_kind"] in {"article_html", "article_markdown"} and metadata["language"] == "zh"
        if direct_chinese and reading_record["translation"] is not None:
            raise WorkspaceError("reading_record_invalid", "Chinese source translation must remain null")
        presentation = _chunk_presentation(
            bundle,
            plan_root,
            source_id=source_id,
            plan_id=plan_id,
            chunk=chunks[index],
            reading_record=reading_record,
            total=len(chunks),
        )
        return {
            "ok": True,
            "status": (
                "source_ready"
                if direct_chinese
                else "translation_required" if reading_record["translation"] is None else "presented"
            ),
            **presentation,
        }

    def _cursor_changed(self) -> dict[str, Any]:
        return {**self.get_reading_state(), "status": "cursor_changed"}

    def reading_window(self) -> dict[str, Any]:
        """Read the authoritative window without advancing or loading Notes."""
        from .source_library import SourceLibrary

        state = self.get_reading_state()
        source_id, plan_id = state["source_id"], state["plan_id"]
        bundle = self.workspace / "sources" / source_id / "parser-bundle"
        metadata = _validate_parser_bundle(bundle)
        direct = metadata["source_kind"] in {"article_html", "article_markdown"} and metadata["language"] == "zh"
        root = bundle.parent / "reading" / "plans" / plan_id
        chunks = _read_chunk_records(root / "chunks.jsonl")
        history = []
        current = None
        for chunk in chunks:
            record = _read_reading_record(root / "records" / f'{chunk["chunk_id"]}.json', chunk["chunk_id"])
            if direct and record["translation"] is not None:
                raise WorkspaceError("reading_record_invalid", "Chinese source translation must remain null")
            item = _chunk_presentation(bundle, root, source_id=source_id, plan_id=plan_id,
                                       chunk=chunk, reading_record=record, total=len(chunks))
            item["status"] = "source_ready" if direct else "presented" if record["translation"] else "translation_required"
            if chunk["chunk_id"] == state["chunk_id"]:
                current = item
                break
            history.append(item)
        return {"state": state, "source": SourceLibrary(self.workspace).get(source_id),
                "current": current, "history": history}

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
        _, _, _, source_id, plan_id, chunk_id, plan_root, _, _ = self._current_chunk_context()
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
            "source_id": source_id,
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
        _, _, _, source_id, _, _ = self._current_reading_selection(require_chunk=False)
        plan_id = _identifier(plan_id, "reading_plan")
        chunk_id = _identifier(chunk_id, "reading_chunk")
        if kinds is not None and (not isinstance(kinds, list) or any(kind not in NOTE_KINDS for kind in kinds)):
            raise WorkspaceError("note_kind_invalid", "Note kind is invalid")
        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
            raise WorkspaceError("note_limit_invalid", "Note limit is invalid")
        plan_root = self.workspace / "sources" / source_id / "reading" / "plans" / plan_id
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
            "source_id": source_id,
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
        _, _, _, source_id, plan_id, chunk_id = self._current_reading_selection(require_chunk=False)
        if plan_id != expected_plan_id:
            return self._cursor_changed()
        glossary_path = self.workspace / "sources" / source_id / "reading" / "plans" / plan_id / "glossary.tsv"
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
            "source_id": source_id,
            "plan_id": plan_id,
            "chunk_id": chunk_id,
            "term": {"source": source, "translation": translation},
        }

    def retranslate_current_chunk(
        self, *, expected_plan_id: str, expected_chunk_id: str, translation: str
    ) -> dict[str, Any]:
        if not isinstance(translation, str) or not translation.strip():
            raise WorkspaceError("translation_invalid", "Translation is empty or invalid")
        _, _, _, source_id, plan_id, chunk_id, plan_root, _, _ = self._current_chunk_context()
        if plan_id != expected_plan_id or chunk_id != expected_chunk_id:
            return self._cursor_changed()
        metadata = _validate_parser_bundle(self.workspace / "sources" / source_id / "parser-bundle")
        if metadata["source_kind"] in {"article_html", "article_markdown"} and metadata["language"] == "zh":
            raise WorkspaceError("translation_not_applicable", "Chinese source text is displayed directly")
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
            "source_id": source_id,
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
        state_path, state, source_state, source_id, plan_id, chunk_id, plan_root, chunks, index = self._current_chunk_context()
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
        source_state["current_chunk_id"] = next_chunk_id
        source_state["reading_started"] = True
        topic_advanced = False
        if next_chunk_id is None and state.get("current_topic_id") is not None:
            topic_id = validate_topic_id(state["current_topic_id"])
            next_source_id = self._next_topic_source(topic_id, state, after_source_id=source_id)
            if next_source_id is not None:
                state["current_source_id"] = next_source_id
                topic_advanced = True
        try:
            _write_document(state_path, state)
        except OSError as exc:
            raise WorkspaceError("reading_cursor_write_failed", "Reading Cursor could not be updated") from exc
        if topic_advanced:
            return {**self.get_reading_state(), "status": "topic_source_advanced", "topic_id": state["current_topic_id"]}
        if next_chunk_id is None:
            if state.get("current_topic_id") is not None:
                return {**self.get_reading_state(), "status": "topic_completed", "topic_id": state["current_topic_id"]}
            return self.get_reading_state()
        return {
            **self.get_reading_state(),
            "status": "continued",
        }

    def search_source(self, *, query: str, limit: int = 5) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            raise WorkspaceError("source_query_invalid", "Source query is empty or invalid")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise WorkspaceError("source_query_limit_invalid", "Source query limit is invalid")
        _, _, _, source_id, source_root = _current_source_state(self.workspace)
        bundle = source_root / "parser-bundle"
        _validate_parser_bundle(bundle)
        lines = (bundle / "content.md").read_text(encoding="utf-8", errors="replace").splitlines()
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
            "status": "source_matches_found" if matches else "source_matches_empty",
            "source_id": source_id,
            "query": query,
            "matches": matches,
        }

    def read_source_range(self, *, start: int, end: int, source_id: str | None = None) -> dict[str, Any]:
        if any(not isinstance(value, int) or isinstance(value, bool) for value in (start, end)):
            raise WorkspaceError("source_range_invalid", "Source range is invalid")
        if source_id is None:
            _, _, _, source_id, source_root = _current_source_state(self.workspace)
        else:
            source_id = validate_source_id(source_id)
            source_root = self.workspace / "sources" / source_id
            from .source_library import SourceLibrary

            SourceLibrary(self.workspace).get(source_id)
        bundle = source_root / "parser-bundle"
        _validate_parser_bundle(bundle)
        lines = (bundle / "content.md").read_text(encoding="utf-8", errors="replace").splitlines()
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
            "source_id": source_id,
            "section_path": list(_source_heading_paths(lines)[start - 1]),
            "source_lines": [start, end],
            "source_text": "\n".join(selected),
            "images": _bound_image_presentations(bundle, selected, image_paths),
        }

    def read_topic_range(self, *, topic_id: str, source_id: str, start: int, end: int) -> dict[str, Any]:
        topic = self._topic(topic_id)
        if source_id not in topic["sources"]:
            raise WorkspaceError("topic_source_missing", f"Source is not in Topic {topic_id}: {source_id}")
        return {**self.read_source_range(source_id=source_id, start=start, end=end), "topic_id": topic_id}

    def switch_source(self, source_id: str) -> dict[str, Any]:
        source_id = validate_source_id(source_id)
        source_root = self.workspace / "sources" / source_id
        from .source_library import SourceLibrary

        SourceLibrary(self.workspace).get(source_id)
        bundle = source_root / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {source_id}")
        _validate_parser_bundle(bundle)
        state_path = self.workspace / "state.json"
        state = _read_document(state_path)
        source_states = state.get("sources")
        if not isinstance(source_states, dict) or not isinstance(source_states.get(source_id), dict):
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        source_state = source_states[source_id]
        if (set(source_state) - {"reading_started"}) != {"current_plan_id", "current_chunk_id"}:
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        state["current_source_id"] = source_id
        try:
            _write_document(state_path, state)
        except OSError as exc:
            raise WorkspaceError("workspace_state_write_failed", "Current Reading Source could not be selected") from exc
        return {
            "ok": True,
            "status": "source_selected",
            "source_id": source_id,
            "plan_id": source_state.get("current_plan_id"),
            "chunk_id": source_state.get("current_chunk_id"),
        }

    def _topic(self, topic_id: str) -> dict[str, Any]:
        topic_id = validate_topic_id(topic_id)
        topic = _read_document(self.workspace / "topics" / topic_id / "topic.yaml")
        sources = topic.get("sources")
        if topic.get("topic_id") != topic_id or not isinstance(sources, list) or any(
            not isinstance(source_id, str) for source_id in sources
        ):
            raise WorkspaceError("topic_invalid", f"Topic is invalid: {topic_id}")
        for index, source_id in enumerate(sources, 1):
            try:
                validate_source_id(source_id)
            except WorkspaceError as exc:
                raise WorkspaceError(
                    "topic_source_invalid", f"Topic {topic_id} entry {index} has an invalid Source ID"
                ) from exc
            source_root = self.workspace / "sources" / source_id
            from .source_library import SourceLibrary

            try:
                SourceLibrary(self.workspace).get(source_id)
            except WorkspaceError as exc:
                if exc.error_id == "source_missing":
                    raise WorkspaceError(
                        "topic_source_missing", f"Topic {topic_id} entry {index} is missing: {source_id}"
                    ) from exc
                raise
            _validate_parser_bundle(source_root / "parser-bundle")
        return topic

    def _next_topic_source(
        self, topic_id: str, state: dict[str, Any], *, after_source_id: str | None = None
    ) -> str | None:
        topic = self._topic(topic_id)
        source_states = state.get("sources")
        if not isinstance(source_states, dict):
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        started = after_source_id is None
        found_after = after_source_id is None
        for source_id in topic["sources"]:
            if not started:
                if source_id == after_source_id:
                    started = True
                    found_after = True
                continue
            source_state = source_states.get(source_id)
            if not isinstance(source_state, dict) or (set(source_state) - {"reading_started"}) != {"current_plan_id", "current_chunk_id"}:
                raise WorkspaceError("workspace_state_invalid", f"Workspace state is invalid for Source: {source_id}")
            if source_state["current_plan_id"] is None:
                raise WorkspaceError("reading_plan_missing", f"Topic Source has no Reading Plan: {source_id}")
            if source_state["current_chunk_id"] is not None:
                return source_id
        if not found_after:
            raise WorkspaceError("topic_source_missing", f"Current Source is not in Topic: {after_source_id}")
        return None

    def select_topic(self, topic_id: str) -> dict[str, Any]:
        topic_id = validate_topic_id(topic_id)
        state_path = self.workspace / "state.json"
        state = _read_document(state_path)
        next_source_id = self._next_topic_source(topic_id, state)
        state["current_topic_id"] = topic_id
        if next_source_id is not None:
            state["current_source_id"] = next_source_id
        _write_document(state_path, state)
        if next_source_id is None:
            return {"ok": True, "status": "topic_completed", "topic_id": topic_id, "source_id": None}
        return {**self.get_reading_state(), "status": "topic_selected", "topic_id": topic_id}

    def search_topic(self, *, topic_id: str, query: str, limit: int = 5) -> dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            raise WorkspaceError("source_query_invalid", "Source query is empty or invalid")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
            raise WorkspaceError("source_query_limit_invalid", "Source query limit is invalid")
        topic = self._topic(topic_id)
        terms = [term.casefold() for term in re.findall(r"[\w]+", query) if len(term) > 1]
        terms = terms or [query.strip().casefold()]
        matches: list[dict[str, Any]] = []
        for source_id in topic["sources"]:
            bundle = self.workspace / "sources" / source_id / "parser-bundle"
            lines = (bundle / "content.md").read_text(encoding="utf-8", errors="replace").splitlines()
            paths = _source_heading_paths(lines)
            for index, line in enumerate(lines):
                if not any(term in line.casefold() for term in terms):
                    continue
                start = max(0, index - 1)
                end = min(len(lines), index + 2)
                matches.append(
                    {
                        "source_id": source_id,
                        "section_path": list(paths[index]),
                        "source_lines": [start + 1, end],
                        "snippet": " ".join(part.strip() for part in lines[start:end] if part.strip())[:320],
                    }
                )
                if len(matches) == limit:
                    return {"ok": True, "status": "topic_matches_found", "topic_id": topic_id, "query": query, "matches": matches}
        return {
            "ok": True,
            "status": "topic_matches_found" if matches else "topic_matches_empty",
            "topic_id": topic_id,
            "query": query,
            "matches": matches,
        }

    def topic_notes(self, topic_id: str) -> dict[str, Any]:
        topic = self._topic(topic_id)
        notes: list[dict[str, Any]] = []
        for source_id in topic["sources"]:
            plans_root = self.workspace / "sources" / source_id / "reading" / "plans"
            for plan_root in sorted(plans_root.glob("plan-*")):
                for chunk in _read_chunk_records(plan_root / "chunks.jsonl"):
                    record = _read_reading_record(
                        plan_root / "records" / f'{chunk["chunk_id"]}.json', chunk["chunk_id"]
                    )
                    for note in record["notes"]:
                        if "anchor" in note and note["anchor"].get("source_lines") is not None:
                            notes.append(
                                {
                                    "source_id": source_id,
                                    "plan_id": plan_root.name,
                                    "chunk_id": chunk["chunk_id"],
                                    **note,
                                }
                            )
        return {"ok": True, "status": "topic_notes_listed", "topic_id": topic_id, "notes": notes}

    def _validate_topic_range(self, source_id: str, source_lines: Any) -> tuple[int, int]:
        validate_source_id(source_id)
        if (
            not isinstance(source_lines, list)
            or len(source_lines) != 2
            or any(not isinstance(value, int) or isinstance(value, bool) for value in source_lines)
        ):
            raise WorkspaceError("topic_synthesis_invalid", "Topic Synthesis Source Anchor is invalid")
        start, end = source_lines
        content = self.workspace / "sources" / source_id / "parser-bundle" / "content.md"
        lines = content.read_text(encoding="utf-8", errors="replace").splitlines()
        if start < 1 or end < start or end > len(lines):
            raise WorkspaceError("topic_synthesis_invalid", "Topic Synthesis Source Anchor is invalid")
        return start, end

    def synthesize_topic(self, topic_id: str, draft: dict[str, Any]) -> dict[str, Any]:
        topic_id = validate_topic_id(topic_id)
        topic = self._topic(topic_id)
        topic_sources = set(topic["sources"])
        if not isinstance(draft, dict) or set(draft) != {"selected_ranges", "claims"}:
            raise WorkspaceError("topic_synthesis_invalid", "Topic Synthesis draft is invalid")
        selected_ranges = draft["selected_ranges"]
        claims = draft["claims"]
        if not isinstance(selected_ranges, list) or not isinstance(claims, list) or not claims:
            raise WorkspaceError("topic_synthesis_invalid", "Topic Synthesis draft is invalid")
        allowed: set[tuple[str, int, int]] = set()
        for selected in selected_ranges:
            if not isinstance(selected, dict) or set(selected) != {"source_id", "source_lines"}:
                raise WorkspaceError("topic_synthesis_invalid", "Selected Source range is invalid")
            source_id = selected["source_id"]
            if source_id not in topic_sources:
                raise WorkspaceError("topic_synthesis_invalid", "Selected Source is outside the Topic")
            start, end = self._validate_topic_range(source_id, selected["source_lines"])
            allowed.add((source_id, start, end))
        for note in self.topic_notes(topic_id)["notes"]:
            start, end = note["anchor"]["source_lines"]
            allowed.add((note["source_id"], start, end))

        normalized_claims: list[dict[str, Any]] = []
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {"text", "anchors"}:
                raise WorkspaceError("topic_synthesis_invalid", "Topic Synthesis claim is invalid")
            text = claim["text"]
            anchors = claim["anchors"]
            if not isinstance(text, str) or not text.strip() or not isinstance(anchors, list) or not anchors:
                raise WorkspaceError("topic_synthesis_invalid", "Every claim requires text and Source Anchors")
            normalized_anchors: list[dict[str, Any]] = []
            for anchor in anchors:
                if not isinstance(anchor, dict) or set(anchor) not in (
                    {"source_id", "source_lines"}, {"source_id", "source_lines", "quote"}
                ):
                    raise WorkspaceError("topic_synthesis_invalid", "Topic Synthesis Source Anchor is invalid")
                source_id = anchor["source_id"]
                if source_id not in topic_sources:
                    raise WorkspaceError("topic_synthesis_invalid", "Claim Source is outside the Topic")
                start, end = self._validate_topic_range(source_id, anchor["source_lines"])
                if (source_id, start, end) not in allowed:
                    raise WorkspaceError("topic_synthesis_invalid", "Claim is not grounded in a Reading Note or selected range")
                if "quote" in anchor:
                    quote = anchor["quote"]
                    selected_text = "\n".join(
                        (self.workspace / "sources" / source_id / "parser-bundle" / "content.md")
                        .read_text(encoding="utf-8", errors="replace")
                        .splitlines()[start - 1 : end]
                    )
                    if not isinstance(quote, str) or not quote.strip() or quote not in selected_text:
                        raise WorkspaceError("topic_synthesis_invalid", "Claim quote is not present at its Source Anchor")
                normalized_anchors.append(anchor)
            normalized_claims.append({"text": text.strip(), "anchors": normalized_anchors})

        synthesis_root = self.workspace / "topics" / topic_id / "synthesis"
        used = [
            int(match.group(1))
            for path in synthesis_root.glob("synthesis-*.json")
            if (match := re.fullmatch(r"synthesis-(\d+)\.json", path.name))
        ]
        synthesis_id = f"synthesis-{max(used, default=0) + 1:03d}"
        path = synthesis_root / f"{synthesis_id}.json"
        _write_document(
            path,
            {"topic_id": topic_id, "synthesis_id": synthesis_id, "claims": normalized_claims},
        )
        return {"ok": True, "status": "topic_synthesized", "topic_id": topic_id, "synthesis_id": synthesis_id, "path": str(path)}
