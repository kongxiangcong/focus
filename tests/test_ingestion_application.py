from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from core import IngestionApplication, IngestionExternalError, SourceLibrary, WorkspaceError
from host.service import HostService


class RecordingParser:
    def __init__(self) -> None:
        self.calls = 0

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        self.calls += 1
        raise AssertionError("parser must not run before confirmation")


class ValidParser:
    def __init__(self) -> None:
        self.calls = 0

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        self.calls += 1
        (candidate / "images").mkdir(parents=True)
        (candidate / "source.pdf").write_bytes(source.read_bytes())
        (candidate / "content.md").write_text("# Stored Paper\n\nBody.\n", encoding="utf-8")
        (candidate / "metadata.json").write_text(
            json.dumps(
                {
                    "source_kind": "paper_pdf",
                    "language": "en",
                    "parser": "article-parser",
                    "batch_id": "fixture-batch",
                }
            ),
            encoding="utf-8",
        )
        (candidate / "validation.json").write_text(
            json.dumps({"ok": True, "warnings": []}), encoding="utf-8"
        )
        return {"title": "Stored Paper", "short_name": "Stored"}


class InvalidParser(ValidParser):
    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        result = super().parse(source, candidate, checkpoint=checkpoint)
        (candidate / "validation.json").write_text('{"ok": false}\n', encoding="utf-8")
        return result


class LongTitleParser(ValidParser):
    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        result = super().parse(source, candidate, checkpoint=checkpoint)
        title = "DeepStack: " + "Scalable design space exploration " * 8
        (candidate / "content.md").write_text(f"# {title}\n\nBody.\n", encoding="utf-8")
        return {"title": title, "short_name": title}


class ResumableParser(ValidParser):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures
        self.starts = 0
        self.resumes = 0

    def _complete(self, source, candidate, checkpoint):
        if self.calls <= self.failures:
            raise IngestionExternalError("network", "temporary network failure", transient=True)
        return ValidParser.parse(self, source, candidate, checkpoint=checkpoint)

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        self.starts += 1
        self.calls += 1
        checkpoint({"reference_kind": "batch_id", "reference_id": "remote-batch"})
        return self._complete(source, candidate, checkpoint)

    def resume(self, source: Path, candidate: Path, *, checkpoint):
        self.resumes += 1
        self.calls += 1
        return self._complete(source, candidate, checkpoint)


class UnknownAcceptanceParser:
    def __init__(self) -> None:
        self.calls = 0

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        self.calls += 1
        raise IngestionExternalError(
            "acceptance_unknown", "submission outcome is unknown", acceptance_unknown=True
        )


class BlockingParser(ValidParser):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = 0
        self.resumes = 0

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        checkpoint({"reference_kind": "batch_id", "reference_id": "blocking-batch"})
        self.started.set()
        self.release.wait(5)
        return super().parse(source, candidate, checkpoint=checkpoint)

    def resume(self, source: Path, candidate: Path, *, checkpoint):
        self.resumes += 1
        return super().parse(source, candidate, checkpoint=checkpoint)

    def cancel(self, checkpoint):
        self.cancelled += 1
        return True


class InspectingRuntime:
    def __init__(self, *, valid=True) -> None:
        self.calls = 0
        self.valid = valid

    def inspect(self, candidate: Path):
        self.calls += 1
        return {
            "title_matches": self.valid,
            "image_observed": self.valid,
            "notes": "bounded candidate inspection",
        }


