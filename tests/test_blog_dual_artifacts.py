from __future__ import annotations

import json
import shutil
import unittest
import uuid
import zlib
from pathlib import Path

from core import BlogApplication, BlogExternalError, WorkspaceError
from core.article_blog import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_NOT_APPLICABLE,
    STATUS_PENDING,
    check_images,
    check_references,
    decode_image,
    validate_applicability,
    validate_blog_candidate,
)


ROOT = Path(__file__).resolve().parents[1]

SOURCE_CONTENT = "\n".join(
    [
        "# Fixture Paper",
        "",
        "## 1 Introduction",
        "",
        "The workload stalls on the interconnect.",
        "",
        "## 2 Method",
        "",
        "![Figure 1](images/image-001.png)",
        "",
        "Figure 1 shows the pipeline and its buffers.",
        "",
        "## 3 Experiments",
        "",
        "Table 1 reports throughput for every baseline.",
    ]
)

REFERENCES = "\n".join(
    [
        "## 参考文献",
        "",
        "1. Fixture Authors. 2026. Fixture Paper. arXiv:0000.0000。",
        "2. Other Authors. 2025. Baseline Comparison. arXiv:1111.1111。",
    ]
)

READING_BLOG = "\n".join(
    [
        "# 固件论文带读",
        "",
        "## 导语与问题背景",
        "",
        "第 1 节指出互连是瓶颈。" + "展开说明。" * 140,
        "",
        "## 方法与机制",
        "",
        "核心模块按输入、输出与设计原因展开[1]。" + "机制细节。" * 140,
        "",
        "## 实验与证据",
        "",
        "![Figure 1](assets/image-001.png)",
        "",
        "Table 1 说明指标方向与基线差异。" + "证据细节。" * 140,
        "",
        "## 局限与边界",
        "",
        "结果只在给定配置下成立。" + "边界说明。" * 90,
        "",
        REFERENCES,
    ]
)

VALUE_ANALYSIS = "\n".join(
    [
        "# 论文价值分析：固件论文",
        "",
        "## 研究问题",
        "",
        "对象是分布式 3D 堆叠加速器上的设计空间探索；瓶颈是搜索规模与评估成本。" + "问题说明。" * 60,
        "",
        "## 输入输出",
        "",
        "输入是工作负载描述与资源约束，输出是候选设计与估价。" + "边界说明。" * 60,
        "",
        "## 模块拆解",
        "",
        "| 模块 | 拿到什么 | 做什么 | 产出什么 |",
        "|---|---|---|---|",
        "| 搜索器 | 设计变量与合法空间 | 生成并筛选候选 | 候选集合 |",
        "",
        "各模块围绕设计动机、内部机制与代价展开。" + "模块说明。" * 60,
        "",
        "## 一个运行例子",
        "",
        "追踪一个候选如何产生、通过合法性检查并获得估价。" + "推演说明。" * 60,
        "",
        "## 贡献与边界",
        "",
        "贡献是搜索规模下的估价准确性；本次未实际运行实现，结论只来自静态核查。" + "边界说明。" * 60,
    ]
)

EVIDENCE_MAP = "\n".join(
    [
        "# Evidence Map",
        "",
        "## 贡献与原文锚点",
        "",
        "| 贡献 | 原文锚点 | 报告的证据 | 假设与边界 |",
        "|---|---|---|---|",
        "| 搜索规模 | 第 2 节 | Figure 1 | 仅在单核配置下验证 |",
    ]
)


def png_bytes(payload: bytes = b"figure") -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return len(body).to_bytes(4, "big") + kind + body + (zlib.crc32(kind + body) & 0xFFFFFFFF).to_bytes(4, "big")

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 6, 0, 0, 0]))
    data = chunk(b"IDAT", zlib.compress(payload))
    return header + ihdr + data + chunk(b"IEND", b"")


