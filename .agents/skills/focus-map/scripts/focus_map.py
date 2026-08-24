#!/usr/bin/env python3
"""Create or reuse a source-anchored FOCUS Reading Plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import WorkspaceCore, WorkspaceError


def _read_draft(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError("reading_plan_input_invalid", "Reading Plan draft is invalid") from exc
    if not isinstance(value, dict):
        raise WorkspaceError("reading_plan_input_invalid", "Reading Plan draft is invalid")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    mapping = subparsers.add_parser("map")
    mapping.add_argument("--workspace", type=Path, required=True)
    mapping.add_argument("--paper-id", required=True)
    mapping.add_argument("--scope")
    mapping.add_argument("--draft", type=Path)
    mapping.add_argument("--reinitialize", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        core = WorkspaceCore(args.workspace)
        result = core.map_reading_plan(
            args.paper_id,
            draft=_read_draft(args.draft),
            scope=args.scope,
            reinitialize=args.reinitialize,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkspaceError, OSError) as exc:
        error_id = exc.error_id if isinstance(exc, WorkspaceError) else "reading_plan_write_failed"
        print(json.dumps({"ok": False, "error_id": error_id, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
