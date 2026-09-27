from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import unittest
import uuid
import zlib
from pathlib import Path

from core import (
    ARTICLE_BLOG_METHOD_VERSION,
    BlogCore,
    WorkspaceError,
    blog_root,
    blog_status,
    bundle_fingerprint,
    validate_blog_candidate,
    validate_blog_metadata,
)
from core.article_blog import STATUS_COMPLETED, STATUS_FAILED, STATUS_PENDING


ROOT = Path(__file__).resolve().parents[1]
METHODS = ROOT / "methods" / "article-blog"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


ARTICLE2BLOG = load_module("focus_article2blog", METHODS / "scripts" / "article2blog.py")

def png_bytes(payload: bytes = b"figure") -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return len(body).to_bytes(4, "big") + kind + body + (zlib.crc32(kind + body) & 0xFFFFFFFF).to_bytes(4, "big")

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 6, 0, 0, 0]))
    return header + ihdr + chunk(b"IDAT", zlib.compress(payload)) + chunk(b"IEND", b"")


BLOG_BODY = "\n".join(
    [
        "# 固件论文带读",
        "",
        "## 导语与问题背景",
        "",
        "本文要解决的是一个具体的吞吐瓶颈。" + "展开说明。" * 140,
        "",
        "## 方法与机制",
        "",
        "核心模块按输入、输出与设计原因展开；公式说明变量与约束。" + "机制细节。" * 140,
        "",
        "## 实验与证据",
        "",
        "表格说明指标方向、基线与决定性差异；消融支持哪个设计选择。" + "证据细节。" * 140,
        "",
        "![Figure 1](assets/image-001.png)",
        "",
        "## 局限与边界",
        "",
        "结果只在给定配置下成立。" + "边界说明。" * 90,
        "",
        "## 参考文献",
        "",
        "1. Fixture Authors. 2026. Fixture Paper. arXiv:0000.0000。",
    ]
)

EVIDENCE_BODY = "\n".join(
    [
        "# Evidence Map",
        "",
        "## 贡献与原文锚点",
        "",
        "| 贡献 | 原文锚点 | 报告的证据 | 假设与边界 |",
        "|---|---|---|---|",
        "| 提升吞吐 | 第 3 节 | Table 2 | 仅在单核配置下验证 |",
    ]
)