class BlockingRuntime(InspectingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = 0

    def inspect(self, candidate: Path):
        self.started.set()
        self.release.wait(5)
        return super().inspect(candidate)

    def cancel(self):
        self.cancelled += 1
        self.release.set()
        return True


class IngestionApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.pdf = self.root / "selected.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nselected\n")

    def tearDown(self):
        self.temporary.cleanup()

    def test_staging_survives_reopen_and_changed_input_invalidates_confirmation(self):
        parser = RecordingParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")

        staged = app.stage_pdf(self.pdf, topic_title="Systems")
        self.assertEqual("awaiting_confirmation", staged["status"])
        self.assertEqual(0, parser.calls)
        reopened = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        self.assertEqual(staged["item_id"], reopened.get(staged["item_id"])["item_id"])

        confirmed = reopened.confirm(
            staged["item_id"], services=["mineru"], purpose="register source", scope="ingestion"
        )
        self.assertEqual("confirmed", confirmed["status"])
        replacement = self.root / "replacement.pdf"
        replacement.write_bytes(b"%PDF-1.4\nreplacement\n")
        updated = reopened.update_staged(staged["item_id"], source=replacement)
        self.assertEqual("awaiting_confirmation", updated["status"])
        self.assertIsNone(updated["confirmation"])
        self.assertEqual(0, parser.calls)

        with self.assertRaisesRegex(WorkspaceError, "confirmation"):
            reopened.process(staged["item_id"], request_id="request-1")

        persisted = json.loads(
            (self.workspace / "inbox" / staged["item_id"] / "item.json").read_text(encoding="utf-8")
        )
        self.assertEqual("awaiting_confirmation", persisted["status"])

    def test_confirmed_pdf_publishes_a_viewable_source_without_a_reading_plan(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")

        completed = app.process(item["item_id"], request_id="request-1")

        self.assertEqual(("completed", "published", "attached"), (
            completed["status"], completed["document_status"], completed["topic_status"]
        ))
        self.assertEqual(1, parser.calls)
        source_id = completed["source_id"]
        source_root = self.workspace / "sources" / source_id
        self.assertEqual(self.pdf.read_bytes(), (source_root / "parser-bundle" / "source.pdf").read_bytes())
        self.assertEqual("# Stored Paper\n\nBody.\n", (source_root / "parser-bundle" / "content.md").read_text(encoding="utf-8"))
        state = json.loads((self.workspace / "state.json").read_text(encoding="utf-8"))
        self.assertEqual({"current_plan_id": None, "current_chunk_id": None}, state["sources"][source_id])
        self.assertFalse((source_root / "reading").exists())
        topic = json.loads((self.workspace / "topics" / "systems" / "topic.yaml").read_text(encoding="utf-8"))
        self.assertEqual([source_id], topic["sources"])

        repeated = app.process(item["item_id"], request_id="request-1")
        self.assertEqual(source_id, repeated["source_id"])
        self.assertEqual(1, parser.calls)

    def test_long_publisher_title_does_not_become_an_unsafe_storage_name(self):
        app = IngestionApplication(self.workspace, parser=LongTitleParser(), writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        result = app.process(item["item_id"], request_id="long-title")
        self.assertEqual("completed", result["status"])
        self.assertLessEqual(len(result["source_id"]), 86)
        source = json.loads(
            (self.workspace / "sources" / result["source_id"] / "source.yaml").read_text(encoding="utf-8")
        )
        self.assertGreater(len(source["title"]), len(source["short_name"]))

    def test_same_original_reuses_one_source_across_topics_without_touching_reading_state(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        first = app.stage_pdf(self.pdf, topic_title="First")
        app.confirm(first["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        one = app.process(first["item_id"], request_id="first-request")
        state_path = self.workspace / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["sources"][one["source_id"]]["reading_started"] = True
        state_path.write_text(json.dumps(state), encoding="utf-8")

        renamed = self.root / "renamed.pdf"
        renamed.write_bytes(self.pdf.read_bytes())
        second = app.stage_pdf(renamed, topic_title="Second")
        app.confirm(second["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        two = app.process(second["item_id"], request_id="second-request")

        self.assertEqual((one["source_id"], "reused", 1), (two["source_id"], two["document_status"], parser.calls))
        topics = list((self.workspace / "topics").glob("*/topic.yaml"))
        self.assertEqual(2, len(topics))
        self.assertEqual(1, len(list((self.workspace / "sources").iterdir())))
        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertTrue(after["sources"][one["source_id"]]["reading_started"])

    def test_invalid_candidate_is_rejected_before_publication(self):
        app = IngestionApplication(self.workspace, parser=InvalidParser(), writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        result = app.process(item["item_id"], request_id="invalid-request")
        self.assertEqual(("failed", "candidate_rejected", "parser_bundle_invalid"), (
            result["status"], result["document_status"], result["error"]["error_id"]
        ))
        self.assertFalse((self.workspace / "sources").exists())

    def test_topic_failure_keeps_the_published_source_accessible(self):
        app = IngestionApplication(self.workspace, parser=ValidParser(), writer_id="host-a")
        item = app.stage_pdf(self.pdf, topic_id="missing-topic")
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        result = app.process(item["item_id"], request_id="attachment-request")

        self.assertEqual(("topic_attachment_pending", "published", "pending_recovery"), (
            result["status"], result["document_status"], result["topic_status"]
        ))
        bundle = self.workspace / "sources" / result["source_id"] / "parser-bundle"
        self.assertTrue((bundle / "source.pdf").is_file())
        self.assertTrue((bundle / "content.md").is_file())

        SourceLibrary(self.workspace).create_topic("Recovered", topic_id="missing-topic")
        recovered = app.continue_run(item["item_id"], request_id="attachment-retry")
        self.assertEqual(("completed", "reused", "attached"), (
            recovered["status"], recovered["document_status"], recovered["topic_status"]
        ))
        self.assertEqual(
            [result["source_id"]],
            json.loads((self.workspace / "topics" / "missing-topic" / "topic.yaml").read_text(encoding="utf-8"))["sources"],
        )

    def test_stale_expected_version_retains_candidate_and_second_writer_is_rejected(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        first_pdf = self.root / "first.pdf"
        first_pdf.write_bytes(b"%PDF-1.4\nfirst\n")
        second_pdf = self.root / "second.pdf"
        second_pdf.write_bytes(b"%PDF-1.4\nsecond\n")
        first = app.stage_pdf(first_pdf)
        second = app.stage_pdf(second_pdf)
        for item in (first, second):
            app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        app.process(first["item_id"], request_id="first")
        conflict = app.process(second["item_id"], request_id="second")
        self.assertEqual(("commit_conflict", "candidate_retained"), (
            conflict["status"], conflict["document_status"]
        ))
        self.assertTrue((self.workspace / "inbox" / second["item_id"] / "candidate").is_dir())

        third_pdf = self.root / "third.pdf"
        third_pdf.write_bytes(b"%PDF-1.4\nthird\n")
        other = IngestionApplication(self.workspace, parser=ValidParser(), writer_id="host-b")
        third = other.stage_pdf(third_pdf)
        other.confirm(third["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        with self.assertRaisesRegex(WorkspaceError, "writer"):
            other.process(third["item_id"], request_id="third")

    def test_host_is_a_thin_adapter_over_the_same_application(self):
        upload_root = self.workspace / "uploads" / "fixture"
        upload_root.mkdir(parents=True)
        uploaded = upload_root / "selected.pdf"
        uploaded.write_bytes(self.pdf.read_bytes())
        host = HostService(
            self.workspace,
            self.root / "host-data",
            ingestion_parser=ValidParser(),
        )
        try:
            host.store.put("upload:fixture", {"name": uploaded.name, "path": str(uploaded)})
            staged = host.inbox_stage("fixture", topic_title="Systems")
            host.inbox_confirm(staged["item_id"])
            result = host.inbox_process(staged["item_id"], request_id="host-request")
            self.assertEqual("completed", result["status"])
            self.assertEqual(result, host.inbox_item(staged["item_id"]))
        finally:
            host.store.close()

    def test_transient_failure_resumes_remote_task_twice_then_waits_for_manual_retry(self):
        parser = ResumableParser(failures=3)
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")

        waiting = app.process(item["item_id"], request_id="resumable")

        self.assertEqual(("retry_waiting", 1, 2), (waiting["status"], parser.starts, parser.resumes))
        parse_step = waiting["run"]["steps"]["parse"]
        self.assertEqual("remote-batch", parse_step["checkpoint"]["reference_id"])
        self.assertEqual(3, len(parse_step["attempts"]))
        reopened = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        completed = reopened.continue_run(item["item_id"], request_id="manual-resume")
        self.assertEqual(("completed", 1, 3), (completed["status"], parser.starts, parser.resumes))
        self.assertNotIn("error", completed)

    def test_unknown_remote_acceptance_requires_reconciliation_without_resubmission(self):
        parser = UnknownAcceptanceParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")

        result = app.process(item["item_id"], request_id="unknown")

        self.assertEqual("status_check_required", result["status"])
        self.assertEqual(1, parser.calls)
        self.assertNotIn("checkpoint", result["run"]["steps"]["parse"])

    def test_optional_runtime_inspects_candidate_but_cannot_replace_core_validation(self):
        runtime = InspectingRuntime()
        app = IngestionApplication(
            self.workspace, parser=ValidParser(), runtime=runtime, writer_id="host-a"
        )
        item = app.stage_pdf(self.pdf)
        with self.assertRaisesRegex(WorkspaceError, "services"):
            app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        app.confirm(
            item["item_id"],
            services=["mineru", "codex"],
            purpose="register source",
            scope="ingestion",
        )
        result = app.process(item["item_id"], request_id="runtime")
        self.assertEqual(("completed", 1, "completed"), (
            result["status"], runtime.calls, result["run"]["steps"]["runtime"]["status"]
        ))

        other_pdf = self.root / "other.pdf"
        other_pdf.write_bytes(b"%PDF-1.4\nother\n")
        invalid_runtime = InspectingRuntime(valid=False)
        other = IngestionApplication(
            self.workspace, parser=ValidParser(), runtime=invalid_runtime, writer_id="host-a"
        )
        staged = other.stage_pdf(other_pdf)
        other.confirm(
            staged["item_id"], services=["mineru", "codex"], purpose="register source", scope="ingestion"
        )
        rejected = other.process(staged["item_id"], request_id="runtime-invalid")
        self.assertEqual(("failed", "candidate_retained", "runtime_result_invalid"), (
            rejected["status"], rejected["document_status"], rejected["error"]["error_id"]
        ))

    def test_cancel_closes_attempt_before_remote_stop_and_rejects_late_candidate(self):
        parser = BlockingParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        result = {}

        def run_process():
            result.update(app.process(item["item_id"], request_id="blocking"))

        worker = threading.Thread(target=run_process)
        worker.start()
        self.assertTrue(parser.started.wait(2))
        cancelled = app.cancel(item["item_id"])
        self.assertEqual(("cancelled", 1), (cancelled["status"], parser.cancelled))
        parser.release.set()
        worker.join(5)

        self.assertEqual("cancelled", result["status"])
        self.assertEqual("candidate_retained", result["document_status"])
        self.assertFalse((self.workspace / "sources").exists())
        continued = app.continue_run(item["item_id"], request_id="after-cancel")
        self.assertEqual(("completed", 1), (continued["status"], parser.resumes))

    def test_cancel_interrupts_runtime_and_keeps_it_outside_core_authority(self):
        runtime = BlockingRuntime()
        app = IngestionApplication(
            self.workspace, parser=ValidParser(), runtime=runtime, writer_id="host-a"
        )
        item = app.stage_pdf(self.pdf)
        app.confirm(
            item["item_id"], services=["mineru", "codex"], purpose="register source", scope="ingestion"
        )
        result = {}

        worker = threading.Thread(
            target=lambda: result.update(app.process(item["item_id"], request_id="runtime-blocking"))
        )
        worker.start()
        self.assertTrue(runtime.started.wait(2))
        cancelled = app.cancel(item["item_id"])
        worker.join(5)

        self.assertEqual(("cancelled", "stop_requested", 1), (
            cancelled["status"], cancelled["runtime_status"], runtime.cancelled
        ))
        self.assertEqual(("cancelled", "candidate_retained"), (
            result["status"], result["document_status"]
        ))
        self.assertFalse((self.workspace / "sources").exists())


if __name__ == "__main__":
    unittest.main()
