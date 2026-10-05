from __future__ import annotations

import http.client
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from core import IngestionApplication, IngestionExternalError, SourceLibrary, WorkspaceError
from core.ingestion import persist_candidate_result
from host.server import Server
from workspace_fixture import HostService


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
        result = {"title": "Stored Paper", "short_name": "Stored"}
        persist_candidate_result(candidate, result)
        return result


class FigurelessParser(ValidParser):
    """A paper without figures: no `images/` directory and no image references."""

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        result = super().parse(source, candidate, checkpoint=checkpoint)
        (candidate / "images").rmdir()
        return result


FIGURE_PNG = b"\x89PNG\r\n\x1a\nfigure-bytes"


class FigureParser(ValidParser):
    """A paper carrying one real figure: the file exists and is referenced."""

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        result = super().parse(source, candidate, checkpoint=checkpoint)
        (candidate / "images" / "image-001.png").write_bytes(FIGURE_PNG)
        (candidate / "content.md").write_text(
            "# Stored Paper\n\nBody.\n\n![Figure 1](images/image-001.png)\n", encoding="utf-8"
        )
        return result


class DanglingImageParser(ValidParser):
    def __init__(self, reference: str = "images/image-001.png") -> None:
        super().__init__()
        self.reference = reference

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        result = super().parse(source, candidate, checkpoint=checkpoint)
        (candidate / "images").rmdir()
        (candidate / "content.md").write_text(
            f"# Stored Paper\n\nBody.\n\n![Figure 1]({self.reference})\n", encoding="utf-8"
        )
        return result


class InvalidParser(ValidParser):
    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        result = super().parse(source, candidate, checkpoint=checkpoint)
        (candidate / "validation.json").write_text('{"ok": false}\n', encoding="utf-8")
        return result


class MismatchedOriginalParser(ValidParser):
    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        result = super().parse(source, candidate, checkpoint=checkpoint)
        (candidate / "source.pdf").write_bytes(b"%PDF-1.4\nnot-the-selected-file\n")
        return result


class LongTitleParser(ValidParser):
    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        result = super().parse(source, candidate, checkpoint=checkpoint)
        title = "DeepStack: " + "Scalable design space exploration " * 8
        (candidate / "content.md").write_text(f"# {title}\n\nBody.\n", encoding="utf-8")
        result = {"title": title, "short_name": title}
        persist_candidate_result(candidate, result)
        return result


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


class CheckpointedNonResumableParser(ValidParser):
    """Saves a task reference, reports the outcome as unknown, cannot query it."""

    def __init__(self) -> None:
        super().__init__()
        self.submissions = 0

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        self.submissions += 1
        if self.submissions == 1:
            if checkpoint is not None:
                checkpoint({"reference_kind": "batch_id", "reference_id": "stuck-batch"})
            raise IngestionExternalError(
                "upload_acceptance_unknown", "submission outcome is unknown", acceptance_unknown=True
            )
        return super().parse(source, candidate, checkpoint=checkpoint)


class AcceptanceUnknownParser(ValidParser):
    """Reports the first submissions as unknown-outcome, then parses normally.

    `unknown` counts submissions whose outcome stayed unknown, `resumes`
    counts remote queries; inherited `calls` counts completed parses.
    """

    def __init__(self, unknown_failures: int = 1, *, checkpointed: bool = False) -> None:
        super().__init__()
        self.unknown_failures = unknown_failures
        self.checkpointed = checkpointed
        self.unknown = 0
        self.resumes = 0

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        if self.unknown < self.unknown_failures:
            self.unknown += 1
            if self.checkpointed and checkpoint is not None:
                checkpoint({"reference_kind": "batch_id", "reference_id": "unknown-batch"})
            raise IngestionExternalError(
                "upload_acceptance_unknown", "submission outcome is unknown", acceptance_unknown=True
            )
        return super().parse(source, candidate, checkpoint=checkpoint)

    def resume(self, source: Path, candidate: Path, *, checkpoint):
        self.resumes += 1
        return super().parse(source, candidate, checkpoint=checkpoint)


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