class ArticleBlogMethodPackTests(unittest.TestCase):
    def setUp(self):
        runs = ROOT / "tmp" / "test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.root = runs / f"article-blog-{uuid.uuid4().hex[:8]}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    @staticmethod
    def _snapshot(paths):
        return {path: path.read_bytes() for root in paths for path in root.rglob("*") if path.is_file()}

    def _registered_paper(self, *, valid_bundle: bool = True):
        workspace = self.root / "workspace"
        source_root = workspace / "sources" / "Fixture-paper"
        bundle = source_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (source_root / "source.yaml").write_text(
            json.dumps(
                {
                    "source_kind": "paper_pdf",
                    "source_id": "Fixture-paper",
                    "title": "Fixture Paper",
                    "short_name": "Fixture",
                    "identity": "fixture:blog",
                }
            ),
            encoding="utf-8",
        )
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "content.md").write_text(
            "# Fixture Paper\n\n## Method\nEvidence.\n\n![Figure](images/image-001.png)\n",
            encoding="utf-8",
        )
        (bundle / "metadata.json").write_text(
            '{"title": "Fixture Paper", "source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "fixture-batch"}\n',
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text(json.dumps({"ok": valid_bundle}) + "\n", encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(png_bytes())
        (workspace / "state.json").write_bytes(b"not blog input\n")
        reading = source_root / "reading"
        (reading / "plans" / "plan-001").mkdir(parents=True)
        (reading / "plans" / "plan-001" / "chunks.jsonl").write_bytes(b"private chunks\n")
        (reading / "plans" / "plan-001" / "glossary.tsv").write_bytes(b"private glossary\n")
        return workspace, source_root, bundle

    @staticmethod
    def _cli(module, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = module.main(args)
        text = stdout.getvalue() if code == 0 else stderr.getvalue()
        return code, json.loads(text)

    def test_pack_exposes_one_method_entry_with_unified_script_name(self):
        self.assertTrue((METHODS / "SKILL.md").is_file())
        self.assertTrue((METHODS / "reference" / "reading-blog-method.md").is_file())
        self.assertTrue((METHODS / "reference" / "value-analysis-method.md").is_file())
        self.assertTrue((METHODS / "scripts" / "article2blog.py").is_file())
        self.assertFalse((METHODS / "scripts" / "paper2blog.py").exists())
        self.assertFalse((ROOT / ".agents" / "skills" / "paper2blog").exists())
        self.assertIn(ARTICLE_BLOG_METHOD_VERSION, (METHODS / "SKILL.md").read_text(encoding="utf-8"))

    def test_prepare_builds_skeleton_and_core_publishes_blog_without_reading_access(self):
        workspace, source_root, bundle = self._registered_paper()
        protected_before = self._snapshot((bundle, source_root / "reading"))
        pointers_before = (workspace / "state.json").read_bytes()
        candidate = source_root / ".blog-candidate"

        code, prepared = self._cli(
            ARTICLE2BLOG,
            ["prepare", "--workspace", str(workspace), "--source-id", "Fixture-paper", "--candidate", str(candidate)],
        )

        self.assertEqual(0, code)
        self.assertTrue(prepared["ok"])
        self.assertFalse(blog_root(workspace, "Fixture-paper").exists())

        core = BlogCore(workspace)
        installed = core.install_prepared(
            source_id="Fixture-paper", candidate=candidate, writer_id="test-writer", request_id="req-1"
        )
        self.assertEqual("installed", installed["status"])

        blog = source_root / "blog"
        self.assertTrue((blog / "evidence" / "evidence-map.md").is_file())
        self.assertTrue((blog / "evidence" / "implementation-notes.md").is_file())
        self.assertTrue((blog / "assets" / "image-001.png").is_file())
        self.assertTrue((blog / "metadata.json").is_file())
        self.assertFalse((blog / "source.pdf").exists())

        metadata = json.loads((blog / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual("Fixture-paper", metadata["source_id"])
        self.assertEqual("article-blog", metadata["method"])
        self.assertEqual(ARTICLE_BLOG_METHOD_VERSION, metadata["method_version"])
        self.assertEqual(bundle_fingerprint(bundle), metadata["bundle_fingerprint"])
        validate_blog_metadata(metadata, source_id="Fixture-paper", bundle=bundle)

        status = blog_status(workspace, "Fixture-paper")
        self.assertTrue(status["generated"])
        self.assertEqual(
            {"value_analysis": STATUS_PENDING, "reading_blog": STATUS_PENDING, "html": STATUS_PENDING},
            {name: entry["status"] for name, entry in status["artifacts"].items()},
        )
        self.assertEqual(protected_before, self._snapshot((bundle, source_root / "reading")))
        self.assertEqual(pointers_before, (workspace / "state.json").read_bytes())

    def test_replayed_install_returns_the_recorded_result_without_republishing(self):
        workspace, source_root, _ = self._registered_paper()
        candidate = source_root / ".blog-candidate"
        self._cli(
            ARTICLE2BLOG,
            ["prepare", "--workspace", str(workspace), "--source-id", "Fixture-paper", "--candidate", str(candidate)],
        )
        core = BlogCore(workspace)
        first = core.install_prepared(
            source_id="Fixture-paper", candidate=candidate, writer_id="test-writer", request_id="req-1"
        )
        blog = source_root / "blog"
        (blog / "blog.md").write_text(BLOG_BODY, encoding="utf-8")
        before = self._snapshot((blog,))
        replay = core.install_prepared(
            source_id="Fixture-paper", candidate=blog, writer_id="test-writer", request_id="req-1"
        )
        self.assertEqual(first["version"], replay["version"])
        self.assertEqual(before, self._snapshot((blog,)))

    def test_a_second_writer_cannot_commit_blog_assets(self):
        workspace, source_root, _ = self._registered_paper()
        candidate = source_root / ".blog-candidate"
        self._cli(
            ARTICLE2BLOG,
            ["prepare", "--workspace", str(workspace), "--source-id", "Fixture-paper", "--candidate", str(candidate)],
        )
        core = BlogCore(workspace)
        core.install_prepared(
            source_id="Fixture-paper", candidate=candidate, writer_id="writer-a", request_id="req-1"
        )
        with self.assertRaises(WorkspaceError) as caught:
            core.commit(
                source_id="Fixture-paper",
                files={"blog.md": BLOG_BODY},
                statuses={"reading_blog": STATUS_COMPLETED},
                writer_id="writer-b",
                request_id="req-2",
            )
        self.assertEqual("writer_conflict", caught.exception.error_id)
        self.assertFalse((source_root / "blog" / "blog.md").exists())

    def test_commit_is_idempotent_and_records_status(self):
        workspace, source_root, _ = self._registered_paper()
        candidate = source_root / ".blog-candidate"
        self._cli(
            ARTICLE2BLOG,
            ["prepare", "--workspace", str(workspace), "--source-id", "Fixture-paper", "--candidate", str(candidate)],
        )
        core = BlogCore(workspace)
        core.install_prepared(
            source_id="Fixture-paper", candidate=candidate, writer_id="writer-a", request_id="req-1"
        )
        first = core.commit(
            source_id="Fixture-paper",
            files={"blog.md": BLOG_BODY},
            statuses={"reading_blog": STATUS_COMPLETED},
            writer_id="writer-a",
            request_id="req-2",
        )
        written = (source_root / "blog" / "blog.md").read_text(encoding="utf-8")
        (source_root / "blog" / "blog.md").write_text("tampered", encoding="utf-8")
        replay = core.commit(
            source_id="Fixture-paper",
            files={"blog.md": "other"},
            statuses={"reading_blog": STATUS_FAILED},
            writer_id="writer-a",
            request_id="req-2",
        )
        self.assertEqual(first["version"], replay["version"])
        self.assertEqual("tampered", (source_root / "blog" / "blog.md").read_text(encoding="utf-8"))
        status = blog_status(workspace, "Fixture-paper")
        self.assertEqual(STATUS_COMPLETED, status["artifacts"]["reading_blog"]["status"])
        self.assertEqual(written, BLOG_BODY)

    def test_prepare_rejects_an_invalid_bundle_without_touching_private_data(self):
        workspace, source_root, bundle = self._registered_paper(valid_bundle=False)
        protected_before = self._snapshot((bundle, source_root / "reading"))
        pointers_before = (workspace / "state.json").read_bytes()

        code, payload = self._cli(
            ARTICLE2BLOG,
            [
                "prepare",
                "--workspace",
                str(workspace),
                "--source-id",
                "Fixture-paper",
                "--candidate",
                str(source_root / ".blog-candidate"),
            ],
        )

        self.assertEqual(1, code)
        self.assertEqual("parser_bundle_invalid", payload["error_id"])
        self.assertFalse(blog_root(workspace, "Fixture-paper").exists())
        self.assertEqual(protected_before, self._snapshot((bundle, source_root / "reading")))
        self.assertEqual(pointers_before, (workspace / "state.json").read_bytes())

    def test_prepare_and_check_a_blog_workspace(self):
        bundle = self.root / "bundle"
        (bundle / "images").mkdir(parents=True)
        (bundle / "content.md").write_text(
            "# A Paper\n\n## Method\nEvidence.\n\n![Figure](images/image-001.png)\n",
            encoding="utf-8",
        )
        (bundle / "metadata.json").write_text(
            '{"title": "A Paper", "source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "fixture-batch"}\n',
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(png_bytes())
        blog = self.root / "blog"

        prepared = ARTICLE2BLOG._prepare(bundle, blog)
        self.assertTrue(prepared["ok"])
        self.assertTrue((blog / "assets" / "image-001.png").is_file())
        self.assertFalse((blog / "source.pdf").exists())
        self.assertIn("A Paper", (blog / "evidence" / "evidence-map.md").read_text(encoding="utf-8"))

        failed = validate_blog_candidate(blog, bundle=bundle)
        self.assertFalse(failed["ok"])
        self.assertIn("blog.md is missing or empty", failed["errors"])

        (blog / "evidence" / "evidence-map.md").write_text(EVIDENCE_BODY, encoding="utf-8")
        (blog / "blog.md").write_text(BLOG_BODY, encoding="utf-8")
        rendered = ARTICLE2BLOG._render(blog)
        self.assertTrue(rendered["ok"])
        html = (blog / "index.html").read_text(encoding="utf-8")
        self.assertIn("<h1>", html)
        # Self-contained by default: the referenced image is inlined, not linked.
        self.assertIn("data:image/png;base64,", html)
        self.assertNotIn('src="assets/image-001.png"', html)

        checked = validate_blog_candidate(blog, bundle=bundle)
        self.assertEqual([], checked["errors"])
        self.assertTrue(checked["ok"])

    def test_reading_html_omits_internal_diagnostics_without_changing_evidence(self):
        blog = self.root / "quiet-blog"
        bundle = self.root / "quiet-bundle"
        (blog / "evidence").mkdir(parents=True)
        bundle.mkdir()
        (bundle / "content.md").write_text("## 2 Method\nInternal source excerpt.\n", encoding="utf-8")
        (blog / "blog.md").write_text("# Reading\n\n第 2 节解释了方法。\n", encoding="utf-8")
        metadata = {"warnings": ["审计证据与证据缺口"], "verification_level": "paper_reading"}
        (blog / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        evidence = blog / "evidence" / "evidence-map.md"
        evidence.write_text("原文锚点和内部审计证据", encoding="utf-8")
        protected = (blog / "metadata.json", evidence, blog / "blog.md")
        before = {path: path.read_bytes() for path in protected}
        ARTICLE2BLOG._render(blog, bundle=bundle)
        markup = (blog / "index.html").read_text(encoding="utf-8")
        self.assertIn("第 2 节解释了方法", markup)
        self.assertNotIn('<aside class="source-evidence">', markup)
        self.assertNotIn('href="#bundle-', markup)
        self.assertNotIn("<footer>", markup)
        for label in ("原文锚点", "证据缺口", "审计证据", "实现核查层级"):
            self.assertNotIn(label, markup)
        self.assertEqual(before, {path: path.read_bytes() for path in protected})

    def test_check_reports_a_stale_html(self):
        bundle = self.root / "bundle"
        (bundle / "images").mkdir(parents=True)
        (bundle / "content.md").write_text("# A Paper\n\nEvidence.\n", encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "b"}\n',
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")
        blog = self.root / "blog"
        ARTICLE2BLOG._prepare(bundle, blog)
        (blog / "evidence" / "evidence-map.md").write_text(EVIDENCE_BODY, encoding="utf-8")
        (blog / "blog.md").write_text(BLOG_BODY, encoding="utf-8")
        ARTICLE2BLOG._render(blog)
        (blog / "blog.md").write_text(BLOG_BODY + "\n补充一句。\n", encoding="utf-8")
        stale_time = (blog / "index.html").stat().st_mtime_ns + 1_000_000_000
        os.utime(blog / "blog.md", ns=(stale_time, stale_time))
        checked = ARTICLE2BLOG._check(blog, require_html=True)
        self.assertFalse(checked["ok"])
        self.assertIn("index.html is stale or not rendered from the current blog.md", checked["errors"])

    def test_bundle_fingerprint_binding_detects_a_changed_bundle(self):
        workspace, source_root, bundle = self._registered_paper()
        candidate = source_root / ".blog-candidate"
        self._cli(
            ARTICLE2BLOG,
            ["prepare", "--workspace", str(workspace), "--source-id", "Fixture-paper", "--candidate", str(candidate)],
        )
        metadata = json.loads((candidate / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(bundle_fingerprint(bundle), metadata["bundle_fingerprint"])
        (bundle / "content.md").write_text("# Fixture Paper\n\nDifferent body.\n", encoding="utf-8")
        with self.assertRaises(WorkspaceError) as caught:
            validate_blog_metadata(metadata, source_id="Fixture-paper", bundle=bundle)
        self.assertEqual("blog_bundle_mismatch", caught.exception.error_id)


class ArticleBlogBoundaryTests(unittest.TestCase):
    @staticmethod
    def _tracked_paths():
        completed = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
        )
        return completed.stdout.splitlines()

    def test_active_surface_has_no_paper2blog_reference(self):
        allowed = {
            # The historical asset name is only defined where it is retired.
            "CONTEXT.md",
            "docs/adr/0013-article-blog-dual-artifacts-and-failure-semantics.md",
            "docs/requirements/v0.2/stage-2-blog.md",
            "tests/test_article_blog_method_pack.py",  # This guard names the retired identifier itself.
        }
        findings = []
        for relative in self._tracked_paths():
            if relative in allowed or relative.startswith(".scratch/"):
                continue
            path = ROOT / relative
            if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".yaml", ".json", ".ts", ".tsx"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "paper2blog" in content:
                findings.append(relative)
        self.assertEqual([], findings)

    def test_method_pack_is_the_only_method_copy(self):
        skipped = {"node_modules", ".git", "tmp", ".scratch", "workspace", "__pycache__"}
        findings = [
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*")
            if path.is_file()
            and path.name in {"reading-blog-method.md", "value-analysis-method.md", "article2blog.py"}
            and not skipped.intersection(path.parts)
        ]
        self.assertEqual(
            sorted(
                [
                    "methods/article-blog/reference/reading-blog-method.md",
                    "methods/article-blog/reference/value-analysis-method.md",
                    "methods/article-blog/scripts/article2blog.py",
                ]
            ),
            sorted(findings),
        )


if __name__ == "__main__":
    unittest.main()