class ArchitectureRuntime:
    """Controlled Runtime for an architecture paper, with optional retrieval."""

    def __init__(self, *, applicable: bool = True, value_body: str = VALUE_ANALYSIS, retrieval=None):
        self.calls: list[str] = []
        self.applicable = applicable
        self.value_body = value_body
        self.retrieval = retrieval
        self.network_seen: list[bool] = []

    def classify(self, *, bundle, evidence, method_dir):
        self.calls.append("classify")
        if self.applicable:
            return {
                "applicable": True,
                "direction": "design_space_exploration",
                "reason": "主贡献是设计变量与搜索选择，验证对象是候选估价",
            }
        return {"applicable": False, "direction": None, "reason": "主贡献是数据集与训练技巧，不涉及硬件架构方向"}

    def write_artifact(self, *, artifact, bundle, candidate, method_dir, network):
        self.calls.append(artifact)
        self.network_seen.append(network)
        if artifact == "reading_blog":
            return {"files": {"evidence/evidence-map.md": EVIDENCE_MAP, "blog.md": READING_BLOG}, "warnings": []}
        return {"files": {"value-analysis.md": self.value_body}, "warnings": []}

    def search_implementation(self, *, bundle, method_dir, network):
        self.calls.append("search_implementation")
        if self.retrieval is None:
            raise BlogExternalError("network_unavailable", "no network route to the repository host")
        return self.retrieval


