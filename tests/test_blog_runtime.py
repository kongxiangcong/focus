"""The real Runtime adapter returns candidates for guarded Core commits."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from host.blog_runtime import CodexBlogRuntime, READING_BLOG_SCHEMA, VALUE_ANALYSIS_SCHEMA


class RecordingCodexBlogRuntime(CodexBlogRuntime):
    def __init__(self):
        self.calls = []

    def _run(self, prompt, *, cwd, schema=None):
        self.calls.append((prompt, cwd, schema))
        if schema is READING_BLOG_SCHEMA:
            return {"evidence_map": "# 原文证据", "blog": "# 带读博客"}
        return {"value_analysis": "# 论文价值分析"}


class BlogRuntimeTests(unittest.TestCase):
    def test_returns_structured_articles_without_model_file_writes(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            bundle = base / "bundle"
            bundle.mkdir()
            (bundle / "content.md").write_text("## 1 Method\nFigure 1 shows the design.", encoding="utf-8")
            candidate = base / "candidate"
            (candidate / "assets").mkdir(parents=True)
            (candidate / "assets" / "image-001.png").write_bytes(b"fixture")
            (candidate / "evidence").mkdir()
            (candidate / "evidence" / "evidence-map.md").write_text("# 共享证据", encoding="utf-8")
            (candidate / "evidence" / "implementation-notes.md").write_text("仅论文阅读", encoding="utf-8")
            runtime = RecordingCodexBlogRuntime()

            reading = runtime.write_artifact(
                artifact="reading_blog", bundle=bundle, candidate=candidate,
                method_dir=root / "methods/article-blog", network=False,
            )
            value = runtime.write_artifact(
                artifact="value_analysis", bundle=bundle, candidate=candidate,
                method_dir=root / "methods/article-blog", network=False,
            )

            self.assertEqual({"evidence/evidence-map.md", "blog.md"}, set(reading["files"]))
            self.assertEqual({"value-analysis.md": "# 论文价值分析"}, value["files"])
            self.assertFalse((candidate / "blog.md").exists())
            self.assertIn("Figure 1 shows the design", runtime.calls[0][0])
            self.assertIn("image-001.png", runtime.calls[0][0])
            self.assertIn("# 共享证据", runtime.calls[1][0])
            self.assertIn("仅论文阅读", runtime.calls[1][0])


if __name__ == "__main__":
    unittest.main()
