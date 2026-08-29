#!/usr/bin/env python3
"""Read, search, annotate, and advance the current FOCUS Reading Source."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import WorkspaceCore, WorkspaceError


def _read_text(path: Path, *, error_id: str, label: str) -> str:
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkspaceError(error_id, f"{label} file is invalid") from exc
    if not value.strip():
        raise WorkspaceError(error_id, f"{label} is empty or invalid")
    return value


def _read_json(path: Path, *, error_id: str, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError(error_id, f"{label} file is invalid") from exc


def _read_json_stdin(*, error_id: str, label: str):
    try:
        value = json.loads(sys.stdin.read())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError(error_id, f"{label} input is invalid") from exc
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("state", "current"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)

    continuing = commands.add_parser("continue")
    continuing.add_argument("--workspace", type=Path, required=True)
    continuing.add_argument("--expected-plan-id", required=True)
    continuing.add_argument("--expected-chunk-id", required=True)
    continuing.add_argument("--pending-notes", type=Path)

    note = commands.add_parser("append-note")
    note.add_argument("--workspace", type=Path, required=True)
    note.add_argument("--expected-plan-id", required=True)
    note.add_argument("--expected-chunk-id", required=True)
    note.add_argument("--kind", choices=("thought", "emphasis", "question", "clarification"), required=True)
    note.add_argument("--origin", choices=("user", "dialogue"), required=True)
    note.add_argument("--content-file", type=Path, required=True)
    note.add_argument("--anchor", type=Path)

    notes = commands.add_parser("list-notes")
    notes.add_argument("--workspace", type=Path, required=True)
    notes.add_argument("--plan-id", required=True)
    notes.add_argument("--chunk-id", required=True)
    notes.add_argument("--kinds", nargs="*")
    notes.add_argument("--limit", type=int)

    search = commands.add_parser("search")
    search.add_argument("--workspace", type=Path, required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=5)

    source_range = commands.add_parser("read-range")
    source_range.add_argument("--workspace", type=Path, required=True)
    source_range.add_argument("--start", type=int, required=True)
    source_range.add_argument("--end", type=int, required=True)

    glossary = commands.add_parser("update-glossary")
    glossary.add_argument("--workspace", type=Path, required=True)
    glossary.add_argument("--expected-plan-id", required=True)
    glossary.add_argument("--source", required=True)
    glossary.add_argument("--translation", required=True)

    translation = commands.add_parser("retranslate")
    translation.add_argument("--workspace", type=Path, required=True)
    translation.add_argument("--expected-plan-id", required=True)
    translation.add_argument("--expected-chunk-id", required=True)
    translation.add_argument("--translation-file", type=Path, required=True)

    switching = commands.add_parser("switch")
    switching.add_argument("--workspace", type=Path, required=True)
    switching.add_argument("--source-id", required=True)

    topic = commands.add_parser("topic")
    topic.add_argument("topic_id")
    topic.add_argument("--workspace", type=Path, required=True)

    topic_search = commands.add_parser("topic-search")
    topic_search.add_argument("topic_id")
    topic_search.add_argument("--workspace", type=Path, required=True)
    topic_search.add_argument("--query", required=True)
    topic_search.add_argument("--limit", type=int, default=5)

    topic_range = commands.add_parser("topic-range")
    topic_range.add_argument("topic_id")
    topic_range.add_argument("source_id")
    topic_range.add_argument("--workspace", type=Path, required=True)
    topic_range.add_argument("--start", type=int, required=True)
    topic_range.add_argument("--end", type=int, required=True)

    topic_notes = commands.add_parser("topic-notes")
    topic_notes.add_argument("topic_id")
    topic_notes.add_argument("--workspace", type=Path, required=True)

    synthesis = commands.add_parser("synthesize-topic")
    synthesis.add_argument("topic_id")
    synthesis.add_argument("--workspace", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        core = WorkspaceCore(args.workspace)
        if args.command == "state":
            result = core.get_reading_state()
        elif args.command == "current":
            result = core.get_current_chunk()
        elif args.command == "continue":
            pending_notes = [] if args.pending_notes is None else _read_json(
                args.pending_notes, error_id="note_invalid", label="Pending Notes"
            )
            result = core.continue_reading(
                expected_plan_id=args.expected_plan_id,
                expected_chunk_id=args.expected_chunk_id,
                pending_notes=pending_notes,
            )
        elif args.command == "append-note":
            anchor = None if args.anchor is None else _read_json(
                args.anchor, error_id="note_invalid", label="Note anchor"
            )
            result = core.append_note(
                expected_plan_id=args.expected_plan_id,
                expected_chunk_id=args.expected_chunk_id,
                kind=args.kind,
                origin=args.origin,
                content=_read_text(args.content_file, error_id="note_invalid", label="Note"),
                anchor=anchor,
            )
        elif args.command == "list-notes":
            result = core.list_notes(
                plan_id=args.plan_id,
                chunk_id=args.chunk_id,
                kinds=args.kinds,
                limit=args.limit,
            )
        elif args.command == "search":
            result = core.search_source(query=args.query, limit=args.limit)
        elif args.command == "read-range":
            result = core.read_source_range(start=args.start, end=args.end)
        elif args.command == "update-glossary":
            result = core.update_glossary(
                expected_plan_id=args.expected_plan_id,
                source=args.source,
                translation=args.translation,
            )
        elif args.command == "retranslate":
            result = core.retranslate_current_chunk(
                expected_plan_id=args.expected_plan_id,
                expected_chunk_id=args.expected_chunk_id,
                translation=_read_text(
                    args.translation_file,
                    error_id="translation_invalid",
                    label="Translation",
                ),
            )
        elif args.command == "switch":
            result = core.switch_source(args.source_id)
        elif args.command == "topic":
            result = core.select_topic(args.topic_id)
        elif args.command == "topic-search":
            result = core.search_topic(topic_id=args.topic_id, query=args.query, limit=args.limit)
        elif args.command == "topic-range":
            result = core.read_topic_range(
                topic_id=args.topic_id,
                source_id=args.source_id,
                start=args.start,
                end=args.end,
            )
        elif args.command == "topic-notes":
            result = core.topic_notes(args.topic_id)
        else:
            result = core.synthesize_topic(
                args.topic_id,
                _read_json_stdin(error_id="topic_synthesis_invalid", label="Topic Synthesis"),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkspaceError, OSError) as exc:
        error_id = exc.error_id if isinstance(exc, WorkspaceError) else "reading_workspace_failed"
        print(
            json.dumps({"ok": False, "error_id": error_id, "message": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
