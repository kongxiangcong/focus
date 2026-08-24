#!/usr/bin/env python3
"""Present and cache the current FOCUS Reading Chunk."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import WorkspaceCore, WorkspaceError


def _read_text(path: Path | None, *, error_id: str, label: str) -> str | None:
    if path is None:
        return None
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkspaceError(error_id, f"{label} file is invalid") from exc
    if not value.strip():
        raise WorkspaceError(error_id, f"{label} is empty or invalid")
    return value


def _read_translation(path: Path | None) -> str | None:
    return _read_text(path, error_id="translation_invalid", label="Translation")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    present = subparsers.add_parser("present")
    present.add_argument("--workspace", type=Path, required=True)
    present.add_argument("--translation-file", type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--workspace", type=Path, required=True)
    restore.add_argument("--translation-file", type=Path)
    continuing = subparsers.add_parser("continue")
    continuing.add_argument("--workspace", type=Path, required=True)
    continuing.add_argument("--translation-file", type=Path)
    switching = subparsers.add_parser("switch")
    switching.add_argument("--workspace", type=Path, required=True)
    switching.add_argument("--paper-id", required=True)
    save_note = subparsers.add_parser("save-note")
    save_note.add_argument("--workspace", type=Path, required=True)
    save_note.add_argument("--content-file", type=Path, required=True)
    emphasis = subparsers.add_parser("emphasize")
    emphasis.add_argument("--workspace", type=Path, required=True)
    emphasis.add_argument("--content-file", type=Path, required=True)
    discussion = subparsers.add_parser("record-discussion")
    discussion.add_argument("--workspace", type=Path, required=True)
    discussion.add_argument("--question-file", type=Path, required=True)
    discussion.add_argument("--answer-file", type=Path, required=True)
    correction = subparsers.add_parser("correct-term")
    correction.add_argument("--workspace", type=Path, required=True)
    correction.add_argument("--source", required=True)
    correction.add_argument("--translation", required=True)
    retranslation = subparsers.add_parser("retranslate")
    retranslation.add_argument("--workspace", type=Path, required=True)
    retranslation.add_argument("--translation-file", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        core = WorkspaceCore(args.workspace)
        if args.command in {"present", "restore"}:
            result = core.present_current_chunk(translation=_read_translation(args.translation_file))
        elif args.command == "continue":
            result = core.continue_reading(translation=_read_translation(args.translation_file))
        elif args.command in {"save-note", "emphasize"}:
            result = core.append_current_note(
                kind="reader" if args.command == "save-note" else "emphasis",
                content=_read_text(args.content_file, error_id="note_content_invalid", label="Note"),
            )
        elif args.command == "record-discussion":
            result = core.record_current_discussion(
                question=_read_text(
                    args.question_file,
                    error_id="discussion_question_invalid",
                    label="Discussion question",
                ),
                answer=_read_text(
                    args.answer_file,
                    error_id="discussion_answer_invalid",
                    label="Discussion answer",
                ),
            )
        elif args.command == "correct-term":
            result = core.correct_current_term(source=args.source, translation=args.translation)
        elif args.command == "retranslate":
            result = core.retranslate_current_chunk(
                translation=_read_translation(args.translation_file)
            )
        else:
            result = core.switch_paper(args.paper_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkspaceError, OSError) as exc:
        error_id = exc.error_id if isinstance(exc, WorkspaceError) else "reading_chunk_read_failed"
        print(json.dumps({"ok": False, "error_id": error_id, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
