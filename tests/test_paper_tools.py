from __future__ import annotations

import importlib.util
import io
import json
import os
import unittest
import shutil
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
        validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
        self.assertTrue(validation["ok"])

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
