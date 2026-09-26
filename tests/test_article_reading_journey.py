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
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


ARTICLE = load_module("journey_article", ROOT / ".agents/skills/article-parser/scripts/article_parser.py")
FOCUS_MAP = load_module("journey_article_map", ROOT / ".agents/skills/focus-map/scripts/focus_map.py")
FOCUS_READ = load_module("journey_article_read", ROOT / ".agents/skills/focus-read/scripts/focus_read.py")
ARTICLE_BLOG = load_module("journey_article_blog", ROOT / "methods" / "article-blog" / "scripts" / "article2blog.py")


class ArticleReadingJourneyTests(unittest.TestCase):
    def setUp(self):
        runs = ROOT / "tmp" / "test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.root = runs / f"a-{uuid.uuid4().hex[:8]}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    @staticmethod
    def _run(module, args, **kwargs):
        stdin = kwargs.pop("stdin", "")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), mock.patch("sys.stdin", io.StringIO(stdin)):
            code = module.main(args, **kwargs)
        text = stdout.getvalue() if code == 0 else stderr.getvalue()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = json.loads(text.splitlines()[-1])
        return code, payload

    def test_local_article_parse_map_read_and_blog_prepare_share_one_bundle(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        html = self.root / "article.html"
        html.write_text("<html><head><title>中文系统文章</title></head><body><article><h1>中文系统文章</h1>"
                        "<h2>第一节</h2><p>第一段解释统一读写路径。" + "来源内容应当保持完整。" * 10 +
                        "</p><h2>第二节</h2><p>第二段解释游标推进。</p></article></body></html>", encoding="utf-8")

        code, parsed = self._run(
            ARTICLE,
            [
                "parse-file",
                str(html),
                "--workspace",
                str(workspace),
                "--title",
                "中文系统文章",
                "--short-name",
                "中文系统",
                "--topic",
                "系统",
            ],
        )
        self.assertEqual(0, code)
        source_id = parsed["source_id"]
        draft = json.dumps(
                {
                    "chunks": [
                        {"section_path": ["中文系统文章", "第一节"], "source_lines": [1, 5], "images": []},
                        {"section_path": ["中文系统文章", "第二节"], "source_lines": [6, 7], "images": []},
                    ],
                    "glossary": [],
                },
                ensure_ascii=False,
        )

        code, mapped = self._run(
            FOCUS_MAP,
            ["map", "--workspace", str(workspace), "--source-id", source_id],
            stdin=draft,
        )
        self.assertEqual((0, "plan-001"), (code, mapped["plan_id"]))
        from core import WorkspaceCore
        core = WorkspaceCore(workspace)
        current = core.reading_window()["current"]
        self.assertEqual("source_ready", current["status"])
        self.assertIn("第一段解释统一读写路径", current["source_text"])
        self.assertIsNone(current["translation"])
        self.assertEqual(source_id, core.reading_window()["source"]["source_id"])

        code, rejected = self._run(
            ARTICLE_BLOG,
            [
                "prepare",
                "--workspace",
                str(workspace),
                "--source-id",
                source_id,
                "--candidate",
                str(self.root / "blog-candidate"),
            ],
        )
        self.assertEqual(0, code)
        self.assertEqual("article_html", rejected["metadata"]["source_kind"])


if __name__ == "__main__":
    unittest.main()
