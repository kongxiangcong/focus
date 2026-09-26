"""Source Notes use the real Core and an isolated registered Source."""
import tempfile
import unittest
from pathlib import Path

import test_focus_read
from core.source_notes import SourceNotes
from core.reading_workspace import WorkspaceCore, WorkspaceError
from core.source_library import SourceLibrary


class SourceNotesTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_focus_read.FocusReadTests()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.notes = SourceNotes(self.workspace)
        self.source = "fixture-paper"
        self.bundle = self.notes.bundle_version(self.source)

    def tearDown(self):
        self.fixture.tearDown()

    def save(self, request_id="request-1234", **extra):
        return self.notes.save(self.source, bundle=self.bundle, request_id=request_id,
                               intent_id="intent-12345", content="An example and conclusion.",
                               kind="conclusion", origin="dialogue", evidence_role="explanation", **extra)

    def test_save_replay_append_and_reopen(self):
        first = self.save()
        self.assertEqual(first, self.save())
        self.assertEqual(first, self.notes.result(self.source, "request-1234"))
        second = self.save("request-5678")
        self.assertNotEqual(first["note"]["noteId"], second["note"]["noteId"])
        self.assertEqual(2, len(SourceNotes(self.workspace).list(self.source)))

    def test_changed_payload_and_cancelled_request_rejected(self):
        self.save()
        with self.assertRaises(WorkspaceError) as caught:
            self.notes.save(self.source, bundle=self.bundle, request_id="request-1234",
                            intent_id="intent-12345", content="Different", kind="conclusion", origin="dialogue", evidence_role="explanation")
        self.assertEqual("note_request_conflict", caught.exception.error_id)
        self.notes.cancel(self.source, "request-9999")
        with self.assertRaises(WorkspaceError) as caught:
            self.save("request-9999")
        self.assertEqual("note_cancelled", caught.exception.error_id)

    def test_bad_evidence_rejected_without_note(self):
        with self.assertRaises(WorkspaceError) as caught:
            self.notes.save(self.source, bundle=self.bundle, request_id="request-bad1", intent_id="intent-12345",
                content="Claim", kind="conclusion", origin="dialogue", evidence_role="source_claim",
                anchor={"sourceId": self.source, "bundle": self.bundle,
                        "sourceLines": [1, 1], "quote": "invented quote"})
        self.assertEqual("note_anchor_invalid", caught.exception.error_id)
        self.assertEqual([], self.notes.list(self.source))

    def test_source_claim_requires_anchor(self):
        with self.assertRaises(WorkspaceError) as caught:
            self.notes.save(self.source, bundle=self.bundle, request_id="request-bad2", intent_id="intent-12345",
                content="Claim", kind="conclusion", origin="dialogue", evidence_role="source_claim")
        self.assertEqual("note_anchor_required", caught.exception.error_id)

    def test_edit_delete_and_undo_survive_reopen_with_monotonic_revision(self):
        created = self.save()["note"]
        note_id = created["noteId"]
        edited = self.notes.change(self.source, note_id=note_id, request_id="edit-12345",
                                   expected_revision=1, operation="edit", content="Corrected wording")
        self.assertEqual(2, edited["note"]["revision"])
        reopened = SourceNotes(self.workspace)
        restored = reopened.change(self.source, note_id=note_id, request_id="undo-12345",
                                   expected_revision=2, operation="undo")
        self.assertEqual("An example and conclusion.", restored["note"]["content"])
        self.assertEqual(3, restored["note"]["revision"])
        self.assertFalse(restored["note"]["canUndo"])
        deleted = reopened.change(self.source, note_id=note_id, request_id="delete-12345",
                                  expected_revision=3, operation="delete")
        self.assertEqual([], reopened.list(self.source))
        self.assertEqual(deleted, reopened.result(self.source, "delete-12345"))
        restored = SourceNotes(self.workspace).change(self.source, note_id=note_id,
            request_id="restore-12345", expected_revision=4, operation="undo")
        self.assertFalse(restored["note"]["deleted"])
        self.assertEqual(5, restored["note"]["revision"])

    def test_undo_create_and_stale_edit_conflict_preserve_input(self):
        created = self.save()["note"]
        note_id = created["noteId"]
        changed = self.notes.change(self.source, note_id=note_id, request_id="edit-22222",
                                    expected_revision=1, operation="edit", content="New wording")
        conflict = self.notes.change(self.source, note_id=note_id, request_id="edit-33333",
                                     expected_revision=1, operation="edit", content="My unsaved input")
        self.assertEqual("conflict", conflict["status"])
        self.assertEqual("My unsaved input", conflict["attemptedContent"])
        self.assertEqual("New wording", conflict["current"]["content"])
        self.assertEqual(conflict, self.notes.change(self.source, note_id=note_id, request_id="edit-33333",
                             expected_revision=1, operation="edit", content="My unsaved input"))
        self.assertEqual("New wording", self.notes.list(self.source)[0]["content"])
        fresh = self.save("request-undo")['note']
        undone = self.notes.change(self.source, note_id=fresh["noteId"], request_id="undo-create",
                                   expected_revision=1, operation="undo")
        self.assertTrue(undone["note"]["deleted"])
        self.assertEqual(2, undone["note"]["revision"])

    def test_old_anchor_keeps_bundle_identity_and_becomes_unavailable(self):
        anchored = self.notes.save(self.source, bundle=self.bundle, request_id="anchor-1234",
            intent_id="intent-12345", content="The alias address keeps order.", kind="conclusion",
            origin="dialogue", evidence_role="source_claim",
            anchor={"sourceId": self.source, "bundle": self.bundle, "sourceLines": [4, 4],
                    "quote": "The alias address keeps source order."})["note"]
        content = self.workspace / "sources" / self.source / "parser-bundle" / "content.md"
        content.write_text(content.read_text(encoding="utf-8").replace("keeps source order", "has a different version"), encoding="utf-8")
        viewed = self.notes.list(self.source)[0]
        self.assertEqual(self.bundle, viewed["anchor"]["bundle"])
        self.assertEqual(anchored["anchor"]["sourceLines"], viewed["anchor"]["sourceLines"])
        self.assertTrue(viewed["sourceUpdated"])
        self.assertEqual("unavailable", viewed["referenceStatus"])

    def test_real_core_plan_rebuild_keeps_one_source_note_collection(self):
        created = self.save()["note"]
        SourceLibrary(self.workspace).unselect_plan(self.source)
        mapped = WorkspaceCore(self.workspace).map_reading_plan(self.source, draft={
            "chunks": [
                {"section_path": ["Fixture Paper", "Method"], "source_lines": [1, 6],
                 "images": ["images/image-001.png"]},
                {"section_path": ["Fixture Paper", "Runtime"], "source_lines": [7, 10], "images": []},
                {"section_path": ["Fixture Paper", "Results"], "source_lines": [11, 12], "images": []},
            ], "glossary": []})
        self.assertEqual("plan-002", mapped["plan_id"])
        self.assertEqual(created["noteId"], self.notes.list(self.source)[0]["noteId"])
        self.assertEqual(1, len(self.notes.list(self.source)))


if __name__ == "__main__":
    unittest.main()
