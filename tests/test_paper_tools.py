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
                (output / "content.md").write_text(
                    "# Fixture Paper\n\n![Figure](images/image-001.png)\n", encoding="utf-8"
                )
                (output / "images" / "image-001.png").write_bytes(b"image")
                (output / "metadata.json").write_text(
                    json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "paper-parser", "batch_id": batch_id}),
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
        self.assertEqual("fixture-paper", response["source_id"])
        source_root = workspace / "sources" / "fixture-paper"
        self.assertTrue((source_root / "parser-bundle" / "source.pdf").is_file())
        paper = json.loads((source_root / "source.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["accelerator-architecture"], paper["topics"])
        topic = json.loads(
            (workspace / "topics" / "accelerator-architecture" / "topic.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(["fixture-paper"], topic["sources"])
        pointers = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("fixture-paper", pointers["current_source_id"])
        self.assertEqual(
            {
                "current_plan_id": None,
                "current_chunk_id": None,
            },
            pointers["sources"]["fixture-paper"],
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
                (output / "content.md").write_text("# Incomplete\n", encoding="utf-8")
                (output / "metadata.json").write_text(
                    '{"source_kind": "paper_pdf", "language": "en", "parser": "paper-parser", "batch_id": "fixture-batch"}\n', encoding="utf-8"
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
        self.assertFalse((workspace / "sources" / "incomplete" / "source.yaml").exists())
        self.assertFalse((workspace / "topics" / "parsing" / "topic.yaml").exists())
        self.assertFalse((workspace / "state.json").exists())

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
                (output / "content.md").write_text("# Rollback\n", encoding="utf-8")
                (output / "metadata.json").write_text(
                    json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "paper-parser", "batch_id": batch_id}), encoding="utf-8"
                )
                (output / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")

        write_document = WORKSPACE_CORE._write_document

        def fail_pointer_write(path, value):
            if path.name == "state.json":
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
        self.assertFalse((workspace / "sources" / "rollback-paper").exists())
        self.assertFalse((workspace / "topics" / "failure-safety" / "topic.yaml").exists())
        self.assertFalse((workspace / "state.json").exists())
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
                (output / "content.md").write_text("# Resumed\n", encoding="utf-8")
                (output / "metadata.json").write_text(
                    json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "paper-parser", "batch_id": batch_id}),
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
        self.assertFalse((workspace / "sources" / "resumed-paper" / "source.yaml").exists())
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
        self.assertTrue((workspace / "sources" / "resumed-paper" / "source.yaml").is_file())
        self.assertEqual(
            b"%PDF-1.4\nfixture\n",
            (workspace / "sources" / "resumed-paper" / "parser-bundle" / "source.pdf").read_bytes(),
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
                (output / "content.md").write_text(f"# Version {batch_id}\n", encoding="utf-8")
                (output / "metadata.json").write_text(
                    json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "paper-parser", "batch_id": batch_id}),
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
        original = (workspace / "sources" / "collision-paper" / "parser-bundle" / "content.md").read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, PARSER.main(command, hosted=hosted))

        self.assertEqual(
            original,
            (workspace / "sources" / "collision-paper" / "parser-bundle" / "content.md").read_bytes(),
        )
        self.assertTrue((workspace / "sources" / "collision-paper-002" / "source.yaml").is_file())
        topic = json.loads((workspace / "topics" / "identity" / "topic.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["collision-paper", "collision-paper-002"], topic["sources"])

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
        self.assertTrue((workspace / "sources" / "可配置脉动阵列" / "source.yaml").is_file())

    def test_existing_paper_is_reused_only_by_explicit_selection(self):
        workspace = self.root / "workspace"
        bundle = workspace / "sources" / "existing-paper" / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "content.md").write_text("# Existing\n", encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"source_kind": "paper_pdf", "language": "en", "parser": "paper-parser", "batch_id": "fixture-batch"}\n', encoding="utf-8"
        )
        (bundle / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")
        (bundle.parent / "source.yaml").write_text(
            json.dumps({"source_kind": "paper_pdf", "source_id": "existing-paper", "title": "Existing Paper", "topics": []}),
            encoding="utf-8",
        )
        before = (bundle / "content.md").read_bytes()

        with contextlib.redirect_stdout(io.StringIO()):
            result = PARSER.main(
                [
                    "reuse",
                    "--workspace",
                    str(workspace),
                    "--source-id",
                    "existing-paper",
                    "--topic",
                    "Second Topic",
                ]
            )

        self.assertEqual(0, result)
        paper = json.loads((bundle.parent / "source.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["second-topic"], paper["topics"])
        topic = json.loads((workspace / "topics" / "second-topic" / "topic.yaml").read_text(encoding="utf-8"))
        self.assertEqual(["existing-paper"], topic["sources"])
        self.assertEqual(before, (bundle / "content.md").read_bytes())

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
        paper = (output / "content.md").read_text(encoding="utf-8")
        self.assertIn("![Second](images/image-001.png)", paper)
        self.assertIn("![First](images/image-002.jpg)", paper)
        self.assertEqual(b"second-image", (output / "images" / "image-001.png").read_bytes())
        self.assertEqual(b"first-image", (output / "images" / "image-002.jpg").read_bytes())
        self.assertFalse((output / "raw").exists())
        self.assertFalse((output / "images" / "unreferenced.png").exists())
        metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual("paper-parser", metadata["parser"])
        self.assertEqual("source-reference-order", metadata["image_naming"])
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
                    "--source-id",
                    "paper",
                    "--topic",
                    "Topic",
                ]
            )
        self.assertEqual(1, result)
        self.assertEqual("workspace_missing", json.loads(stderr.getvalue())["error_id"])

        workspace = self.root / "workspace-errors"
        workspace.mkdir()
        for source_id, expected in (("missing", "source_missing"), ("no-bundle", "parser_bundle_missing")):
            if source_id == "no-bundle":
                source_root = workspace / "sources" / source_id
                source_root.mkdir(parents=True)
                (source_root / "source.yaml").write_text(
                    json.dumps({"source_kind": "paper_pdf", "source_id": source_id, "title": "No Bundle", "topics": []}),
                    encoding="utf-8",
                )
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = PARSER.main(
                    [
                        "reuse",
                        "--workspace",
                        str(workspace),
                        "--source-id",
                        source_id,
                        "--topic",
                        "Topic",
                    ]
                )
            self.assertEqual(1, result)
            self.assertEqual(expected, json.loads(stderr.getvalue())["error_id"])

        source_root = workspace / "sources" / "valid-paper"
        bundle = source_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "content.md").write_text("# Valid\n", encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"source_kind": "paper_pdf", "language": "en", "parser": "paper-parser", "batch_id": "fixture-batch"}\n', encoding="utf-8"
        )
        (bundle / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")
        (source_root / "source.yaml").write_text(
            json.dumps({"source_kind": "paper_pdf", "source_id": "valid-paper", "title": "Valid", "topics": []}), encoding="utf-8"
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = PARSER.main(
                [
                    "reuse",
                    "--workspace",
                    str(workspace),
                    "--source-id",
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
        try:
            with mock.patch.object(PARSER.urllib.request, "urlopen", side_effect=remote_error):
                with self.assertRaises(PARSER.ParserError) as caught:
                    PARSER._request("GET", "https://mineru.net/api/v4/file-urls/batch", token="token")
        finally:
            remote_error.close()

        self.assertNotIn("echoed-token-value", str(caught.exception))


class PaperToBlogTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"paper-blog-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _registered_paper(self, *, valid_bundle: bool = True):
        workspace = self.root / "workspace"
        source_root = workspace / "sources" / "fixture-paper"
        bundle = source_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (source_root / "source.yaml").write_text(
            json.dumps({"source_kind": "paper_pdf", "source_id": "fixture-paper", "title": "Fixture Paper", "topics": ["systems"]}),
            encoding="utf-8",
        )
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "content.md").write_text(
            "# Fixture Paper\n\n## Method\nEvidence.\n\n![Figure](images/image-001.png)\n",
            encoding="utf-8",
        )
        (bundle / "metadata.json").write_text(
            '{"title": "Fixture Paper", "source_kind": "paper_pdf", "language": "en", "parser": "paper-parser", "batch_id": "fixture-batch"}\n',
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text(
            json.dumps({"ok": valid_bundle}) + "\n",
            encoding="utf-8",
        )
        (bundle / "images" / "image-001.png").write_bytes(b"fixture")
        (workspace / "state.json").write_bytes(b"not blog input\n")
        reading = source_root / "reading"
        (reading / "plans" / "plan-001").mkdir(parents=True)
        (reading / "plans" / "plan-001" / "chunks.jsonl").write_bytes(b"private chunks\n")
        (reading / "plans" / "plan-001" / "glossary.tsv").write_bytes(b"private glossary\n")
        return workspace, source_root, bundle

    @staticmethod
    def _snapshot(paths):
        return {path: path.read_bytes() for root in paths for path in root.rglob("*") if path.is_file()}

    def test_registered_paper_blog_is_generated_beside_bundle_without_reading_access(self):
        workspace, source_root, bundle = self._registered_paper()
        protected_before = self._snapshot((bundle, source_root / "reading"))
        pointers_before = (workspace / "state.json").read_bytes()

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            prepared = BLOG.main(
                ["prepare", "--workspace", str(workspace), "--source-id", "fixture-paper"]
            )

        self.assertEqual(0, prepared)
        response = json.loads(stdout.getvalue())
        blog = source_root / "blog"
        self.assertEqual(str(blog.resolve()), response["output"])
        self.assertTrue((blog / "evidence-map.md").is_file())
        self.assertTrue((blog / "content.md").is_file())
        self.assertTrue((blog / "metadata.json").is_file())
        self.assertTrue((blog / "assets" / "image-001.png").is_file())

        (blog / "evidence-map.md").write_text("# Evidence Map\n\nComplete evidence.\n", encoding="utf-8")
        (blog / "blog.md").write_text(
            "# 技术博客\n\n## 方法与设计\n\n## 实验与证据\n\n## 局限与边界\n\n"
            "![Figure](assets/image-001.png)\n\n## 参考文献\n\n" + "正文证据。" * 500,
            encoding="utf-8",
        )
        with mock.patch.object(
            BLOG,
            "_render_markdown",
            return_value='<h1>技术博客</h1><img src="assets/image-001.png"><p>正文</p>',
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                rendered = BLOG.main(["render", str(blog)])

        self.assertEqual(0, rendered)
        self.assertTrue((blog / "blog.html").is_file())
        self.assertEqual(protected_before, self._snapshot((bundle, source_root / "reading")))
        self.assertEqual(pointers_before, (workspace / "state.json").read_bytes())

    def test_failed_registered_paper_blog_returns_structured_error_without_mutating_private_data(self):
        workspace, source_root, bundle = self._registered_paper(valid_bundle=False)
        protected_before = self._snapshot((bundle, source_root / "reading"))
        pointers_before = (workspace / "state.json").read_bytes()
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            result = BLOG.main(
                ["prepare", "--workspace", str(workspace), "--source-id", "fixture-paper"]
            )

        self.assertEqual(1, result)
        self.assertEqual("parser_bundle_invalid", json.loads(stderr.getvalue())["error_id"])
        self.assertFalse((source_root / "blog").exists())
        self.assertEqual(protected_before, self._snapshot((bundle, source_root / "reading")))
        self.assertEqual(pointers_before, (workspace / "state.json").read_bytes())

    def test_public_prepare_rejects_unregistered_bundle_and_caller_selected_output(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                BLOG.main(["prepare", str(self.root / "bundle"), "--output", str(self.root / "blog")])

        self.assertEqual(2, caught.exception.code)

    def test_prepare_and_check_workspace(self):
        bundle = self.root / "bundle"
        (bundle / "images").mkdir(parents=True)
        (bundle / "content.md").write_text(
            "# A Paper\n\n## Method\nEvidence.\n\n![Figure](images/image-001.png)\n",
            encoding="utf-8",
        )
        (bundle / "metadata.json").write_text(
            '{"title": "A Paper", "source_kind": "paper_pdf", "language": "en", "parser": "paper-parser", "batch_id": "fixture-batch"}\n',
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
            (workspace / "content.md").read_text(encoding="utf-8"),
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

        original_blog = (workspace / "blog.md").read_text(encoding="utf-8")
        (workspace / "blog.md").write_text(original_blog.replace("正文", "证据"), encoding="utf-8")
        stale = BLOG._check(workspace)
        self.assertFalse(stale["ok"])
        self.assertIn("blog.html is stale or not rendered from the current blog.md", stale["errors"])


if __name__ == "__main__":
    unittest.main()
