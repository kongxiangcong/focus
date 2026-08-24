from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
GUIDE_SCRIPT = ROOT / ".agents" / "skills" / "focus-guide" / "scripts" / "focus_guide.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


FOCUS_GUIDE = load_module("focus_guide_cli", GUIDE_SCRIPT)
WORKSPACE_CORE = importlib.import_module("core.reading_workspace")


class FocusGuideTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"focus-guide-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _workspace(self):
        workspace = self.root / "workspace"
        paper_root = workspace / "papers" / "fixture-paper"
        bundle = paper_root / "parser-bundle"
        plan = paper_root / "reading" / "plans" / "plan-001"
        (bundle / "images").mkdir(parents=True)
        plan.mkdir(parents=True)
        (paper_root / "paper.yaml").write_text(
            json.dumps({"paper_id": "fixture-paper", "title": "Fixture Paper", "topics": ["systems"]}),
            encoding="utf-8",
        )
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "paper.md").write_text(
            "# Method\nSource mechanism.\n![Architecture](images/image-001.png)\n"
            "图 1：原始架构图。\n## Results\nMore evidence.\n",
            encoding="utf-8",
        )
        (bundle / "metadata.json").write_text('{"parser":"mineru-precision-api"}\n', encoding="utf-8")
        (bundle / "validation.json").write_text('{"ok":true}\n', encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(b"image")
        records = [
            {
                "chunk_id": "chunk-001",
                "index": 1,
                "section_path": ["Method"],
                "source_lines": [1, 4],
                "images": ["images/image-001.png"],
                "translation": None,
                "notes": [],
            },
            {
                "chunk_id": "chunk-002",
                "index": 2,
                "section_path": ["Results"],
                "source_lines": [5, 6],
                "images": [],
                "translation": None,
                "notes": [],
            },
        ]
        (plan / "chunks.jsonl").write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8"
        )
        (plan / "glossary.tsv").write_text("mechanism\t机制\n", encoding="utf-8")
        (workspace / "pointers.yaml").write_text(
            json.dumps(
                {
                    "current_paper_id": "fixture-paper",
                    "papers": {
                        "fixture-paper": {
                            "current_plan_id": "plan-001",
                            "current_chunk_id": "chunk-001",
                            "current_explanation_id": "explanation-007",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return workspace, paper_root, plan

    def _add_second_paper(self, workspace: Path):
        paper_root = workspace / "papers" / "second-paper"
        bundle = paper_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (paper_root / "paper.yaml").write_text(
            json.dumps({"paper_id": "second-paper", "title": "Second Paper", "topics": ["systems"]}),
            encoding="utf-8",
        )
        (bundle / "source.pdf").write_bytes(b"%PDF second")
        (bundle / "paper.md").write_text("# Second\nSource.\n", encoding="utf-8")
        (bundle / "metadata.json").write_text('{"parser":"mineru-precision-api"}\n', encoding="utf-8")
        (bundle / "validation.json").write_text('{"ok":true}\n', encoding="utf-8")
        pointers_path = workspace / "pointers.yaml"
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        pointers["papers"]["second-paper"] = {
            "current_plan_id": None,
            "current_chunk_id": None,
            "current_explanation_id": "explanation-002",
        }
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        return paper_root

    def test_first_presentation_caches_translation_and_new_process_reuses_it_with_original_image_caption(self):
        workspace, _, plan = self._workspace()
        pointers_before = (workspace / "pointers.yaml").read_bytes()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            requested = FOCUS_GUIDE.main(["present", "--workspace", str(workspace)])

        self.assertEqual(0, requested)
        request = json.loads(stdout.getvalue())
        self.assertEqual("translation_required", request["status"])
        self.assertEqual("mechanism", request["glossary"][0]["source"])
        self.assertIn("Source mechanism.", request["source_text"])
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())

        translation = self.root / "translation.txt"
        translation.write_text("# 方法\n源机制。", encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            presented = FOCUS_GUIDE.main(
                ["present", "--workspace", str(workspace), "--translation-file", str(translation)]
            )

        self.assertEqual(0, presented)
        response = json.loads(stdout.getvalue())
        self.assertEqual("presented", response["status"])
        self.assertEqual("# 方法\n源机制。", response["translation"])
        self.assertFalse(response["cached"])
        self.assertEqual("图 1：原始架构图。", response["images"][0]["caption"])
        self.assertTrue(Path(response["images"][0]["path"]).is_file())
        self.assertTrue({"summary", "key_points", "image_explanation", "user_evaluation"}.isdisjoint(response))
        self.assertEqual(pointers_before, (workspace / "pointers.yaml").read_bytes())

        completed = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(GUIDE_SCRIPT), "present", "--workspace", str(workspace)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        restored = json.loads(completed.stdout)
        self.assertTrue(restored["cached"])
        self.assertEqual(response["translation"], restored["translation"])
        self.assertEqual(pointers_before, (workspace / "pointers.yaml").read_bytes())

    def test_translation_write_failure_preserves_prior_chunk_record(self):
        workspace, _, plan = self._workspace()
        translation = self.root / "translation.txt"
        translation.write_text("受控翻译", encoding="utf-8")
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        stderr = io.StringIO()

        with mock.patch.object(WORKSPACE_CORE, "_replace_text", side_effect=OSError("controlled failure")):
            with contextlib.redirect_stderr(stderr):
                result = FOCUS_GUIDE.main(
                    ["present", "--workspace", str(workspace), "--translation-file", str(translation)]
                )

        self.assertEqual(1, result)
        self.assertEqual("reading_chunk_write_failed", json.loads(stderr.getvalue())["error_id"])
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())

    def test_missing_plan_chunk_and_completed_reading_return_direct_results(self):
        workspace, _, _ = self._workspace()
        pointers_path = workspace / "pointers.yaml"
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))

        pointers["papers"]["fixture-paper"]["current_plan_id"] = None
        pointers["papers"]["fixture-paper"]["current_chunk_id"] = None
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            missing_plan = FOCUS_GUIDE.main(["present", "--workspace", str(workspace)])
        self.assertEqual(1, missing_plan)
        self.assertEqual("reading_plan_missing", json.loads(stderr.getvalue())["error_id"])

        pointers["papers"]["fixture-paper"]["current_plan_id"] = "plan-001"
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            completed = FOCUS_GUIDE.main(["present", "--workspace", str(workspace)])
        self.assertEqual(0, completed)
        self.assertEqual("reading_completed", json.loads(stdout.getvalue())["status"])

        pointers["papers"]["fixture-paper"]["current_chunk_id"] = "chunk-999"
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            missing_chunk = FOCUS_GUIDE.main(["present", "--workspace", str(workspace)])
        self.assertEqual(1, missing_chunk)
        self.assertEqual("reading_chunk_missing", json.loads(stderr.getvalue())["error_id"])

    def test_continue_advances_exactly_one_chunk_and_new_process_restores_it(self):
        workspace, _, plan = self._workspace()
        chunks_path = plan / "chunks.jsonl"
        records = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
        records[1]["translation"] = "结果证据。"
        chunks_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
        pointers_path = workspace / "pointers.yaml"
        before = json.loads(pointers_path.read_text(encoding="utf-8"))
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            result = FOCUS_GUIDE.main(["continue", "--workspace", str(workspace)])

        self.assertEqual(0, result)
        response = json.loads(stdout.getvalue())
        self.assertEqual("chunk-002", response["chunk_id"])
        self.assertEqual("结果证据。", response["translation"])
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        self.assertEqual("chunk-002", pointers["papers"]["fixture-paper"]["current_chunk_id"])
        self.assertEqual(
            before["papers"]["fixture-paper"]["current_explanation_id"],
            pointers["papers"]["fixture-paper"]["current_explanation_id"],
        )

        pointer_bytes = pointers_path.read_bytes()
        for _ in range(2):
            restored = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", str(GUIDE_SCRIPT), "restore", "--workspace", str(workspace)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(0, restored.returncode, restored.stderr)
            restored_response = json.loads(restored.stdout)
            self.assertEqual(("fixture-paper", "plan-001", "chunk-002"), tuple(restored_response[key] for key in ("paper_id", "plan_id", "chunk_id")))
        self.assertEqual(pointer_bytes, pointers_path.read_bytes())

    def test_uncached_continue_waits_for_translation_before_advancing(self):
        workspace, _, plan = self._workspace()
        pointers_path = workspace / "pointers.yaml"
        pointers_before = pointers_path.read_bytes()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            requested = FOCUS_GUIDE.main(["continue", "--workspace", str(workspace)])

        self.assertEqual(0, requested)
        request = json.loads(stdout.getvalue())
        self.assertEqual("continue_translation_required", request["status"])
        self.assertEqual("chunk-002", request["chunk_id"])
        self.assertEqual(pointers_before, pointers_path.read_bytes())
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())

        translation = self.root / "next-translation.txt"
        translation.write_text("## 结果\n更多证据。", encoding="utf-8")
        stderr = io.StringIO()
        with mock.patch.object(WORKSPACE_CORE, "_replace_text", side_effect=OSError("controlled failure")):
            with contextlib.redirect_stderr(stderr):
                failed = FOCUS_GUIDE.main(
                    ["continue", "--workspace", str(workspace), "--translation-file", str(translation)]
                )
        self.assertEqual(1, failed)
        self.assertEqual("reading_cursor_write_failed", json.loads(stderr.getvalue())["error_id"])
        self.assertEqual(pointers_before, pointers_path.read_bytes())
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            continued = FOCUS_GUIDE.main(
                ["continue", "--workspace", str(workspace), "--translation-file", str(translation)]
            )

        self.assertEqual(0, continued)
        response = json.loads(stdout.getvalue())
        self.assertEqual("chunk-002", response["chunk_id"])
        self.assertEqual("## 结果\n更多证据。", response["translation"])
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        self.assertEqual("chunk-002", pointers["papers"]["fixture-paper"]["current_chunk_id"])

    def test_continue_on_final_chunk_completes_without_resetting_plan(self):
        workspace, _, _ = self._workspace()
        pointers_path = workspace / "pointers.yaml"
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        pointers["papers"]["fixture-paper"]["current_chunk_id"] = "chunk-002"
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = FOCUS_GUIDE.main(["continue", "--workspace", str(workspace)])

        self.assertEqual(0, result)
        self.assertEqual("reading_completed", json.loads(stdout.getvalue())["status"])
        completed = json.loads(pointers_path.read_text(encoding="utf-8"))
        self.assertEqual("plan-001", completed["papers"]["fixture-paper"]["current_plan_id"])
        self.assertIsNone(completed["papers"]["fixture-paper"]["current_chunk_id"])

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(0, FOCUS_GUIDE.main(["present", "--workspace", str(workspace)]))
        self.assertEqual("reading_completed", json.loads(stdout.getvalue())["status"])
        self.assertEqual(completed, json.loads(pointers_path.read_text(encoding="utf-8")))

    def test_switching_current_paper_preserves_each_papers_independent_pointers(self):
        workspace, _, _ = self._workspace()
        self._add_second_paper(workspace)
        pointers_path = workspace / "pointers.yaml"
        before = json.loads(pointers_path.read_text(encoding="utf-8"))

        for paper_id in ("second-paper", "fixture-paper"):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = FOCUS_GUIDE.main(
                    ["switch", "--workspace", str(workspace), "--paper-id", paper_id]
                )
            self.assertEqual(0, result)
            self.assertEqual(paper_id, json.loads(stdout.getvalue())["paper_id"])
            current = json.loads(pointers_path.read_text(encoding="utf-8"))
            self.assertEqual(paper_id, current["current_paper_id"])
            self.assertEqual(before["papers"], current["papers"])

    def test_next_chunk_resolution_failure_leaves_prior_cursor_intact(self):
        workspace, _, plan = self._workspace()
        chunks_path = plan / "chunks.jsonl"
        records = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
        records[1]["chunk_id"] = "broken-next-chunk"
        chunks_path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
        pointers_path = workspace / "pointers.yaml"
        before = pointers_path.read_bytes()
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            result = FOCUS_GUIDE.main(["continue", "--workspace", str(workspace)])

        self.assertEqual(1, result)
        self.assertEqual("reading_plan_invalid", json.loads(stderr.getvalue())["error_id"])
        self.assertEqual(before, pointers_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
