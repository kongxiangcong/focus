#!/usr/bin/env python3
"""Parse a PDF with MinerU's hosted precision API.

Uses only the Python standard library. Credentials are read from MINERU_API_TOKEN
and are never serialized. The normalized bundle is deliberately small while raw
API output remains available for source-fidelity checks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

BASE_URL = "https://mineru.net"
TOKEN_ENV = "MINERU_API_TOKEN"
MAX_SOURCE_BYTES = 200 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_ZIP_BYTES = 500 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".jp2"}
PENDING_STATES = {"waiting-file", "pending", "running", "converting"}


class ParserError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _token() -> str:
    value = os.environ.get(TOKEN_ENV, "").strip()
    if not value:
        raise ParserError(f"{TOKEN_ENV} is not configured")
    return value


def _request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    json_body: dict[str, Any] | None = None,
    body_path: Path | None = None,
    timeout: float = 60.0,
) -> bytes:
    if not url.startswith("https://"):
        raise ParserError("Refusing a non-HTTPS MinerU URL")
    headers = {"Accept": "application/json", "User-Agent": "focus-paper-parser/1"}
    data: bytes | Any | None = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    elif body_path is not None:
        data = body_path.read_bytes()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise ParserError("MinerU response exceeded the safety limit")
            return payload
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise ParserError(f"MinerU HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ParserError(f"MinerU network error: {exc.reason}") from exc


def _json_request(*args: Any, **kwargs: Any) -> dict[str, Any]:
    payload = _request(*args, **kwargs)
    try:
        result = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParserError("MinerU returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise ParserError("MinerU returned a non-object JSON response")
    if result.get("code") != 0:
        raise ParserError(f"MinerU API error: {result.get('msg', 'unknown error')}")
    return result


def _download(url: str, destination: Path) -> None:
    if not url.startswith("https://"):
        raise ParserError("Refusing a non-HTTPS result URL")
    request = urllib.request.Request(url, headers={"User-Agent": "focus-paper-parser/1"})
    try:
        with urllib.request.urlopen(request, timeout=120, context=ssl.create_default_context()) as response:
            final_url = response.geturl()
            if not final_url.startswith("https://"):
                raise ParserError("Result download redirected outside HTTPS")
            total = 0
            with destination.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ZIP_BYTES:
                        raise ParserError("MinerU result ZIP exceeded the safety limit")
                    handle.write(chunk)
    except urllib.error.URLError as exc:
        raise ParserError(f"MinerU result download failed: {exc.reason}") from exc


def _safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ParserError("MinerU archive has too many members")
        expanded = sum(member.file_size for member in members)
        if expanded > MAX_EXPANDED_BYTES:
            raise ParserError("MinerU archive expands beyond the safety limit")
        for member in members:
            posix = PurePosixPath(member.filename.replace("\\", "/"))
            if posix.is_absolute() or ".." in posix.parts:
                raise ParserError(f"Unsafe archive member: {member.filename}")
        bundle.extractall(destination)


def _select_full_markdown(raw_root: Path) -> Path:
    exact = sorted(raw_root.rglob("full.md"), key=lambda p: (len(p.parts), p.as_posix()))
    candidates = exact or sorted(raw_root.rglob("*.md"), key=lambda p: (-p.stat().st_size, p.as_posix()))
    if not candidates or candidates[0].stat().st_size == 0:
        raise ParserError("MinerU ZIP does not contain non-empty Markdown")
    return candidates[0]


def _copy_images(markdown: Path, raw_root: Path, output: Path) -> list[str]:
    image_root = output / "images"
    image_root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    search_root = markdown.parent
    for source in sorted(search_root.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        relative = source.relative_to(search_root)
        if relative.parts and relative.parts[0].lower() == "images":
            relative = Path(*relative.parts[1:])
        if not relative.parts:
            relative = Path(source.name)
        target = image_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append((Path("images") / relative).as_posix())
    return copied


def _normalize(source: Path, archive: Path, output: Path, batch_id: str, model: str, language: str) -> None:
    if output.exists() and any(output.iterdir()):
        raise ParserError(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    raw_root = output / "raw" / "mineru"
    raw_root.mkdir(parents=True)
    _safe_extract(archive, raw_root)
    markdown = _select_full_markdown(raw_root)
    shutil.copy2(source, output / "source.pdf")
    shutil.copy2(markdown, output / "paper.md")
    images = _copy_images(markdown, raw_root, output)
    source_hash = _sha256(source)
    metadata = {
        "schema_version": 1,
        "source_file": source.name,
        "source_sha256": source_hash,
        "parser": "mineru-precision-api",
        "api_version": "v4",
        "model_version": model,
        "language": language,
        "batch_id": batch_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "raw_markdown": markdown.relative_to(raw_root).as_posix(),
        "image_count": len(images),
    }
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    headings = sum(1 for line in (output / "paper.md").read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("#"))
    validation = {
        "schema_version": 1,
        "ok": True,
        "checks": {
            "source_copy_sha256_matches": _sha256(output / "source.pdf") == source_hash,
            "paper_markdown_nonempty": (output / "paper.md").stat().st_size > 0,
            "metadata_parseable": True,
            "raw_output_preserved": any(raw_root.rglob("*")),
        },
        "inventory": {"headings": headings, "images": len(images)},
        "warnings": ["Semantic reading order and central figures, tables, and equations still require source spot checks."],
    }
    validation["ok"] = all(validation["checks"].values())
    (output / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _poll(batch_id: str, token: str, deadline: float, interval: float) -> dict[str, Any]:
    url = f"{BASE_URL}/api/v4/extract-results/batch/{batch_id}"
    while True:
        result = _json_request("GET", url, token=token)
        entries = result.get("data", {}).get("extract_result", [])
        if not isinstance(entries, list) or not entries:
            state = "pending"
            entry: dict[str, Any] = {}
        else:
            entry = entries[0]
            state = str(entry.get("state", "pending"))
        if state == "done":
            return entry
        if state == "failed":
            raise ParserError(f"MinerU parsing failed: {entry.get('err_msg', 'unknown error')}")
        if state not in PENDING_STATES:
            raise ParserError(f"MinerU returned unknown task state: {state}")
        if time.monotonic() >= deadline:
            raise ParserError(f"Polling timed out; resume with batch_id {batch_id}")
        time.sleep(interval)


def _complete(source: Path, output: Path, batch_id: str, model: str, language: str, timeout: float, interval: float) -> None:
    token = _token()
    entry = _poll(batch_id, token, time.monotonic() + timeout, interval)
    result_url = entry.get("full_zip_url")
    if not isinstance(result_url, str) or not result_url:
        raise ParserError("Completed MinerU task has no full_zip_url")
    with tempfile.TemporaryDirectory(prefix="focus-mineru-") as temp_dir:
        archive = Path(temp_dir) / "result.zip"
        _download(result_url, archive)
        if not zipfile.is_zipfile(archive):
            raise ParserError("MinerU result is not a ZIP archive")
        _normalize(source, archive, output, batch_id, model, language)


def _parse(args: argparse.Namespace) -> None:
    source = args.source.resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ParserError("Source must be an existing PDF file")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ParserError("Source exceeds MinerU's 200 MB precision-API limit")
    token = _token()
    data_id = f"focus-{_sha256(source)[:16]}-{uuid.uuid4().hex[:8]}"
    payload = {
        "files": [{"name": source.name, "data_id": data_id, "is_ocr": args.ocr}],
        "model_version": args.model,
        "enable_formula": True,
        "enable_table": True,
        "language": args.language,
    }
    result = _json_request("POST", f"{BASE_URL}/api/v4/file-urls/batch", token=token, json_body=payload)
    data = result.get("data", {})
    batch_id = data.get("batch_id")
    urls = data.get("file_urls")
    if not isinstance(batch_id, str) or not isinstance(urls, list) or len(urls) != 1:
        raise ParserError("MinerU upload-link response is incomplete")
    _request("PUT", urls[0], body_path=source, timeout=300)
    print(json.dumps({"status": "uploaded", "batch_id": batch_id}, ensure_ascii=False), flush=True)
    _complete(source, args.output.resolve(), batch_id, args.model, args.language, args.timeout, args.poll_interval)
    print(json.dumps({"status": "done", "batch_id": batch_id, "output": str(args.output.resolve())}, ensure_ascii=False))


def _resume(args: argparse.Namespace) -> None:
    source = args.source.resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ParserError("Source must be an existing PDF file")
    _complete(source, args.output.resolve(), args.batch_id, args.model, args.language, args.timeout, args.poll_interval)
    print(json.dumps({"status": "done", "batch_id": args.batch_id, "output": str(args.output.resolve())}, ensure_ascii=False))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--output", type=Path, required=True)
    common.add_argument("--model", choices=("vlm", "pipeline"), default="vlm")
    common.add_argument("--language", default="en")
    common.add_argument("--timeout", type=float, default=1800.0)
    common.add_argument("--poll-interval", type=float, default=5.0)
    parse = subparsers.add_parser("parse", parents=[common])
    parse.add_argument("source", type=Path)
    parse.add_argument("--ocr", action="store_true")
    parse.set_defaults(func=_parse)
    resume = subparsers.add_parser("resume", parents=[common])
    resume.add_argument("batch_id")
    resume.add_argument("--source", type=Path, required=True)
    resume.set_defaults(func=_resume)
    return parser


def main() -> int:
    try:
        args = _build_parser().parse_args()
        args.func(args)
        return 0
    except (ParserError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
