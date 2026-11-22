"""Atomic file writes shared by Workspace data and Parser Bundle publication."""
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .workspace_lifecycle import require_write


def write_document(path: Path, value: dict[str, Any]) -> None:
    require_write(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for attempt in range(5):
            try:
                temporary.replace(path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02)
    finally:
        temporary.unlink(missing_ok=True)


def replace_text(path: Path, value: str, *, newline: str | None = None) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8", newline=newline)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
