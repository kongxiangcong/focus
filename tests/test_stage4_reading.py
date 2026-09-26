"""Stage 4 user operations through HostService with real Workspace assets."""
import http.client
import json
import queue
import shutil
import threading
import unittest
import uuid

import test_focus_read
from host.service import HostService
from host.server import Server
from core.reading_workspace import WorkspaceError, _reading_plan_records, _source_heading_paths
from core.reading_application import ReadingExternalError
from core.source_notes import SourceNotes


class SourceHeadingTests(unittest.TestCase):
    def test_code_comments_do_not_change_source_section_paths(self):
        for opening, closing in [('```python', '```'), ('~~~~python', '~~~~')]:
            with self.subTest(opening=opening):
                lines = ['# Article', '## Code', opening, '# example.py', '### comment',
                         closing, 'Explanation', '## Next', 'Text']
                paths = _source_heading_paths(lines)
                self.assertEqual(paths[2:7], [('Article', 'Code')] * 5)
                self.assertEqual(paths[7:], [('Article', 'Next')] * 2)


class ReadingRuntimeDouble:
    def __init__(self):
        self.calls = []

    def context(self, **kwargs):
        self.calls.append("context")
        return {"structure": "Method, Runtime, Results", "terms": [], "symbols": [], "references": []}

    def plan(self, **kwargs):
        self.calls.append("plan")
        raise AssertionError("The existing Plan should be reused")

    def translate(self, **kwargs):
        self.calls.append("translate")
        return "已准备的译文"

    def check(self, **kwargs):
        self.calls.append("check")
        return {"passed": True, "issues": {}, "coverage": [chunk["chunk_id"] for chunk in kwargs["chunks"]]}

    def cancel(self):
        self.calls.append("cancel")


class WaitingRuntime(ReadingRuntimeDouble):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def translate(self, **kwargs):
        self.entered.set()
        if not self.release.wait(3):
            raise AssertionError("test did not release Runtime")
        return super().translate(**kwargs)


class PlanningRuntime(ReadingRuntimeDouble):
    def __init__(self, draft):
        super().__init__()
        self.draft = draft

    def plan(self, **kwargs):
        self.calls.append("plan")
        return self.draft


class RepairingRuntime(ReadingRuntimeDouble):
    def __init__(self, *, always_fail=False):
        super().__init__()
        self.always_fail = always_fail

    def check(self, **kwargs):
        self.calls.append("check")
        coverage = [chunk["chunk_id"] for chunk in kwargs["chunks"]]
        if self.always_fail or self.calls.count("check") == 1:
            return {"passed": False, "issues": {"chunk-002": "术语译法不一致"}, "coverage": coverage}
        return {"passed": True, "issues": {}, "coverage": coverage}


class TransientRuntime(ReadingRuntimeDouble):
    def __init__(self, failures):
        super().__init__()
        self.failures = failures

    def context(self, **kwargs):
        self.calls.append("context")
        if self.calls.count("context") <= self.failures:
            raise ReadingExternalError("temporary", transient=True)
        return {"structure": "Method, Runtime, Results", "terms": [], "symbols": [], "references": []}


