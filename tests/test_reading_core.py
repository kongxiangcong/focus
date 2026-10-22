"""Reading workspace behaviour through the deterministic Core API.

These tests used to load the retired `focus-read` skill CLI. They now call
`core.WorkspaceCore` directly, which is the same module the Host drives at
runtime.
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

import reading_fixture
from core import reading_workspace


class ReadingCoreTests(reading_fixture.ReadingFixture, unittest.TestCase):
    def test_default_state_and_chunk_projection_exclude_notes_and_unmatched_glossary(self):
        workspace, _, plan = self._workspace()
        record_path = plan / "records" / "chunk-001.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["notes"] = [
            {"kind": "thought", "origin": "user", "content": f"历史思考 {index}"}
            for index in range(100)
        ]
        record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

        core = self.core(workspace)
        state = core.get_reading_state()
        chunk = core.get_current_chunk()

        self.assertEqual("reading", state["status"])
        self.assertNotIn("notes", state)
        self.assertEqual("translation_required", chunk["status"])
        self.assertNotIn("notes", chunk)
        self.assertEqual(
            [{"source": "alias address", "translation": "别名地址"}],
            chunk["relevant_glossary"],
        )
        self.assertNotIn("unused term", json.dumps(chunk, ensure_ascii=False))
        self.assertLess(len(json.dumps(state, ensure_ascii=False)), 300)

    def test_chinese_paper_source_is_ready_without_translation(self):
        workspace, source_root, _ = self._workspace()
        metadata_path = source_root / "parser-bundle" / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["language"] = "zh"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        chunk = self.core(workspace).get_current_chunk()

        self.assertEqual("source_ready", chunk["status"])
        self.assertIsNone(chunk["translation"])

    def test_translation_and_notes_change_only_the_current_reading_record(self):
        workspace, _, plan = self._workspace()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        core = self.core(workspace)
        translated = core.retranslate_current_chunk(
            expected_plan_id="plan-001",
            expected_chunk_id="chunk-001",
            translation="别名地址保持原文顺序。",
        )
        note = {
            "kind": "clarification",
            "origin": "dialogue",
            "content": "最终地址在运行阶段解析。",
            "anchor": {"source_lines": [4, 4], "quote": "alias address"},
        }
        first = core.append_note(
            expected_plan_id="plan-001",
            expected_chunk_id="chunk-001",
            kind=note["kind"],
            origin=note["origin"],
            content=note["content"],
            anchor=note["anchor"],
        )
        second = core.append_note(
            expected_plan_id="plan-001",
            expected_chunk_id="chunk-001",
            kind=note["kind"],
            origin=note["origin"],
            content=note["content"],
            anchor=note["anchor"],
        )

        self.assertEqual("retranslated", translated["status"])
        self.assertEqual("note_saved", first["status"])
        self.assertEqual("note_unchanged", second["status"])
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())
        record = json.loads((plan / "records" / "chunk-001.json").read_text(encoding="utf-8"))
        self.assertEqual("别名地址保持原文顺序。", record["translation"])
        self.assertEqual(1, len(record["notes"]))
        listed = core.list_notes(
            plan_id="plan-001",
            chunk_id="chunk-001",
            kinds=["clarification"],
            limit=1,
        )
        self.assertEqual(record["notes"], listed["notes"])

    def test_continue_uses_expected_receipt_saves_pending_notes_and_does_not_pretranslate(self):
        workspace, _, plan = self._workspace()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        pending = [{"kind": "question", "origin": "user", "content": "运行时由谁完成重定位？"}]
        core = self.core(workspace)

        advanced = core.continue_reading(
            expected_plan_id="plan-001",
            expected_chunk_id="chunk-001",
            pending_notes=pending,
        )
        retry = core.continue_reading(
            expected_plan_id="plan-001",
            expected_chunk_id="chunk-001",
            pending_notes=pending,
        )

        self.assertEqual(("continued", "chunk-002"), (advanced["status"], advanced["chunk_id"]))
        self.assertEqual(("cursor_changed", "chunk-002"), (retry["status"], retry["chunk_id"]))
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())
        current_record = json.loads((plan / "records" / "chunk-001.json").read_text(encoding="utf-8"))
        next_record = json.loads((plan / "records" / "chunk-002.json").read_text(encoding="utf-8"))
        self.assertEqual(1, len(current_record["notes"]))
        self.assertIsNone(next_record["translation"])
        current = core.get_current_chunk()
        self.assertEqual("translation_required", current["status"])
        self.assertEqual("chunk-002", current["chunk_id"])

    def test_cursor_write_failure_keeps_distilled_note_and_retry_does_not_duplicate_it(self):
        workspace, _, plan = self._workspace()
        pending = [{"kind": "thought", "origin": "dialogue", "content": "一条稳定结论。"}]
        core = self.core(workspace)
        original = reading_workspace._write_document

        def fail_state(path, value):
            if path.name == "state.json":
                raise OSError("controlled failure")
            return original(path, value)

        with mock.patch.object(reading_workspace, "_write_document", side_effect=fail_state):
            with self.assertRaises(reading_workspace.WorkspaceError) as caught:
                core.continue_reading(
                    expected_plan_id="plan-001",
                    expected_chunk_id="chunk-001",
                    pending_notes=pending,
                )

        self.assertEqual("reading_cursor_write_failed", caught.exception.error_id)
        state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("chunk-001", state["sources"]["fixture-paper"]["current_chunk_id"])
        saved = json.loads((plan / "records" / "chunk-001.json").read_text(encoding="utf-8"))
        self.assertEqual(pending, saved["notes"])

        result = core.continue_reading(
            expected_plan_id="plan-001",
            expected_chunk_id="chunk-001",
            pending_notes=pending,
        )
        self.assertEqual("chunk-002", result["chunk_id"])
        saved = json.loads((plan / "records" / "chunk-001.json").read_text(encoding="utf-8"))
        self.assertEqual(1, len(saved["notes"]))

    def test_search_returns_bounded_snippets_then_range_read_without_moving_cursor(self):
        workspace, _, _ = self._workspace()
        state_before = (workspace / "state.json").read_bytes()
        core = self.core(workspace)

        found = core.search_source(query="alias address", limit=1)
        match = found["matches"][0]
        evidence = core.read_source_range(
            start=match["source_lines"][0],
            end=match["source_lines"][1],
        )

        self.assertEqual(1, len(found["matches"]))
        self.assertIn("snippet", match)
        self.assertNotIn("content", match)
        self.assertIn("alias address", evidence["source_text"])
        self.assertEqual(state_before, (workspace / "state.json").read_bytes())

    def test_glossary_update_and_paper_switch_leave_plan_and_each_cursor_intact(self):
        workspace, _, plan = self._workspace()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        core = self.core(workspace)
        updated = core.update_glossary(
            expected_plan_id="plan-001",
            source="alias address",
            translation="别名寻址",
        )
        self.assertEqual("glossary_updated", updated["status"])
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())
        current = core.get_current_chunk()
        self.assertEqual(
            [{"source": "alias address", "translation": "别名寻址"}],
            current["relevant_glossary"],
        )

        other_root = workspace / "sources" / "other-paper"
        other_bundle = other_root / "parser-bundle"
        (other_bundle / "images").mkdir(parents=True)
        (other_bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (other_bundle / "content.md").write_text("# Other\n", encoding="utf-8")
        (other_bundle / "metadata.json").write_text('{"source_kind":"paper_pdf","language":"en","parser":"article-parser","batch_id":"fixture-batch"}\n', encoding="utf-8")
        (other_bundle / "validation.json").write_text('{"ok":true}\n', encoding="utf-8")
        (other_root / "source.yaml").write_text(
            json.dumps({"source_kind": "paper_pdf", "source_id": "other-paper", "title": "Other", "short_name": "other", "identity": "fixture:other"}),
            encoding="utf-8",
        )
        state_path = workspace / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        original_cursor = dict(state["sources"]["fixture-paper"])
        state["sources"]["other-paper"] = {"current_plan_id": None, "current_chunk_id": None}
        state_path.write_text(json.dumps(state), encoding="utf-8")

        switched = core.switch_source("other-paper")
        self.assertEqual("other-paper", switched["source_id"])
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual("other-paper", state["current_source_id"])
        self.assertEqual(original_cursor, state["sources"]["fixture-paper"])

    def test_final_continue_completes_plan_and_old_receipt_cannot_restart_it(self):
        workspace, _, _ = self._workspace()
        state_path = workspace / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["sources"]["fixture-paper"]["current_chunk_id"] = "chunk-003"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        core = self.core(workspace)

        completed = core.continue_reading(expected_plan_id="plan-001", expected_chunk_id="chunk-003")
        retry = core.continue_reading(expected_plan_id="plan-001", expected_chunk_id="chunk-003")

        self.assertEqual("reading_completed", completed["status"])
        self.assertIsNone(completed["chunk_id"])
        self.assertEqual("plan-001", completed["plan_id"])
        self.assertEqual("reading_completed", retry["status"])


if __name__ == "__main__":
    unittest.main()
