from __future__ import annotations

import json
import shutil
import threading
import unittest
import uuid
import zlib
from pathlib import Path

from core import (
    ARTICLE_BLOG_METHOD_VERSION,
    BlogApplication,
    BlogExternalError,
    IngestionApplication,
    WorkspaceError,
    blog_root,
)
from core.article_blog import STATUS_COMPLETED, STATUS_FAILED, STATUS_PENDING
from core.ingestion import persist_candidate_result


ROOT = Path(__file__).resolve().parents[1]

SOURCE_CONTENT = "\n".join(
    [
        "# Fixture Paper",
        "",
        "## 1 Introduction",
        "",
        "Evidence.",
        "",
        "## 2 Method",
        "",
        "![Figure 1](images/image-001.png)",
        "",
        "Figure 1 shows the pipeline.",
        "",
        "## 3 Experiments",
        "",
        "Table 1 reports throughput.",
    ]
)


def png_bytes(payload: bytes = b"figure") -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return len(body).to_bytes(4, "big") + kind + body + (zlib.crc32(kind + body) & 0xFFFFFFFF).to_bytes(4, "big")

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 6, 0, 0, 0]))
    return header + ihdr + chunk(b"IDAT", zlib.compress(payload)) + chunk(b"IEND", b"")


READING_BLOG_BODY = "\n".join(
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


class ValidParser:
    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        (candidate / "images").mkdir(parents=True)
        (candidate / "source.pdf").write_bytes(source.read_bytes())
        (candidate / "content.md").write_text("# Stored Paper\n\nBody.\n", encoding="utf-8")
        (candidate / "metadata.json").write_text(
            json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "fixture-batch"}),
            encoding="utf-8",
        )
        (candidate / "validation.json").write_text(json.dumps({"ok": True, "warnings": []}), encoding="utf-8")
        result = {"title": "Stored Paper", "short_name": "Stored"}
        persist_candidate_result(candidate, result)
        return result


class RecordingRuntime:
    """Controlled Runtime: writes the artifacts a real Runtime would produce."""

    def __init__(self, *, body: str = READING_BLOG_BODY, files: dict[str, str] | None = None, warnings=None):
        self.calls = 0
        self.artifacts: list[str] = []
        self.body = body
        self.files = files
        self.warnings = warnings or []

    def classify(self, *, bundle, evidence, method_dir):
        return {"applicable": False, "direction": None, "reason": "测试夹具：默认非架构类论文"}

    def write_artifact(self, *, artifact, bundle, candidate, method_dir, network):
        self.calls += 1
        self.artifacts.append(artifact)
        if self.files is not None:
            return {"files": dict(self.files), "warnings": list(self.warnings)}
        return {
            "files": {"evidence/evidence-map.md": EVIDENCE_BODY, "blog.md": self.body},
            "warnings": list(self.warnings),
        }


class FailingRuntime(RecordingRuntime):
    """Fails the first `failures` calls, then behaves like a healthy Runtime."""

    def __init__(self, error_id: str = "runtime_failed", transient: bool = False, failures: int = 1):
        super().__init__()
        self.error_id = error_id
        self.transient = transient
        self.failures = failures

    def write_artifact(self, *, artifact, bundle, candidate, method_dir, network):
        self.calls += 1
        if self.calls <= self.failures:
            raise BlogExternalError(self.error_id, "runtime could not write the artifact", transient=self.transient)
        return {
            "files": {"evidence/evidence-map.md": EVIDENCE_BODY, "blog.md": self.body},
            "warnings": list(self.warnings),
        }


class LateRuntime(RecordingRuntime):
    """Signals when the Runtime started so the test can cancel meanwhile."""

    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def write_artifact(self, *, artifact, bundle, candidate, method_dir, network):
        self.calls += 1
        self.started.set()
        self.release.wait(10)
        return {"files": {"evidence/evidence-map.md": EVIDENCE_BODY, "blog.md": self.body}}


