#!/usr/bin/env python3
"""Parse a Chinese HTML article with MinerU-HTML into one Parser Bundle."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import urllib.parse
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "paper-parser" / "scripts"))

from core import ArticleParserTask, WorkspaceCore, WorkspaceError, validate_topic_id
from mineru_precision import (
    BASE_URL,
    ParserError,
    _bundle_image_checks,
    _download,
    _json_request,
    _rewrite_and_copy_images,
    _safe_extract,
    _select_full_markdown,
    _token,
    _upload,
)


PENDING_STATES = {"pending", "running", "converting", "waiting-file"}


class ArticleParserError(ParserError):
    def __init__(
        self,
        message: str,
        error_id: str = "article_parser_failed",
        *,
        recoverable: bool = True,
    ):
        super().__init__(message)
        self.error_id = error_id
        self.recoverable = recoverable


def _article_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ArticleParserError("Article URL must use HTTP or HTTPS", "source_url_invalid")
    return value


def _validate_registration(title: str, topic: str, topic_id: str | None) -> None:
    if not title.strip():
        raise WorkspaceError("source_title_invalid", "Reading Source title is empty or invalid")
    if not topic.strip():
        raise WorkspaceError("topic_invalid", "Topic title is empty or invalid")
    if topic_id is not None:
        validate_topic_id(topic_id)


def _select_main_html(raw_root: Path) -> Path:
    candidates = sorted(raw_root.rglob("main.html"), key=lambda path: (len(path.parts), path.as_posix()))
    selected = next((path for path in candidates if path.is_file() and path.stat().st_size), None)
    if selected is None:
        raise ArticleParserError("MinerU ZIP does not contain non-empty main.html")
    return selected


def _normalize(
    archive: Path,
    output: Path,
    *,
    reference_kind: str,
    reference_id: str,
    source_url: str,
) -> None:
    if output.exists() and any(output.iterdir()):
        raise ArticleParserError(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    raw_root = output.parent / f".focus-mineru-html-extract-{uuid.uuid4().hex}"
    raw_root.mkdir()
    try:
        _safe_extract(archive, raw_root)
        markdown_path = _select_full_markdown(raw_root)
        html_path = _select_main_html(raw_root)
        content, images = _rewrite_and_copy_images(markdown_path, raw_root, output)
        (output / "content.md").write_text(content, encoding="utf-8")
        shutil.copy2(html_path, output / "source.html")
    finally:
        shutil.rmtree(raw_root, ignore_errors=True)

    metadata = {
        "source_kind": "article_html",
        "language": "zh",
        "parser": "article-parser",
        "model_version": "MinerU-HTML",
        reference_kind: reference_id,
        "image_count": len(images),
    }
    if source_url:
        metadata["source_url"] = source_url
    (output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    links_resolve, names_sequential = _bundle_image_checks(output / "content.md", output)
    checks = {
        "source_html_nonempty": (output / "source.html").stat().st_size > 0,
        "content_markdown_nonempty": (output / "content.md").stat().st_size > 0,
        "metadata_parseable": True,
        "image_links_resolve": links_resolve,
        "image_names_sequential": names_sequential,
    }
    validation = {
        "ok": all(checks.values()),
        "checks": checks,
        "warnings": ["Source order, embedded media, and article boundaries still require a source spot check."],
    }
    (output / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not validation["ok"]:
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise ArticleParserError(f"Normalized Parser Bundle failed validation: {failed}")


def _poll(reference_kind: str, reference_id: str, timeout: float, interval: float) -> str:
    token = _token()
    deadline = time.monotonic() + timeout
    while True:
        if reference_kind == "task_id":
            result = _json_request("GET", f"{BASE_URL}/api/v4/extract/task/{reference_id}", token=token)
            entry = result.get("data", {})
        else:
            result = _json_request("GET", f"{BASE_URL}/api/v4/extract-results/batch/{reference_id}", token=token)
            entries = result.get("data", {}).get("extract_result", [])
            entry = entries[0] if isinstance(entries, list) and entries else {}
        state = str(entry.get("state", "pending")) if isinstance(entry, dict) else "pending"
        if state == "done":
            result_url = entry.get("full_zip_url")
            if not isinstance(result_url, str) or not result_url:
                raise ArticleParserError("Completed MinerU task has no full_zip_url", recoverable=False)
            return result_url
        if state == "failed":
            raise ArticleParserError(
                f"MinerU parsing failed: {entry.get('err_msg', 'unknown error')}", recoverable=False
            )
        if state not in PENDING_STATES:
            raise ArticleParserError(f"MinerU returned unknown task state: {state}", recoverable=False)
        if time.monotonic() >= deadline:
            raise ArticleParserError(f"Polling timed out; resume with {reference_kind} {reference_id}")
        time.sleep(interval)


class MinerUHTMLHostedParser:
    def start_url(self, url: str) -> tuple[str, str]:
        result = _json_request(
            "POST",
            f"{BASE_URL}/api/v4/extract/task",
            token=_token(),
            json_body={"url": url, "model_version": "MinerU-HTML"},
        )
        task_id = result.get("data", {}).get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise ArticleParserError("MinerU URL submission did not return a task_id")
        return "task_id", task_id

    def start_file(self, source: Path) -> tuple[str, str]:
        result = _json_request(
            "POST",
            f"{BASE_URL}/api/v4/file-urls/batch",
            token=_token(),
            json_body={
                "files": [{"name": source.name, "data_id": f"focus-{uuid.uuid4().hex}"}],
                "model_version": "MinerU-HTML",
            },
        )
        data = result.get("data", {})
        batch_id = data.get("batch_id")
        urls = data.get("file_urls")
        if not isinstance(batch_id, str) or not isinstance(urls, list) or len(urls) != 1:
            raise ArticleParserError("MinerU upload-link response is incomplete")
        _upload(urls[0], source)
        return "batch_id", batch_id

    def complete(
        self,
        task: ArticleParserTask,
        source: Path | None,
        output: Path,
        *,
        timeout: float,
        interval: float,
    ) -> None:
        try:
            result_url = _poll(task.reference_kind, task.reference_id, timeout, interval)
        except ArticleParserError as exc:
            if task.source_url and str(exc).startswith("MinerU parsing failed:"):
                raise ArticleParserError(
                    f"MinerU could not read this URL: {exc}. Save the article as one .html file and use parse-file.",
                    "url_fetch_failed",
                    recoverable=False,
                ) from exc
            raise
        transfer_root = output.parent / f".focus-mineru-html-{uuid.uuid4().hex}"
        transfer_root.mkdir(parents=True)
        try:
            archive = transfer_root / "result.zip"
            _download(result_url, archive)
            if not zipfile.is_zipfile(archive):
                raise ArticleParserError("MinerU result is not a ZIP archive")
            _normalize(
                archive,
                output,
                reference_kind=task.reference_kind,
                reference_id=task.reference_id,
                source_url=task.source_url,
            )
        finally:
            shutil.rmtree(transfer_root, ignore_errors=True)


def _finish(core: WorkspaceCore, task: ArticleParserTask, hosted: Any, timeout: float, interval: float) -> None:
    staging = core.prepare_parser_bundle(task)
    try:
        hosted.complete(
            task,
            core.article_task_source(task),
            staging,
            timeout=timeout,
            interval=interval,
        )
        core.install_parser_bundle(task, staging)
    except Exception as exc:
        core.discard_parser_bundle(task)
        if isinstance(exc, ArticleParserError) and not exc.recoverable:
            core.discard_parser_task(task)
        raise


def _parse_url(args: argparse.Namespace, hosted: Any) -> None:
    url = _article_url(args.url)
    if not args.authorize_cloud_fetch:
        raise WorkspaceError(
            "cloud_fetch_authorization_required", "Explicit MinerU cloud-fetch authorization is required"
        )
    core = WorkspaceCore(args.workspace)
    url_name = PurePosixPath(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
    title = args.title or Path(url_name).stem or "article"
    _validate_registration(title, args.topic, args.topic_id)
    try:
        reference_kind, reference_id = hosted.start_url(url)
    except ParserError as exc:
        raise ArticleParserError(
            f"MinerU could not read this URL: {exc}. Save the article as one .html file and use parse-file.",
            "url_fetch_failed",
        ) from exc
    task = core.create_article_parser_task(
        reference_id,
        reference_kind,
        title=title,
        topic_title=args.topic,
        topic_id=args.topic_id,
        source_url=url,
        local_html=None,
    )
    print(json.dumps({"status": "submitted", reference_kind: reference_id, "source_id": task.source_id}, ensure_ascii=False), flush=True)
    _finish(core, task, hosted, args.timeout, args.poll_interval)
    print(json.dumps({"status": "done", reference_kind: reference_id, "source_id": task.source_id}, ensure_ascii=False))


def _parse_file(args: argparse.Namespace, hosted: Any) -> None:
    source = args.source.resolve()
    if not source.is_file() or source.suffix.lower() != ".html":
        raise ArticleParserError("Source must be an existing .html file", "source_html_missing")
    if not args.authorize_upload:
        raise WorkspaceError(
            "upload_authorization_required", "Explicit MinerU upload authorization is required for this HTML file"
        )
    core = WorkspaceCore(args.workspace)
    title = args.title or source.stem
    _validate_registration(title, args.topic, args.topic_id)
    reference_kind, reference_id = hosted.start_file(source)
    task = core.create_article_parser_task(
        reference_id,
        reference_kind,
        title=title,
        topic_title=args.topic,
        topic_id=args.topic_id,
        source_url="",
        local_html=source,
    )
    print(json.dumps({"status": "uploaded", reference_kind: reference_id, "source_id": task.source_id}, ensure_ascii=False), flush=True)
    _finish(core, task, hosted, args.timeout, args.poll_interval)
    print(json.dumps({"status": "done", reference_kind: reference_id, "source_id": task.source_id}, ensure_ascii=False))


def _resume(args: argparse.Namespace, hosted: Any) -> None:
    core = WorkspaceCore(args.workspace)
    task = core.load_article_parser_task(args.reference_id)
    _finish(core, task, hosted, args.timeout, args.poll_interval)
    print(
        json.dumps(
            {"status": "done", task.reference_kind: task.reference_id, "source_id": task.source_id},
            ensure_ascii=False,
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", type=Path, required=True)
    common.add_argument("--title")
    common.add_argument("--topic", required=True)
    common.add_argument("--topic-id")
    common.add_argument("--timeout", type=float, default=1800.0)
    common.add_argument("--poll-interval", type=float, default=5.0)
    parse_url = commands.add_parser("parse-url", parents=[common])
    parse_url.add_argument("url")
    parse_url.add_argument("--authorize-cloud-fetch", action="store_true")
    parse_url.set_defaults(func=_parse_url)
    parse_file = commands.add_parser("parse-file", parents=[common])
    parse_file.add_argument("source", type=Path)
    parse_file.add_argument("--authorize-upload", action="store_true")
    parse_file.set_defaults(func=_parse_file)
    resume = commands.add_parser("resume")
    resume.add_argument("reference_id")
    resume.add_argument("--workspace", type=Path, required=True)
    resume.add_argument("--timeout", type=float, default=1800.0)
    resume.add_argument("--poll-interval", type=float, default=5.0)
    resume.set_defaults(func=_resume)
    return parser


def main(argv: list[str] | None = None, *, hosted: Any | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        args.func(args, hosted or MinerUHTMLHostedParser())
        return 0
    except (ParserError, WorkspaceError, OSError, zipfile.BadZipFile) as exc:
        print(
            json.dumps(
                {"ok": False, "error_id": getattr(exc, "error_id", "article_parser_failed"), "message": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
