#!/usr/bin/env python3
"""Parse a selected PDF or HTML article into one canonical Parser Bundle."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
import tempfile
import shutil
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core import (
    ParserTask,
    SourceLibrary,
    WorkspaceCore,
    WorkspaceError,
    validate_topic_id,
)
from core.mineru import MinerUHostedParser as MinerUPdfHostedParser, MAX_SOURCE_BYTES, ParserError
from core.mineru_selector import AutoMinerUParser
from core.reading_workspace import _write_document, _read_document, _validate_parser_bundle


class ArticleParserError(ParserError):
    def __init__(self, message, error_id="article_parser_failed", *, recoverable=True):
        super().__init__(message)
        self.error_id = error_id
        self.recoverable = recoverable


def _validate_registration(title, short_name, topic, topic_id):
    if title is not None and not title.strip():
        raise WorkspaceError("source_title_invalid", "Source title is empty")
    if short_name is not None and not short_name.strip():
        raise WorkspaceError("source_short_name_invalid", "Source short name is empty")
    if topic is not None and not topic.strip():
        raise WorkspaceError("topic_invalid", "Topic title is empty")
    if topic_id is not None:
        validate_topic_id(topic_id)


class PDFHostedParser:
    def __init__(self):
        self.pdf = MinerUPdfHostedParser()

    def start_pdf(self, source, *, model, language, ocr):
        return self.pdf.start(source, model=model, language=language, ocr=ocr)

    def complete_pdf(self, task, source, output, *, timeout, interval):
        self.pdf.complete(source, output, batch_id=task.batch_id, model=task.model,
                          language=task.language, timeout=timeout, interval=interval)


def _finish_pdf(core: WorkspaceCore, task: ParserTask, hosted: Any, timeout: float, interval: float) -> dict[str, Any]:
    staging = core.prepare_parser_bundle(task)
    try:
        hosted.complete_pdf(
            task,
            core.parser_task_source(task),
            staging,
            timeout=timeout,
            interval=interval,
        )
        return core.install_parser_bundle(task, staging)
    except Exception as exc:
        core.discard_parser_bundle(task)
        if isinstance(exc, ParserError) and not exc.recoverable:
            core.discard_parser_task(task)
        raise


def _parse_url(args, hosted):
    raise ArticleParserError("Save the article as one complete SingleFile .html file and use parse-file.",
                             "saved_html_required", recoverable=False)


def _parse_file(args, hosted):
    source = args.source.resolve()
    if not source.is_file() or source.suffix.lower() not in {".html", ".pdf"}:
        raise ArticleParserError("Source must be an existing .pdf or .html file", "source_file_missing")
    if source.suffix.lower() == ".pdf":
        _parse_pdf_file(args, hosted, source)
        return
    from core.html_article import LocalHTMLParser, article_identity
    _validate_registration(args.title, args.short_name, args.topic, args.topic_id)
    library = SourceLibrary(args.workspace)
    identity = article_identity(source)
    existing = library.find(identity)
    if existing:
        topic = library.attach(existing["source_id"], topic_title=args.topic, topic_id=args.topic_id) if args.topic or args.topic_id else None
        print(json.dumps({"status": "reused", "source_id": existing["source_id"], "topic_id": topic}, ensure_ascii=False))
        return
    staging = args.workspace / "parser-tasks"
    staging.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="local-html-", dir=staging) as temporary:
        candidate = Path(temporary) / "candidate"
        parsed = LocalHTMLParser().parse(source, candidate)
        (candidate / "ingestion-result.json").unlink()
        result = library.register(candidate, source_kind="article_html", identity=identity,
                                  title=args.title or parsed["title"], short_name=args.short_name or parsed["short_name"],
                                  source_url=parsed["source_url"] or None, published_at=args.published_at,
                                  topic_title=args.topic, topic_id=args.topic_id)
        print(json.dumps({**result, "status": "done"}, ensure_ascii=False))


def _parse_pdf_file(args: argparse.Namespace, hosted: Any, source: Path) -> None:
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ArticleParserError("Source exceeds MinerU's 200 MB precision-API limit", "source_pdf_too_large")
    core = WorkspaceCore(args.workspace)
    _validate_registration(args.title, args.short_name, args.topic, args.topic_id)
    existing = SourceLibrary(args.workspace).find_original(source, source_kind="paper_pdf")
    if existing is not None:
        topic_id = None
        if args.topic is not None or args.topic_id is not None:
            topic_id = SourceLibrary(args.workspace).attach(
                existing["source_id"], topic_title=args.topic, topic_id=args.topic_id
            )
        print(json.dumps({"status": "reused", "source_id": existing["source_id"], "topic_id": topic_id}, ensure_ascii=False))
        return
    if hosted is None:
        task_id = uuid.uuid4().hex
        task_root = args.workspace / "parser-tasks" / task_id
        task_root.mkdir(parents=True)
        shutil.copy2(source, task_root / "source.pdf")
        task = {"task_id": task_id, "title": args.title, "short_name": args.short_name,
                "topic": args.topic, "topic_id": args.topic_id, "published_at": args.published_at,
                "checkpoint": None}
        _write_document(task_root / "auto-task.json", task)
        _finish_auto_pdf(args.workspace, task_root, task, args.timeout, args.poll_interval,
                         model=args.model, language=args.language, ocr=args.ocr)
        return
    batch_id = hosted.start_pdf(source, model=args.model, language=args.language, ocr=args.ocr)
    task = core.create_parser_task(
        batch_id,
        source,
        title=args.title or "",
        short_name=args.short_name or "",
        topic_title=args.topic,
        topic_id=args.topic_id,
        published_at=args.published_at,
        model=args.model,
        language=args.language,
    )
    print(json.dumps({"status": "uploaded", "batch_id": batch_id}, ensure_ascii=False), flush=True)
    result = _finish_pdf(core, task, hosted, args.timeout, args.poll_interval)
    print(json.dumps({**result, "status": "done", "batch_id": batch_id}, ensure_ascii=False))


def _resume(args, hosted):
    if hosted is None:
        task_root = args.workspace / "parser-tasks" / args.reference_id
        if (task_root / "auto-task.json").is_file():
            task = _read_document(task_root / "auto-task.json")
            if task.get("task_id") != args.reference_id:
                raise WorkspaceError("parser_task_invalid", "Parser task ID mismatch")
            _finish_auto_pdf(args.workspace, task_root, task, args.timeout, args.poll_interval)
            return
        hosted = PDFHostedParser()  # older remote-only tasks
    core = WorkspaceCore(args.workspace)
    task = core.load_parser_task(args.reference_id)
    result = _finish_pdf(core, task, hosted, args.timeout, args.poll_interval)
    print(json.dumps({**result, "status": "done", "batch_id": task.batch_id}, ensure_ascii=False))


def _finish_auto_pdf(workspace, task_root, task, timeout, interval, *, model="vlm", language="en", ocr=False):
    source = task_root / "source.pdf"
    candidate = task_root / "candidate"
    parser = AutoMinerUParser(model=model, language=language, ocr=ocr, timeout=timeout, interval=interval)
    def checkpoint(value):
        task["checkpoint"] = value
        _write_document(task_root / "auto-task.json", task)
        print(json.dumps({"status": "parsing", "task_id": task["task_id"],
                          "backend": value.get("backend"), "reference_id": value.get("reference_id")}, ensure_ascii=False), flush=True)
    if not candidate.joinpath("validation.json").is_file():
        if candidate.exists():
            shutil.rmtree(candidate)
        if task.get("checkpoint"):
            parser.resume(source, candidate, checkpoint=task["checkpoint"], on_checkpoint=checkpoint)
        else:
            parser.parse(source, candidate, checkpoint=checkpoint)
    _validate_parser_bundle(candidate)
    parsed = _read_document(candidate / "ingestion-result.json")
    if not isinstance(parsed.get("title"), str) or not isinstance(parsed.get("short_name"), str):
        raise WorkspaceError("parser_result_invalid", "Candidate result is invalid")
    identity = "paper-original:" + __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    result = SourceLibrary(workspace).register(candidate, source_kind="paper_pdf", identity=identity,
        title=task.get("title") or parsed["title"], short_name=task.get("short_name") or parsed["short_name"],
        topic_title=task.get("topic"), topic_id=task.get("topic_id"), published_at=task.get("published_at"))
    shutil.rmtree(task_root, ignore_errors=True)
    print(json.dumps({**result, "status": "done", "task_id": task["task_id"]}, ensure_ascii=False))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", type=Path, required=True)
    common.add_argument("--title")
    common.add_argument("--short-name")
    common.add_argument("--topic")
    common.add_argument("--topic-id")
    common.add_argument("--published-at")
    common.add_argument("--timeout", type=float, default=1800.0)
    common.add_argument("--poll-interval", type=float, default=5.0)
    parse_url = commands.add_parser("parse-url", parents=[common])
    parse_url.add_argument("url")
    parse_url.set_defaults(func=_parse_url)
    parse_file = commands.add_parser("parse-file", parents=[common])
    parse_file.add_argument("source", type=Path)
    parse_file.add_argument("--model", choices=("vlm", "pipeline"), default="vlm")
    parse_file.add_argument("--language", default="en")
    parse_file.add_argument("--ocr", action="store_true")
    parse_file.set_defaults(func=_parse_file)
    resume = commands.add_parser("resume")
    resume.add_argument("reference_id")
    resume.add_argument("--workspace", type=Path, required=True)
    resume.add_argument("--timeout", type=float, default=1800.0)
    resume.add_argument("--poll-interval", type=float, default=5.0)
    resume.set_defaults(func=_resume)
    return parser


def main(argv: list[str] | None = None, *, hosted: Any | None = None) -> int:
    lease = None
    try:
        args = _build_parser().parse_args(argv)
        from core.workspace_lifecycle import open_command_workspace
        lease = open_command_workspace(args.workspace)
        args.func(args, hosted)
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
    finally:
        if lease:
            lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
