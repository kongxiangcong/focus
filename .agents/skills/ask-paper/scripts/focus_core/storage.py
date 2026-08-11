from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from .errors import FocusError


WORKSPACE_SCHEMA = 1
PAPER_SCHEMA = 2
ROUTE_SCHEMA = 1
EVIDENCE_SCHEMA = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def load_yaml(path: Path, *, code: str = "INVALID_YAML") -> dict[str, Any]:
    if not path.is_file():
        raise FocusError("FILE_NOT_FOUND", f"Required file does not exist: {path}", path=str(path))
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise FocusError(code, f"Cannot read YAML file: {path}", path=str(path), cause=str(exc)) from exc
    if not isinstance(value, dict):
        raise FocusError(code, f"YAML root must be a mapping: {path}", path=str(path))
    return value


def load_json_or_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FocusError("EVENT_FILE_NOT_FOUND", f"Event file does not exist: {path}", path=str(path))
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise FocusError("INVALID_EVENT_FILE", f"Cannot parse event file: {path}", path=str(path), cause=str(exc)) from exc
    if not isinstance(value, dict):
        raise FocusError("INVALID_EVENT_FILE", "Event root must be an object", path=str(path))
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def atomic_write_yaml(path: Path, value: dict[str, Any], *, sort_keys: bool = False) -> None:
    text = yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=sort_keys,
        default_flow_style=False,
        width=100,
    )
    atomic_write_text(path, text)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("row is not an object")
                rows.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise FocusError(
            "INVALID_JSONL",
            f"Cannot parse JSONL ledger: {path}",
            path=str(path),
            line=line_number if "line_number" in locals() else None,
            cause=str(exc),
        ) from exc
    return rows


def append_jsonl_rows(path: Path, rows: Iterable[dict[str, Any]], *, id_field: str) -> int:
    existing = read_jsonl(path)
    existing_ids = {str(row.get(id_field)) for row in existing if row.get(id_field) is not None}
    pending = [row for row in rows if str(row.get(id_field)) not in existing_ids]
    if not pending:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in pending:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return len(pending)


def sha256_file(path: Path) -> str:
    if not path.is_file():
        raise FocusError("SOURCE_NOT_FOUND", f"Source file does not exist: {path}", path=str(path))
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_value(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def require_within(path: Path, root: Path, *, code: str = "PATH_ESCAPE") -> Path:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if not is_relative_to(resolved, resolved_root):
        raise FocusError(code, f"Path escapes the authorized root: {path}", path=str(path), root=str(root))
    return resolved


def resolve_relative(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    candidate = require_within(root / relative, root)
    if must_exist and not candidate.exists():
        raise FocusError("ARTIFACT_NOT_FOUND", f"Artifact does not exist: {relative}", artifact=relative)
    return candidate


def portable_relative(path: Path, root: Path) -> str:
    resolved = require_within(path, root)
    return resolved.relative_to(root.resolve()).as_posix()


def safe_slug(value: str, *, fallback: str = "paper", limit: int = 80) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return (slug or fallback)[:limit].rstrip("-")


def safe_directory_name(value: str, *, fallback: str = "paper", limit: int = 120) -> str:
    cleaned = unicodedata.normalize("NFKC", value)
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
    return (cleaned or fallback)[:limit].rstrip(" .")


def validate_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise FocusError("INVALID_IDENTIFIER", f"Invalid {field}", field=field, value=value)
    return value


def ensure_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise FocusError("INVALID_CONTRACT", f"{field} must be a list", field=field)
    return value


def ensure_nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FocusError("INVALID_CONTRACT", f"{field} must be non-empty text", field=field)
    return value.strip()


def workspace_paths(workspace: Path) -> dict[str, Path]:
    return {
        "marker": workspace / "workspace.yaml",
        "registry": workspace / "reading-registry.yaml",
        "control": workspace / ".paper-companion",
        "locks": workspace / ".paper-companion" / "locks",
        "routes": workspace / ".paper-companion" / "routes",
        "runs": workspace / ".paper-companion" / "runs",
        "migrations": workspace / ".paper-companion" / "migrations",
        "transactions": workspace / ".paper-companion" / "transactions",
        "profile_dir": workspace / "cognitive-profile",
        "profile": workspace / "cognitive-profile" / "profile.yaml",
        "profile_evidence": workspace / "cognitive-profile" / "evidence.jsonl",
        "profile_history": workspace / "cognitive-profile" / "history",
        "corpus": workspace / "research-corpus",
    }


def route_path(workspace: Path, route_id: str) -> Path:
    validate_identifier(route_id, "route_id")
    return workspace_paths(workspace)["routes"] / f"{route_id}.yaml"


def lock_path(workspace: Path, lock_key: str) -> Path:
    validate_identifier(lock_key, "lock_key")
    return workspace_paths(workspace)["locks"] / f"{lock_key}.lock"


def acquire_lock(workspace: Path, lock_key: str, route_id: str) -> Path:
    path = lock_path(workspace, lock_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "lock_key": lock_key,
        "owner_route_id": route_id,
        "acquired_at": now_iso(),
    }
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        owner = load_yaml(path, code="INVALID_LOCK") if path.is_file() else {}
        raise FocusError(
            "LOCK_HELD",
            "Another routed execution holds this paper or input lock",
            lock_key=lock_key,
            owner_route_id=owner.get("owner_route_id"),
        ) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))
        handle.flush()
        os.fsync(handle.fileno())
    return path


def require_lock_owner(workspace: Path, lock_key: str, route_id: str) -> None:
    path = lock_path(workspace, lock_key)
    lock = load_yaml(path, code="INVALID_LOCK")
    if lock.get("owner_route_id") != route_id:
        raise FocusError(
            "LOCK_OWNER_MISMATCH",
            "Route does not own the required lock",
            route_id=route_id,
            owner_route_id=lock.get("owner_route_id"),
        )


def release_lock(workspace: Path, lock_key: str, route_id: str) -> None:
    path = lock_path(workspace, lock_key)
    if not path.exists():
        return
    require_lock_owner(workspace, lock_key, route_id)
    path.unlink()

