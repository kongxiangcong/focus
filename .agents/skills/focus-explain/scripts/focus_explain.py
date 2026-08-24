#!/usr/bin/env python3
"""Persist and resume private FOCUS Explanation Sessions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import ExplanationWorkspaceCore, WorkspaceError


def _read_content(path: Path, *, error_id: str, label: str) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkspaceError(error_id, f"{label} file is invalid") from exc
    if not content.strip():
        raise WorkspaceError(error_id, f"{label} is empty or invalid")
    return content


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    new = subparsers.add_parser("new")
    new.add_argument("--workspace", type=Path, required=True)
    new.add_argument("--question-file", type=Path, required=True)
    answer = subparsers.add_parser("answer")
    answer.add_argument("--workspace", type=Path, required=True)
    answer.add_argument("--answer-file", type=Path, required=True)
    asking = subparsers.add_parser("ask")
    asking.add_argument("--workspace", type=Path, required=True)
    asking.add_argument("--question-file", type=Path, required=True)
    continuing = subparsers.add_parser("continue")
    continuing.add_argument("--workspace", type=Path, required=True)
    continuing.add_argument("--content-file", type=Path, required=True)
    selecting = subparsers.add_parser("select")
    selecting.add_argument("--workspace", type=Path, required=True)
    selecting.add_argument("--explanation-id", required=True)
    resume = subparsers.add_parser("resume")
    resume.add_argument("--workspace", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        core = ExplanationWorkspaceCore(args.workspace)
        if args.command == "new":
            result = core.new_explanation(
                question=_read_content(
                    args.question_file,
                    error_id="explanation_question_invalid",
                    label="Explanation question",
                )
            )
        elif args.command == "answer":
            result = core.append_answer(
                answer=_read_content(
                    args.answer_file,
                    error_id="explanation_answer_invalid",
                    label="Explanation answer",
                )
            )
        elif args.command in {"ask", "continue"}:
            content_file = args.question_file if args.command == "ask" else args.content_file
            result = core.append_question(
                question=_read_content(
                    content_file,
                    error_id="explanation_question_invalid",
                    label="Explanation continuation",
                )
            )
        elif args.command == "select":
            result = core.select_explanation(args.explanation_id)
        else:
            result = core.resume_explanation()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkspaceError, OSError) as exc:
        error_id = exc.error_id if isinstance(exc, WorkspaceError) else "explanation_read_failed"
        print(
            json.dumps({"ok": False, "error_id": error_id, "message": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
