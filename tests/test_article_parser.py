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
        from workspace_fixture import publish_workspace
        publish_workspace(self.workspace)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = ARTICLE.main(args, hosted=hosted)
        output = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
        error = json.loads(stderr.getvalue()) if stderr.getvalue() else None
        return code, output, error

    def test_saved_html_is_local_and_may_attach_topic(self):
        from test_html_ingestion import saved_html
        html = self.root / "saved.html"
        html.write_text(saved_html(), encoding="utf-8")
        hosted = HostedPdf()
        code, output, error = self.run_parser(
            ["parse-file", str(html), "--workspace", str(self.workspace), "--short-name", "文章工作名", "--topic", "AI Systems"], hosted)
        self.assertEqual((0, None, 0), (code, error, hosted.starts))
        self.assertEqual("文章工作名-article", output[-1]["source_id"])
        topic = json.loads((self.workspace / "topics/ai-systems/topic.yaml").read_text(encoding="utf-8"))
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

    def test_saved_html_canonical_url_reuses_without_parser_or_network(self):
        from test_html_ingestion import saved_html
        html = self.root / "saved.html"
        html.write_text(saved_html(), encoding="utf-8")
        args = ["parse-file", str(html), "--workspace", str(self.workspace)]
        hosted = HostedPdf()
        self.assertEqual(0, self.run_parser(args, hosted)[0])
        html.write_text(saved_html(url="https://example.com/article?utm_source=other"), encoding="utf-8")
        code, output, error = self.run_parser(args, hosted)
        self.assertEqual((0, None, 0), (code, error, hosted.starts))
        self.assertEqual("reused", output[-1]["status"])

    def test_url_requires_saved_html_without_remote_submission(self):
        hosted = HostedPdf()
        code, _, error = self.run_parser(
            ["parse-url", "https://example.com/article", "--workspace", str(self.workspace)], hosted)
        self.assertEqual((1, 0), (code, hosted.starts))
        self.assertEqual("saved_html_required", error["error_id"])


if __name__ == "__main__":
    unittest.main()