class Stage4PreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_focus_read.FocusReadTests()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.runtime = ReadingRuntimeDouble()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)

    def tearDown(self):
        self.host.close()
        self.fixture.tearDown()

    def test_preparation_only_notifies_then_manual_open_starts_reading(self):
        before = json.loads((self.workspace / "state.json").read_text(encoding="utf-8"))
        prepare_id = uuid.uuid4().hex
        result = self.host.prepare_reading("fixture-paper", request_id=prepare_id)
        self.assertEqual("running", result["preparations"]["fixture-paper"]["status"])
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertFalse(self.host.reading_workers["fixture-paper"].is_alive())
        ready = self.host.snapshot()["preparations"]["fixture-paper"]
        self.assertTrue(ready["ready"])
        self.assertEqual(before, json.loads((self.workspace / "state.json").read_text(encoding="utf-8")))
        self.assertFalse(before["sources"]["fixture-paper"].get("reading_started", False))
        self.assertEqual(3, self.runtime.calls.count("translate"))
        repeated = self.host.prepare_reading("fixture-paper", request_id=prepare_id)
        self.assertEqual(result["readingOperation"], repeated["readingOperation"])
        self.assertEqual(3, self.runtime.calls.count("translate"))
        open_id = uuid.uuid4().hex
        opened = self.host.open_prepared_reading("fixture-paper", request_id=open_id)
        self.assertEqual("chunk-001", self.host.snapshot()["current"]["chunkId"])
        self.assertEqual(3, self.runtime.calls.count("translate"))
        self.assertTrue(json.loads((self.workspace / "state.json").read_text(encoding="utf-8"))["sources"]["fixture-paper"]["reading_started"])
        replayed = self.host.open_prepared_reading("fixture-paper", request_id=open_id)
        self.assertEqual(opened["readingOperation"], replayed["readingOperation"])
        self.assertEqual(opened["readingOperation"]["reading_revision"],
                         json.loads((self.workspace / "state.json").read_text())["reading_revision"])

    def test_cancel_fences_late_translation_and_manual_resume_reuses_context(self):
        self.host.close()
        self.runtime = WaitingRuntime()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.assertTrue(self.runtime.entered.wait(3))
        self.host.cancel_preparation("fixture-paper")
        self.runtime.release.set()
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertEqual("cancelled", self.host.snapshot()["preparations"]["fixture-paper"]["status"])
        self.assertEqual(0, self.host.snapshot()["preparations"]["fixture-paper"]["completed"])
        self.host.resume_preparation("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertTrue(self.host.snapshot()["preparations"]["fixture-paper"]["ready"])
        self.assertEqual(1, self.runtime.calls.count("context"))

    def test_first_entry_creates_complete_candidate_without_selecting_plan(self):
        self.host.close()
        plan_path = self.workspace / "sources/fixture-paper/reading/plans/plan-001/chunks.jsonl"
        chunks = [json.loads(line) for line in plan_path.read_text(encoding="utf-8").splitlines()]
        draft = {"chunks": [{key: chunk[key] for key in ("section_path", "source_lines", "images")}
                            for chunk in chunks], "glossary": [["alias address", "别名地址"]]}
        state_path = self.workspace / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["sources"]["fixture-paper"].update(current_plan_id=None, current_chunk_id=None, reading_started=False)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.runtime = PlanningRuntime(draft)
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        result = self.host.snapshot()["preparations"]["fixture-paper"]
        self.assertTrue(result["ready"], self.host.reading_app.status("fixture-paper"))
        self.assertEqual("plan-002", result["plan_id"])
        self.assertEqual(1, self.runtime.calls.count("plan"))
        self.assertIsNone(json.loads(state_path.read_text(encoding="utf-8"))["sources"]["fixture-paper"]["current_plan_id"])
        self.host.open_prepared_reading("fixture-paper", request_id=uuid.uuid4().hex)
        opened = self.host.snapshot()
        self.assertEqual("plan-002", opened["current"]["planId"])
        self.assertEqual("chunk-001", opened["current"]["chunkId"])

    def test_invalid_plan_feedback_is_bounded_and_preserves_selected_assets(self):
        self.host.close()
        chunks_path = self.workspace / "sources/fixture-paper/reading/plans/plan-001/chunks.jsonl"
        original = chunks_path.read_bytes()
        chunks = [json.loads(line) for line in original.decode().splitlines()]
        draft = {"chunks": [{key: c[key] for key in ("section_path", "source_lines", "images")}
                            for c in chunks], "glossary": []}

        class CorrectingPlan(PlanningRuntime):
            def plan(self, **kwargs):
                self.calls.append("plan")
                self.feedback = kwargs["context"].get("plan_feedback")
                return {"chunks": [], "glossary": []} if self.calls.count("plan") == 1 else self.draft

        self.runtime = CorrectingPlan(draft)
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex, rebuild=True)
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertTrue(self.host.snapshot()["preparations"]["fixture-paper"]["ready"])
        self.assertEqual(2, self.runtime.calls.count("plan"))
        self.assertIn("invalid", self.runtime.feedback["validation_error"])
        self.assertEqual(original, chunks_path.read_bytes())
        self.assertEqual("plan-001", json.loads((self.workspace / "state.json").read_text())["sources"]["fixture-paper"]["current_plan_id"])
        self.runtime.draft = {"chunks": [], "glossary": []}
        self.runtime.calls.clear()
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex, rebuild=True)
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertEqual("failed", self.host.snapshot()["preparations"]["fixture-paper"]["status"])
        self.assertEqual(3, self.runtime.calls.count("plan"))
        self.assertEqual(original, chunks_path.read_bytes())

    def test_mixed_bundle_requires_explicit_chunk_languages(self):
        bundle = self.workspace / "sources/fixture-paper/parser-bundle"
        metadata_path = bundle / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["language"] = "mixed"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        chunks_path = self.workspace / "sources/fixture-paper/reading/plans/plan-001/chunks.jsonl"
        chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
        draft = {"chunks": [{key: chunk[key] for key in ("section_path", "source_lines", "images")}
                             for chunk in chunks], "glossary": []}
        with self.assertRaisesRegex(WorkspaceError, "requires each Chunk language"):
            _reading_plan_records(bundle, draft)
        draft["chunks"][0]["language"] = "zh"
        for chunk in draft["chunks"][1:]:
            chunk["language"] = "en"
        records, _ = _reading_plan_records(bundle, draft)
        self.assertEqual("zh", records[0]["language"])

    def test_only_affected_candidate_is_repaired_then_rechecked(self):
        self.host.close()
        self.runtime = RepairingRuntime()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertTrue(self.host.snapshot()["preparations"]["fixture-paper"]["ready"])
        self.assertEqual(4, self.runtime.calls.count("translate"))
        self.assertEqual(2, self.runtime.calls.count("check"))

    def test_two_failed_repair_rounds_do_not_claim_ready(self):
        self.host.close()
        self.runtime = RepairingRuntime(always_fail=True)
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        result = self.host.snapshot()["preparations"]["fixture-paper"]
        self.assertEqual("failed", result["status"])
        self.assertFalse(result["ready"])
        self.assertEqual(2, self.host.reading_app.status("fixture-paper")["repair_rounds"])
        self.runtime.always_fail = False
        self.host.resume_preparation("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        recovered = self.host.reading_app.status("fixture-paper")
        self.assertTrue(recovered["ready"])
        self.assertEqual(0, recovered["repair_rounds"])
        self.assertEqual(2, recovered["attempt_history"][-1]["repair_rounds"])
        self.assertEqual(4, self.runtime.calls.count("check"))

    def test_host_restart_interrupts_attempt_until_explicit_resume(self):
        self.host.close()
        self.runtime = WaitingRuntime()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.assertTrue(self.runtime.entered.wait(3))
        closing = threading.Thread(target=self.host.close)
        closing.start()
        self.runtime.release.set()
        closing.join(3)
        self.assertFalse(closing.is_alive())
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.assertEqual("interrupted", self.host.snapshot()["preparations"]["fixture-paper"]["status"])
        self.assertEqual(1, self.runtime.calls.count("context"))
        self.host.resume_preparation("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertTrue(self.host.snapshot()["preparations"]["fixture-paper"]["ready"])
        self.assertEqual(1, self.runtime.calls.count("context"))

    def test_public_http_reading_operations_keep_preparation_separate(self):
        self.host.close()
        self.runtime = WaitingRuntime()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        server = Server(("127.0.0.1", 0), self.host)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            path = "/library/sources/fixture-paper/open"
            connection.request("POST", path, body=json.dumps({"requestId": uuid.uuid4().hex}),
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(200, response.status)
            self.assertEqual("running", json.load(response)["value"]["preparations"]["fixture-paper"]["status"])
            self.runtime.release.set()
            self.host.reading_workers["fixture-paper"].join(3)
            connection.request("GET", "/reader/window")
            prepared = json.load(connection.getresponse())["value"]
            self.assertTrue(prepared["preparations"]["fixture-paper"]["ready"])
            self.assertFalse(json.loads((self.workspace / "state.json").read_text())["sources"]["fixture-paper"].get("reading_started", False))
            connection.request("POST", path, body=json.dumps({"requestId": uuid.uuid4().hex}),
                               headers={"Content-Type": "application/json"})
            opened = json.load(connection.getresponse())["value"]
            self.assertEqual("chunk-001", opened["current"]["chunkId"])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()

    def test_check_interruption_requires_resume_without_retranslating(self):
        class InterruptedCheck(ReadingRuntimeDouble):
            def check(self, **kwargs):
                self.calls.append("check")
                if self.calls.count("check") == 1:
                    raise ReadingExternalError("check interrupted")
                return {"passed": True, "issues": {},
                        "coverage": [chunk["chunk_id"] for chunk in kwargs["chunks"]]}

        self.host.close()
        self.runtime = InterruptedCheck()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        failed = self.host.snapshot()["preparations"]["fixture-paper"]
        self.assertEqual("failed", failed["status"])
        self.assertFalse(failed["ready"])
        self.assertEqual(failed["total"], failed["completed"])
        self.host.close()
        calls = list(self.runtime.calls)
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.assertEqual(calls, self.runtime.calls)
        self.assertFalse(self.host.snapshot()["preparations"]["fixture-paper"]["ready"])
        self.host.resume_preparation("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertTrue(self.host.snapshot()["preparations"]["fixture-paper"]["ready"])
        self.assertEqual(calls + ["check"], self.runtime.calls)

    def test_preparation_notifies_subscribers_before_runtime_finishes(self):
        class SteppedRuntime(ReadingRuntimeDouble):
            def __init__(self):
                super().__init__()
                self.entered = threading.Event()
                self.release = threading.Event()
                self.second = threading.Event()
                self.finish = threading.Event()

            def translate(self, **kwargs):
                if not self.entered.is_set():
                    self.entered.set()
                    self.release.wait(3)
                else:
                    self.second.set()
                    self.finish.wait(3)
                return super().translate(**kwargs)

        self.host.close()
        self.runtime = SteppedRuntime()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        try:
            self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
            self.assertTrue(self.runtime.entered.wait(3))
            generation = self.host.generation
            self.runtime.release.set()
            self.assertTrue(self.runtime.second.wait(3))
            self.assertEqual(1, self.host.snapshot()["preparations"]["fixture-paper"]["completed"])
            self.assertGreater(self.host.generation, generation)
        finally:
            self.runtime.release.set()
            self.runtime.finish.set()
            self.host.reading_workers["fixture-paper"].join(3)

    def test_request_identity_and_second_writer_cannot_replace_running_attempt(self):
        self.host.close()
        self.runtime = WaitingRuntime()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        request_id = uuid.uuid4().hex
        self.host.prepare_reading("fixture-paper", request_id=request_id)
        self.assertTrue(self.runtime.entered.wait(3))
        with self.assertRaises(WorkspaceError):
            self.host.prepare_reading("fixture-paper", request_id=request_id, rebuild=True)
        second = HostService(self.workspace, self.fixture.root / "other-host", reading_runtime=ReadingRuntimeDouble())
        try:
            with self.assertRaises(WorkspaceError):
                second.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
            self.assertEqual("running", self.host.reading_app.status("fixture-paper")["status"])
        finally:
            second.close()
            self.runtime.release.set()
            self.host.reading_workers["fixture-paper"].join(3)

    def test_glossary_version_conflict_does_not_publish_late_translation(self):
        self.host.close()
        self.runtime = WaitingRuntime()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.assertTrue(self.runtime.entered.wait(3))
        glossary = self.workspace / "sources/fixture-paper/reading/plans/plan-001/glossary.tsv"
        glossary.write_text(glossary.read_text(encoding="utf-8") + "new term\t新术语\n", encoding="utf-8")
        self.runtime.release.set()
        self.host.reading_workers["fixture-paper"].join(3)
        status = self.host.snapshot()["preparations"]["fixture-paper"]
        self.assertEqual("commit_conflict", status["status"])
        record = json.loads((self.workspace / "sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json").read_text())
        self.assertIsNone(record["translation"])
        conflicts = list((self.workspace / "sources/fixture-paper/reading/conflicts").glob("*.json"))
        self.assertEqual(1, len(conflicts))
        self.assertEqual("reading_glossary_changed", json.loads(conflicts[0].read_text())["reason"])

    def test_reference_exclusion_cannot_hide_following_appendix(self):
        self._assert_reference_exclusion("References", "[1] Citation.")

    def test_numbered_chinese_references_preserve_following_learning_path(self):
        self._assert_reference_exclusion("10.3 参考资料", "- Citation.")

    def _assert_reference_exclusion(self, heading, entry):
        self.host.close()
        content = self.workspace / "sources/fixture-paper/parser-bundle/content.md"
        content.write_text(f"# X\n\n## Body\nA method.\n![Architecture](images/image-001.png)\nFigure 1: Architecture.\n## {heading}\n{entry}\n## Appendix\nThe derivation.\n", encoding="utf-8")
        state_path = self.workspace / "state.json"
        state = json.loads(state_path.read_text())
        state["sources"]["fixture-paper"].update(current_plan_id=None, current_chunk_id=None)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        draft = {"chunks": [
            {"section_path": ["X", "Body"], "source_lines": [1, 6], "images": ["images/image-001.png"]},
            {"section_path": ["X", "Appendix"], "source_lines": [9, 10], "images": []}],
            "excluded_ranges": [[7, 8]], "glossary": []}
        self.runtime = PlanningRuntime(draft)
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertTrue(self.host.snapshot()["preparations"]["fixture-paper"]["ready"])
        provenance = json.loads((self.workspace / "sources/fixture-paper/reading/plans/plan-002/provenance.json").read_text())
        self.assertEqual([[7, 8]], provenance["excluded_ranges"])
        self.runtime.draft = {"chunks": [
            {"section_path": ["X", "Body"], "source_lines": [1, 10], "images": ["images/image-001.png"]}],
            "glossary": []}
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex, rebuild=True)
        self.host.reading_workers["fixture-paper"].join(3)
        rejected = self.host.snapshot()["preparations"]["fixture-paper"]
        self.assertEqual("failed", rejected["status"])
        self.assertIn("Exclude bibliography", rejected["error"])

    def test_transport_retry_budget_is_persisted_separately_from_repairs(self):
        self.host.close()
        self.runtime = TransientRuntime(2)
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        run = self.host.reading_app.status("fixture-paper")
        self.assertTrue(run["ready"])
        self.assertEqual(2, run["transport_retries"])
        self.assertEqual(0, run["repair_rounds"])

    def test_source_a_ready_while_viewing_b_keeps_b_selected(self):
        self.host.close()
        source = self.workspace / "sources/fixture-paper"
        second = self.workspace / "sources/second-paper"
        shutil.copytree(source, second)
        metadata = second / "source.yaml"
        value = json.loads(metadata.read_text(encoding="utf-8"))
        value.update(source_id="second-paper", identity="fixture:second")
        metadata.write_text(json.dumps(value), encoding="utf-8")
        state_path = self.workspace / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["sources"]["second-paper"] = dict(state["sources"]["fixture-paper"])
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.runtime = WaitingRuntime()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.assertTrue(self.runtime.entered.wait(3))
        self.host.core.core.switch_source("second-paper")
        self.assertEqual("second-paper", self.host.snapshot()["source"]["sourceId"])
        self.runtime.release.set()
        self.host.reading_workers["fixture-paper"].join(3)
        snapshot = self.host.snapshot()
        self.assertTrue(snapshot["preparations"]["fixture-paper"]["ready"])
        self.assertEqual("second-paper", snapshot["source"]["sourceId"])


class Stage4NavigationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_focus_read.FocusReadTests()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.runtime = ReadingRuntimeDouble()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        self.host.open_prepared_reading("fixture-paper", request_id=uuid.uuid4().hex)

    def tearDown(self):
        self.host.close()
        self.fixture.tearDown()

    def receipt(self):
        view = self.host.snapshot()
        return {"sourceId": view["current"]["sourceId"], "planId": view["current"]["planId"],
                "chunkId": view["current"]["chunkId"], "readingRevision": view["readingRevision"]}

    def rebuild_draft(self):
        plan_path = self.workspace / "sources/fixture-paper/reading/plans/plan-001/chunks.jsonl"
        chunks = [json.loads(line) for line in plan_path.read_text(encoding="utf-8").splitlines()]
        return {"chunks": [{key: chunk[key] for key in ("section_path", "source_lines", "images")}
                           for chunk in chunks], "glossary": [["alias address", "别名地址"]]}

    def test_rebuild_keeps_old_reading_then_requires_versioned_activation(self):
        self.host.continue_cached({"receipt": self.receipt(), "requestId": uuid.uuid4().hex})
        old = self.host.snapshot()
        old_record = (self.workspace / "sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json").read_bytes()
        candidate_runtime = PlanningRuntime(self.rebuild_draft())
        self.host.reading_app.runtime = candidate_runtime
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex, rebuild=True)
        self.host.reading_workers["fixture-paper"].join(3)
        preparation = self.host.snapshot()["preparations"]["fixture-paper"]
        self.assertTrue(preparation["ready"], preparation)
        self.assertTrue(preparation["candidate"])
        self.assertEqual("plan-002", preparation["plan_id"])
        self.assertEqual("chunk-002", self.host.snapshot()["current"]["chunkId"])
        reopened = self.host.open_prepared_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.assertEqual("plan-001", reopened["current"]["planId"])
        self.assertEqual("chunk-002", reopened["current"]["chunkId"])
        self.assertEqual(old_record, (self.workspace / "sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json").read_bytes())
        self.assertEqual(3, candidate_runtime.calls.count("translate"))
        stale_revision = old["readingRevision"]
        self.host.continue_cached({"receipt": self.receipt(), "requestId": uuid.uuid4().hex})
        with self.assertRaises(WorkspaceError):
            self.host.activate_reading_candidate("fixture-paper", {"planId": "plan-002",
                "readingRevision": stale_revision, "requestId": uuid.uuid4().hex})
        revision = self.host.snapshot()["readingRevision"]
        request_id = uuid.uuid4().hex
        activated = self.host.activate_reading_candidate("fixture-paper", {"planId": "plan-002",
            "readingRevision": revision, "requestId": request_id})
        self.assertEqual("chunk-001", activated["current"]["chunkId"])
        self.assertEqual("plan-002", activated["current"]["planId"])
        again = self.host.activate_reading_candidate("fixture-paper", {"planId": "plan-002",
            "readingRevision": revision, "requestId": request_id})
        self.assertEqual(activated["readingOperation"], again["readingOperation"])
        with self.assertRaises(WorkspaceError):
            self.host.activate_reading_candidate("fixture-paper", {"planId": "plan-001",
                "readingRevision": revision, "requestId": request_id})
        self.assertEqual(old_record, (self.workspace / "sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json").read_bytes())
        content = self.workspace / "sources/fixture-paper/parser-bundle/content.md"
        content.write_text(content.read_text(encoding="utf-8") + "\nVersion two.\n", encoding="utf-8")
        self.assertIn("旧版原文", self.host.snapshot()["readingUnavailable"])
        with self.assertRaises(WorkspaceError):
            self.host.continue_cached({"receipt": {"sourceId": "fixture-paper", "planId": "plan-002",
                "chunkId": "chunk-001", "readingRevision": self.host.snapshot()["readingRevision"]},
                "requestId": uuid.uuid4().hex})
        historical = self.host.core.reference({"sourceId": "fixture-paper", "planId": "plan-001", "chunkId": "chunk-001"})
        self.assertIn("alias address", historical["sourceMarkdown"])
        self.assertNotIn("Version two", historical["sourceMarkdown"])
        if historical["images"]:
            self.assertIn("historical-assets", historical["images"][0]["src"])
        archive = self.workspace / "sources/fixture-paper/reading/bundles"
        shutil.rmtree(next(archive.iterdir()))
        with self.assertRaisesRegex(ValueError, "原版本引用不可定位"):
            self.host.core.reference({"sourceId": "fixture-paper", "planId": "plan-001", "chunkId": "chunk-001"})

    def test_failed_candidate_does_not_block_selected_plan(self):
        runtime = PlanningRuntime({"chunks": [], "glossary": []})
        self.host.reading_app.runtime = runtime
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex, rebuild=True)
        self.host.reading_workers["fixture-paper"].join(3)
        self.assertEqual("failed", self.host.snapshot()["preparations"]["fixture-paper"]["status"])
        opened = self.host.library_read("fixture-paper", request_id=uuid.uuid4().hex)
        self.assertEqual("plan-001", opened["current"]["planId"])
        self.assertEqual("chunk-001", opened["current"]["chunkId"])

    def test_cancelled_candidate_cannot_write_late_or_move_old_cursor(self):
        class BlockingPlanRuntime(PlanningRuntime):
            def __init__(self, draft):
                super().__init__(draft)
                self.entered = threading.Event()
                self.release = threading.Event()

            def translate(self, **kwargs):
                self.entered.set()
                self.release.wait(3)
                return super().translate(**kwargs)

        runtime = BlockingPlanRuntime(self.rebuild_draft())
        self.host.reading_app.runtime = runtime
        before = self.host.snapshot()
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex, rebuild=True)
        self.assertTrue(runtime.entered.wait(3))
        self.host.cancel_preparation("fixture-paper")
        runtime.release.set()
        self.host.reading_workers["fixture-paper"].join(3)
        after = self.host.snapshot()
        self.assertEqual(before["current"]["chunkId"], after["current"]["chunkId"])
        self.assertEqual(before["current"]["planId"], after["current"]["planId"])
        self.assertEqual("cancelled", after["preparations"]["fixture-paper"]["status"])
        candidate = self.workspace / "sources/fixture-paper/reading/plans/plan-002/records/chunk-001.json"
        self.assertIsNone(json.loads(candidate.read_text(encoding="utf-8"))["translation"])

    def test_explicit_candidate_glossary_revision_retranslates_affected_only(self):
        runtime = PlanningRuntime(self.rebuild_draft())
        self.host.reading_app.runtime = runtime
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex, rebuild=True)
        self.host.reading_workers["fixture-paper"].join(3)
        ready = self.host.snapshot()["preparations"]["fixture-paper"]
        self.assertTrue(ready["ready"])
        plan_root = self.workspace / "sources/fixture-paper/reading/plans/plan-002"
        unaffected = (plan_root / "records/chunk-003.json").read_bytes()
        old_asset = (self.workspace / "sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json").read_bytes()
        before_translations = runtime.calls.count("translate")
        self.host.revise_candidate_glossary("fixture-paper", {"planId": "plan-002",
            "expectedGlossaryRevision": ready["glossary_revision"],
            "terms": [{"source": "alias address", "translation": "地址别名"}],
            "requestId": uuid.uuid4().hex})
        self.host.reading_workers["fixture-paper"].join(3)
        revised = self.host.snapshot()["preparations"]["fixture-paper"]
        self.assertTrue(revised["ready"], revised)
        self.assertEqual(before_translations + 2, runtime.calls.count("translate"))
        self.assertEqual(unaffected, (plan_root / "records/chunk-003.json").read_bytes())
        self.assertEqual(old_asset, (self.workspace / "sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json").read_bytes())
        with self.assertRaises(WorkspaceError):
            self.host.revise_candidate_glossary("fixture-paper", {"planId": "plan-002",
                "expectedGlossaryRevision": ready["glossary_revision"], "terms": [],
                "requestId": uuid.uuid4().hex})

    def test_one_continue_per_version_and_replay_returns_original_result(self):
        first = self.receipt()
        request = uuid.uuid4().hex
        result = self.host.continue_cached({"receipt": first, "requestId": request})
        self.assertEqual("chunk-002", result["current"]["chunkId"])
        self.assertEqual("chunk-002", result["readingOperation"]["chunk_id"])
        repeated = self.host.continue_cached({"receipt": first, "requestId": request})
        self.assertEqual(result["readingOperation"], repeated["readingOperation"])
        with self.assertRaises(WorkspaceError):
            self.host.continue_cached({"receipt": first, "requestId": uuid.uuid4().hex})
        with self.assertRaises(WorkspaceError):
            self.host.continue_cached({"receipt": {**first, "chunkId": "chunk-002"}, "requestId": request})
        self.assertEqual(3, self.runtime.calls.count("translate"))

    def test_restart_can_query_and_replay_committed_continue(self):
        first = self.receipt()
        request = uuid.uuid4().hex
        committed = self.host.continue_cached({"receipt": first, "requestId": request})["readingOperation"]
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / "host", reading_runtime=self.runtime)
        self.assertEqual(committed, self.host.reading_request_result(request))
        replay = self.host.continue_cached({"receipt": first, "requestId": request})
        self.assertEqual(committed, replay["readingOperation"])
        self.assertEqual("chunk-002", replay["current"]["chunkId"])
        self.assertEqual(3, self.runtime.calls.count("translate"))

    def test_last_chunk_needs_finish_then_reread_invalidates_old_receipt(self):
        self.host.continue_cached({"receipt": self.receipt(), "requestId": uuid.uuid4().hex})
        self.host.continue_cached({"receipt": self.receipt(), "requestId": uuid.uuid4().hex})
        last = self.receipt()
        with self.assertRaises(WorkspaceError):
            self.host.continue_cached({"receipt": last, "requestId": uuid.uuid4().hex})
        self.assertEqual("reading", self.host.snapshot()["status"])
        finished = self.host.finish_reading({"receipt": last, "requestId": uuid.uuid4().hex})
        self.assertEqual("completed", finished["status"])
        self.assertIsNone(finished["current"])
        self.host.open_prepared_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.assertEqual("completed", self.host.snapshot()["status"])
        rereread = self.host.reread_reading({"receipt": {"sourceId": "fixture-paper", "planId": "plan-001",
            "chunkId": None, "readingRevision": self.host.snapshot()["readingRevision"]}, "requestId": uuid.uuid4().hex})
        self.assertEqual("chunk-001", rereread["current"]["chunkId"])
        with self.assertRaises(WorkspaceError):
            self.host.continue_cached({"receipt": {**last, "chunkId": "chunk-001"}, "requestId": uuid.uuid4().hex})
        self.assertEqual(3, self.runtime.calls.count("translate"))

    def test_review_only_allows_prior_chunks_and_never_changes_cursor(self):
        with self.assertRaises(WorkspaceError):
            self.host.review_chunk("fixture-paper", "plan-001", "chunk-003")
        self.host.continue_cached({"receipt": self.receipt(), "requestId": uuid.uuid4().hex})
        before = self.host.snapshot()
        reviewed = self.host.review_chunk("fixture-paper", "plan-001", "chunk-001")
        self.assertEqual("chunk-001", reviewed["reviewChunk"]["chunkId"])
        self.assertEqual(before["readingRevision"], reviewed["readingRevision"])
        self.assertEqual("chunk-002", self.host.snapshot()["current"]["chunkId"])
        with self.assertRaises(WorkspaceError):
            self.host.review_chunk("fixture-paper", "plan-001", "chunk-003")


