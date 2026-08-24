from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import os
import shutil
import unittest
import urllib.error
import uuid
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PARSER = load_module(
    "focus_mineru_precision",
    ROOT / ".agents" / "skills" / "paper-parser" / "scripts" / "mineru_precision.py",
)
WORKSPACE_CORE = importlib.import_module("core.reading_workspace")
BLOG = load_module(
    "focus_paper2blog",
    ROOT / ".agents" / "skills" / "paper2blog" / "scripts" / "paper2blog.py",
)


class PaperParserTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"paper-tools-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_authorized_parse_registers_paper_only_after_valid_bundle(self):
        source = self.root / "fixture.pdf"
        source.write_bytes(b"%PDF-1.4\nfixture\n")
        workspace = self.root / "workspace"
        workspace.mkdir()

        class HostedParserFixture:
            def start(self, source, *, model, language, ocr):
                return "batch-fixture"

            def complete(self, source, output, *, batch_id, model, language, timeout, interval):
                (output / "images").mkdir(parents=True)
                shutil.copy2(source, output / "source.pdf")
                (output / "paper.md").write_text(
                    "# Fixture Paper\n\n![Figure](images/image-001.png)\n", encoding="utf-8"
                )
                (output / "images" / "image-001.png").write_bytes(b"image")
                (output / "metadata.json").write_text(
                    json.dumps({"parser": "mineru-precision-api", "batch_id": batch_id}),
                    encoding="utf-8",
                )
                (output / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = PARSER.main(
                [
                    "parse",
                    str(source),
                    "--workspace",
                    str(workspace),
                    "--title",
                    "Fixture Paper",
                    "--topic",
                    "Accelerator Architecture",
                    "--authorize-upload",
                ],
                hosted=HostedParserFixture(),
            )

        self.assertEqual(0, result)
        response = json.loads(stdout.getvalue().splitlines()[-1])
        self.assertEqual("fixture-paper", response["paper_id"])
        paper_root = workspace / "papers" / "fixture-paper"
        self.assertTrue((paper_root / "parser-bundle" / "source.pdf").is_file())
        paper = json.loads((paper_root / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["accelerator-architecture"], paper["topics"])
        topic = json.loads(
            (workspace / "topics" / "accelerator-architecture" / "topic.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(["fixture-paper"], topic["papers"])
        pointers = json.loads((workspace / "pointers.yaml").read_text(encoding="utf-8"))
        self.assertEqual("fixture-paper", pointers["current_paper_id"])
        self.assertEqual(
            {
                "current_plan_id": None,
                "current_chunk_id": None,
                "current_explanation_id": None,
            },
            pointers["papers"]["fixture-paper"],
        )

    def test_invalid_parse_result_leaves_no_registered_paper_or_topic(self):
        source = self.root / "fixture.pdf"
        source.write_bytes(b"%PDF-1.4\nfixture\n")
        workspace = self.root / "workspace"
        workspace.mkdir()

        class InvalidHostedParserFixture:
            def start(self, source, *, model, language, ocr):
                return "batch-invalid"

            def complete(self, source, output, **kwargs):
                (output / "images").mkdir(parents=True)
                shutil.copy2(source, output / "source.pdf")
                (output / "paper.md").write_text("# Incomplete\n", encoding="utf-8")
                (output / "metadata.json").write_text(
                    '{"parser": "mineru-precision-api"}\n', encoding="utf-8"
                )
                (output / "validation.json").write_text('{"ok": false}\n', encoding="utf-8")

        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            result = PARSER.main(
                [
                    "parse",
                    str(source),
                    "--workspace",
                    str(workspace),
                    "--title",
                    "Incomplete",
                    "--topic",
                    "Parsing",
                    "--authorize-upload",
                ],
                hosted=InvalidHostedParserFixture(),
            )

        self.assertEqual(1, result)
        self.assertEqual("parser_bundle_invalid", json.loads(stderr.getvalue())["error_id"])
        self.assertFalse((workspace / "papers" / "incomplete" / "paper.yaml").exists())
        self.assertFalse((workspace / "topics" / "parsing" / "topic.yaml").exists())
        self.assertFalse((workspace / "pointers.yaml").exists())

    def test_registration_write_failure_rolls_back_bundle_and_membership(self):
        source = self.root / "fixture.pdf"
        source.write_bytes(b"%PDF-1.4\nfixture\n")
        workspace = self.root / "workspace"
        workspace.mkdir()

        class HostedParserFixture:
            def start(self, source, **kwargs):
                return "batch-write-failure"

            def complete(self, source, output, *, batch_id, **kwargs):
                (output / "images").mkdir(parents=True)
                shutil.copy2(source, output / "source.pdf")
                (output / "paper.md").write_text("# Rollback\n", encoding="utf-8")
                (output / "metadata.json").write_text(
                    json.dumps({"parser": "mineru-precision-api", "batch_id": batch_id}), encoding="utf-8"
                )
                (output / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")

        write_document = WORKSPACE_CORE._write_document

        def fail_pointer_write(path, value):
            if path.name == "pointers.yaml":
                raise OSError("controlled pointer write failure")
            write_document(path, value)

        with mock.patch.object(WORKSPACE_CORE, "_write_document", side_effect=fail_pointer_write):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = PARSER.main(
                    [
                        "parse",
                        str(source),
                        "--workspace",
                        str(workspace),
                        "--title",
                        "Rollback Paper",
                        "--topic",
                        "Failure Safety",
                        "--authorize-upload",
                    ],
                    hosted=HostedParserFixture(),
                )

        self.assertEqual(1, result)
        self.assertFalse((workspace / "papers" / "rollback-paper").exists())
        self.assertFalse((workspace / "topics" / "failure-safety" / "topic.yaml").exists())
        self.assertFalse((workspace / "pointers.yaml").exists())
        self.assertTrue((workspace / "parser-tasks" / "batch-write-failure" / "task.json").is_file())

    def test_timed_out_parse_resumes_by_batch_reference_without_reupload(self):
        source = self.root / "fixture.pdf"
        source.write_bytes(b"%PDF-1.4\nfixture\n")
        workspace = self.root / "workspace"
        workspace.mkdir()

        class InterruptibleHostedParserFixture:
            def __init__(self):
                self.starts = 0
                self.completions = 0

            def start(self, source, *, model, language, ocr):
                self.starts += 1
                return "batch-resumable"

            def complete(self, source, output, *, batch_id, **kwargs):
                self.completions += 1
                if self.completions == 1:
                    raise PARSER.ParserError(f"Polling timed out; resume with batch_id {batch_id}")
                (output / "images").mkdir(parents=True)
                shutil.copy2(source, output / "source.pdf")
                (output / "paper.md").write_text("# Resumed\n", encoding="utf-8")
                (output / "metadata.json").write_text(
                    json.dumps({"parser": "mineru-precision-api", "batch_id": batch_id}),
                    encoding="utf-8",
                )
                (output / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")

        hosted = InterruptibleHostedParserFixture()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            first = PARSER.main(
                [
                    "parse",
                    str(source),
                    "--workspace",
                    str(workspace),
                    "--title",
                    "Resumed Paper",
                    "--topic",
                    "Recovery",
                    "--authorize-upload",
                ],
                hosted=hosted,
            )
        self.assertEqual(1, first)
        task_root = workspace / "parser-tasks" / "batch-resumable"
        task_path = task_root / "task.json"
        self.assertTrue(task_path.is_file())
        self.assertEqual(source.read_bytes(), (task_root / "source.pdf").read_bytes())
        task_text = task_path.read_text(encoding="utf-8").lower()
        self.assertNotIn("hash", task_text)
        self.assertNotIn("token", task_text)
        self.assertNotIn("url", task_text)
        self.assertFalse((workspace / "papers" / "resumed-paper" / "paper.yaml").exists())
        source.write_bytes(b"%PDF replacement that was not uploaded")

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            resumed = PARSER.main(
                [
                    "resume",
                    "batch-resumable",
                    "--workspace",
                    str(workspace),
                ],
                hosted=hosted,
            )

        self.assertEqual(0, resumed)
        self.assertEqual(1, hosted.starts)
        self.assertEqual(2, hosted.completions)
        self.assertTrue((workspace / "papers" / "resumed-paper" / "paper.yaml").is_file())
        self.assertEqual(
            b"%PDF-1.4\nfixture\n",
            (workspace / "papers" / "resumed-paper" / "parser-bundle" / "source.pdf").read_bytes(),
        )
        self.assertFalse(task_root.exists())

    def test_reparse_allocates_numeric_suffix_without_overwriting_existing_paper(self):
        source = self.root / "fixture.pdf"
        source.write_bytes(b"%PDF-1.4\nfixture\n")
        workspace = self.root / "workspace"
        workspace.mkdir()

        class HostedParserFixture:
            def __init__(self):
                self.number = 0

            def start(self, source, **kwargs):
                self.number += 1
                return f"batch-{self.number}"

            def complete(self, source, output, *, batch_id, **kwargs):
                (output / "images").mkdir(parents=True)
                shutil.copy2(source, output / "source.pdf")
                (output / "paper.md").write_text(f"# Version {batch_id}\n", encoding="utf-8")
                (output / "metadata.json").write_text(
                    json.dumps({"parser": "mineru-precision-api", "batch_id": batch_id}),
                    encoding="utf-8",
                )
                (output / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")

        hosted = HostedParserFixture()
        command = [
            "parse",
            str(source),
            "--workspace",
            str(workspace),
            "--title",
            "Collision Paper",
            "--topic",
            "Identity",
            "--authorize-upload",
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, PARSER.main(command, hosted=hosted))
        original = (workspace / "papers" / "collision-paper" / "parser-bundle" / "paper.md").read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, PARSER.main(command, hosted=hosted))

        self.assertEqual(
            original,
            (workspace / "papers" / "collision-paper" / "parser-bundle" / "paper.md").read_bytes(),
        )
        self.assertTrue((workspace / "papers" / "collision-paper-002" / "paper.yaml").is_file())
        topic = json.loads((workspace / "topics" / "identity" / "topic.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["collision-paper", "collision-paper-002"], topic["papers"])

        chinese_command = [
            "parse",
            str(source),
            "--workspace",
            str(workspace),
            "--title",
            "可配置脉动阵列",
            "--topic",
            "Identity",
            "--authorize-upload",
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, PARSER.main(chinese_command, hosted=hosted))
        self.assertTrue((workspace / "papers" / "可配置脉动阵列" / "paper.yaml").is_file())

    def test_existing_paper_is_reused_only_by_explicit_selection(self):
        workspace = self.root / "workspace"
        bundle = workspace / "papers" / "existing-paper" / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "paper.md").write_text("# Existing\n", encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"parser": "mineru-precision-api"}\n', encoding="utf-8"
        )
        (bundle / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")
        (bundle.parent / "paper.yaml").write_text(
            json.dumps({"paper_id": "existing-paper", "title": "Existing Paper", "topics": []}),
            encoding="utf-8",
        )
        before = (bundle / "paper.md").read_bytes()

        with contextlib.redirect_stdout(io.StringIO()):
            result = PARSER.main(
                [
                    "reuse",
                    "--workspace",
                    str(workspace),
                    "--paper-id",
                    "existing-paper",
                    "--topic",
                    "Second Topic",
                ]
            )

        self.assertEqual(0, result)
        paper = json.loads((bundle.parent / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["second-topic"], paper["topics"])
        topic = json.loads((workspace / "topics" / "second-topic" / "topic.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["existing-paper"], topic["papers"])
        self.assertEqual(before, (bundle / "paper.md").read_bytes())

    def test_normalize_builds_compact_bundle_and_rewrites_images_in_reference_order(self):
        source = self.root / "input.pdf"
        source.write_bytes(b"%PDF-1.4\nfixture\n")
        archive = self.root / "result.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(
                "paper/full.md",
                "# Fixture Paper\n\n![Second](images/z.png)\n\n![First](images/a.jpg)\n",
            )
            bundle.writestr("paper/images/a.jpg", b"first-image")
            bundle.writestr("paper/images/z.png", b"second-image")
            bundle.writestr("paper/images/unreferenced.png", b"unused-image")
            bundle.writestr("paper/fixture_content_list.json", "[]")
        output = self.root / "output"

        PARSER._normalize(source, archive, output, "batch-fixture", "vlm", "en")

        self.assertEqual(source.read_bytes(), (output / "source.pdf").read_bytes())
        paper = (output / "paper.md").read_text(encoding="utf-8")
        self.assertIn("![Second](images/image-001.png)", paper)
        self.assertIn("![First](images/image-002.jpg)", paper)
        self.assertEqual(b"second-image", (output / "images" / "image-001.png").read_bytes())
        self.assertEqual(b"first-image", (output / "images" / "image-002.jpg").read_bytes())
        self.assertFalse((output / "raw").exists())
        self.assertFalse((output / "images" / "unreferenced.png").exists())
        metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual("mineru-precision-api", metadata["parser"])
        self.assertEqual("paper-reference-order", metadata["image_naming"])
        self.assertNotIn("token", json.dumps(metadata).lower())
        self.assertNotIn("hash", json.dumps(metadata).lower())
        validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
        self.assertTrue(validation["ok"])
        self.assertNotIn("hash", json.dumps(validation).lower())

    def test_upload_requires_authorization_before_hosted_parser_is_called(self):
        source = self.root / "fixture.pdf"
        source.write_bytes(b"%PDF fixture")
        workspace = self.root / "workspace"
        workspace.mkdir()

        class HostedParserFixture:
            def start(self, *args, **kwargs):
                raise AssertionError("hosted parser must not be called")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = PARSER.main(
                [
                    "parse",
                    str(source),
                    "--workspace",
                    str(workspace),
                    "--title",
                    "Unauthorized",
                    "--topic",
                    "Security",
                ],
                hosted=HostedParserFixture(),
            )

        self.assertEqual(1, result)
        self.assertEqual("upload_authorization_required", json.loads(stderr.getvalue())["error_id"])
        self.assertFalse((workspace / "parser-tasks").exists())

    def test_missing_workspace_paper_and_parser_bundle_return_structured_errors(self):
        missing_workspace = self.root / "missing"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = PARSER.main(
                [
                    "reuse",
                    "--workspace",
                    str(missing_workspace),
                    "--paper-id",
                    "paper",
                    "--topic",
                    "Topic",
                ]
            )
        self.assertEqual(1, result)
        self.assertEqual("workspace_missing", json.loads(stderr.getvalue())["error_id"])

        workspace = self.root / "workspace-errors"
        workspace.mkdir()
        for paper_id, expected in (("missing", "paper_missing"), ("no-bundle", "parser_bundle_missing")):
            if paper_id == "no-bundle":
                paper_root = workspace / "papers" / paper_id
                paper_root.mkdir(parents=True)
                (paper_root / "paper.yaml").write_text(
                    json.dumps({"paper_id": paper_id, "title": "No Bundle", "topics": []}),
                    encoding="utf-8",
                )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = PARSER.main(
                    [
                        "reuse",
                        "--workspace",
                        str(workspace),
                        "--paper-id",
                        paper_id,
                        "--topic",
                        "Topic",
                    ]
                )
            self.assertEqual(1, result)
            self.assertEqual(expected, json.loads(stderr.getvalue())["error_id"])

        paper_root = workspace / "papers" / "valid-paper"
        bundle = paper_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "paper.md").write_text("# Valid\n", encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"parser": "mineru-precision-api"}\n', encoding="utf-8"
        )
        (bundle / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")
        (paper_root / "paper.yaml").write_text(
            json.dumps({"paper_id": "valid-paper", "title": "Valid", "topics": []}), encoding="utf-8"
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = PARSER.main(
                [
                    "reuse",
                    "--workspace",
                    str(workspace),
                    "--paper-id",
                    "valid-paper",
                    "--existing-topic-id",
                    "missing-topic",
                ]
            )
        self.assertEqual(1, result)
        self.assertEqual("topic_missing", json.loads(stderr.getvalue())["error_id"])

    def test_safe_extract_rejects_path_traversal(self):
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../escape.txt", "bad")
        with self.assertRaises(PARSER.ParserError):
            PARSER._safe_extract(archive, self.root / "output")

    def test_signed_upload_url_is_passed_to_curl_over_stdin(self):
        source = self.root / "input.pdf"
        source.write_bytes(b"%PDF fixture")
        signed_url = "https://storage.example/upload?signature=secret"

        with mock.patch.object(PARSER.shutil, "which", return_value="curl.exe"):
            with mock.patch.object(PARSER.subprocess, "run") as run:
                run.return_value.returncode = 0
                PARSER._upload(signed_url, source)

        args, kwargs = run.call_args
        self.assertNotIn(signed_url, args[0])
        self.assertIn(signed_url, kwargs["input"])
        self.assertIn(json.dumps(str(source)), kwargs["input"])

    def test_token_falls_back_to_dotenv_without_overriding_environment(self):
        (self.root / ".env").write_text("# local secret\nMINERU_API_TOKEN=dotenv-token\n", encoding="utf-8")
        previous_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("MINERU_API_TOKEN", None)
                self.assertEqual("dotenv-token", PARSER._token())
            with mock.patch.dict(os.environ, {"MINERU_API_TOKEN": "environment-token"}):
                self.assertEqual("environment-token", PARSER._token())
        finally:
            os.chdir(previous_cwd)

    def test_http_errors_do_not_relay_remote_body_that_may_contain_credentials(self):
        remote_error = urllib.error.HTTPError(
            "https://mineru.net/api/v4/file-urls/batch",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b"echoed-token-value"),
        )
        with mock.patch.object(PARSER.urllib.request, "urlopen", side_effect=remote_error):
            with self.assertRaises(PARSER.ParserError) as caught:
                PARSER._request("GET", "https://mineru.net/api/v4/file-urls/batch", token="token")

        self.assertNotIn("echoed-token-value", str(caught.exception))


class PaperToBlogTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"paper-blog-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_prepare_and_check_workspace(self):
        bundle = self.root / "bundle"
        (bundle / "images").mkdir(parents=True)
        (bundle / "paper.md").write_text(
            "# A Paper\n\n## Method\nEvidence.\n\n![Figure](images/image-001.png)\n",
            encoding="utf-8",
        )
        (bundle / "metadata.json").write_text(
            '{"title": "A Paper", "parser": "mineru-precision-api"}\n',
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(b"fixture")
        workspace = self.root / "blog"

        prepared = BLOG._prepare(bundle, workspace)

        self.assertTrue(prepared["ok"])
        self.assertTrue((workspace / "assets" / "image-001.png").is_file())
        self.assertFalse((workspace / "source.pdf").exists())
        self.assertIn(
            "![Figure](assets/image-001.png)",
            (workspace / "paper.md").read_text(encoding="utf-8"),
        )
        self.assertIn("A Paper", (workspace / "evidence-map.md").read_text(encoding="utf-8"))
        failed = BLOG._check(workspace)
        self.assertFalse(failed["ok"])
        self.assertIn("blog.md is missing", failed["errors"])

        (workspace / "evidence-map.md").write_text("# Evidence Map\n\nComplete evidence.\n", encoding="utf-8")
        (workspace / "blog.md").write_text(
            "# 技术博客\n\n## 方法与设计\n\n## 实验与证据\n\n## 局限与边界\n\n"
            "![Figure](assets/image-001.png)\n\n## 参考文献\n\n" + "正文证据。" * 500,
            encoding="utf-8",
        )
        with mock.patch.object(
            BLOG,
            "_render_markdown",
            return_value='<h1>技术博客</h1><img src="assets/image-001.png"><p>正文</p>',
        ):
            rendered = BLOG._render(workspace)

        self.assertTrue(rendered["ok"])
        self.assertTrue((workspace / "blog.html").is_file())
        checked = BLOG._check(workspace)
        self.assertTrue(checked["ok"])


if __name__ == "__main__":
    unittest.main()
