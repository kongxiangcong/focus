from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


FOCUS_MAP = load_module(
    "journey_focus_map",
    ROOT / ".agents" / "skills" / "focus-map" / "scripts" / "focus_map.py",
)
FOCUS_READ = load_module(
    "journey_focus_read",
    ROOT / ".agents" / "skills" / "focus-read" / "scripts" / "focus_read.py",
)


class ReadingJourneyTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"reading-journey-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _workspace(self):
        workspace = self.root / "workspace"
        paper_root = workspace / "papers" / "journey-paper"
        bundle = paper_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (paper_root / "paper.yaml").write_text(
            json.dumps({"paper_id": "journey-paper", "title": "Journey Paper", "topics": ["systems"]}),
            encoding="utf-8",
        )
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "paper.md").write_text(
            "# Journey Paper\n\n## Compile Time\nThe compiler emits relocation metadata.\n\n"
            "## Runtime\nThe loader resolves the final address.\n\n"
            "## Result\nThe program uses the resolved address.\n",
            encoding="utf-8",
        )
        (bundle / "metadata.json").write_text('{"parser":"mineru-precision-api"}\n', encoding="utf-8")
        (bundle / "validation.json").write_text('{"ok":true}\n', encoding="utf-8")
        (workspace / "state.json").write_text(
            json.dumps(
                {
                    "current_paper_id": "journey-paper",
                    "papers": {"journey-paper": {"current_plan_id": None, "current_chunk_id": None}},
                }
            ),
            encoding="utf-8",
        )
        draft = self.root / "draft.json"
        draft.write_text(
            json.dumps(
                {
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
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return workspace, paper_root, draft

    @staticmethod
    def _run(module, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = module.main(args)
        return code, json.loads(stdout.getvalue() or stderr.getvalue())

    def test_map_read_question_search_note_continue_and_restore_share_one_cursor(self):
        workspace, paper_root, draft = self._workspace()
        code, mapped = self._run(
            FOCUS_MAP,
            [
                "map",
                "--workspace",
                str(workspace),
                "--paper-id",
                "journey-paper",
                "--draft",
                str(draft),
            ],
        )
        self.assertEqual(0, code)
        self.assertEqual(("plan-001", "chunk-001"), (mapped["plan_id"], mapped["chunk_id"]))

        code, current = self._run(FOCUS_READ, ["current", "--workspace", str(workspace)])
        self.assertEqual(0, code)
        self.assertEqual("translation_required", current["status"])
        self.assertEqual([{"source": "relocation", "translation": "重定位"}], current["relevant_glossary"])

        translation = self.root / "translation.txt"
        translation.write_text("编译器生成重定位元数据。", encoding="utf-8")
        code, _ = self._run(
            FOCUS_READ,
            [
                "retranslate",
                "--workspace",
                str(workspace),
                "--expected-plan-id",
                "plan-001",
                "--expected-chunk-id",
                "chunk-001",
                "--translation-file",
                str(translation),
            ],
        )
        self.assertEqual(0, code)

        state_before_questions = (workspace / "state.json").read_bytes()
        code, matches = self._run(
            FOCUS_READ,
            ["search", "--workspace", str(workspace), "--query", "final address", "--limit", "2"],
        )
        self.assertEqual(0, code)
        self.assertTrue(matches["matches"])
        selected = matches["matches"][0]["source_lines"]
        code, evidence = self._run(
            FOCUS_READ,
            [
                "read-range",
                "--workspace",
                str(workspace),
                "--start",
                str(selected[0]),
                "--end",
                str(selected[1]),
            ],
        )
        self.assertEqual(0, code)
        self.assertIn("final address", evidence["source_text"])
        self.assertEqual(state_before_questions, (workspace / "state.json").read_bytes())

        note = self.root / "clarification.txt"
        note.write_text("编译器保留重定位信息，加载器在运行前解析最终地址。", encoding="utf-8")
        code, saved = self._run(
            FOCUS_READ,
            [
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
            ],
        )
        self.assertEqual(0, code)
        self.assertEqual("note_saved", saved["status"])

        chunks_path = paper_root / "reading" / "plans" / "plan-001" / "chunks.jsonl"
        chunks_before_continue = chunks_path.read_bytes()
        code, advanced = self._run(
            FOCUS_READ,
            [
                "continue",
                "--workspace",
                str(workspace),
                "--expected-plan-id",
                "plan-001",
                "--expected-chunk-id",
                "chunk-001",
            ],
        )
        self.assertEqual(0, code)
        self.assertEqual(("continued", "chunk-002"), (advanced["status"], advanced["chunk_id"]))
        self.assertEqual(chunks_before_continue, chunks_path.read_bytes())

        code, restored = self._run(FOCUS_READ, ["state", "--workspace", str(workspace)])
        self.assertEqual(0, code)
        self.assertEqual(("plan-001", "chunk-002"), (restored["plan_id"], restored["chunk_id"]))
        code, next_chunk = self._run(FOCUS_READ, ["current", "--workspace", str(workspace)])
        self.assertEqual(0, code)
        self.assertEqual("translation_required", next_chunk["status"])
        self.assertNotIn("notes", next_chunk)
        self.assertNotIn("编译器保留重定位信息", json.dumps(next_chunk, ensure_ascii=False))

    def test_read_requires_plan_but_never_creates_a_parallel_session(self):
        workspace, paper_root, _ = self._workspace()
        code, error = self._run(FOCUS_READ, ["state", "--workspace", str(workspace)])
        self.assertEqual(1, code)
        self.assertEqual("reading_plan_missing", error["error_id"])
        self.assertFalse((paper_root / "reading").exists())


if __name__ == "__main__":
    unittest.main()
