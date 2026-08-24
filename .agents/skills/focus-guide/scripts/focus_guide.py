#!/usr/bin/env python3
"""Present and cache the current FOCUS Reading Chunk."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import WorkspaceCore, WorkspaceError


def _read_translation(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise WorkspaceError("translation_invalid", "Translation file is invalid") from exc
    if not value.strip():
        raise WorkspaceError("translation_invalid", "Translation is empty or invalid")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    present = subparsers.add_parser("present")
    present.add_argument("--workspace", type=Path, required=True)
    present.add_argument("--translation-file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        core = WorkspaceCore(args.workspace)
        result = core.present_current_chunk(translation=_read_translation(args.translation_file))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkspaceError, OSError) as exc:
        error_id = exc.error_id if isinstance(exc, WorkspaceError) else "reading_chunk_read_failed"
        print(json.dumps({"ok": False, "error_id": error_id, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
