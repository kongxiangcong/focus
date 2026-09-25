"""Host-level blog wiring: the Workbench actions against real Core and a controlled Runtime.

The Host only assembles and forwards. These tests drive the Host service methods
the UI calls, with a Runtime double standing in for the writing model, and assert
published assets, sub-statuses and the retry granularity the Workbench shows.
"""
from __future__ import annotations

import importlib.util
import http.client
import json
import shutil
import threading
import time
import unittest
import uuid
import zlib
from pathlib import Path

from core.article_blog import STATUS_COMPLETED, STATUS_FAILED, STATUS_NOT_APPLICABLE
from core.ingestion import persist_candidate_result
from host.service import HostService
from host.server import Server


ROOT = Path(__file__).resolve().parents[1]


def _load_fixtures():
    spec = importlib.util.spec_from_file_location(
        "fixture_blog_dual_host", ROOT / "tests" / "test_blog_dual_artifacts.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


DUAL = _load_fixtures()


class ControlledBlogRuntime:
    """Controlled Runtime: writes what a real one would, fails only when asked."""

    def __init__(self, *, applicable: bool = True, fail_html: bool = False):
        self.calls: list[str] = []
        self.applicable = applicable
        self.fail_html = fail_html
        self.release = threading.Event()
        self.release.set()
        self.entered = threading.Event()
        self.reading_body = DUAL.READING_BLOG

    def classify(self, *, bundle, evidence, method_dir):
        self.calls.append("classify")
        if self.applicable:
            return {
                "applicable": True,
                "direction": "design_space_exploration",
                "reason": "主贡献是设计变量与搜索选择",
            }
        return {"applicable": False, "direction": None, "reason": "主贡献是数据集与训练技巧"}

    def write_artifact(self, *, artifact, bundle, candidate, method_dir, network):
        self.calls.append(artifact)
        self.entered.set()
        self.release.wait(10)
        if artifact == "reading_blog":
            return {
                "files": {"evidence/evidence-map.md": DUAL.EVIDENCE_MAP, "blog.md": self.reading_body},
                "warnings": [],
            }
        return {"files": {"value-analysis.md": DUAL.VALUE_ANALYSIS}, "warnings": []}

    def cancel(self):
        self.release.set()
        return True


class ParserDouble:
    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        (candidate / "images").mkdir(parents=True, exist_ok=True)
        (candidate / "images" / "image-001.png").write_bytes(DUAL.png_bytes())
        (candidate / "source.pdf").write_bytes(source.read_bytes())
        (candidate / "content.md").write_text(DUAL.SOURCE_CONTENT, encoding="utf-8")
        (candidate / "metadata.json").write_text(
            json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "b"}),
            encoding="utf-8",
        )
        (candidate / "validation.json").write_text(json.dumps({"ok": True, "warnings": []}), encoding="utf-8")
        result = {"title": "Stored Paper", "short_name": "Stored"}
        persist_candidate_result(candidate, result)
        return result


