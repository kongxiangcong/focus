from __future__ import annotations

import importlib.util
import json
import shutil
import unittest
import uuid
from pathlib import Path

from core import BlogApplication
from core.article_blog import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    check_html,
    validate_blog_candidate,
)


ROOT = Path(__file__).resolve().parents[1]


def _load_fixtures():
    """Reuse the dual-artifact fixtures instead of keeping a second copy."""
    spec = importlib.util.spec_from_file_location(
        "fixture_blog_reading", ROOT / "tests" / "test_blog_reading_artifact.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


FIXTURE = _load_fixtures()


class HtmlRuntime(FIXTURE.ReadingRuntime):
    """Controlled Runtime that can add formulas and warnings to the Reading Blog."""

    def __init__(
        self,
        *,
        warnings=None,
        math: bool = False,
        emphasis: bool = False,
    ):
        super().__init__()
        self.warnings = list(warnings or [])
        self.math = math
        self.emphasis = emphasis

    def write_artifact(self, *, artifact, bundle, candidate, method_dir, network):
        result = super().write_artifact(
            artifact=artifact, bundle=bundle, candidate=candidate, method_dir=method_dir, network=network
        )
        files = dict(result["files"])
        if self.emphasis:
            name = "blog.md"
            files[name] += "\n\n**专业术语**：==有证据支持的关键结论==。\n"
        warnings = list(result.get("warnings", [])) + self.warnings
        if artifact == "reading_blog" and self.math:
            files["blog.md"] = files["blog.md"].replace(
                "## 实验与证据",
                "吞吐由 $T = \\frac{N}{B}$ 给出，其中 $N$ 是请求数，$B$ 是带宽。\n\n"
                "$$\\mathrm{Speedup} = \\frac{T_{\\mathrm{base}}}{T_{\\mathrm{new}}}$$\n\n"
                "## 实验与证据",
            )
        return {"files": files, "warnings": warnings}


class BlogHtmlTests(unittest.TestCase):
    """Ticket 04: one self-contained index.html with one reading page."""

    def setUp(self):
        runs = ROOT / "tmp" / "test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.root = runs / f"blog-html-{uuid.uuid4().hex[:8]}"
        self.root.mkdir()
        self.workspace = self.root / "workspace"
        self.source_root, self.bundle = self._registered_paper()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _registered_paper(self, source_id: str = "Fixture-paper"):
        source_root = self.workspace / "sources" / source_id
        bundle = source_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True, exist_ok=True)
        (source_root / "source.yaml").write_text(
            json.dumps(
                {
                    "source_kind": "paper_pdf",
                    "source_id": source_id,
                    "title": "Fixture Paper",
                    "short_name": "Fixture",
                    "identity": "fixture:blog",
                }
            ),
            encoding="utf-8",
        )
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "content.md").write_text(FIXTURE.SOURCE_CONTENT, encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "b"}\n',
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text('{"ok": true, "warnings": []}\n', encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(FIXTURE.png_bytes())
        (self.workspace / "state.json").write_text(
            json.dumps({"current_source_id": source_id, "sources": {}}), encoding="utf-8"
        )
        return source_root, bundle

    def _app(self, runtime, *, method_dir=None):
        return BlogApplication(
            self.workspace, runtime=runtime, writer_id="writer-a", method_dir=method_dir
        )

    def _broken_method_dir(self) -> Path:
        """A method pack whose renderer fails, so only rendering is broken."""
        real = ROOT / "methods" / "article-blog" / "scripts" / "article2blog.py"
        target = self.root / "broken-method"
        (target / "scripts").mkdir(parents=True)
        (target / "scripts" / "article2blog.py").write_text(
            "\n".join(
                [
                    "from pathlib import Path",
                    f"__file__ = {str(real)!r}",
                    "exec(compile(Path(__file__).read_text(encoding='utf-8'), __file__, 'exec'))",
                    "def _render(blog_dir, *, embed_images=True, bundle=None):",
                    "    raise RuntimeError('renderer exploded')",
                ]
            ),
            encoding="utf-8",
        )
        return target

    # ------------------------------------------------------- one self-contained file

    def test_generated_html_is_self_contained_with_one_page(self):
        app = self._app(HtmlRuntime(math=True))
        result = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual("completed", result["html"]["status"])
        blog = self.source_root / "blog"
        html = (blog / "index.html").read_text(encoding="utf-8")

        self.assertEqual(1, html.count('data-kind="reading_blog"'))
        self.assertNotIn('role="tab"', html)
        self.assertIn('data-kind="reading_blog"', html)

        self.assertIn("<img src=\"data:image/png;base64,", html)
        self.assertNotIn('src="http', html)
        self.assertNotIn('href="http', html)
        self.assertNotIn("url(http", html)
        self.assertIn("data-tex=", html)
        self.assertIn("katex.render", html)
        self.assertIn("data:font/woff2;base64,", html)
        self.assertNotIn('href="#bundle-section-1"', html)
        self.assertNotIn('id="bundle-section-1"', html)
        self.assertNotIn('id="bundle-figure-1"', html)
        self.assertNotIn('data-source-anchor="figure-1"', html)

        checked = validate_blog_candidate(blog, bundle=self.bundle, require_html=True)
        self.assertEqual([], checked["errors"])
        self.assertEqual(1, checked["metrics"]["html_panels"])
        self.assertEqual(1, checked["metrics"]["html_embedded_images"])

    def test_the_reading_blog_render_reading_emphasis(self):
        result = self._app(HtmlRuntime(math=True, emphasis=True)).generate(
            "Fixture-paper", request_id="emphasis", authorized_by="manual_trigger")
        self.assertEqual("completed", result["html"]["status"])
        blog = self.source_root / "blog"
        html = (blog / "index.html").read_text(encoding="utf-8")
        self.assertEqual(1, html.count('<strong>专业术语</strong>'))
        self.assertEqual(1, html.count('<mark>有证据支持的关键结论</mark>'))
        for name in ("blog.md",):
            self.assertIn("==有证据支持的关键结论==", (blog / name).read_text(encoding="utf-8"))
        checked = validate_blog_candidate(blog, bundle=self.bundle, require_html=True)
        self.assertEqual([], checked["errors"])

    # ---------------------------------------------------------------- T04 (HTML part)


    # ---------------------------------------------------------------- T17 (visible)

    def test_footer_shows_warnings_and_claims_no_quality_review(self):
        app = self._app(HtmlRuntime(warnings=["未实际运行实验脚本"], math=True))
        app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        html = (self.source_root / "blog" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("诚实降级与证据缺口", html)
        self.assertNotIn("未实际运行实验脚本", html)
        self.assertNotIn("实现核查层级", html)
        self.assertNotIn("质量通过", html)

    # ------------------------------------------------------------------- T07 / T08

    def test_render_failure_leaves_the_blog_and_the_old_html_untouched(self):
        app = self._app(HtmlRuntime())
        app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        blog = self.source_root / "blog"
        before = {
            name: (blog / name).read_bytes()
            for name in ("blog.md", "index.html", "metadata.json")
        }

        broken = self._app(HtmlRuntime(), method_dir=self._broken_method_dir())
        failed = broken.regenerate("Fixture-paper", artifact="html", request_id="req-2", authorized_by="manual_trigger")

        self.assertEqual("failed", failed["outcome"]["status"])
        self.assertEqual("blog_render_failed", failed["outcome"]["error_id"])
        for name, payload in before.items():
            if name == "metadata.json":
                continue
            self.assertEqual(payload, (blog / name).read_bytes())
        metadata = json.loads((blog / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(STATUS_FAILED, metadata["artifacts"]["html"]["status"])
        self.assertEqual(STATUS_COMPLETED, metadata["artifacts"]["reading_blog"]["status"])
        self.assertEqual([], broken.runtime.calls)

        retried = app.regenerate("Fixture-paper", artifact="html", request_id="req-3", authorized_by="manual_trigger")
        self.assertEqual("completed", retried["outcome"]["status"])
        self.assertEqual(STATUS_COMPLETED, json.loads((blog / "metadata.json").read_text(encoding="utf-8"))["artifacts"]["html"]["status"])
        self.assertIn('data-kind="reading_blog"', (blog / "index.html").read_text(encoding="utf-8"))
        # Re-rendering rewrites only index.html.
        for name in ("blog.md",):
            self.assertEqual(before[name], (blog / name).read_bytes())
        self.assertNotIn("html", app.runtime.calls)

    def test_regenerating_an_article_follows_with_a_re_render(self):
        app = self._app(HtmlRuntime())
        app.runtime.reading_body = "# 太短\n"
        first = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        self.assertEqual("failed", first["outcome"]["status"])

        app.runtime.reading_body = FIXTURE.READING_BLOG
        retried = app.regenerate(
            "Fixture-paper", artifact="reading_blog", request_id="req-2", authorized_by="manual_trigger"
        )
        self.assertEqual("completed", retried["outcome"]["status"])
        self.assertEqual("completed", retried["html"]["status"])
        html = (self.source_root / "blog" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('class="not-applicable"', html)




if __name__ == "__main__":
    unittest.main()


class BlogHtmlValidatorTests(unittest.TestCase):
    @staticmethod
    def document(body="<p>Reading</p>", extra="", active="true"):
        return ('<!doctype html><html><head>' + extra + '</head><body>'
                '<section id="panel-0" data-kind="reading_blog" data-active="' + active + '">' + body + '</section></body></html>')

    def test_single_page_passes(self):
        self.assertEqual(([], []), check_html(self.document()))

    def test_artifact_tabs_are_rejected(self):
        self.assertTrue(check_html(self.document('<button role="tab">old tab</button>'))[0])

    def test_extra_page_is_rejected(self):
        self.assertTrue(check_html(self.document().replace('</body>', '<section id="panel-1">old page</section></body>'))[0])

    def test_hidden_reading_page_is_rejected(self):
        self.assertTrue(check_html(self.document(active="false"))[0])

    def test_external_stylesheet_is_rejected(self):
        self.assertTrue(any('self-contained' in e for e in check_html(self.document(extra='<link href="https://cdn.test/a.css">'))[0]))

    def test_linked_image_is_rejected(self):
        self.assertTrue(any('not embedded' in e for e in check_html(self.document('<img src="assets/x.png">'))[0]))

    def test_formulas_require_renderer(self):
        self.assertTrue(any('formula renderer' in e for e in check_html(self.document('<span data-tex="x">x</span>'))[0]))