class BlogApplicationTests(unittest.TestCase):
    def setUp(self):
        runs = ROOT / "tmp" / "test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.root = runs / f"blog-app-{uuid.uuid4().hex[:8]}"
        self.root.mkdir()
        self.workspace = self.root / "workspace"
        self._registered_paper()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # ---------------------------------------------------------------- fixtures

    def _registered_paper(self, source_id: str = "Fixture-paper"):
        workspace = self.workspace
        source_root = workspace / "sources" / source_id
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
            '{"title": "Fixture Paper", "source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "fixture-batch"}\n',
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text(json.dumps({"ok": True, "warnings": []}), encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(png_bytes())
        (workspace / "state.json").write_text(
            json.dumps({"current_source_id": source_id, "current_topic_id": None, "sources": {source_id: {"current_plan_id": None, "current_chunk_id": None}}}),
            encoding="utf-8",
        )
        return source_root, bundle

    @staticmethod
    def _snapshot(paths):
        return {path: path.read_bytes() for root in paths for path in root.rglob("*") if path.is_file()}

    def _app(self, runtime=None, writer_id: str = "writer-a", **kwargs):
        return BlogApplication(
            self.workspace, runtime=runtime or RecordingRuntime(), writer_id=writer_id, **kwargs
        )

    # ------------------------------------------------------------------ T02

    def test_manual_trigger_generates_and_publishes_the_reading_blog(self):
        runtime = RecordingRuntime()
        app = self._app(runtime)
        source_root, bundle = self._registered_paper()

        result = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual("completed", result["outcome"]["status"])
        blog = source_root / "blog"
        self.assertTrue((blog / "blog.md").is_file())
        self.assertTrue((blog / "evidence" / "evidence-map.md").is_file())
        self.assertTrue((blog / "metadata.json").is_file())
        self.assertEqual(1, runtime.calls)

        metadata = json.loads((blog / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(ARTICLE_BLOG_METHOD_VERSION, metadata["method_version"])
        self.assertEqual(STATUS_COMPLETED, metadata["artifacts"]["reading_blog"]["status"])

        status = app.status("Fixture-paper")
        # The controlled Runtime judged this fixture non-architectural, so Value
        # Analysis is not applicable rather than pending; index.html is rendered
        # from the published blog.md and shows that judgement on its second page.
        self.assertEqual(
            {"value_analysis": "not_applicable", "reading_blog": STATUS_COMPLETED, "html": STATUS_COMPLETED},
            {name: entry["status"] for name, entry in status["artifacts"].items()},
        )
        self.assertTrue((blog / "index.html").is_file())
        opened = app.open_artifact("Fixture-paper", "reading_blog")
        self.assertEqual(str((blog / "blog.md").resolve()), str(Path(opened["path"]).resolve()))
        self.assertEqual("text/markdown", opened["mediaType"])

    def test_generation_does_not_create_plans_translations_or_notes(self):
        app = self._app()
        source_root, _ = self._registered_paper()
        state_before = (self.workspace / "state.json").read_bytes()

        app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertFalse((source_root / "reading").exists())
        self.assertEqual(state_before, (self.workspace / "state.json").read_bytes())

    def test_generation_requires_an_explicit_authorization(self):
        app = self._app()
        with self.assertRaises(WorkspaceError) as caught:
            app.generate("Fixture-paper", request_id="req-1", authorized_by="silent_default")
        self.assertEqual("blog_not_authorized", caught.exception.error_id)
        self.assertFalse(blog_root(self.workspace, "Fixture-paper").exists())

    def test_generating_shows_a_sub_status_and_leaves_reading_untouched(self):
        runtime = LateRuntime()
        app = self._app(runtime)
        _, _ = self._registered_paper()
        state_before = (self.workspace / "state.json").read_bytes()
        outcome: dict = {}

        def worker():
            outcome["result"] = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(runtime.started.wait(10))
        during = app.status("Fixture-paper")
        self.assertEqual("generating", during["artifacts"]["reading_blog"]["status"])
        self.assertEqual("running", during["runStatus"])
        self.assertEqual(state_before, (self.workspace / "state.json").read_bytes())
        runtime.release.set()
        thread.join(20)
        self.assertEqual("completed", outcome["result"]["outcome"]["status"])

    # ------------------------------------------------------------------ T05

    def test_runtime_claiming_success_with_an_invalid_candidate_is_not_published(self):
        runtime = RecordingRuntime(body="# 太短\n\n只有一句话。\n")
        app = self._app(runtime)
        source_root, _ = self._registered_paper()

        result = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual("failed", result["outcome"]["status"])
        self.assertEqual("blog_candidate_invalid", result["outcome"]["error_id"])
        self.assertFalse((source_root / "blog" / "blog.md").exists())
        status = app.status("Fixture-paper")
        self.assertEqual(STATUS_FAILED, status["artifacts"]["reading_blog"]["status"])
        self.assertIsNotNone(status["error"])
        self.assertNotEqual("completed", status["runStatus"])

    def test_runtime_failure_is_recorded_without_publishing(self):
        runtime = FailingRuntime("runtime_timeout", transient=True)
        app = self._app(runtime)
        source_root, _ = self._registered_paper()

        result = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        self.assertEqual("failed", result["outcome"]["status"])
        self.assertEqual("runtime_timeout", result["outcome"]["error_id"])
        self.assertFalse((source_root / "blog" / "blog.md").exists())
        metadata = json.loads((source_root / "blog" / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(STATUS_FAILED, metadata["artifacts"]["reading_blog"]["status"])

    # ------------------------------------------------------------------ T09

    def test_repeated_requests_and_restart_replay_return_the_published_result(self):
        runtime = RecordingRuntime()
        app = self._app(runtime)
        self._registered_paper()

        first = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        second = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        third = app.generate("Fixture-paper", request_id="req-other", authorized_by="manual_trigger")
        restarted = self._app(runtime).generate("Fixture-paper", request_id="req-new", authorized_by="manual_trigger")

        self.assertEqual("completed", first["outcome"]["status"])
        for replay in (second, third, restarted):
            self.assertTrue(replay["replayed"])
            self.assertEqual("completed", replay["artifacts"]["reading_blog"]["status"])
        self.assertEqual(1, runtime.calls)

    # ------------------------------------------------------------------ T10

    def test_failure_never_touches_the_bundle_and_only_retries_the_uncommitted_step(self):
        runtime = FailingRuntime()
        app = self._app(runtime)
        source_root, bundle = self._registered_paper()
        bundle_before = self._snapshot((bundle,))

        app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        self.assertEqual(bundle_before, self._snapshot((bundle,)))

        recovered = app.generate("Fixture-paper", request_id="req-2", authorized_by="manual_trigger")
        self.assertEqual("completed", recovered["outcome"]["status"])
        self.assertTrue((source_root / "blog" / "blog.md").is_file())
        self.assertEqual(bundle_before, self._snapshot((bundle,)))

    def test_cancel_stops_the_attempt_and_its_late_result_cannot_publish(self):
        runtime = LateRuntime()
        app = self._app(runtime)
        source_root, _ = self._registered_paper()
        outcome: dict = {}

        def worker():
            outcome["result"] = app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(runtime.started.wait(10))
        cancelled = app.cancel("Fixture-paper")
        runtime.release.set()
        thread.join(20)

        self.assertTrue(cancelled["cancelledAttempts"])
        self.assertEqual("rejected", outcome["result"]["outcome"]["status"])
        self.assertFalse((source_root / "blog" / "blog.md").exists())
        status = app.status("Fixture-paper")
        self.assertEqual(STATUS_PENDING, status["artifacts"]["reading_blog"]["status"])

        runtime2 = RecordingRuntime()
        retried = self._app(runtime2).generate("Fixture-paper", request_id="req-2", authorized_by="manual_trigger")
        self.assertEqual("completed", retried["outcome"]["status"])
        self.assertTrue((source_root / "blog" / "blog.md").is_file())

    # ------------------------------------------------------------------ T18

    def test_a_second_writer_cannot_publish_blog_artifacts(self):
        runtime = RecordingRuntime()
        app = self._app(runtime)
        source_root, _ = self._registered_paper()
        app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        published = (source_root / "blog" / "blog.md").read_text(encoding="utf-8")

        other = BlogApplication(self.workspace, runtime=RecordingRuntime(body=READING_BLOG_BODY + "\n第二版。\n"), writer_id="writer-b")
        with self.assertRaises(WorkspaceError) as caught:
            other.regenerate("Fixture-paper", artifact="reading_blog", request_id="req-2", authorized_by="manual_trigger")
        self.assertEqual("writer_conflict", caught.exception.error_id)
        self.assertEqual(published, (source_root / "blog" / "blog.md").read_text(encoding="utf-8"))

        with self.assertRaises(WorkspaceError) as caught_generate:
            other.generate("Fixture-paper", request_id="req-3", authorized_by="manual_trigger")
        self.assertEqual("writer_conflict", caught_generate.exception.error_id)

    # ------------------------------------------------------------------ T06/T13

    def test_regenerate_by_artifact_overwrites_only_that_artifact(self):
        runtime = RecordingRuntime()
        app = self._app(runtime)
        source_root, _ = self._registered_paper()
        app.generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        first = (source_root / "blog" / "blog.md").read_text(encoding="utf-8")

        runtime.body = READING_BLOG_BODY.replace("固件论文带读", "固件论文带读（第二版）")
        result = app.regenerate("Fixture-paper", artifact="reading_blog", request_id="req-2", authorized_by="manual_trigger")

        self.assertEqual("completed", result["outcome"]["status"])
        second = (source_root / "blog" / "blog.md").read_text(encoding="utf-8")
        self.assertNotEqual(first, second)
        self.assertIn("第二版", second)
        versions = sorted(path.name for path in (source_root / "blog").iterdir())
        self.assertNotIn("v1", versions)

    # ------------------------------------------------------------------ T01

    def test_ingestion_without_the_blog_option_makes_zero_blog_runtime_calls(self):
        runtime = RecordingRuntime()
        source = self.root / "paper.pdf"
        source.write_bytes(b"%PDF-1.4\nfixture paper\n")
        ingestion = IngestionApplication(self.workspace, parser=ValidParser(), writer_id="writer-a")
        staged = ingestion.stage_pdf(source)
        ingestion.confirm(staged["item_id"], services=["mineru"], purpose="入库", scope="ingestion")
        processed = ingestion.process(staged["item_id"], request_id="ingest-1")

        self.assertEqual("published", processed["document_status"])
        self.assertFalse(blog_root(self.workspace, processed["source_id"]).exists())
        self.assertEqual(0, runtime.calls)

        app = self._app(runtime)
        status = app.status(processed["source_id"])
        self.assertFalse(status["generated"])
        self.assertEqual(0, runtime.calls)


if __name__ == "__main__":
    unittest.main()