def forbid_codex_processes():
    """Any external Codex call during default ingestion is a failure."""
    return patch("subprocess.Popen", side_effect=AssertionError("default ingestion must not spawn Codex"))


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

    def test_publish_file_lock_is_retryable_without_reparsing(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id='host-a')
        item = app.stage_pdf(self.pdf, topic_title='Systems')
        app.confirm(item['item_id'], services=['mineru'], purpose='register source', scope='ingestion')
        original_replace = Path.replace
        def replace(path, target):
            if path.name.endswith('.staging'):
                raise PermissionError('simulated Windows publication lock')
            return original_replace(path, target)
        with patch.object(Path, 'replace', replace):
            failed = app.process(item['item_id'], request_id='locked-publish')
        self.assertEqual('retry_waiting', failed['status'])
        self.assertEqual('source_publish_failed', failed['error']['error_id'])
        self.assertEqual('completed', failed['run']['steps']['parse']['status'])
        self.assertTrue((self.workspace / 'inbox' / item['item_id'] / 'candidate/source.pdf').is_file())
        completed = app.continue_run(item['item_id'], request_id='retry-publish')
        self.assertEqual('completed', completed['status'])
        self.assertEqual(1, parser.calls)

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

    def test_candidate_original_must_match_the_confirmed_inbox_file(self):
        app = IngestionApplication(self.workspace, parser=MismatchedOriginalParser(), writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        result = app.process(item["item_id"], request_id="mismatched-original")
        self.assertEqual(("failed", "candidate_rejected", "candidate_original_mismatch"), (
            result["status"], result["document_status"], result["error"]["error_id"]
        ))
        self.assertFalse((self.workspace / "sources").exists())

    def test_reopen_recovers_a_valid_candidate_written_before_attempt_state(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        confirmed = app.confirm(
            item["item_id"], services=["mineru"], purpose="register source", scope="ingestion"
        )
        confirmation = confirmed["confirmation"]
        root = self.workspace / "inbox" / item["item_id"]
        parser.parse(root / "source.pdf", root / "candidate")
        persisted = json.loads((root / "item.json").read_text(encoding="utf-8"))
        persisted["status"] = "processing"
        persisted["request_id"] = "crashed-request"
        persisted["run"] = {
            "run_id": "crashed-run",
            "steps": {
                "parse": {
                    "status": "running",
                    "attempts": [{
                        "attempt_id": "lost-result",
                        "status": "running",
                        "commit_allowed": True,
                        "service": "mineru",
                        "configuration": confirmation["service_config"]["mineru"],
                        "method_version": confirmation["method_version"],
                        "input_version": confirmation["input_version"],
                    }],
                },
                "publish": {"status": "pending", "attempts": []},
                "attach": {"status": "pending", "attempts": []},
            },
        }
        (root / "item.json").write_text(json.dumps(persisted), encoding="utf-8")

        reopened = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        completed = reopened.continue_run(item["item_id"], request_id="recovered-request")

        self.assertEqual(("completed", 1), (completed["status"], parser.calls))
        attempts = completed["run"]["steps"]["parse"]["attempts"]
        self.assertEqual(("interrupted", False), (attempts[0]["status"], attempts[0]["commit_allowed"]))
        self.assertEqual(("completed", True), (attempts[1]["status"], attempts[1]["commit_allowed"]))
        source = json.loads(
            (self.workspace / "sources" / completed["source_id"] / "source.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual("Stored", source["short_name"])

    def test_confirmation_is_bound_to_the_parser_configuration_only(self):
        parser = ValidParser()
        parser.model = "parser-v1"
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        self.assertEqual(["mineru"], item["services"])
        confirmed = app.confirm(
            item["item_id"], services=["mineru"], purpose="register source", scope="ingestion"
        )
        self.assertEqual({"mineru"}, set(confirmed["confirmation"]["service_config"]))
        self.assertEqual("parser-v1", confirmed["confirmation"]["service_config"]["mineru"]["model"])
        parser.model = "changed-after-confirmation"

        with self.assertRaisesRegex(WorkspaceError, "confirmation"):
            app.process(item["item_id"], request_id="configuration-changed")
        self.assertEqual(0, parser.calls)

    def test_confirmation_declares_only_the_service_default_ingestion_uses(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        self.assertFalse(hasattr(app, "runtime"))
        with self.assertRaises(TypeError):
            IngestionApplication(self.workspace, parser=parser, writer_id="host-a", runtime=object())
        item = app.stage_pdf(self.pdf)
        self.assertEqual(["mineru"], item["services"])
        with self.assertRaisesRegex(WorkspaceError, "services"):
            app.confirm(item["item_id"], services=["mineru", "codex"], purpose="register source", scope="ingestion")

        with forbid_codex_processes():
            app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
            completed = app.process(item["item_id"], request_id="no-ai-review")
        self.assertEqual("completed", completed["status"])
        self.assertEqual(1, parser.calls)
        self.assertEqual({"parse", "publish", "attach"}, set(completed["run"]["steps"]))
        self.assertNotIn("runtime_result", completed)

    def test_a_paper_without_figures_publishes_without_any_ai_review(self):
        parser = FigurelessParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")

        with forbid_codex_processes():
            completed = app.process(item["item_id"], request_id="figureless")

        self.assertEqual(("completed", "published", "attached"), (
            completed["status"], completed["document_status"], completed["topic_status"]
        ))
        self.assertEqual(1, parser.calls)
        bundle = self.workspace / "sources" / completed["source_id"] / "parser-bundle"
        self.assertEqual("# Stored Paper\n\nBody.\n", (bundle / "content.md").read_text(encoding="utf-8"))
        self.assertFalse((bundle / "images").exists())
        topic = json.loads((self.workspace / "topics" / "systems" / "topic.yaml").read_text(encoding="utf-8"))
        self.assertEqual([completed["source_id"]], topic["sources"])

    def test_a_paper_with_a_referenced_figure_publishes_with_zero_runtime_calls(self):
        parser = FigureParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")

        with forbid_codex_processes():
            completed = app.process(item["item_id"], request_id="with-figure")

        self.assertEqual(("completed", "published", "attached"), (
            completed["status"], completed["document_status"], completed["topic_status"]
        ))
        self.assertEqual(1, parser.calls)
        self.assertEqual({"parse", "publish", "attach"}, set(completed["run"]["steps"]))
        bundle = self.workspace / "sources" / completed["source_id"] / "parser-bundle"
        self.assertEqual(FIGURE_PNG, (bundle / "images" / "image-001.png").read_bytes())
        self.assertIn(
            "images/image-001.png", (bundle / "content.md").read_text(encoding="utf-8")
        )
        state = json.loads((self.workspace / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {"current_plan_id": None, "current_chunk_id": None}, state["sources"][completed["source_id"]]
        )
        self.assertFalse((self.workspace / "sources" / completed["source_id"] / "reading").exists())

    def test_referenced_images_must_still_resolve_when_figures_are_optional(self):
        for reference in ("images/image-001.png", "../outside.png"):
            with self.subTest(reference=reference):
                workspace = self.root / f"workspace-{abs(hash(reference))}"
                workspace.mkdir()
                app = IngestionApplication(
                    workspace, parser=DanglingImageParser(reference), writer_id="host-a"
                )
                item = app.stage_pdf(self.pdf)
                app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
                rejected = app.process(item["item_id"], request_id="dangling-image")
                self.assertEqual(("failed", "candidate_rejected", "parser_bundle_invalid"), (
                    rejected["status"], rejected["document_status"], rejected["error"]["error_id"]
                ))
                self.assertFalse((workspace / "sources").exists())

    def test_repeated_add_of_an_unfinished_original_returns_the_same_task(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        first = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(first["item_id"], services=["mineru"], purpose="register source", scope="ingestion")

        renamed = self.root / "renamed.pdf"
        renamed.write_bytes(self.pdf.read_bytes())
        repeated = app.stage_pdf(renamed, topic_title="Other Topic")

        self.assertEqual(first["item_id"], repeated["item_id"])
        self.assertTrue(repeated["duplicate"])
        self.assertEqual("confirmed", repeated["status"])
        self.assertEqual("Systems", repeated["topic_title"])
        self.assertTrue(repeated["confirmation"])
        self.assertEqual(1, len(list((self.workspace / "inbox").glob("*/item.json"))))
        self.assertFalse((self.workspace / "topics" / "other-topic").exists())
        self.assertEqual(0, parser.calls)
        self.assertNotIn("duplicate", app.get(first["item_id"]))

    def test_repeated_add_after_restart_finds_the_persisted_task(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        staged = app.stage_pdf(self.pdf, topic_title="Systems")
        reopened = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        repeated = reopened.stage_pdf(self.pdf)
        self.assertEqual(staged["item_id"], repeated["item_id"])
        self.assertTrue(repeated["duplicate"])
        self.assertEqual("Systems", repeated["topic_title"])
        self.assertEqual("awaiting_confirmation", repeated["status"])

    def test_every_unfinished_status_blocks_a_second_parsing_task(self):
        parser = BlockingParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        started = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(started["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        worker = threading.Thread(target=lambda: app.process(started["item_id"], request_id="in-flight"))
        worker.start()
        self.assertTrue(parser.started.wait(2))

        statuses = ["awaiting_confirmation", "confirmed", "processing", "failed", "status_check_required",
                    "retry_waiting", "commit_conflict", "topic_attachment_pending", "cancelled", "interrupted"]
        for status in statuses:
            with self.subTest(status=status):
                item_id = app.stage_pdf(self.pdf, topic_title="Other")["item_id"]
                self.assertEqual(started["item_id"], item_id)
                persisted = json.loads(
                    (self.workspace / "inbox" / item_id / "item.json").read_text(encoding="utf-8")
                )
                persisted["status"] = status
                (self.workspace / "inbox" / item_id / "item.json").write_text(
                    json.dumps(persisted), encoding="utf-8"
                )
                repeated = app.stage_pdf(self.pdf)
                self.assertEqual(started["item_id"], repeated["item_id"])
                self.assertTrue(repeated["duplicate"])
                self.assertEqual(status, repeated["status"])
                self.assertEqual(1, len(list((self.workspace / "inbox").glob("*/item.json"))))

        app.cancel(started["item_id"])
        parser.release.set()
        worker.join(5)
        self.assertFalse((self.workspace / "sources").exists())

    def test_repeated_add_of_a_completed_original_still_reuses_the_source(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        first = app.stage_pdf(self.pdf, topic_title="First")
        app.confirm(first["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        done = app.process(first["item_id"], request_id="first")
        state_path = self.workspace / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["sources"][done["source_id"]]["reading_started"] = True
        state_path.write_text(json.dumps(state), encoding="utf-8")

        second = app.stage_pdf(self.pdf, topic_title="Second")

        self.assertNotEqual(first["item_id"], second["item_id"])
        self.assertFalse(second.get("duplicate", False))
        self.assertEqual("awaiting_confirmation", second["status"])
        self.assertEqual("Second", second["topic_title"])
        app.confirm(second["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        reused = app.process(second["item_id"], request_id="second")
        self.assertEqual((done["source_id"], "reused"), (reused["source_id"], reused["document_status"]))
        self.assertEqual(1, parser.calls)
        after = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertTrue(after["sources"][done["source_id"]]["reading_started"])
        self.assertEqual(1, len(list((self.workspace / "sources").iterdir())))

    def test_repeated_add_of_a_pending_attachment_task_returns_the_recovery_task(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        first = app.stage_pdf(self.pdf, topic_id="missing-topic")
        app.confirm(first["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        pending = app.process(first["item_id"], request_id="attachment-failure")
        self.assertEqual("topic_attachment_pending", pending["status"])

        renamed = self.root / "renamed.pdf"
        renamed.write_bytes(self.pdf.read_bytes())
        repeated = app.stage_pdf(renamed, topic_title="Other Topic")

        self.assertEqual(first["item_id"], repeated["item_id"])
        self.assertTrue(repeated["duplicate"])
        self.assertEqual("missing-topic", repeated["topic_id"])
        self.assertIsNone(repeated["topic_title"])
        self.assertEqual("pending_recovery", repeated["topic_status"])
        self.assertTrue(repeated["confirmation"])
        self.assertEqual(1, len(list((self.workspace / "inbox").glob("*/item.json"))))
        self.assertFalse((self.workspace / "topics" / "other-topic").exists())
        self.assertEqual(1, parser.calls)

        SourceLibrary(self.workspace).create_topic("Recovered", topic_id="missing-topic")
        recovered = app.continue_run(first["item_id"], request_id="attachment-retry")
        self.assertEqual(("completed", "reused", "attached"), (
            recovered["status"], recovered["document_status"], recovered["topic_status"]
        ))

    def test_concurrent_repeated_staging_produces_exactly_one_task(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        results = []
        errors = []

        def stage(label):
            source = self.root / f"copy-{label}.pdf"
            source.write_bytes(self.pdf.read_bytes())
            try:
                results.append(app.stage_pdf(source, topic_title=f"Topic {label}"))
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        workers = [threading.Thread(target=stage, args=(label,)) for label in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)

        self.assertEqual([], errors)
        self.assertEqual(4, len(results))
        self.assertEqual(1, len({result["item_id"] for result in results}))
        duplicates = [result for result in results if result.get("duplicate")]
        self.assertEqual(3, len(duplicates))
        original = next(result for result in results if not result.get("duplicate"))
        self.assertEqual(
            {original["item_id"]},
            {json.loads(path.read_text(encoding="utf-8"))["item_id"]
             for path in (self.workspace / "inbox").glob("*/item.json")},
        )
        # Staging never creates Topic relationships; only the one unfinished task exists.
        self.assertFalse((self.workspace / "topics").exists())

    def test_editing_a_staged_source_cannot_bypass_identity_reuse(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        other_pdf = self.root / "other.pdf"
        other_pdf.write_bytes(b"%PDF-1.4\nother\n")
        first = app.stage_pdf(self.pdf, topic_title="Systems")
        second = app.stage_pdf(other_pdf, topic_title="Other")

        with self.assertRaisesRegex(WorkspaceError, "unfinished Inbox task"):
            app.update_staged(second["item_id"], source=self.pdf)
        self.assertEqual(
            other_pdf.read_bytes(),
            (self.workspace / "inbox" / second["item_id"] / "source.pdf").read_bytes(),
        )
        self.assertEqual("other.pdf", app.get(second["item_id"])["file_name"])
        self.assertEqual(2, len(list((self.workspace / "inbox").glob("*/item.json"))))

        # Re-selecting the item's own current original keeps the edit legitimate.
        renamed_own = self.root / "renamed-other.pdf"
        renamed_own.write_bytes(other_pdf.read_bytes())
        edited = app.update_staged(second["item_id"], source=renamed_own)
        self.assertEqual("awaiting_confirmation", edited["status"])
        self.assertIsNone(edited["confirmation"])
        self.assertEqual("renamed-other.pdf", edited["file_name"])

    def test_new_original_next_to_an_unfinished_task_still_stages_normally(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        staged = app.stage_pdf(self.pdf, topic_title="Systems")
        other_pdf = self.root / "other.pdf"
        other_pdf.write_bytes(b"%PDF-1.4\nother\n")
        staged_other = app.stage_pdf(other_pdf)
        self.assertNotEqual(staged["item_id"], staged_other["item_id"])
        self.assertFalse(staged_other.get("duplicate", False))
        self.assertEqual(2, len(list((self.workspace / "inbox").glob("*/item.json"))))

    def test_processing_rejects_a_disk_input_that_no_longer_matches_confirmation(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        (self.workspace / "inbox" / item["item_id"] / "source.pdf").write_bytes(
            b"%PDF-1.4\nchanged-after-confirmation\n"
        )

        with self.assertRaisesRegex(WorkspaceError, "confirmation"):
            app.process(item["item_id"], request_id="changed-on-disk")
        self.assertEqual(0, parser.calls)

    def test_core_rejects_an_inbox_file_replaced_while_parser_is_running(self):
        parser = BlockingParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        result = {}
        worker = threading.Thread(
            target=lambda: result.update(app.process(item["item_id"], request_id="replace-during-parse"))
        )
        worker.start()
        self.assertTrue(parser.started.wait(2))
        (self.workspace / "inbox" / item["item_id"] / "source.pdf").write_bytes(
            b"%PDF-1.4\nreplaced-during-parse\n"
        )
        parser.release.set()
        worker.join(5)

        self.assertEqual(
            ("failed", "candidate_original_mismatch"),
            (result["status"], result["error"]["error_id"]),
        )
        self.assertFalse((self.workspace / "sources").exists())

    def test_configuration_drift_can_be_explicitly_reconfirmed_without_old_checkpoint(self):
        parser = ResumableParser(failures=3)
        parser.model = "parser-v1"
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        waiting = app.process(item["item_id"], request_id="old-configuration")
        self.assertEqual("retry_waiting", waiting["status"])
        parser.model = "parser-v2"
        with self.assertRaisesRegex(WorkspaceError, "confirmation"):
            app.continue_run(item["item_id"], request_id="drifted-configuration")

        reconfirmed = app.confirm(
            item["item_id"], services=["mineru"], purpose="register source", scope="ingestion"
        )
        self.assertIsNone(reconfirmed["run"])
        completed = app.process(item["item_id"], request_id="new-configuration")

        self.assertEqual(("completed", 2, 2), (completed["status"], parser.starts, parser.resumes))
        attempt = completed["run"]["steps"]["parse"]["attempts"][0]
        self.assertEqual("parser-v2", attempt["configuration"]["model"])

    def test_reopen_interrupts_a_running_step_before_continuation(self):
        app = IngestionApplication(self.workspace, parser=ValidParser(), writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        root = self.workspace / "inbox" / item["item_id"]
        persisted = json.loads((root / "item.json").read_text(encoding="utf-8"))
        persisted["status"] = "processing"
        persisted["run"] = {
            "run_id": "publish-crash",
            "steps": {
                "parse": {"status": "completed", "attempts": []},
                "publish": {
                    "status": "running",
                    "attempts": [{"attempt_id": "publish-lost", "status": "running", "commit_allowed": True}],
                },
                "attach": {"status": "pending", "attempts": []},
            },
        }
        (root / "item.json").write_text(json.dumps(persisted), encoding="utf-8")

        reopened = IngestionApplication(self.workspace, parser=ValidParser(), writer_id="host-a")
        recovered = reopened.get(item["item_id"])

        self.assertEqual("interrupted", recovered["run"]["steps"]["publish"]["status"])
        self.assertEqual(
            ("interrupted", False),
            (
                recovered["run"]["steps"]["publish"]["attempts"][0]["status"],
                recovered["run"]["steps"]["publish"]["attempts"][0]["commit_allowed"],
            ),
        )

    def test_cancelled_item_cannot_replace_its_confirmed_input(self):
        parser = BlockingParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        result = {}
        worker = threading.Thread(
            target=lambda: result.update(app.process(item["item_id"], request_id="cancel-before-edit"))
        )
        worker.start()
        self.assertTrue(parser.started.wait(2))
        app.cancel(item["item_id"])
        replacement = self.root / "replacement.pdf"
        replacement.write_bytes(b"%PDF-1.4\nreplacement\n")

        with self.assertRaisesRegex(WorkspaceError, "edited"):
            app.update_staged(item["item_id"], source=replacement)
        parser.release.set()
        worker.join(5)
        persisted = app.get(item["item_id"])
        self.assertEqual(("cancelled", self.pdf.name), (persisted["status"], persisted["file_name"]))
        self.assertEqual(self.pdf.read_bytes(), (self.workspace / "inbox" / item["item_id"] / "source.pdf").read_bytes())

    def test_cancel_between_processing_and_attempt_creation_prevents_external_call(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        lookup_started = threading.Event()
        release_lookup = threading.Event()
        result = {}

        def delayed_lookup(_library, _identity):
            lookup_started.set()
            release_lookup.wait(5)
            return None

        with patch.object(SourceLibrary, "find", autospec=True, side_effect=delayed_lookup):
            worker = threading.Thread(
                target=lambda: result.update(app.process(item["item_id"], request_id="cancel-gap"))
            )
            worker.start()
            self.assertTrue(lookup_started.wait(2))
            app.cancel(item["item_id"])
            release_lookup.set()
            worker.join(5)

        self.assertEqual(("cancelled", 0), (result["status"], parser.calls))
        self.assertFalse((self.workspace / "sources").exists())

    def test_cancel_during_duplicate_lookup_prevents_topic_attachment(self):
        parser = ValidParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        first = app.stage_pdf(self.pdf, topic_title="First")
        app.confirm(first["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        app.process(first["item_id"], request_id="first-copy")
        duplicate = app.stage_pdf(self.pdf, topic_title="Second")
        app.confirm(
            duplicate["item_id"], services=["mineru"], purpose="register source", scope="ingestion"
        )
        lookup_started = threading.Event()
        release_lookup = threading.Event()
        original_find = SourceLibrary.find
        result = {}

        def delayed_lookup(library, identity):
            lookup_started.set()
            release_lookup.wait(5)
            return original_find(library, identity)

        with patch.object(SourceLibrary, "find", autospec=True, side_effect=delayed_lookup):
            worker = threading.Thread(
                target=lambda: result.update(
                    app.process(duplicate["item_id"], request_id="duplicate-cancel")
                )
            )
            worker.start()
            self.assertTrue(lookup_started.wait(2))
            app.cancel(duplicate["item_id"])
            release_lookup.set()
            worker.join(5)

        self.assertEqual("cancelled", result["status"])
        self.assertFalse((self.workspace / "topics" / "second" / "topic.yaml").exists())

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
        recovered = app.continue_run(second["item_id"], request_id="second-retry")
        self.assertEqual(("completed", 2), (recovered["status"], parser.calls))

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
            host.close()

    def test_host_returns_the_existing_task_for_a_repeated_add(self):
        upload_root = self.workspace / "uploads" / "fixture"
        upload_root.mkdir(parents=True)
        uploaded = upload_root / "selected.pdf"
        uploaded.write_bytes(self.pdf.read_bytes())
        renamed = upload_root / "renamed.pdf"
        renamed.write_bytes(self.pdf.read_bytes())
        host = HostService(
            self.workspace,
            self.root / "host-duplicate",
            ingestion_parser=ValidParser(),
        )
        try:
            host.store.put("upload:fixture", {"name": uploaded.name, "path": str(uploaded)})
            host.store.put("upload:renamed", {"name": renamed.name, "path": str(renamed)})
            first = host.inbox_stage("fixture", topic_title="Systems")
            repeated = host.inbox_stage("renamed", topic_title="Another")

            self.assertEqual(first["item_id"], repeated["item_id"])
            self.assertTrue(repeated["duplicate"])
            self.assertEqual("Systems", repeated["topic_title"])
            self.assertEqual(1, len(host.inbox_items()))
            self.assertEqual(repeated["item_id"], host.inbox_item(repeated["item_id"])["item_id"])
            self.assertEqual(1, len(host.ingestion.list_inbox()))
        finally:
            host.close()

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

    def test_resubmit_requires_an_explicit_current_risk_choice(self):
        parser = AcceptanceUnknownParser(unknown_failures=1)
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        unknown = app.process(item["item_id"], request_id="initial")

        self.assertEqual("status_check_required", unknown["status"])
        self.assertFalse(unknown["remote_reference"])
        choice = unknown["resubmit_risk"]["choice_id"]

        # Ordinary paths cannot silently produce a second submission.
        with self.assertRaisesRegex(WorkspaceError, "resubmit explicitly"):
            app.process(item["item_id"], request_id="silent-retry")
        with self.assertRaisesRegex(WorkspaceError, "task reference"):
            app.continue_run(item["item_id"], request_id="silent-continue")
        with self.assertRaisesRegex(WorkspaceError, "risk choice"):
            app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id="stale-choice")
        self.assertEqual("status_check_required", app.validate_resubmit(
            item["item_id"], request_id="check", risk_choice_id=choice
        )["status"])
        self.assertEqual((1, 0), (parser.unknown, parser.calls))

        resubmitted = app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id=choice)

        self.assertEqual(("completed", "published", "attached"), (
            resubmitted["status"], resubmitted["document_status"], resubmitted["topic_status"]
        ))
        self.assertEqual((1, 1), (parser.unknown, parser.calls))
        attempts = resubmitted["run"]["steps"]["parse"]["attempts"]
        self.assertEqual(("failed", False), (attempts[0]["status"], attempts[0]["commit_allowed"]))
        self.assertEqual(("completed", True, "resubmit-1"), (
            attempts[1]["status"], attempts[1]["commit_allowed"], attempts[1]["resubmit_request_id"]
        ))
        self.assertNotIn("resubmit_risk", resubmitted)

    def test_resubmit_replays_are_idempotent_across_repeat_unknown_and_restart(self):
        parser = AcceptanceUnknownParser(unknown_failures=2)
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        app.process(item["item_id"], request_id="initial")
        first_choice = app.get(item["item_id"])["resubmit_risk"]["choice_id"]

        again_unknown = app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id=first_choice)
        self.assertEqual("status_check_required", again_unknown["status"])
        second_choice = again_unknown["resubmit_risk"]["choice_id"]
        self.assertNotEqual(first_choice, second_choice)

        # A repeated click of the same request replays without another submission.
        replayed = app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id=second_choice)
        self.assertEqual("status_check_required", replayed["status"])
        self.assertEqual(2, parser.unknown)

        reopened = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        completed = reopened.resubmit(item["item_id"], request_id="resubmit-2", risk_choice_id=second_choice)
        self.assertEqual("completed", completed["status"])

        # Replaying either request after completion returns the existing result.
        self.assertEqual("completed", reopened.resubmit(
            item["item_id"], request_id="resubmit-2", risk_choice_id=second_choice
        )["status"])
        self.assertEqual("completed", reopened.resubmit(
            item["item_id"], request_id="resubmit-1", risk_choice_id=first_choice
        )["status"])
        self.assertEqual((2, 1), (parser.unknown, parser.calls))
        self.assertEqual(1, len(list((self.workspace / "sources").iterdir())))

    def test_resubmit_with_a_reference_archives_it_and_rejects_the_late_result(self):
        parser = AcceptanceUnknownParser(unknown_failures=1, checkpointed=True)
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        unknown = app.process(item["item_id"], request_id="initial")
        self.assertTrue(unknown["remote_reference"])
        old_attempt_id = unknown["run"]["steps"]["parse"]["attempts"][0]["attempt_id"]
        choice = unknown["resubmit_risk"]["choice_id"]

        resubmitted = app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id=choice)

        self.assertEqual("completed", resubmitted["status"])
        self.assertEqual((1, 1, 0), (parser.unknown, parser.calls, parser.resumes))
        attempts = resubmitted["run"]["steps"]["parse"]["attempts"]
        self.assertEqual("unknown-batch", attempts[0]["checkpoint"]["reference_id"])
        self.assertFalse(attempts[0]["commit_allowed"])
        self.assertNotIn("checkpoint", resubmitted["run"]["steps"]["parse"])

        # A late result from the superseded attempt cannot publish through Core.
        bundle = self.workspace / "sources" / resubmitted["source_id"] / "parser-bundle"
        with self.assertRaisesRegex(WorkspaceError, "not allowed to commit"):
            app.core.publish(
                bundle,
                expected_version=app.core.version,
                request_id="late-result",
                writer_id="host-a",
                title="Stored Paper",
                short_name="Stored",
                identity="paper-original:" + item["fingerprint"],
                item_path=self.workspace / "inbox" / item["item_id"] / "item.json",
                attempt_id=old_attempt_id,
            )
        self.assertEqual(1, len(list((self.workspace / "sources").iterdir())))

    def test_a_known_reference_is_queried_and_resumed_before_resubmission(self):
        parser = AcceptanceUnknownParser(unknown_failures=1, checkpointed=True)
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        unknown = app.process(item["item_id"], request_id="initial")
        self.assertEqual("status_check_required", unknown["status"])

        completed = app.continue_run(item["item_id"], request_id="query-original")

        self.assertEqual("completed", completed["status"])
        self.assertEqual((1, 1), (parser.unknown, parser.resumes))
        self.assertEqual(1, parser.calls)
        attempts = completed["run"]["steps"]["parse"]["attempts"]
        self.assertEqual(("failed", False), (attempts[0]["status"], attempts[0]["commit_allowed"]))
        self.assertEqual(("completed", True), (attempts[1]["status"], attempts[1]["commit_allowed"]))

    def test_a_changed_input_or_service_invalidates_the_previous_risk_choice(self):
        parser = AcceptanceUnknownParser(unknown_failures=1)
        parser.model = "parser-v1"
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        unknown = app.process(item["item_id"], request_id="initial")
        choice = unknown["resubmit_risk"]["choice_id"]

        parser.model = "parser-v2"
        with self.assertRaisesRegex(WorkspaceError, "confirmation"):
            app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id=choice)
        self.assertEqual(1, parser.unknown)

        reconfirmed = app.confirm(
            item["item_id"], services=["mineru"], purpose="register source", scope="ingestion"
        )
        self.assertNotIn("resubmit_risk", reconfirmed)
        with self.assertRaisesRegex(WorkspaceError, "resubmitted"):
            app.resubmit(item["item_id"], request_id="resubmit-2", risk_choice_id=choice)
        self.assertEqual((1, 0), (parser.unknown, parser.calls))

        completed = app.process(item["item_id"], request_id="fresh-after-reconfirm")
        self.assertEqual("completed", completed["status"])
        self.assertEqual((1, 1), (parser.unknown, parser.calls))

    def test_concurrent_resubmit_of_the_same_request_submits_once(self):
        parser = AcceptanceUnknownParser(unknown_failures=1)
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        app.process(item["item_id"], request_id="initial")
        choice = app.get(item["item_id"])["resubmit_risk"]["choice_id"]
        results, errors = [], []

        def resubmit():
            try:
                results.append(
                    app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id=choice)
                )
            except Exception as exc:  # the losing caller is rejected, never duplicated
                errors.append(exc)

        workers = [threading.Thread(target=resubmit) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)

        self.assertEqual(2, len(results) + len(errors))
        self.assertEqual(1, len([result for result in results if result.get("status") == "completed"]))
        self.assertEqual((1, 1), (parser.unknown, parser.calls))
        attempts = app.get(item["item_id"])["run"]["steps"]["parse"]["attempts"]
        self.assertEqual(1, len([entry for entry in attempts if entry.get("resubmit_request_id")]))
        self.assertEqual(1, len(list((self.workspace / "sources").iterdir())))

    def test_concurrent_resubmit_with_different_requests_submits_once(self):
        parser = AcceptanceUnknownParser(unknown_failures=1)
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        app.process(item["item_id"], request_id="initial")
        choice = app.get(item["item_id"])["resubmit_risk"]["choice_id"]
        results, errors = [], []

        def resubmit(request_id):
            try:
                results.append(
                    app.resubmit(item["item_id"], request_id=request_id, risk_choice_id=choice)
                )
            except Exception as exc:  # the losing caller is rejected, never duplicated
                errors.append(exc)

        workers = [
            threading.Thread(target=resubmit, args=(request_id,))
            for request_id in ("resubmit-1", "resubmit-2")
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(5)

        self.assertEqual(2, len(results) + len(errors))
        self.assertEqual(1, len([result for result in results if result.get("status") == "completed"]))
        self.assertEqual((1, 1), (parser.unknown, parser.calls))
        attempts = app.get(item["item_id"])["run"]["steps"]["parse"]["attempts"]
        self.assertEqual(1, len([entry for entry in attempts if entry.get("resubmit_request_id")]))
        self.assertEqual(1, len(list((self.workspace / "sources").iterdir())))

    def test_a_cancelled_acceptance_unknown_task_recovers_through_explicit_resubmit(self):
        parser = AcceptanceUnknownParser(unknown_failures=1)
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        unknown = app.process(item["item_id"], request_id="initial")
        choice = unknown["resubmit_risk"]["choice_id"]

        app.cancel(item["item_id"])
        self.assertEqual("cancelled", app.get(item["item_id"])["status"])

        # An ordinary continue would silently resubmit; it is refused instead.
        with self.assertRaisesRegex(WorkspaceError, "resubmit explicitly"):
            app.continue_run(item["item_id"], request_id="after-cancel")
        self.assertEqual("cancelled", app.get(item["item_id"])["status"])

        recovered = app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id=choice)
        self.assertEqual(("completed", "published"), (recovered["status"], recovered["document_status"]))
        self.assertEqual((1, 1), (parser.unknown, parser.calls))
        self.assertNotIn("resubmit_pending", recovered)

    def test_remote_reference_requires_a_resume_capable_parser(self):
        parser = CheckpointedNonResumableParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        unknown = app.process(item["item_id"], request_id="initial")

        self.assertEqual("status_check_required", unknown["status"])
        # A checkpoint exists but this Parser cannot query it back.
        self.assertFalse(unknown["remote_reference"])
        with self.assertRaisesRegex(WorkspaceError, "resubmit explicitly"):
            app.continue_run(item["item_id"], request_id="doomed-query")

        choice = unknown["resubmit_risk"]["choice_id"]
        resubmitted = app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id=choice)
        self.assertEqual("completed", resubmitted["status"])
        attempts = resubmitted["run"]["steps"]["parse"]["attempts"]
        self.assertEqual("stuck-batch", attempts[0]["checkpoint"]["reference_id"])
        self.assertFalse(attempts[0]["commit_allowed"])
        self.assertNotIn("checkpoint", resubmitted["run"]["steps"]["parse"])

    def test_resubmit_prefers_an_already_published_source(self):
        parser = AcceptanceUnknownParser(unknown_failures=1)
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf, topic_title="Systems")
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        unknown = app.process(item["item_id"], request_id="initial")
        self.assertEqual("status_check_required", unknown["status"])
        choice = unknown["resubmit_risk"]["choice_id"]

        # The same original gets published while this task is stuck: a valid
        # bundle registered under the identical original identity.
        root = self.workspace / "inbox" / item["item_id"]
        ValidParser().parse(root / "source.pdf", root / "candidate")
        registered = SourceLibrary(self.workspace).register(
            root / "candidate",
            source_kind="paper_pdf",
            title="Stored Paper",
            short_name="Stored",
            identity="paper-original:" + item["fingerprint"],
        )

        resubmitted = app.resubmit(item["item_id"], request_id="resubmit-1", risk_choice_id=choice)

        self.assertEqual(("completed", "reused"), (resubmitted["status"], resubmitted["document_status"]))
        self.assertEqual(registered["source_id"], resubmitted["source_id"])
        # No new remote submission: the existing Source covers the original.
        self.assertEqual((1, 0), (parser.unknown, parser.calls))
        self.assertEqual(1, len(list((self.workspace / "sources").iterdir())))

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

    def test_parser_cancellation_cannot_be_overwritten_by_a_late_candidate(self):
        parser = BlockingParser()
        app = IngestionApplication(self.workspace, parser=parser, writer_id="host-a")
        item = app.stage_pdf(self.pdf)
        app.confirm(item["item_id"], services=["mineru"], purpose="register source", scope="ingestion")
        result = {}
        worker = threading.Thread(
            target=lambda: result.update(app.process(item["item_id"], request_id="parser-cancel"))
        )
        worker.start()
        self.assertTrue(parser.started.wait(2))
        app.cancel(item["item_id"])
        parser.release.set()
        worker.join(5)

        self.assertEqual(("cancelled", "candidate_retained"), (result["status"], result["document_status"]))
        self.assertFalse((self.workspace / "sources").exists())

    def test_codex_configuration_never_gates_or_invalidates_default_ingestion(self):
        """T26: a configured or unavailable Codex never joins default ingestion.

        Only the actually used Parser is declared; changing the Codex binary or
        model alone keeps a valid confirmation and produces zero Runtime calls.
        """
        configured = self.root / "codex-fixture"
        configured.write_bytes(b"fixture")
        for label, binary in (("configured", configured), ("unavailable", self.root / "absent-codex")):
            with self.subTest(codex=label):
                workspace = self.root / f"workspace-codex-{label}"
                workspace.mkdir()
                host = HostService(
                    workspace,
                    self.root / f"host-codex-{label}",
                    backend="codex",
                    codex_bin=binary,
                    model="codex-model-a",
                    ingestion_parser=ValidParser(),
                )
                try:
                    upload_root = workspace / "uploads" / "fixture"
                    upload_root.mkdir(parents=True)
                    uploaded = upload_root / "selected.pdf"
                    uploaded.write_bytes(b"%PDF-1.4\nselected\n")
                    host.store.put("upload:fixture", {"name": uploaded.name, "path": str(uploaded)})
                    staged = host.inbox_stage("fixture", topic_title="Systems")
                    confirmed = host.inbox_confirm(staged["item_id"])
                    self.assertEqual(["mineru"], confirmed["confirmation"]["services"])
                    self.assertEqual(["mineru"], sorted(confirmed["confirmation"]["service_config"]))

                    host.codex_bin = self.root / "moved-codex"
                    host.models["codex"] = "codex-model-b"

                    with forbid_codex_processes():
                        completed = host.inbox_process(
                            staged["item_id"], request_id=f"codex-{label}"
                        )
                    self.assertEqual(("completed", "published", "attached"), (
                        completed["status"], completed["document_status"], completed["topic_status"]
                    ))
                    self.assertFalse(hasattr(host.ingestion, "runtime"))
                finally:
                    host.close()

    def test_host_entry_publishes_the_source_without_any_ai_review(self):
        workspace = self.root / "host-entry"
        workspace.mkdir()
        host = HostService(workspace, self.root / "host-entry-data", ingestion_parser=FigureParser())
        server = Server(("127.0.0.1", 0), host)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            with forbid_codex_processes():
                connection.request("POST", "/library/inbox?name=paper.pdf&topic=Systems", self.pdf.read_bytes())
                response = connection.getresponse()
                staged = json.loads(response.read())["value"]
                self.assertEqual(201, response.status)
                self.assertEqual(["mineru"], staged["services"])
                self.assertEqual("awaiting_confirmation", staged["status"])

                connection.request("POST", f"/library/inbox/{staged['item_id']}/confirm", b"{}")
                response = connection.getresponse()
                confirmed = json.loads(response.read())["value"]
                self.assertEqual(["mineru"], confirmed["confirmation"]["services"])
                self.assertEqual(["mineru"], sorted(confirmed["confirmation"]["service_config"]))

                connection.request("POST", f"/library/inbox/{staged['item_id']}/process",
                                   json.dumps({"requestId": "host-no-review"}).encode())
                response = connection.getresponse()
                self.assertEqual(202, response.status)
                response.read()

                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    connection.request("GET", "/library/inbox")
                    response = connection.getresponse()
                    items = json.loads(response.read())["value"]
                    if items and items[0]["status"] == "completed":
                        break
                    time.sleep(0.05)
                completed = items[0]
                self.assertEqual(("completed", "published", "attached"), (
                    completed["status"], completed["document_status"], completed["topic_status"]
                ))

                connection.request("GET", f"/library/sources/{completed['source_id']}/original")
                response = connection.getresponse()
                self.assertEqual(200, response.status)
                self.assertEqual(self.pdf.read_bytes(), response.read())
                connection.request("GET", f"/library/sources/{completed['source_id']}/content")
                response = connection.getresponse()
                self.assertEqual(200, response.status)
                self.assertIn(
                    "images/image-001.png",
                    response.read().decode("utf-8").replace("\r\n", "\n"),
                )
                connection.request(
                    "GET", f"/library/sources/{completed['source_id']}/images/image-001.png"
                )
                response = connection.getresponse()
                self.assertEqual(200, response.status)
                self.assertEqual(FIGURE_PNG, response.read())
                connection.request("GET", "/library/topics")
                response = connection.getresponse()
                self.assertEqual(
                    [{"topicId": "systems", "title": "Systems", "sourceIds": [completed["source_id"]]}],
                    json.loads(response.read())["value"],
                )
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            worker.join(5)
            host.close()

    def test_http_entry_returns_the_existing_task_for_a_repeated_add(self):
        workspace = self.root / "host-duplicate-entry"
        workspace.mkdir()
        host = HostService(workspace, self.root / "host-duplicate-data", ingestion_parser=ValidParser())
        server = Server(("127.0.0.1", 0), host)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            with forbid_codex_processes():
                connection.request("POST", "/library/inbox?name=paper.pdf&topic=Systems", self.pdf.read_bytes())
                response = connection.getresponse()
                staged = json.loads(response.read())["value"]
                self.assertEqual(201, response.status)
                self.assertFalse(staged.get("duplicate"))

                renamed = self.pdf.read_bytes()
                connection.request("POST", "/library/inbox?name=renamed.pdf&topic=Other", renamed)
                response = connection.getresponse()
                repeated = json.loads(response.read())["value"]
                self.assertEqual(201, response.status)
                self.assertEqual(staged["item_id"], repeated["item_id"])
                self.assertTrue(repeated["duplicate"])
                self.assertEqual("Systems", repeated["topic_title"])
                self.assertEqual("awaiting_confirmation", repeated["status"])

                connection.request("GET", "/library/inbox")
                response = connection.getresponse()
                items = json.loads(response.read())["value"]
                self.assertEqual(1, len(items))
                self.assertEqual(staged["item_id"], items[0]["item_id"])
                self.assertNotIn("duplicate", items[0])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            worker.join(5)
            host.close()

    def test_host_forwards_resubmission_and_rejects_a_stale_choice(self):
        upload_root = self.workspace / "uploads" / "fixture"
        upload_root.mkdir(parents=True)
        uploaded = upload_root / "selected.pdf"
        uploaded.write_bytes(self.pdf.read_bytes())
        host = HostService(
            self.workspace,
            self.root / "host-resubmit",
            ingestion_parser=AcceptanceUnknownParser(unknown_failures=1),
        )
        try:
            host.store.put("upload:fixture", {"name": uploaded.name, "path": str(uploaded)})
            staged = host.inbox_stage("fixture", topic_title="Systems")
            host.inbox_confirm(staged["item_id"])
            unknown = host.inbox_process(staged["item_id"], request_id="initial")
            choice = unknown["resubmit_risk"]["choice_id"]

            with self.assertRaisesRegex(WorkspaceError, "risk choice"):
                host.inbox_resubmit(staged["item_id"], request_id="resubmit-1", risk_choice_id="stale")

            completed = host.inbox_resubmit(staged["item_id"], request_id="resubmit-2", risk_choice_id=choice)
            self.assertEqual(("completed", "published"), (completed["status"], completed["document_status"]))
            self.assertEqual(completed, host.inbox_item(staged["item_id"]))
        finally:
            host.close()

    def test_http_entry_resubmit_validates_the_risk_choice_and_runs_the_application(self):
        workspace = self.root / "host-resubmit-entry"
        workspace.mkdir()
        parser = AcceptanceUnknownParser(unknown_failures=1)
        host = HostService(workspace, self.root / "host-resubmit-data", ingestion_parser=parser)
        server = Server(("127.0.0.1", 0), host)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request("POST", "/library/inbox?name=paper.pdf&topic=Systems", self.pdf.read_bytes())
            staged = json.loads(connection.getresponse().read())["value"]
            connection.request("POST", f"/library/inbox/{staged['item_id']}/confirm", b"{}")
            connection.getresponse().read()
            connection.request("POST", f"/library/inbox/{staged['item_id']}/process",
                               json.dumps({"requestId": "initial"}).encode())
            response = connection.getresponse()
            self.assertEqual(202, response.status)
            response.read()

            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                connection.request("GET", "/library/inbox")
                items = json.loads(connection.getresponse().read())["value"]
                if items and items[0]["status"] == "status_check_required":
                    break
                time.sleep(0.05)
            while staged["item_id"] in host.ingestion_workers:
                time.sleep(0.05)
            item = items[0]
            choice = item["resubmit_risk"]["choice_id"]
            self.assertFalse(item["remote_reference"])

            # A direct request with a stale risk choice is rejected server-side.
            connection.request("POST", f"/library/inbox/{item['item_id']}/resubmit",
                               json.dumps({"requestId": "resubmit-1", "riskChoiceId": "stale"}).encode())
            response = connection.getresponse()
            self.assertEqual(400, response.status)
            self.assertIn("risk choice", json.loads(response.read())["error"]["message"])

            connection.request("POST", f"/library/inbox/{item['item_id']}/resubmit",
                               json.dumps({"requestId": "resubmit-2", "riskChoiceId": choice}).encode())
            response = connection.getresponse()
            self.assertEqual(202, response.status)
            response.read()

            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                connection.request("GET", "/library/inbox")
                items = json.loads(connection.getresponse().read())["value"]
                if items and items[0]["status"] == "completed":
                    break
                time.sleep(0.05)
            completed = items[0]
            self.assertEqual("published", completed["document_status"])
            self.assertEqual((1, 1), (parser.unknown, parser.calls))
            self.assertEqual(1, len(list((workspace / "sources").iterdir())))
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            worker.join(5)
            host.close()

    def test_host_writer_identity_changes_per_open_and_rejects_second_writer(self):
        first = HostService(self.workspace, self.root / "host-one", ingestion_parser=ValidParser())
        first_id = first.ingestion.writer_id
        first.close()
        reopened = HostService(self.workspace, self.root / "host-one", ingestion_parser=ValidParser())
        try:
            self.assertNotEqual(first_id, reopened.ingestion.writer_id)
            with self.assertRaises(WorkspaceError) as error:
                HostService(self.workspace, self.root / 'host-two', ingestion_parser=ValidParser())
            self.assertEqual('workspace_busy', error.exception.error_id)
        finally:
            reopened.close()
        second = HostService(self.workspace, self.root / 'host-two', ingestion_parser=ValidParser())
        try:
            self.assertNotEqual(first_id, second.ingestion.writer_id)
        finally:
            second.close()


if __name__ == "__main__":
    unittest.main()
