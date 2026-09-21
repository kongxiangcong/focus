from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ARTICLE = load_module("article_parser_current", ROOT / ".agents" / "skills" / "article-parser" / "scripts" / "article_parser.py")


class Hosted:
    def __init__(self, *, fail_start: bool = False, timeout: bool = False):
        self.fail_start = fail_start
        self.timeout = timeout
        self.starts = 0

    def start_url(self, url):
        self.starts += 1
        if self.fail_start:
            raise ARTICLE.ParserError("access denied")
        return "task_id", "article-task"

    def start_file(self, source):
        self.starts += 1
        return "batch_id", "article-batch"

    def complete(self, task, source, output, *, timeout, interval):
        if self.timeout:
            raise ARTICLE.ArticleParserError("Polling timed out; resume with task_id article-task")
        output.mkdir(parents=True)
        (output / "images").mkdir()
        (output / "source.html").write_text("<h1>完整文章标题</h1>", encoding="utf-8")
        (output / "content.md").write_text("# 完整文章标题\n\n正文。\n", encoding="utf-8")
        metadata = {
            "source_kind": "article_html",
            "language": "zh",
            "parser": "article-parser",
            task.reference_kind: task.reference_id,
        }
        if task.source_url:
            metadata["source_url"] = task.source_url
        (output / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        (output / "validation.json").write_text(json.dumps({"ok": True, "warnings": []}), encoding="utf-8")


class HostedPdf:
    def __init__(self, *, timeout_once: bool = False):
        self.starts = 0
        self.completions = 0
        self.timeout_once = timeout_once

    def start_pdf(self, source, *, model, language, ocr):
        self.starts += 1
        return "pdf-batch"

    def complete_pdf(self, task, source, output, *, timeout, interval):
        self.completions += 1
        if self.timeout_once and self.completions == 1:
            raise ARTICLE.ParserError("Polling timed out; resume with batch_id pdf-batch")
        (output / "images").mkdir(parents=True)
        shutil.copy2(source, output / "source.pdf")
        (output / "content.md").write_text(
            "# Unified Paper\n\n![Figure](images/image-001.png)\n", encoding="utf-8"
        )
        (output / "images" / "image-001.png").write_bytes(b"image")
        (output / "metadata.json").write_text(
            json.dumps(
                {
                    "source_kind": "paper_pdf",
                    "language": task.language,
                    "parser": "article-parser",
                    "batch_id": task.batch_id,
                }
            ),
            encoding="utf-8",
        )
        (output / "validation.json").write_text(
            json.dumps({"ok": True, "warnings": []}), encoding="utf-8"
        )


class ArticleParserTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_parser(self, args, hosted):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = ARTICLE.main(args, hosted=hosted)
        output = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        error = json.loads(stderr.getvalue()) if stderr.getvalue() else None
        return code, output, error

    def test_url_invocation_is_authorization_and_registers_after_title_resolution(self):
        hosted = Hosted()
        code, output, error = self.run_parser(
            ["parse-url", "https://example.com/post?utm_source=noise", "--workspace", str(self.workspace), "--short-name", "核心对象与主张"],
            hosted,
        )
        self.assertEqual((0, None), (code, error))
        self.assertEqual("submitted", output[0]["status"])
        self.assertNotIn("source_id", output[0])
        self.assertEqual("核心对象与主张-article", output[1]["source_id"])
        source = json.loads((self.workspace / "sources" / "核心对象与主张-article" / "source.yaml").read_text(encoding="utf-8"))
        self.assertEqual("完整文章标题", source["title"])
        self.assertEqual("https://example.com/post", source["source_url"])
        self.assertNotIn("topics", source)
        self.assertEqual([], list((self.workspace / "parser-tasks").iterdir()))

    def test_saved_html_upload_needs_no_second_flag_and_may_attach_topic(self):
        html = self.root / "saved.html"
        html.write_text("<html>saved</html>", encoding="utf-8")
        code, output, error = self.run_parser(
            ["parse-file", str(html), "--workspace", str(self.workspace), "--short-name", "文章工作名", "--topic", "AI Systems"],
            Hosted(),
        )
        self.assertEqual((0, None), (code, error))
        self.assertEqual("文章工作名-article", output[-1]["source_id"])
        topic = json.loads((self.workspace / "topics" / "ai-systems" / "topic.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["文章工作名-article"], topic["sources"])

    def test_pdf_uses_the_same_parse_file_operation_and_article_parser_provenance(self):
        source = self.root / "selected.pdf"
        source.write_bytes(b"%PDF-1.4\nselected bytes\n")
        hosted = HostedPdf()
        code, output, error = self.run_parser(
            [
                "parse-file",
                str(source),
                "--workspace",
                str(self.workspace),
                "--short-name",
                "Unified",
            ],
            hosted,
        )

        self.assertEqual((0, None, 1), (code, error, hosted.starts))
        self.assertEqual("Unified-paper", output[-1]["source_id"])
        bundle = self.workspace / "sources" / "Unified-paper" / "parser-bundle"
        self.assertEqual(source.read_bytes(), (bundle / "source.pdf").read_bytes())
        self.assertEqual(
            "article-parser",
            json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))["parser"],
        )
        state = json.loads((self.workspace / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {"current_plan_id": None, "current_chunk_id": None},
            state["sources"]["Unified-paper"],
        )

    def test_identical_pdf_reuses_the_bundle_without_resubmission(self):
        source = self.root / "selected.pdf"
        source.write_bytes(b"%PDF-1.4\nsame bytes\n")
        hosted = HostedPdf()
        first = ["parse-file", str(source), "--workspace", str(self.workspace), "--short-name", "Reuse"]
        self.assertEqual(0, self.run_parser(first, hosted)[0])
        original = (self.workspace / "sources" / "Reuse-paper" / "parser-bundle" / "content.md").read_bytes()
        renamed = self.root / "renamed.pdf"
        renamed.write_bytes(source.read_bytes())
        code, output, error = self.run_parser(
            [
                "parse-file",
                str(renamed),
                "--workspace",
                str(self.workspace),
                "--topic",
                "Second Topic",
            ],
            hosted,
        )
        self.assertEqual((0, None, 1), (code, error, hosted.starts))
        self.assertEqual("reused", output[-1]["status"])
        self.assertEqual(original, (self.workspace / "sources" / "Reuse-paper" / "parser-bundle" / "content.md").read_bytes())

    def test_pdf_resume_uses_the_persisted_original_without_reupload(self):
        source = self.root / "selected.pdf"
        original = b"%PDF-1.4\noriginal bytes\n"
        source.write_bytes(original)
        hosted = HostedPdf(timeout_once=True)
        first = self.run_parser(
            ["parse-file", str(source), "--workspace", str(self.workspace), "--short-name", "Resume"], hosted
        )
        self.assertEqual(1, first[0])
        source.write_bytes(b"replacement")
        code, output, error = self.run_parser(
            ["resume", "pdf-batch", "--workspace", str(self.workspace)], hosted
        )
        self.assertEqual((0, None, 1, 2), (code, error, hosted.starts, hosted.completions))
        self.assertEqual(original, (self.workspace / "sources" / "Resume-paper" / "parser-bundle" / "source.pdf").read_bytes())

    def test_identical_canonical_url_reuses_without_resubmission(self):
        self.run_parser(
            ["parse-url", "https://example.com/post?utm_source=a", "--workspace", str(self.workspace), "--short-name", "测试文章"],
            Hosted(),
        )
        second = Hosted(fail_start=True)
        code, output, error = self.run_parser(
            ["parse-url", "https://example.com/post", "--workspace", str(self.workspace)], second
        )
        self.assertEqual((0, None, 0), (code, error, second.starts))
        self.assertEqual("reused", output[-1]["status"])

    def test_url_failure_is_direct_and_does_not_bypass_access_controls(self):
        code, _, error = self.run_parser(
            ["parse-url", "https://example.com/blocked", "--workspace", str(self.workspace)], Hosted(fail_start=True)
        )
        self.assertEqual(1, code)
        self.assertEqual("url_fetch_failed", error["error_id"])
        self.assertIn("save the article as one .html file", error["message"].lower())

    def test_timeout_retains_only_resumable_task_and_resume_installs_source(self):
        hosted = Hosted(timeout=True)
        code, _, error = self.run_parser(
            ["parse-url", "https://example.com/slow", "--workspace", str(self.workspace), "--short-name", "慢文章"], hosted
        )
        self.assertEqual((1, "article_parser_failed"), (code, error["error_id"]))
        task = json.loads((self.workspace / "parser-tasks" / "article-task" / "task.json").read_text(encoding="utf-8"))
        self.assertNotIn("source_id", task)
        hosted.timeout = False
        code, output, error = self.run_parser(["resume", "article-task", "--workspace", str(self.workspace)], hosted)
        self.assertEqual((0, None), (code, error))
        self.assertEqual("慢文章-article", output[-1]["source_id"])


if __name__ == "__main__":
    unittest.main()