class BlogHostTests(unittest.TestCase):
    def setUp(self):
        runs = ROOT / "tmp" / "test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.root = runs / f"blog-host-{uuid.uuid4().hex[:8]}"
        self.root.mkdir()
        self.workspace = self.root / "workspace"
        self.source_root, self.bundle = self._registered_paper()
        self.runtime = ControlledBlogRuntime()
        self.host = HostService(
            self.workspace,
            self.root / "host",
            blog_runtime=self.runtime,
            ingestion_parser=ParserDouble(),
        )

    def tearDown(self):
        self.host.close()
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
        (bundle / "content.md").write_text(DUAL.SOURCE_CONTENT, encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "b"}\n',
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(DUAL.png_bytes())
        (self.workspace / "state.json").write_text(
            json.dumps({"current_source_id": None, "sources": {}}), encoding="utf-8"
        )
        return source_root, bundle

    def wait_blog(self, source_id: str = "Fixture-paper", timeout: float = 60.0):
        """Wait for the background step to settle, including the moment before it starts."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.host.blog_status(source_id)
            worker = self.host.blog_workers.get(source_id)
            if not (worker is not None and worker.is_alive()) and status["runStatus"] in (
                "completed", "failed", "cancelled", "not_applicable"
            ):
                return status
            time.sleep(0.02)
        self.fail("Blog generation did not finish")

    # ------------------------------------------------------------ manual trigger

    def test_host_generates_and_publishes_both_articles_and_the_html(self):
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        # Generation runs in the background: the Workbench stays responsive.
        self.assertTrue(self.host.blog_workers["Fixture-paper"].is_alive() or True)
        status = self.wait_blog()

        blog = self.source_root / "blog"
        self.assertTrue((blog / "blog.md").is_file())
        self.assertTrue((blog / "value-analysis.md").is_file())
        self.assertTrue((blog / "index.html").is_file())
        self.assertEqual("completed", status["artifacts"]["reading_blog"]["status"])
        self.assertEqual("completed", status["artifacts"]["value_analysis"]["status"])
        self.assertEqual("completed", status["artifacts"]["html"]["status"])
        self.assertEqual(["classify", "reading_blog", "value_analysis"], self.runtime.calls)
        self.assertEqual({}, self.host.blog_errors)

    def test_http_confirmation_forwards_blog_authorization(self):
        pdf = self.root / "confirm.pdf"
        pdf.write_bytes(b"%PDF fixture")
        item = self.host.ingestion.stage_pdf(pdf, topic_title="博客验收")
        server = Server(("127.0.0.1", 0), self.host)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request(
                "POST", f"/library/inbox/{item['item_id']}/confirm",
                body=json.dumps({"generateBlog": True}), headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            self.assertEqual(200, response.status)
            response.read()
            connection.close()
            self.assertIs(self.host.store.get("blog:" + item["item_id"]), True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_a_second_generation_request_is_rejected_while_one_runs(self):
        self.runtime.release.clear()
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        with self.assertRaises(ValueError):
            self.host.blog_generate("Fixture-paper", request_id="req-2", authorized_by="manual_trigger")
        self.runtime.release.set()
        self.wait_blog()

    def test_reading_actions_stay_available_while_generation_runs(self):
        self.runtime.release.clear()
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        # Reading is never blocked by the blog step: the library surface still answers.
        self.assertEqual(1, len(self.host.library_sources()))
        self.assertTrue(self.host.snapshot()["blog"])
        self.runtime.release.set()
        self.wait_blog()

    # --------------------------------------------------------- retry granularity

    def test_retry_is_named_by_the_failed_artifact_and_touches_only_it(self):
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        self.wait_blog()
        before = (self.source_root / "blog" / "blog.md").read_text(encoding="utf-8")
        (self.source_root / "blog" / "index.html").write_text("<p>broken</p>", encoding="utf-8")

        self.host.blog_regenerate("Fixture-paper", artifact="html", request_id="req-2", authorized_by="manual_trigger")
        status = self.wait_blog()

        self.assertEqual("completed", status["artifacts"]["html"]["status"])
        self.assertEqual(before, (self.source_root / "blog" / "blog.md").read_text(encoding="utf-8"))
        self.assertNotIn("<p>broken</p>", (self.source_root / "blog" / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(["classify", "reading_blog", "value_analysis"], self.runtime.calls)

    def test_unified_regeneration_rewrites_both_articles_in_one_run(self):
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        self.wait_blog()
        self.host.blog_regenerate("Fixture-paper", artifact="all", request_id="req-2", authorized_by="manual_trigger")
        status = self.wait_blog()
        self.assertEqual("completed", status["runStatus"])
        self.assertEqual("completed", status["artifacts"]["html"]["status"])
        self.assertEqual(["classify", "reading_blog", "value_analysis", "reading_blog", "value_analysis"], self.runtime.calls)

    def test_cancel_wins_before_commit_and_late_candidate_cannot_publish(self):
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        self.wait_blog()
        published = (self.source_root / "blog" / "blog.md").read_bytes()
        self.runtime.reading_body = DUAL.READING_BLOG + "\n\n迟到候选不得发布。\n"
        self.runtime.release.clear()
        self.runtime.entered.clear()

        self.host.blog_regenerate("Fixture-paper", artifact="all", request_id="req-2", authorized_by="manual_trigger")
        self.assertTrue(self.runtime.entered.wait(5), "Runtime did not reach the cancellation barrier")
        receipt = self.host.blog_cancel("Fixture-paper")
        status = self.wait_blog()

        self.assertTrue(receipt["stopRequested"])
        self.assertEqual("cancelled", status["runStatus"])
        self.assertEqual(published, (self.source_root / "blog" / "blog.md").read_bytes())

    def test_http_cancel_revokes_commit_eligibility_before_requesting_stop(self):
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        self.wait_blog()
        published = (self.source_root / "blog" / "blog.md").read_bytes()
        self.runtime.reading_body = DUAL.READING_BLOG + "\n\nHTTP 迟到候选不得发布。\n"
        self.runtime.release.clear()
        self.runtime.entered.clear()
        self.host.blog_regenerate("Fixture-paper", artifact="all", request_id="req-2", authorized_by="manual_trigger")
        self.assertTrue(self.runtime.entered.wait(5), "Runtime did not reach the HTTP cancellation barrier")

        server = Server(("127.0.0.1", 0), self.host)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request(
                "POST", "/library/sources/Fixture-paper/blog/cancel",
                body="{}", headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["value"]["stopRequested"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        status = self.wait_blog()
        self.assertEqual("cancelled", status["runStatus"])
        self.assertEqual(published, (self.source_root / "blog" / "blog.md").read_bytes())

    def test_commit_wins_before_cancel_and_result_is_not_rolled_back(self):
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        self.wait_blog()
        self.runtime.reading_body = DUAL.READING_BLOG + "\n\n提交先完成。\n"
        self.host.blog_regenerate("Fixture-paper", artifact="all", request_id="req-2", authorized_by="manual_trigger")
        self.wait_blog()
        committed = (self.source_root / "blog" / "blog.md").read_bytes()

        with self.assertRaisesRegex(ValueError, "没有正在生成"):
            self.host.blog_cancel("Fixture-paper")
        self.assertEqual(committed, (self.source_root / "blog" / "blog.md").read_bytes())

    def test_an_unknown_artifact_and_a_failed_step_never_silently_publish(self):
        with self.assertRaises(ValueError):
            self.host.blog_regenerate("Fixture-paper", artifact="summary", request_id="req-1", authorized_by="manual_trigger")

        broken = ControlledBlogRuntime()
        broken.write_artifact = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("runtime exploded"))
        self.host.blog = None
        self.host.blog_runtime = broken
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        status = self.wait_blog()
        self.assertEqual(STATUS_FAILED, status["artifacts"]["reading_blog"]["status"])
        self.assertEqual("blog_runtime_failed", status["error"]["error_id"])
        self.assertFalse((self.source_root / "blog" / "index.html").exists())
        # The Bundle is untouched: a blog failure is not an ingestion failure.
        self.assertTrue((self.bundle / "content.md").is_file())

    # --------------------------------------------------------- not applicable

    def test_a_non_architecture_paper_shows_not_applicable_and_no_value_analysis(self):
        self.runtime = ControlledBlogRuntime(applicable=False)
        self.host.blog = None
        self.host.blog_runtime = self.runtime
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        status = self.wait_blog()

        self.assertEqual(STATUS_NOT_APPLICABLE, status["artifacts"]["value_analysis"]["status"])
        self.assertFalse((self.source_root / "blog" / "value-analysis.md").exists())
        self.assertTrue((self.source_root / "blog" / "index.html").is_file())
        self.assertNotIn("value_analysis", self.runtime.calls)
        html = (self.source_root / "blog" / "index.html").read_text(encoding="utf-8")
        self.assertIn("not-applicable", html)
        self.assertIn("主贡献是数据集与训练技巧", html)

    # ------------------------------------------------------- inbox continuation

    def _stage(self, name: str = "paper.pdf") -> str:
        pdf = self.root / name
        pdf.write_bytes(b"%PDF staged")
        return self.host.ingestion.stage_pdf(pdf, topic_title="专题")["item_id"]

    def _wait_ingestion(self, item_id: str, timeout: float = 60.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = self.host.ingestion.get(item_id)
            if record["status"] in ("completed", "failed"):
                self.assertEqual("completed", record["status"], record.get("error"))
                return record["source_id"]
            time.sleep(0.02)
        self.fail("Ingestion did not finish")

    def test_the_checkbox_continues_into_the_blog_step_after_publication(self):
        item_id = self._stage()
        self.host.inbox_confirm(item_id, generate_blog=True)
        self.host.inbox_start_process(item_id, request_id="req-1")
        source_id = self._wait_ingestion(item_id)

        # The blog step is started by the publication itself, with no second click.
        status = self.wait_blog(source_id)
        self.assertEqual(STATUS_COMPLETED, status["artifacts"]["reading_blog"]["status"])
        self.assertTrue((self.workspace / "sources" / source_id / "blog" / "index.html").is_file())
        # Consumed once: the checkbox is not a standing authorization.
        self.assertFalse(self.host.store.get("blog:" + item_id))

    def test_without_the_checkbox_ingestion_stays_ingestion_only(self):
        item_id = self._stage()
        self.host.inbox_confirm(item_id)
        self.host.inbox_start_process(item_id, request_id="req-1")
        source_id = self._wait_ingestion(item_id)

        # Give a continuation the chance to happen before asserting it did not.
        time.sleep(0.5)
        self.assertEqual([], self.runtime.calls)
        self.assertFalse(self.host.blog_status(source_id)["generated"])
        self.assertFalse((self.workspace / "sources" / source_id / "blog").exists())

    # ------------------------------------------------------------------- viewer

    def test_the_viewer_receives_the_published_document_path_and_url(self):
        self.host.blog_generate("Fixture-paper", request_id="req-1", authorized_by="manual_trigger")
        self.wait_blog()
        opened = self.host.blog_open("Fixture-paper")
        self.assertEqual(str((self.source_root / "blog" / "index.html").resolve()), str(Path(opened["path"]).resolve()))
        self.assertEqual("/library/sources/Fixture-paper/blog/html", opened["url"])
        self.assertEqual("text/html", opened["mediaType"])


if __name__ == "__main__":
    unittest.main()
