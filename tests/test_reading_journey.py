"""End-to-end Reading journey through the deterministic Core API."""
from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path

from core import WorkspaceCore, WorkspaceError


ROOT = Path(__file__).resolve().parents[1]


class ReadingJourneyTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"r-{uuid.uuid4().hex[:8]}"
        self.root.mkdir()

    def tearDown(self):
        if hasattr(self, 'lease'):
            self.lease.close()
        shutil.rmtree(self.root)

    def _workspace(self):
        workspace = self.root / "workspace"
        source_root = workspace / "sources" / "journey-paper"
        bundle = source_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (source_root / "source.yaml").write_text(
            json.dumps({"source_kind": "paper_pdf", "source_id": "journey-paper", "title": "Journey Paper", "short_name": "journey", "identity": "fixture:journey"}),
            encoding="utf-8",
        )
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "content.md").write_text(
            "# Journey Paper\n\n## Compile Time\nThe compiler emits relocation metadata.\n\n"
            "## Runtime\nThe loader resolves the final address.\n\n"
            "## Result\nThe program uses the resolved address.\n",
            encoding="utf-8",
        )
        (bundle / "metadata.json").write_text('{"source_kind":"paper_pdf","language":"en","parser":"article-parser","batch_id":"fixture-batch"}\n', encoding="utf-8")
        (bundle / "validation.json").write_text('{"ok":true}\n', encoding="utf-8")
        (workspace / "state.json").write_text(
            json.dumps(
                {
                    "current_source_id": "journey-paper",
                    "current_topic_id": None,
                    "sources": {"journey-paper": {"current_plan_id": None, "current_chunk_id": None}},
                }
            ),
            encoding="utf-8",
        )
        from workspace_fixture import publish_workspace
        from core.workspace_lifecycle import WorkspaceLease
        publish_workspace(workspace)
        self.lease = WorkspaceLease(workspace)
        draft = {
            "chunks": [
                {
                    "section_path": ["Journey Paper", "Compile Time"],
                    "source_lines": [1, 5],
                    "images": [],
                },
                {
                    "section_path": ["Journey Paper", "Runtime"],
                    "source_lines": [6, 8],
                    "images": [],
                },
                {
                    "section_path": ["Journey Paper", "Result"],
                    "source_lines": [9, 10],
                    "images": [],
                },
            ],
            "glossary": [["relocation", "重定位"], ["loader", "加载器"]],
        }
        return workspace, source_root, draft

    def test_map_read_question_search_note_continue_and_restore_share_one_cursor(self):
        workspace, source_root, draft = self._workspace()
        core = WorkspaceCore(workspace)

        mapped = core.map_reading_plan("journey-paper", draft=draft)
        self.assertEqual(("plan-001", "chunk-001"), (mapped["plan_id"], mapped["chunk_id"]))

        current = core.get_current_chunk()
        self.assertEqual("translation_required", current["status"])
        self.assertEqual([{"source": "relocation", "translation": "重定位"}], current["relevant_glossary"])

        core.retranslate_current_chunk(
            expected_plan_id="plan-001",
            expected_chunk_id="chunk-001",
            translation="编译器生成重定位元数据。",
        )

        state_before_questions = (workspace / "state.json").read_bytes()
        matches = core.search_source(query="final address", limit=2)
        self.assertTrue(matches["matches"])
        selected = matches["matches"][0]["source_lines"]
        evidence = core.read_source_range(start=selected[0], end=selected[1])
        self.assertIn("final address", evidence["source_text"])
        self.assertEqual(state_before_questions, (workspace / "state.json").read_bytes())

        saved = core.append_note(
            expected_plan_id="plan-001",
            expected_chunk_id="chunk-001",
            kind="clarification",
            origin="dialogue",
            content="编译器保留重定位信息，加载器在运行前解析最终地址。",
        )
        self.assertEqual("note_saved", saved["status"])

        chunks_path = source_root / "reading" / "plans" / "plan-001" / "chunks.jsonl"
        chunks_before_continue = chunks_path.read_bytes()
        advanced = core.continue_reading(expected_plan_id="plan-001", expected_chunk_id="chunk-001")
        self.assertEqual(("continued", "chunk-002"), (advanced["status"], advanced["chunk_id"]))
        self.assertEqual(chunks_before_continue, chunks_path.read_bytes())

        restored = core.get_reading_state()
        self.assertEqual(("plan-001", "chunk-002"), (restored["plan_id"], restored["chunk_id"]))
        next_chunk = core.get_current_chunk()
        self.assertEqual("translation_required", next_chunk["status"])
        self.assertNotIn("notes", next_chunk)
        self.assertNotIn("编译器保留重定位信息", json.dumps(next_chunk, ensure_ascii=False))

    def test_read_requires_plan_but_never_creates_a_parallel_session(self):
        workspace, source_root, _ = self._workspace()

        with self.assertRaises(WorkspaceError) as caught:
            WorkspaceCore(workspace).get_reading_state()

        self.assertEqual("reading_plan_missing", caught.exception.error_id)
        self.assertFalse((source_root / "reading").exists())


if __name__ == "__main__":
    unittest.main()