class DualArtifactTests(unittest.TestCase):
    def setUp(self):
        runs = ROOT / "tmp" / "test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.root = runs / f"blog-dual-{uuid.uuid4().hex[:8]}"
        self.root.mkdir()
        self.workspace = self.root / "workspace"
        self._registered_paper()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _registered_paper(self, source_id: str = "Fixture-paper", image: bytes | None = None):
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
        (bundle / "content.md").write_text(SOURCE_CONTENT, encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "fixture-batch"}\n',
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text('{"ok": true, "warnings": []}\n', encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(image if image is not None else png_bytes())
        (self.workspace / "state.json").write_text(
            json.dumps(
                {
                    "current_source_id": source_id,
                    "current_topic_id": None,
                    "sources": {source_id: {"current_plan_id": None, "current_chunk_id": None}},
                }
            ),
            encoding="utf-8",
        )
        reading = source_root / "reading" / "plans" / "plan-001"
        reading.mkdir(parents=True, exist_ok=True)
        (reading / "chunks.jsonl").write_text('{"chunk_id": "chunk-001"}\n', encoding="utf-8")
        (reading / "records").mkdir(parents=True, exist_ok=True)
        (reading / "records" / "chunk-001.json").write_text(
            json.dumps({"chunk_id": "chunk-001", "translation": None, "notes": [{"type": "thought", "text": "读者私人备注"}]}),
            encoding="utf-8",
        )
        return source_root, bundle

    @staticmethod
    def _snapshot(paths):
        return {path: path.read_bytes() for root in paths for path in root.rglob("*") if path.is_file()}

    def _app(self, runtime, *, network: bool = True, writer_id: str = "writer-a"):
        return BlogApplication(self.workspace, runtime=runtime, writer_id=writer_id, network=network)

    # ------------------------------------------------------------------- T03

    def test_architecture_paper_generates_both_articles_and_evidence(self):
        runtime = ArchitectureRuntime()
        app = self._app(runtime)
        source_root, _ = self._registered_paper()

        result = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual("completed", result["outcome"]["status"])
        blog = source_root / "blog"
        self.assertTrue((blog / "blog.md").is_file())
        self.assertTrue((blog / "value-analysis.md").is_file())
        self.assertTrue((blog / "evidence" / "evidence-map.md").is_file())
        self.assertTrue((blog / "evidence" / "implementation-notes.md").is_file())
        metadata = json.loads((blog / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(STATUS_COMPLETED, metadata["artifacts"]["reading_blog"]["status"])
        self.assertEqual(STATUS_COMPLETED, metadata["artifacts"]["value_analysis"]["status"])
        self.assertTrue(metadata["value_analysis_applicability"]["applicable"])
        self.assertEqual("design_space_exploration", metadata["value_analysis_applicability"]["direction"])
        self.assertIn("value_analysis", runtime.calls)

    # ------------------------------------------------------------------- T04

    def test_non_architecture_paper_skips_value_analysis_with_a_reason(self):
        runtime = ArchitectureRuntime(applicable=False)
        app = self._app(runtime)
        source_root, _ = self._registered_paper()

        result = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual("completed", result["outcome"]["status"])
        blog = source_root / "blog"
        self.assertTrue((blog / "blog.md").is_file())
        self.assertFalse((blog / "value-analysis.md").exists())
        metadata = json.loads((blog / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(STATUS_NOT_APPLICABLE, metadata["artifacts"]["value_analysis"]["status"])
        self.assertFalse(metadata["value_analysis_applicability"]["applicable"])
        self.assertTrue(metadata["value_analysis_applicability"]["reason"])
        self.assertNotIn("value_analysis", runtime.calls)

        with self.assertRaises(WorkspaceError) as caught:
            app.regenerate("Fixture-paper", artifact="value_analysis", request_id="req-2", authorized_by="manual_trigger")
        self.assertEqual("blog_artifact_not_applicable", caught.exception.error_id)

    # -------------------------------------------------------------- T11/T12

    def test_offline_value_analysis_degrades_to_paper_reading_without_failing(self):
        runtime = ArchitectureRuntime(retrieval={"notes": "should not be used", "verification_level": "executed"})
        app = self._app(runtime, network=False)
        source_root, _ = self._registered_paper()

        result = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual("completed", result["outcome"]["status"])
        self.assertNotIn("search_implementation", runtime.calls)
        notes = (source_root / "blog" / "evidence" / "implementation-notes.md").read_text(encoding="utf-8")
        self.assertIn("仅论文阅读", notes)
        self.assertIn("未检索", notes)
        metadata = json.loads((source_root / "blog" / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual("paper_reading", metadata["verification_level"])
        self.assertTrue(any("无网络" in item or "未检索" in item for item in metadata["warnings"]))

    def test_online_value_analysis_records_the_implementation_check(self):
        retrieval = {
            "notes": "# Implementation Notes\n\n沿 `src/search/` 的入口静态核查了候选生成与估价路径。\n",
            "verification_level": "static_review",
            "warnings": ["未实际运行实验脚本"],
        }
        runtime = ArchitectureRuntime(retrieval=retrieval)
        app = self._app(runtime, network=True)
        source_root, _ = self._registered_paper()

        result = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertIn("search_implementation", runtime.calls)
        notes = (source_root / "blog" / "evidence" / "implementation-notes.md").read_text(encoding="utf-8")
        self.assertIn("静态核查", notes)
        metadata = json.loads((source_root / "blog" / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual("static_review", metadata["verification_level"])
        self.assertIn("未实际运行实验脚本", metadata["warnings"])

    def test_a_failing_retrieval_degrades_instead_of_failing_the_step(self):
        runtime = ArchitectureRuntime(retrieval=None)
        app = self._app(runtime, network=True)
        source_root, _ = self._registered_paper()

        result = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual("completed", result["outcome"]["status"])
        notes = (source_root / "blog" / "evidence" / "implementation-notes.md").read_text(encoding="utf-8")
        self.assertIn("仅论文阅读", notes)
        metadata = json.loads((source_root / "blog" / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual("paper_reading", metadata["verification_level"])

    # ------------------------------------------------------------------- T06

    def test_one_failed_article_keeps_the_other_and_only_reruns_the_failed_one(self):
        runtime = ArchitectureRuntime(value_body="# 太短\n")
        app = self._app(runtime)
        source_root, _ = self._registered_paper()

        failed = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual("failed", failed["outcome"]["status"])
        self.assertEqual("blog_candidate_invalid", failed["outcome"]["error_id"])
        self.assertTrue((source_root / "blog" / "blog.md").is_file())
        self.assertFalse((source_root / "blog" / "value-analysis.md").exists())
        metadata = json.loads((source_root / "blog" / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(STATUS_COMPLETED, metadata["artifacts"]["reading_blog"]["status"])
        self.assertEqual(STATUS_FAILED, metadata["artifacts"]["value_analysis"]["status"])

        runtime.value_body = VALUE_ANALYSIS
        retried = app.regenerate("Fixture-paper", artifact="value_analysis", request_id="req-2", authorized_by="manual_trigger")
        self.assertEqual("completed", retried["outcome"]["status"])
        self.assertTrue((source_root / "blog" / "value-analysis.md").is_file())
        self.assertEqual(
            ["classify", "reading_blog", "search_implementation", "value_analysis", "search_implementation", "value_analysis"],
            runtime.calls,
        )
        self.assertEqual(READING_BLOG, (source_root / "blog" / "blog.md").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------- T19

    def test_evidence_notes_stay_separate_from_reading_notes(self):
        runtime = ArchitectureRuntime()
        app = self._app(runtime)
        source_root, _ = self._registered_paper()
        private_before = self._snapshot((source_root / "reading",))
        state_before = (self.workspace / "state.json").read_bytes()

        app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual(private_before, self._snapshot((source_root / "reading",)))
        self.assertEqual(state_before, (self.workspace / "state.json").read_bytes())
        notes = (source_root / "blog" / "evidence" / "evidence-map.md").read_text(encoding="utf-8")
        self.assertIn("Evidence Map", notes)
        self.assertNotIn("读者私人备注", notes)
        self.assertFalse((source_root / "reading" / "blog").exists())


class BlogValidatorTests(unittest.TestCase):
    """Unit boundary: illegal candidates are injected straight into the validator."""

    def setUp(self):
        runs = ROOT / "tmp" / "test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.root = runs / f"blog-validator-{uuid.uuid4().hex[:8]}"
        self.root.mkdir()
        self.blog = self.root / "blog"
        (self.blog / "evidence").mkdir(parents=True)
        (self.blog / "assets").mkdir(parents=True)
        self.bundle = self.root / "bundle"
        (self.bundle / "images").mkdir(parents=True)
        (self.bundle / "content.md").write_text(SOURCE_CONTENT, encoding="utf-8")
        (self.bundle / "images" / "image-001.png").write_bytes(png_bytes())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _fill(self, blog_body: str = READING_BLOG, value_body: str | None = VALUE_ANALYSIS):
        (self.blog / "evidence" / "evidence-map.md").write_text(EVIDENCE_MAP, encoding="utf-8")
        (self.blog / "evidence" / "implementation-notes.md").write_text(
            "# Implementation Notes\n\n本次核查层级：静态核查；未实际运行。\n", encoding="utf-8"
        )
        (self.blog / "assets" / "image-001.png").write_bytes(png_bytes())
        (self.blog / "blog.md").write_text(blog_body, encoding="utf-8")
        if value_body is not None:
            (self.blog / "value-analysis.md").write_text(value_body, encoding="utf-8")

    # ------------------------------------------------------------------- T15

    def test_an_image_that_does_not_decode_fails_and_names_the_file(self):
        self._fill()
        (self.blog / "assets" / "image-001.png").write_bytes(b"not-an-image-at-all")

        checked = validate_blog_candidate(self.blog, bundle=self.bundle, require_value_analysis=True)

        self.assertFalse(checked["ok"])
        self.assertTrue(any("assets/image-001.png" in item for item in checked["errors"]), checked["errors"])
        self.assertTrue(any("does not decode" in item for item in checked["errors"]))

    def test_an_image_that_is_not_from_the_bundle_fails_and_names_the_file(self):
        self._fill()
        (self.blog / "assets" / "image-001.png").write_bytes(png_bytes(b"different-bytes"))

        checked = validate_blog_candidate(self.blog, bundle=self.bundle, require_value_analysis=True)

        self.assertFalse(checked["ok"])
        self.assertTrue(
            any("assets/image-001.png" in item and "Bundle" in item for item in checked["errors"]), checked["errors"]
        )

    def test_decode_image_accepts_a_real_png_and_rejects_garbage(self):
        path = self.root / "ok.png"
        path.write_bytes(png_bytes())
        self.assertEqual((True, "png"), decode_image(path))
        broken = self.root / "broken.png"
        broken.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
        ok, detail = decode_image(broken)
        self.assertFalse(ok)
        self.assertTrue(detail)

    # ------------------------------------------------------------------- T16

    def test_an_unresolvable_citation_fails_and_locates_it(self):
        self._fill(blog_body=READING_BLOG.replace("设计原因展开[1]", "设计原因展开[9]"))

        checked = validate_blog_candidate(self.blog, bundle=self.bundle, require_value_analysis=True)

        self.assertFalse(checked["ok"])
        self.assertTrue(any("[9]" in item for item in checked["errors"]), checked["errors"])

    def test_an_unresolvable_section_anchor_fails_and_locates_it(self):
        self._fill(blog_body=READING_BLOG.replace("第 1 节", "第 12 节"))

        checked = validate_blog_candidate(self.blog, bundle=self.bundle, require_value_analysis=True)

        self.assertFalse(checked["ok"])
        self.assertTrue(any("section 12" in item for item in checked["errors"]), checked["errors"])

    def test_a_figure_anchor_that_the_bundle_text_cannot_hold_is_a_warning(self):
        self._fill(blog_body=READING_BLOG.replace("Table 1", "Table 42"))

        checked = validate_blog_candidate(self.blog, bundle=self.bundle, require_value_analysis=True)

        self.assertTrue(checked["ok"], checked["errors"])
        self.assertTrue(any("Table 42" in item for item in checked["warnings"]), checked["warnings"])

    # ------------------------------------------------------------------- T17

    def test_depth_and_evidence_gaps_stay_warnings_never_a_quality_pass(self):
        self._fill()
        (self.blog / "evidence" / "evidence-map.md").write_text("# Evidence Map\n\n很薄的证据。\n", encoding="utf-8")
        (self.blog / "evidence" / "implementation-notes.md").write_text("未运行；未找到公开实现。\n", encoding="utf-8")
        (self.bundle / "content.md").write_text(SOURCE_CONTENT + "\n" + "补充。" * 20000, encoding="utf-8")

        checked = validate_blog_candidate(self.blog, bundle=self.bundle, require_value_analysis=True)

        self.assertTrue(checked["ok"], checked["errors"])
        self.assertTrue(checked["warnings"])
        self.assertIn("未核查范围", " ".join(checked["warnings"]))
        self.assertIn("未运行", " ".join(checked["warnings"]))
        rendered = json.dumps(checked, ensure_ascii=False)
        self.assertNotIn("质量通过", rendered)
        self.assertNotIn("quality pass", rendered.lower())

    # ------------------------------------------------------------- structure

    def test_value_analysis_must_follow_the_five_part_main_line(self):
        self._fill(value_body="# 论文价值分析\n\n只写了研究问题与输入输出。\n")
        checked = validate_blog_candidate(self.blog, bundle=self.bundle, require_value_analysis=True)
        self.assertFalse(checked["ok"])
        self.assertTrue(any("five-part" in item for item in checked["errors"]), checked["errors"])

    def test_applicability_validation_rejects_an_undecided_or_undefined_direction(self):
        with self.assertRaises(WorkspaceError):
            validate_applicability({"applicable": None, "reason": "没判断"})
        with self.assertRaises(WorkspaceError):
            validate_applicability({"applicable": True, "direction": "marketing", "reason": "随便"})
        self.assertEqual(
            {"applicable": True, "direction": "compiler", "reason": "编译映射为主贡献"},
            validate_applicability({"applicable": True, "direction": "compiler", "reason": "编译映射为主贡献"}),
        )

    def test_image_and_reference_helpers_are_reusable_on_their_own(self):
        errors, warnings = check_images(self.blog, "![x](assets/missing.png)", "", self.bundle)
        self.assertTrue(any("missing.png" in item for item in errors))
        self.assertEqual([], warnings)
        errors, warnings = check_references("body [3] text", "", SOURCE_CONTENT)
        self.assertTrue(errors)
        self.assertEqual([], warnings)

    def test_arabic_section_references_resolve_roman_numbered_headings(self):
        bundle = '\n'.join(['## I. INTRODUCTION', '## II. RELATED WORK',
                            '## III. BACKGROUND', '## IV. ARCHITECTURE', '## V. EVALUATION'])
        errors, _ = check_references('第 1 节；第 2 节；第 3 节；第 4 节；第 5 节',
                                     'Section 4 and Sec. 5', bundle)
        self.assertEqual([], errors)
        self.assertEqual([], check_references('Section 9', '', '## ix. Evaluation')[0])

    def test_roman_matching_does_not_accept_missing_or_partial_section_numbers(self):
        for bundle in ['## II. Related Work', '## IV. Architecture', 'Body mentions Section I.',
                       '## Introduction']:
            with self.subTest(bundle=bundle):
                errors, _ = check_references('第 1 节', '', bundle)
                self.assertTrue(errors)
        self.assertTrue(check_references('第 4 节', '', '## IIII. Invalid numbering')[0])
        self.assertTrue(check_references('第 6 节', '', '## V. Evaluation')[0])


if __name__ == "__main__":
    unittest.main()
