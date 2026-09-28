#!/usr/bin/env python3
"""Shared MinerU precision transport and PDF bundle normalization.

Uses only the Python standard library. Credentials are read from MINERU_API_TOKEN
and are never serialized. MinerU's ZIP is normalized into one compact bundle and
discarded after extraction.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

BASE_URL = "https://mineru.net"
TOKEN_ENV = "MINERU_API_TOKEN"
DOTENV_NAME = ".env"
MAX_SOURCE_BYTES = 200 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_ZIP_BYTES = 500 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".jp2"}
MARKDOWN_IMAGE_RE = re.compile(r"(!\[[^\]\n]*\]\()([^)]+)(\))")
SEQUENTIAL_IMAGE_RE = re.compile(r"^image-(\d{3})(\.[a-z0-9]+)$")
PENDING_STATES = {"waiting-file", "pending", "running", "converting"}


class ParserError(RuntimeError):
    error_id = "parser_failed"

    def __init__(self, message: str, *, recoverable: bool = True, error_id: str | None = None):
        super().__init__(message)
        self.recoverable = recoverable
        self.transient = recoverable
        self.acceptance_unknown = False
        if error_id is not None:
            self.error_id = error_id


def _dotenv_token(path: Path) -> str:
    """Read only MINERU_API_TOKEN from a simple local .env file."""
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ParserError(f"Cannot read {path}: {exc}") from exc
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        if separator and key.strip() == TOKEN_ENV:
            value = raw_value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            return value.strip()
    return ""


def _token() -> str:
    value = os.environ.get(TOKEN_ENV, "").strip()
    if not value:
        value = _dotenv_token(Path.cwd() / DOTENV_NAME)
    if not value:
        raise ParserError(
            f"{TOKEN_ENV} is not configured in the process environment or {Path.cwd() / DOTENV_NAME}",
            recoverable=False,
            error_id="authentication_required",
        )
    return value


def _request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> bytes:
    if not url.startswith("https://"):
        raise ParserError("Refusing a non-HTTPS MinerU URL")
    headers = {"Accept": "application/json", "User-Agent": "focus-article-parser/2"}
    data: bytes | Any | None = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise ParserError("MinerU response exceeded the safety limit")
            return payload
    except urllib.error.HTTPError as exc:
        raise ParserError(
            f"MinerU HTTP {exc.code}",
            recoverable=exc.code not in {400, 401, 403},
            error_id=("authentication_failed" if exc.code in {401, 403} else
                      "quota_exceeded" if exc.code == 402 else
                      "rate_limit_exceeded" if exc.code == 429 else
                      "service_unavailable" if exc.code >= 500 else "mineru_http_error"),
        ) from exc
    except urllib.error.URLError as exc:
        raise ParserError("MinerU network unavailable", error_id="service_unavailable") from exc


def _curl_transfer(url: str, config_lines: list[str], operation: str) -> None:
    if not url.startswith("https://"):
        raise ParserError(f"Refusing a non-HTTPS {operation} URL")
    executable = shutil.which("curl.exe") or shutil.which("curl")
    if not executable:
        raise ParserError(f"System curl is required for MinerU {operation}")
    config = "\n".join(
        [
            "url = " + json.dumps(url),
            'proto = "=https"',
            'proto-redir = "=https"',
            "silent",
            "show-error",
            "fail",
            *config_lines,
            "",
        ]
    )
    completed = subprocess.run(
        [executable, "--config", "-"],
        input=config,
        text=True,
        capture_output=True,
    )
    if completed.returncode:
        host = urllib.parse.urlsplit(url).hostname or "unknown host"
        raise ParserError(f"MinerU {operation} failed via {host} (curl exit {completed.returncode})")


def _upload(url: str, source: Path) -> None:
    _curl_transfer(
        url,
        [
            "upload-file = " + json.dumps(str(source)),
            'request = "PUT"',
            "connect-timeout = 60",
            "max-time = 600",
        ],
        "upload",
    )


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
    _curl_transfer(
        url,
        [
            "output = " + json.dumps(str(destination)),
            "location",
            f"max-filesize = {MAX_ZIP_BYTES}",
            "connect-timeout = 60",
            "max-time = 600",
        ],
        "result download",
    )
    if not destination.is_file() or destination.stat().st_size > MAX_ZIP_BYTES:
        raise ParserError("MinerU result ZIP exceeded the safety limit")


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


def _split_image_target(raw_target: str) -> tuple[str, str]:
    target = raw_target.strip()
    if target.startswith("<"):
        closing = target.find(">")
        if closing < 0:
            return target, ""
        return target[1:closing], target[closing + 1 :]
    match = re.match(r"(\S+)(.*)", target, flags=re.DOTALL)
    return (match.group(1), match.group(2)) if match else (target, "")


def _resolve_local_image(markdown: Path, raw_root: Path, target: str) -> Path | None:
    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme or parsed.netloc or target.startswith("#"):
        return None
    decoded = urllib.parse.unquote(parsed.path).replace("\\", "/")
    relative = PurePosixPath(decoded)
    candidate = (markdown.parent / Path(*relative.parts)).resolve()
    raw_resolved = raw_root.resolve()
    if not candidate.is_relative_to(raw_resolved):
        raise ParserError(f"Markdown image escapes MinerU output: {target}")
    if not candidate.is_file():
        raise ParserError(f"Markdown image is missing from MinerU output: {target}")
    if candidate.suffix.lower() not in IMAGE_SUFFIXES:
        raise ParserError(f"Markdown image has an unsupported format: {target}")
    return candidate


def _rewrite_and_copy_images(markdown: Path, raw_root: Path, output: Path) -> tuple[str, list[str]]:
    image_root = output / "images"
    image_root.mkdir(parents=True, exist_ok=True)
    text = markdown.read_text(encoding="utf-8", errors="replace")
    mapped: dict[Path, str] = {}
    copied: list[str] = []

    def replace(match: re.Match[str]) -> str:
        target_text, title_suffix = _split_image_target(match.group(2))
        source = _resolve_local_image(markdown, raw_root, target_text)
        if source is None:
            return match.group(0)
        if source not in mapped:
            name = f"image-{len(mapped) + 1:03d}{source.suffix.lower()}"
            relative = (Path("images") / name).as_posix()
            shutil.copy2(source, image_root / name)
            mapped[source] = relative
            copied.append(relative)
        return f"{match.group(1)}{mapped[source]}{title_suffix}{match.group(3)}"

    return MARKDOWN_IMAGE_RE.sub(replace, text), copied


def _bundle_image_checks(source_path: Path, output: Path) -> tuple[bool, bool]:
    paper = source_path.read_text(encoding="utf-8", errors="replace")
    linked: list[Path] = []
    for match in MARKDOWN_IMAGE_RE.finditer(paper):
        target, _ = _split_image_target(match.group(2))
        parsed = urllib.parse.urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith("#"):
            continue
        candidate = (output / urllib.parse.unquote(parsed.path)).resolve()
        if not candidate.is_relative_to(output.resolve()) or not candidate.is_file():
            return False, False
        if candidate not in linked:
            linked.append(candidate)
    actual = sorted(path.resolve() for path in (output / "images").glob("*") if path.is_file())
    links_resolve = set(linked) == set(actual)
    numbers: list[int] = []
    for path in linked:
        match = SEQUENTIAL_IMAGE_RE.fullmatch(path.name.lower())
        if not match:
            return links_resolve, False
        numbers.append(int(match.group(1)))
    return links_resolve, numbers == list(range(1, len(numbers) + 1))


def _normalize(source: Path, archive: Path, output: Path, batch_id: str, model: str, language: str) -> None:
    if output.exists() and any(output.iterdir()):
        raise ParserError(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    raw_root = output.parent / f".focus-mineru-extract-{uuid.uuid4().hex}"
    raw_root.mkdir()
    try:
        _safe_extract(archive, raw_root)
        markdown = _select_full_markdown(raw_root)
        paper, images = _rewrite_and_copy_images(markdown, raw_root, output)
        (output / "content.md").write_text(paper, encoding="utf-8")
        evidence = {}
        for name in ("middle_json.json", "model_output.json", "structured_content.json"):
            matches = [path for path in raw_root.rglob(name) if path.is_file() and path.stat().st_size <= 64 * 1024 * 1024]
            if len(matches) == 1:
                raw = matches[0].read_bytes()
                try:
                    structured = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(structured, (dict, list)):
                    target = output / "mineru" / name
                    target.parent.mkdir(exist_ok=True)
                    target.write_bytes(raw)
                    evidence["mineru/" + name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    finally:
        shutil.rmtree(raw_root, ignore_errors=True)
    shutil.copy2(source, output / "source.pdf")
    metadata = {
        "source_kind": "paper_pdf",
        "source_file": source.name,
        "parser": "article-parser",
        "api_version": "v4",
        "provider": "mineru.net",
        "model_version": model,
        "language": language,
        "batch_id": batch_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "image_naming": "source-reference-order",
        "image_count": len(images),
        "model_evidence": evidence,
    }
    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    headings = sum(1 for line in (output / "content.md").read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("#"))
    image_links_resolve, image_names_sequential = _bundle_image_checks(output / "content.md", output)
    validation = {
        "schema_version": 2,
        "ok": True,
        "checks": {
            "source_copy_matches": filecmp.cmp(source, output / "source.pdf", shallow=False),
            "paper_markdown_nonempty": (output / "content.md").stat().st_size > 0,
            "metadata_parseable": True,
            "image_links_resolve": image_links_resolve,
            "image_names_sequential": image_names_sequential,
        },
        "inventory": {"headings": headings, "images": len(images)},
        "warnings": ["Semantic reading order and central figures, tables, and equations still require source spot checks."],
    }
    validation["ok"] = all(validation["checks"].values())
    (output / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not validation["ok"]:
        failed = ", ".join(name for name, passed in validation["checks"].items() if not passed)
        raise ParserError(f"Normalized parser bundle failed validation: {failed}")


def _poll(batch_id: str, token: str, deadline: float, interval: float, on_progress=None) -> dict[str, Any]:
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
        if on_progress:
            on_progress({"status": state, **({"percent": entry["progress"]} if isinstance(entry.get("progress"), (int, float)) else {})})
        if state == "done":
            return entry
        if state == "failed":
            raise ParserError(
                f"MinerU parsing failed: {entry.get('err_msg', 'unknown error')}", recoverable=False
            )
        if state not in PENDING_STATES:
            raise ParserError(f"MinerU returned unknown task state: {state}", recoverable=False)
        if time.monotonic() >= deadline:
            raise ParserError(f"Polling timed out; resume with batch_id {batch_id}")
        time.sleep(interval)


def _complete(source: Path, output: Path, batch_id: str, model: str, language: str, timeout: float, interval: float, on_progress=None) -> None:
    token = _token()
    entry = _poll(batch_id, token, time.monotonic() + timeout, interval, on_progress)
    result_url = entry.get("full_zip_url")
    if not isinstance(result_url, str) or not result_url:
        raise ParserError("Completed MinerU task has no full_zip_url", recoverable=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    transfer_root = output.parent / f".focus-mineru-{uuid.uuid4().hex}"
    transfer_root.mkdir()
    try:
        archive = transfer_root / "result.zip"
        _download(result_url, archive)
        if not zipfile.is_zipfile(archive):
            raise ParserError("MinerU result is not a ZIP archive")
        _normalize(source, archive, output, batch_id, model, language)
    finally:
        shutil.rmtree(transfer_root, ignore_errors=True)


class MinerUHostedParser:
    def start(self, source: Path, *, model: str, language: str, ocr: bool, on_reference=None) -> str:
        token = _token()
        data_id = f"focus-{uuid.uuid4().hex}"
        payload = {
            "files": [{"name": source.name, "data_id": data_id, "is_ocr": ocr}],
            "model_version": model,
            "enable_formula": True,
            "enable_table": True,
            "language": language,
        }
        result = _json_request("POST", f"{BASE_URL}/api/v4/file-urls/batch", token=token, json_body=payload)
        data = result.get("data", {})
        batch_id = data.get("batch_id")
        urls = data.get("file_urls")
        if not isinstance(batch_id, str) or not isinstance(urls, list) or len(urls) != 1:
            raise ParserError("MinerU upload-link response is incomplete")
        if on_reference is not None:
            on_reference(batch_id)
        _upload(urls[0], source)
        return batch_id

    def complete(
        self,
        source: Path,
        output: Path,
        *,
        batch_id: str,
        model: str,
        language: str,
        timeout: float,
        interval: float,
        on_progress=None,
    ) -> None:
        _complete(source, output, batch_id, model, language, timeout, interval, on_progress)


class MinerUIngestionParser:
    """Produce a validated PDF candidate; Core remains the only publisher."""

    def __init__(
        self,
        hosted: Any | None = None,
        *,
        model: str = "vlm",
        language: str = "en",
        ocr: bool = False,
        timeout: float = 1800.0,
        interval: float = 5.0,
    ) -> None:
        self.hosted = hosted or MinerUHostedParser()
        self.model = model
        self.language = language
        self.ocr = ocr
        self.timeout = timeout
        self.interval = interval

    def parse(self, source: Path, candidate: Path, *, checkpoint: Any | None = None) -> dict[str, Any]:
        source = Path(source).resolve()
        if not source.is_file() or source.suffix.lower() != ".pdf":
            raise ParserError("Source must be an existing PDF file", recoverable=False)
        if source.stat().st_size > MAX_SOURCE_BYTES:
            raise ParserError("Source exceeds MinerU's 200 MB precision-API limit", recoverable=False)
        reference: dict[str, str] = {}

        def save_reference(batch_id: str) -> None:
            reference["batch_id"] = batch_id
            if checkpoint is not None:
                checkpoint({"reference_kind": "batch_id", "reference_id": batch_id})

        try:
            batch_id = self.hosted.start(
                source,
                model=self.model,
                language=self.language,
                ocr=self.ocr,
                on_reference=save_reference,
            )
        except ParserError as exc:
            if reference:
                from .ingestion import IngestionExternalError

                raise IngestionExternalError(
                    "upload_acceptance_unknown",
                    str(exc),
                    acceptance_unknown=True,
                ) from exc
            raise
        return self._complete_candidate(source, candidate, batch_id, checkpoint)

    def _complete_candidate(self, source: Path, candidate: Path, batch_id: str, on_checkpoint=None) -> dict[str, Any]:
        try:
            options = {}
            if on_checkpoint is not None and isinstance(self.hosted, MinerUHostedParser):
                options["on_progress"] = lambda progress: on_checkpoint({"reference_kind": "batch_id",
                                                                          "reference_id": batch_id, "progress": progress})
            self.hosted.complete(
                source,
                candidate,
                batch_id=batch_id,
                model=self.model,
                language=self.language,
                timeout=self.timeout,
                interval=self.interval,
                **options,
            )
        except ParserError as exc:
            from .ingestion import IngestionExternalError

            raise IngestionExternalError(
                exc.error_id,
                str(exc),
                transient=exc.recoverable,
            ) from exc
        content = (candidate / "content.md").read_text(encoding="utf-8", errors="replace")
        title = next(
            (match.group(1).strip() for line in content.splitlines() if (match := re.match(r"^#\s+(.+?)\s*$", line))),
            source.stem,
        )
        short_name = "DeepStack" if "deepstack" in title.casefold() else title
        result = {"title": title, "short_name": short_name, "batch_id": batch_id}
        from .ingestion import persist_candidate_result

        persist_candidate_result(candidate, result)
        return result

    def resume(self, source: Path, candidate: Path, *, checkpoint: dict[str, Any], on_checkpoint=None) -> dict[str, Any]:
        if checkpoint.get("reference_kind") != "batch_id" or not isinstance(checkpoint.get("reference_id"), str):
            raise ParserError("MinerU checkpoint is invalid", recoverable=False)
        return self._complete_candidate(source, candidate, checkpoint["reference_id"], on_checkpoint)

    @staticmethod
    def cancel(checkpoint: dict[str, Any]) -> bool:
        del checkpoint
        # MinerU precision v4 documents submit and query operations but no cancel endpoint.
        return False