class QuestionRuntime:
    def __init__(self, workspace, **kwargs):
        self.workspace = workspace
        self.events = queue.Queue()
        self.prompts = []
        self.closed = False

    def open_session(self, resume_key, *, instructions, skills=()):
        return "question-thread"

    def start_turn(self, *, prompt, skills=()):
        self.prompts.append(prompt)
        if "记下来" in prompt:
            bundle = SourceNotes(self.workspace).bundle_version("fixture-paper")
            self.events.put({'id': 42, 'method': 'tool/call', 'params': {'tool': 'focus', 'arguments': {
                'action': 'source_note', 'arguments': json.dumps({'content': '第 1 段说明别名地址。',
                    'kind': 'conclusion', 'origin': 'dialogue', 'evidence_role': 'explanation',
                    'anchor': {'sourceId': 'fixture-paper', 'bundle': bundle,
                               'sourceLines': [4, 4], 'quote': 'alias address'}})}}})
        else:
            self.events.put({'method': 'message/completed', 'params': {'itemId': uuid.uuid4().hex,
                'text': '解释仅针对引用的段落。'}})
            self.events.put({'method': 'turn/completed', 'params': {'status': 'completed'}})

    def send(self, message):
        self.events.put({'method': 'turn/completed', 'params': {'status': 'completed'}})

    def close(self):
        self.closed = True


