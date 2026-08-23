from __future__ import annotations

import importlib.util
import io
import json
import unittest
import shutil
import uuid
import zipfile
from pathlib import Path


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

    def test_normalize_preserves_raw_and_builds_stable_bundle(self):
        source = self.root / "input.pdf"
        source.write_bytes(b"%PDF-1.4\nfixture\n")
        archive = self.root / "result.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("paper/full.md", "# Fixture Paper\n\n![Figure](images/fig.png)\n")
            bundle.writestr("paper/images/fig.png", b"not-a-real-image")
            bundle.writestr("paper/fixture_content_list.json", "[]")
        output = self.root / "output"

        PARSER._normalize(source, archive, output, "batch-fixture", "vlm", "en")

        self.assertEqual(source.read_bytes(), (output / "source.pdf").read_bytes())
        self.assertIn("Fixture Paper", (output / "paper.md").read_text(encoding="utf-8"))
        self.assertTrue((output / "images" / "fig.png").is_file())
        self.assertTrue((output / "raw" / "mineru" / "paper" / "fixture_content_list.json").is_file())
        metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual("mineru-precision-api", metadata["parser"])
        self.assertNotIn("token", json.dumps(metadata).lower())
        validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
        self.assertTrue(validation["ok"])

    def test_safe_extract_rejects_path_traversal(self):
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../escape.txt", "bad")
        with self.assertRaises(PARSER.ParserError):
            PARSER._safe_extract(archive, self.root / "output")


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
        (bundle / "paper.md").write_text("# A Paper\n\n## Method\nEvidence.\n", encoding="utf-8")
        (bundle / "metadata.json").write_text('{"title": "A Paper"}\n', encoding="utf-8")
        (bundle / "images" / "fig.png").write_bytes(b"fixture")
        workspace = self.root / "blog"

        prepared = BLOG._prepare(bundle, workspace)

        self.assertTrue(prepared["ok"])
        self.assertTrue((workspace / "assets" / "fig.png").is_file())
        self.assertIn("A Paper", (workspace / "evidence-map.md").read_text(encoding="utf-8"))
        failed = BLOG._check(workspace)
        self.assertFalse(failed["ok"])
        self.assertIn("blog.md is missing", failed["errors"])


if __name__ == "__main__":
    unittest.main()
