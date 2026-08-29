from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


ARTICLE = load_module(
    "focus_article_parser",
    ROOT / ".agents" / "skills" / "article-parser" / "scripts" / "article_parser.py",
)


class FixtureHosted:
    def __init__(self, archive: Path):
        self.archive = archive
        self.starts: list[tuple] = []
        self.completions = 0

    def start_url(self, url: str):
        self.starts.append(("url", url, "MinerU-HTML"))
        return "task_id", "article-task-1"

    def start_file(self, source: Path):
        self.starts.append(("file", source.name, "MinerU-HTML"))
        return "batch_id", "article-batch-1"

    def complete(self, task, source: Path | None, output: Path, *, timeout: float, interval: float):
        del timeout, interval
        self.completions += 1
        ARTICLE._normalize(
            self.archive,
            output,
            reference_kind=task.reference_kind,
            reference_id=task.reference_id,
            source_url=task.source_url,
        )


class ArticleParserTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"article-parser-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.archive = self.root / "result.zip"
        with zipfile.ZipFile(self.archive, "w") as bundle:
            bundle.writestr(
                "article/full.md",
                "# 中文文章\n\n第一段。\n\n![图](images/cover.png)\n\n## 第二节\n第二段。\n",
            )
            bundle.writestr("article/main.html", "<!doctype html><html lang='zh-CN'><body>中文文章</body></html>")
            bundle.writestr("article/images/cover.png", b"image")
            bundle.writestr("article/images/unused.png", b"unused")

    def tearDown(self):
        shutil.rmtree(self.root)

    @staticmethod
    def _run(args, hosted):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = ARTICLE.main(args, hosted=hosted)
        lines = stderr.getvalue().splitlines() if code else stdout.getvalue().splitlines()
        payload = json.loads(lines[-1])
        return code, payload, stderr.getvalue()

    def test_parse_url_uses_mineru_html_and_registers_common_bundle(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        hosted = FixtureHosted(self.archive)

        code, result, _ = self._run(
            [
                "parse-url",
                "https://example.test/article",
                "--workspace",
                str(workspace),
                "--topic",
                "系统",
                "--authorize-cloud-fetch",
            ],
            hosted,
        )

        self.assertEqual(0, code)
        self.assertEqual([("url", "https://example.test/article", "MinerU-HTML")], hosted.starts)
        self.assertEqual("article-task-1", result["task_id"])
        source_root = workspace / "sources" / "article"
        bundle = source_root / "parser-bundle"
        self.assertEqual(
            {"source.html", "content.md", "images", "metadata.json", "validation.json"},
            {path.name for path in bundle.iterdir()},
        )
        self.assertEqual(["image-001.png"], [path.name for path in (bundle / "images").iterdir()])
        self.assertIn("images/image-001.png", (bundle / "content.md").read_text(encoding="utf-8"))
        metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "source_kind": "article_html",
                "language": "zh",
                "parser": "article-parser",
                "model_version": "MinerU-HTML",
                "source_url": "https://example.test/article",
                "task_id": "article-task-1",
                "image_count": 1,
            },
            metadata,
        )
        self.assertFalse((workspace / "parser-tasks" / "article-task-1").exists())

    def test_parse_file_requires_upload_authorization_and_uses_saved_html(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        html = self.root / "saved.html"
        html.write_text("<!doctype html><html><body>手动保存</body></html>", encoding="utf-8")
        hosted = FixtureHosted(self.archive)
        command = [
            "parse-file",
            str(html),
            "--workspace",
            str(workspace),
            "--title",
            "本地文章",
            "--topic",
            "系统",
        ]

        code, error, _ = self._run(command, hosted)
        self.assertEqual((1, "upload_authorization_required"), (code, error["error_id"]))
        self.assertEqual([], hosted.starts)

        code, result, _ = self._run([*command, "--authorize-upload"], hosted)
        self.assertEqual(0, code)
        self.assertEqual("article-batch-1", result["batch_id"])
        self.assertEqual([("file", "saved.html", "MinerU-HTML")], hosted.starts)
        source_html = workspace / "sources" / "本地文章" / "parser-bundle" / "source.html"
        self.assertIn("中文文章", source_html.read_text(encoding="utf-8"))

    def test_invalid_local_registration_input_is_rejected_before_submission(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        hosted = FixtureHosted(self.archive)

        code, error, _ = self._run(
            [
                "parse-url",
                "https://example.test/article",
                "--workspace",
                str(workspace),
                "--topic",
                "Web",
                "--topic-id",
                "invalid/topic",
                "--authorize-cloud-fetch",
            ],
            hosted,
        )

        self.assertEqual((1, "topic_id_invalid"), (code, error["error_id"]))
        self.assertEqual([], hosted.starts)

    def test_url_submission_failure_points_to_parse_file_without_bypass(self):
        workspace = self.root / "workspace"
        workspace.mkdir()

        class RejectedHosted(FixtureHosted):
            def start_url(self, url: str):
                del url
                raise ARTICLE.ArticleParserError("MinerU URL fetch failed")

        code, error, stderr = self._run(
            [
                "parse-url",
                "https://example.test/blocked",
                "--workspace",
                str(workspace),
                "--title",
                "Blocked",
                "--topic",
                "Web",
                "--authorize-cloud-fetch",
            ],
            RejectedHosted(self.archive),
        )
        self.assertEqual(1, code)
        self.assertEqual("url_fetch_failed", error["error_id"])
        self.assertIn("parse-file", stderr)
        self.assertFalse((workspace / "sources").exists())

    def test_remote_url_fetch_failure_points_to_parse_file(self):
        task = SimpleNamespace(
            reference_kind="task_id",
            reference_id="blocked-task",
            source_url="https://example.test/blocked",
        )
        with mock.patch.object(
            ARTICLE,
            "_poll",
            side_effect=ARTICLE.ArticleParserError("MinerU parsing failed: remote fetch denied"),
        ):
            with self.assertRaises(ARTICLE.ArticleParserError) as caught:
                ARTICLE.MinerUHTMLHostedParser().complete(
                    task, None, self.root / "output", timeout=1, interval=0
                )
        self.assertEqual("url_fetch_failed", caught.exception.error_id)
        self.assertIn("parse-file", str(caught.exception))

    def test_timed_out_url_parse_resumes_with_one_task_reference(self):
        workspace = self.root / "workspace"
        workspace.mkdir()

        class TimeoutOnceHosted(FixtureHosted):
            def complete(self, task, source, output, *, timeout, interval):
                if self.completions == 0:
                    self.completions += 1
                    raise ARTICLE.ArticleParserError(
                        f"Polling timed out; resume with task_id {task.reference_id}"
                    )
                return super().complete(task, source, output, timeout=timeout, interval=interval)

        hosted = TimeoutOnceHosted(self.archive)
        code, error, _ = self._run(
            [
                "parse-url",
                "https://example.test/resume",
                "--workspace",
                str(workspace),
                "--title",
                "恢复文章",
                "--topic",
                "系统",
                "--authorize-cloud-fetch",
            ],
            hosted,
        )
        self.assertEqual(1, code)
        self.assertIn("resume", error["message"])
        task_root = workspace / "parser-tasks" / "article-task-1"
        task = json.loads((task_root / "task.json").read_text(encoding="utf-8"))
        self.assertEqual("article-task-1", task["task_id"])
        self.assertNotIn("batch_id", task)
        self.assertFalse(any("history" in path.name or "receipt" in path.name for path in task_root.iterdir()))

        code, result, _ = self._run(
            ["resume", "article-task-1", "--workspace", str(workspace)], hosted
        )
        self.assertEqual(0, code)
        self.assertEqual("article-task-1", result["task_id"])
        self.assertEqual(1, len(hosted.starts))
        self.assertFalse(task_root.exists())

    def test_terminal_failure_discards_non_resumable_task(self):
        workspace = self.root / "workspace"
        workspace.mkdir()

        class FailedHosted(FixtureHosted):
            def complete(self, task, source, output, *, timeout, interval):
                del task, source, output, timeout, interval
                raise ARTICLE.ArticleParserError(
                    "MinerU parsing failed: access denied", recoverable=False
                )

        code, error, _ = self._run(
            [
                "parse-url",
                "https://example.test/denied",
                "--workspace",
                str(workspace),
                "--title",
                "Denied",
                "--topic",
                "Web",
                "--authorize-cloud-fetch",
            ],
            FailedHosted(self.archive),
        )
        self.assertEqual(1, code)
        self.assertEqual("article_parser_failed", error["error_id"])
        self.assertFalse((workspace / "parser-tasks" / "article-task-1").exists())


if __name__ == "__main__":
    unittest.main()