class Stage4DiscussionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_focus_read.FocusReadTests()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.question_runtimes = []

        def factory(workspace, **kwargs):
            runtime = QuestionRuntime(workspace, **kwargs)
            self.question_runtimes.append(runtime)
            return runtime

        self.host = HostService(self.workspace, self.fixture.root / "host", backend_factory=factory,
                                reading_runtime=ReadingRuntimeDouble())
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex)
        self.host.reading_workers["fixture-paper"].join(3)
        self.host.open_prepared_reading("fixture-paper", request_id=uuid.uuid4().hex)

    def tearDown(self):
        self.host.close()
        self.fixture.tearDown()

    def receipt(self):
        current = self.host.snapshot()["current"]
        return {"sourceId": current["sourceId"], "planId": current["planId"], "chunkId": current["chunkId"],
                "readingRevision": self.host.snapshot()["readingRevision"]}

    def test_review_question_keeps_original_reference_and_notes_survive_reread(self):
        first = self.receipt()
        self.host.continue_cached({"receipt": first, "requestId": uuid.uuid4().hex})
        reviewed = self.host.review_chunk("fixture-paper", "plan-001", "chunk-001")["reviewChunk"]
        self.assertEqual("chunk-001", reviewed["chunkId"])
        before = self.host.snapshot()["readingRevision"]
        self.host.start({"requestId": uuid.uuid4().hex, "sourceId": "fixture-paper",
            "receipt": first, "content": "解释这个例子"})
        self.host.worker.join(3)
        window = self.host.snapshot()
        self.assertEqual(before, window["readingRevision"])
        self.assertEqual("chunk-002", window["current"]["chunkId"])
        self.assertEqual("chunk-001", window["conversation"][-1]["reference"]["chunkId"])
        self.assertIn("alias address", self.question_runtimes[-1].prompts[0])
        self.host.start({"requestId": uuid.uuid4().hex, "sourceId": "fixture-paper",
            "receipt": first, "content": "记下来"})
        self.host.worker.join(3)
        note = self.host.snapshot()["sourceNotes"][0]
        self.assertEqual("fixture-paper", note["sourceId"])
        self.assertEqual("chunk-002", self.host.snapshot()["current"]["chunkId"])
        reread = self.host.reread_reading({"receipt": self.receipt(), "requestId": uuid.uuid4().hex})
        self.assertEqual("chunk-001", reread["current"]["chunkId"])
        self.assertEqual(note["noteId"], reread["sourceNotes"][0]["noteId"])
        changed = self.host.source_note_change("fixture-paper", note["noteId"],
            {"expectedRevision": note["revision"], "requestId": uuid.uuid4().hex,
             "content": "已更正"}, "edit")
        self.assertEqual("已更正", changed["sourceNotes"][0]["content"])
        plan = self.workspace / "sources/fixture-paper/reading/plans/plan-001/chunks.jsonl"
        chunks = [json.loads(line) for line in plan.read_text(encoding="utf-8").splitlines()]
        draft = {"chunks": [{key: chunk[key] for key in ("section_path", "source_lines", "images")}
                            for chunk in chunks], "glossary": []}
        self.host.reading_app.runtime = PlanningRuntime(draft)
        self.host.prepare_reading("fixture-paper", request_id=uuid.uuid4().hex, rebuild=True)
        self.host.reading_workers["fixture-paper"].join(3)
        candidate = self.host.snapshot()["preparations"]["fixture-paper"]
        self.host.activate_reading_candidate("fixture-paper", {"planId": candidate["plan_id"],
            "readingRevision": self.host.snapshot()["readingRevision"], "requestId": uuid.uuid4().hex})
        self.assertEqual(note["noteId"], self.host.snapshot()["sourceNotes"][0]["noteId"])
        content = self.workspace / "sources/fixture-paper/parser-bundle/content.md"
        content.write_text(content.read_text(encoding="utf-8").replace("alias address", "renamed address")
                           + "\nNew version.\n", encoding="utf-8")
        self.assertEqual("historical", self.host.snapshot()["sourceNotes"][0]["referenceStatus"])
        question_id = uuid.uuid4().hex
        self.host.start({"requestId": question_id, "sourceId": "fixture-paper",
                         "receipt": first, "content": "回看旧版例子"})
        self.host.worker.join(3)
        scope = self.host.state["requests"][question_id]["discussion"]
        self.assertNotEqual(self.host.source_notes.bundle_version("fixture-paper"), scope["bundle"])
        old_hits = self.host.discussion_app.candidate(scope, "search", {"query": "alias address"})
        self.assertTrue(old_hits["matches"])
        original = self.host.discussion_app.candidate(scope, "read_range", {"start": 4, "end": 4})
        self.assertIn("alias address", original["source_text"])
        new_hits = self.host.discussion_app.candidate(scope, "search", {"query": "renamed"})
        self.assertFalse(new_hits["matches"])


if __name__ == "__main__":
    unittest.main()
