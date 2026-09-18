from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


FOCUS_READ = load_module(
    "focus_read_cli",
    ROOT / ".agents" / "skills" / "focus-read" / "scripts" / "focus_read.py",
)
WORKSPACE_CORE = importlib.import_module("core.reading_workspace")


class FocusReadTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"focus-read-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _workspace(self):
        workspace = self.root / "workspace"
        source_root = workspace / "sources" / "fixture-paper"
        bundle = source_root / "parser-bundle"
        plan = source_root / "reading" / "plans" / "plan-001"
        records = plan / "records"
        (bundle / "images").mkdir(parents=True)
        records.mkdir(parents=True)
        (source_root / "source.yaml").write_text(
            json.dumps({"source_kind": "paper_pdf", "source_id": "fixture-paper", "title": "Fixture Paper", "short_name": "fixture", "identity": "fixture:read"}),
            encoding="utf-8",
        )
        lines = [
            "# Fixture Paper",
            "",
            "## Method",
            "The alias address keeps source order.",
            "![Architecture](images/image-001.png)",
            "Figure 1: Architecture overview.",
            "",
            "## Runtime",
            "Relocation resolves the alias address at runtime.",
            "",
            "## Results",
            "The array improves throughput.",
        ]
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "content.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (bundle / "metadata.json").write_text('{"source_kind":"paper_pdf","language":"en","parser":"paper-parser","batch_id":"fixture-batch"}\n', encoding="utf-8")
        (bundle / "validation.json").write_text('{"ok":true}\n', encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(b"image")
        chunks = [
            {
                "chunk_id": "chunk-001",
                "index": 1,
                "section_path": ["Fixture Paper", "Method"],
                "source_lines": [1, 6],
                "images": ["images/image-001.png"],
            },
            {
                "chunk_id": "chunk-002",
                "index": 2,
                "section_path": ["Fixture Paper", "Runtime"],
                "source_lines": [7, 10],
                "images": [],
            },
            {
                "chunk_id": "chunk-003",
                "index": 3,
                "section_path": ["Fixture Paper", "Results"],
                "source_lines": [11, 12],
                "images": [],
            },
        ]
        (plan / "chunks.jsonl").write_text(
            "".join(json.dumps(chunk, separators=(",", ":")) + "\n" for chunk in chunks),
            encoding="utf-8",
        )
        (plan / "glossary.tsv").write_text(
            "alias address\t别名地址\narray\t阵列\nunused term\t不应投影\n",
            encoding="utf-8",
        )
        for chunk in chunks:
            (records / f'{chunk["chunk_id"]}.json').write_text(
                json.dumps({"chunk_id": chunk["chunk_id"], "translation": None, "notes": []}),
                encoding="utf-8",
            )
        (workspace / "state.json").write_text(
            json.dumps(
                {
                    "current_source_id": "fixture-paper",
                    "current_topic_id": None,
                    "sources": {"fixture-paper": {"current_plan_id": "plan-001", "current_chunk_id": "chunk-001"}},
                }
            ),
            encoding="utf-8",
        )
        return workspace, source_root, plan

    @staticmethod
    def _run(*args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = FOCUS_READ.main(list(args))
        output = stdout.getvalue() or stderr.getvalue()
        return result, json.loads(output)

    def _text(self, name: str, value: str) -> Path:
        path = self.root / name
        path.write_text(value, encoding="utf-8")
        return path

    def test_default_state_and_chunk_projection_exclude_notes_and_unmatched_glossary(self):
        workspace, _, plan = self._workspace()
        record_path = plan / "records" / "chunk-001.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["notes"] = [
            {"kind": "thought", "origin": "user", "content": f"历史思考 {index}"}
            for index in range(100)
        ]
        record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

        state_code, state = self._run("state", "--workspace", str(workspace))
        chunk_code, chunk = self._run("current", "--workspace", str(workspace))

        self.assertEqual((0, 0), (state_code, chunk_code))
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

        code, chunk = self._run("current", "--workspace", str(workspace))

        self.assertEqual(0, code)
        self.assertEqual("source_ready", chunk["status"])
        self.assertIsNone(chunk["translation"])

    def test_translation_and_notes_change_only_the_current_reading_record(self):
        workspace, _, plan = self._workspace()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        translation = self._text("translation.txt", "别名地址保持原文顺序。")
        code, translated = self._run(
            "retranslate",
            "--workspace",
            str(workspace),
            "--expected-plan-id",
            "plan-001",
            "--expected-chunk-id",
            "chunk-001",
            "--translation-file",
            str(translation),
        )
        note = self._text("note.txt", "最终地址在运行阶段解析。")
        anchor = self._text("anchor.json", '{"source_lines":[4,4],"quote":"alias address"}')
        note_args = (
            "append-note",
            "--workspace",
            str(workspace),
            "--expected-plan-id",
            "plan-001",
            "--expected-chunk-id",
            "chunk-001",
            "--kind",
            "clarification",
            "--origin",
            "dialogue",
            "--content-file",
            str(note),
            "--anchor",
            str(anchor),
        )
        first_code, first = self._run(*note_args)
        second_code, second = self._run(*note_args)

        self.assertEqual((0, 0, 0), (code, first_code, second_code))
        self.assertEqual("retranslated", translated["status"])
        self.assertEqual("note_saved", first["status"])
        self.assertEqual("note_unchanged", second["status"])
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())
        record = json.loads((plan / "records" / "chunk-001.json").read_text(encoding="utf-8"))
        self.assertEqual("别名地址保持原文顺序。", record["translation"])
        self.assertEqual(1, len(record["notes"]))
        _, listed = self._run(
            "list-notes",
            "--workspace",
            str(workspace),
            "--plan-id",
            "plan-001",
            "--chunk-id",
            "chunk-001",
            "--kinds",
            "clarification",
            "--limit",
            "1",
        )
        self.assertEqual(record["notes"], listed["notes"])

    def test_continue_uses_expected_receipt_saves_pending_notes_and_does_not_pretranslate(self):
        workspace, _, plan = self._workspace()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        pending = self._text(
            "pending.json",
            '[{"kind":"question","origin":"user","content":"运行时由谁完成重定位？"}]',
        )
        args = (
            "continue",
            "--workspace",
            str(workspace),
            "--expected-plan-id",
            "plan-001",
            "--expected-chunk-id",
            "chunk-001",
            "--pending-notes",
            str(pending),
        )

        code, advanced = self._run(*args)
        retry_code, retry = self._run(*args)

        self.assertEqual((0, 0), (code, retry_code))
        self.assertEqual(("continued", "chunk-002"), (advanced["status"], advanced["chunk_id"]))
        self.assertEqual(("cursor_changed", "chunk-002"), (retry["status"], retry["chunk_id"]))
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())
        current_record = json.loads((plan / "records" / "chunk-001.json").read_text(encoding="utf-8"))
        next_record = json.loads((plan / "records" / "chunk-002.json").read_text(encoding="utf-8"))
        self.assertEqual(1, len(current_record["notes"]))
        self.assertIsNone(next_record["translation"])
        _, current = self._run("current", "--workspace", str(workspace))
        self.assertEqual("translation_required", current["status"])
        self.assertEqual("chunk-002", current["chunk_id"])

    def test_cursor_write_failure_keeps_distilled_note_and_retry_does_not_duplicate_it(self):
        workspace, _, plan = self._workspace()
        pending = [{"kind": "thought", "origin": "dialogue", "content": "一条稳定结论。"}]
        core = WORKSPACE_CORE.WorkspaceCore(workspace)
        original = WORKSPACE_CORE._write_document

        def fail_state(path, value):
            if path.name == "state.json":
                raise OSError("controlled failure")
            return original(path, value)

        with mock.patch.object(WORKSPACE_CORE, "_write_document", side_effect=fail_state):
            with self.assertRaises(WORKSPACE_CORE.WorkspaceError) as caught:
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

        code, found = self._run(
            "search",
            "--workspace",
            str(workspace),
            "--query",
            "alias address",
            "--limit",
            "1",
        )
        match = found["matches"][0]
        range_code, evidence = self._run(
            "read-range",
            "--workspace",
            str(workspace),
            "--start",
            str(match["source_lines"][0]),
            "--end",
            str(match["source_lines"][1]),
        )

        self.assertEqual((0, 0), (code, range_code))
        self.assertEqual(1, len(found["matches"]))
        self.assertIn("snippet", match)
        self.assertNotIn("content", match)
        self.assertIn("alias address", evidence["source_text"])
        self.assertEqual(state_before, (workspace / "state.json").read_bytes())

    def test_glossary_update_and_paper_switch_leave_plan_and_each_cursor_intact(self):
        workspace, _, plan = self._workspace()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        code, updated = self._run(
            "update-glossary",
            "--workspace",
            str(workspace),
            "--expected-plan-id",
            "plan-001",
            "--source",
            "alias address",
            "--translation",
            "别名寻址",
        )
        self.assertEqual(0, code)
        self.assertEqual("glossary_updated", updated["status"])
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())
        _, current = self._run("current", "--workspace", str(workspace))
        self.assertEqual(
            [{"source": "alias address", "translation": "别名寻址"}],
            current["relevant_glossary"],
        )

        other_root = workspace / "sources" / "other-paper"
        other_bundle = other_root / "parser-bundle"
        (other_bundle / "images").mkdir(parents=True)
        (other_bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (other_bundle / "content.md").write_text("# Other\n", encoding="utf-8")
        (other_bundle / "metadata.json").write_text('{"source_kind":"paper_pdf","language":"en","parser":"paper-parser","batch_id":"fixture-batch"}\n', encoding="utf-8")
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

        code, switched = self._run(
            "switch", "--workspace", str(workspace), "--source-id", "other-paper"
        )
        self.assertEqual(0, code)
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

        code, completed = self._run(
            "continue",
            "--workspace",
            str(workspace),
            "--expected-plan-id",
            "plan-001",
            "--expected-chunk-id",
            "chunk-003",
        )

        self.assertEqual(0, code)
        self.assertEqual("reading_completed", completed["status"])
        self.assertIsNone(completed["chunk_id"])
        self.assertEqual("plan-001", completed["plan_id"])
        retry_code, retry = self._run(
            "continue",
            "--workspace",
            str(workspace),
            "--expected-plan-id",
            "plan-001",
            "--expected-chunk-id",
            "chunk-003",
        )
        self.assertEqual(0, retry_code)
        self.assertEqual("reading_completed", retry["status"])


if __name__ == "__main__":
    unittest.main()
