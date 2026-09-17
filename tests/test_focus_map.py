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


FOCUS_MAP = load_module(
    "focus_map_cli",
    ROOT / ".agents" / "skills" / "focus-map" / "scripts" / "focus_map.py",
)
WORKSPACE_CORE = importlib.import_module("core.reading_workspace")


class FocusMapTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"focus-map-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _workspace(self):
        workspace = self.root / "workspace"
        source_root = workspace / "sources" / "Fixture-paper"
        bundle = source_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (source_root / "source.yaml").write_text(
            json.dumps({"source_id": "Fixture-paper", "source_kind": "paper_pdf", "title": "Fixture Paper", "short_name": "Fixture", "identity": "fixture:paper"}),
            encoding="utf-8",
        )
        lines = [
            "# Fixture Paper",
            "",
            "## Method",
            "The array keeps source order.",
            "",
            "| Module | Role |",
            "|---|---|",
            "| Array | Compute |",
            "",
            "$$",
            "y = Wx",
            "$$",
            "",
            "![Architecture](images/image-001.png)",
            "Figure 1: Architecture overview.",
            "",
            "## Results",
            "Evidence.",
        ]
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "content.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"source_kind":"paper_pdf","language":"en","parser":"paper-parser","batch_id":"fixture-batch"}\n', encoding="utf-8"
        )
        (bundle / "validation.json").write_text('{"ok":true}\n', encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(b"image")
        (workspace / "state.json").write_text(
            json.dumps(
                {
                    "current_source_id": "Fixture-paper",
                    "current_topic_id": None,
                    "sources": {"Fixture-paper": {"current_plan_id": None, "current_chunk_id": None}},
                }
            ),
            encoding="utf-8",
        )
        return workspace, source_root

    def _draft(self, chunks=None):
        return json.dumps(
                {
                    "chunks": chunks
                    or [
                        {"section_path": ["Fixture Paper", "Method"], "source_lines": [1, 5], "images": []},
                        {"section_path": ["Fixture Paper", "Method"], "source_lines": [6, 8], "images": []},
                        {"section_path": ["Fixture Paper", "Method"], "source_lines": [9, 13], "images": []},
                        {
                            "section_path": ["Fixture Paper", "Method"],
                            "source_lines": [14, 16],
                            "images": ["images/image-001.png"],
                        },
                        {"section_path": ["Fixture Paper", "Results"], "source_lines": [17, 18], "images": []},
                    ],
                    "glossary": [["array", "阵列"], ["source order", "源顺序"]],
                },
                ensure_ascii=False,
        )

    def _map(self, workspace: Path, *extra: str, draft: str = ""):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), mock.patch("sys.stdin", io.StringIO(draft)):
            result = FOCUS_MAP.main(
                ["map", "--workspace", str(workspace), "--source-id", "Fixture-paper", *extra]
            )
        return result, json.loads(stdout.getvalue())

    def test_map_installs_fixed_chunks_records_glossary_and_cursor_state(self):
        workspace, source_root = self._workspace()
        result, response = self._map(workspace, draft=self._draft())

        self.assertEqual(0, result)
        self.assertEqual(("plan-001", "chunk-001"), (response["plan_id"], response["chunk_id"]))
        plan = source_root / "reading" / "plans" / "plan-001"
        chunks = [json.loads(line) for line in (plan / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual({"chunk_id", "index", "section_path", "source_lines", "images"}, set(chunks[0]))
        self.assertEqual([1, 2, 3, 4, 5], [chunk["index"] for chunk in chunks])
        self.assertEqual("array\t阵列\nsource order\t源顺序\n", (plan / "glossary.tsv").read_text(encoding="utf-8"))
        for chunk in chunks:
            record = json.loads((plan / "records" / f'{chunk["chunk_id"]}.json').read_text(encoding="utf-8"))
            self.assertEqual({"chunk_id": chunk["chunk_id"], "translation": None, "notes": []}, record)
        state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {"current_plan_id": "plan-001", "current_chunk_id": "chunk-001", "reading_started": False},
            state["sources"]["Fixture-paper"],
        )

    def test_repeated_map_reuses_current_plan_without_resetting_cursor(self):
        workspace, source_root = self._workspace()
        self._map(workspace, draft=self._draft())
        state_path = workspace / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["sources"]["Fixture-paper"]["current_chunk_id"] = "chunk-003"
        state_path.write_text(json.dumps(state), encoding="utf-8")

        result, response = self._map(workspace)

        self.assertEqual(0, result)
        self.assertTrue(response["reused"])
        self.assertEqual("chunk-003", response["chunk_id"])
        self.assertEqual(["plan-001"], [path.name for path in (source_root / "reading" / "plans").iterdir()])

    def test_reinitialize_preserves_old_plan_and_records_before_selecting_new_plan(self):
        workspace, source_root = self._workspace()
        self._map(workspace, draft=self._draft())
        old_plan = source_root / "reading" / "plans" / "plan-001"
        old_record = old_plan / "records" / "chunk-001.json"
        old_record.write_text(
            json.dumps(
                {
                    "chunk_id": "chunk-001",
                    "translation": "旧译文",
                    "notes": [{"kind": "thought", "origin": "user", "content": "旧思考"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        old_snapshot = {path.relative_to(old_plan): path.read_bytes() for path in old_plan.rglob("*") if path.is_file()}

        result, response = self._map(
            workspace,
            "--reinitialize",
            draft=self._draft(),
        )

        self.assertEqual(0, result)
        self.assertEqual("plan-002", response["plan_id"])
        self.assertTrue(response["reinitialized"])
        self.assertEqual(
            old_snapshot,
            {path.relative_to(old_plan): path.read_bytes() for path in old_plan.rglob("*") if path.is_file()},
        )
        new_record = json.loads(
            (source_root / "reading" / "plans" / "plan-002" / "records" / "chunk-001.json").read_text(encoding="utf-8")
        )
        self.assertEqual({"chunk_id": "chunk-001", "translation": None, "notes": []}, new_record)

    def test_failed_state_install_removes_new_plan_and_preserves_old_selection(self):
        workspace, source_root = self._workspace()
        self._map(workspace, draft=self._draft())
        state_before = (workspace / "state.json").read_bytes()
        old_plan = source_root / "reading" / "plans" / "plan-001"
        old_before = {path.relative_to(old_plan): path.read_bytes() for path in old_plan.rglob("*") if path.is_file()}

        original = WORKSPACE_CORE._write_document

        def fail_state(path, value):
            if path.name == "state.json":
                raise OSError("controlled failure")
            return original(path, value)

        stderr = io.StringIO()
        with mock.patch.object(WORKSPACE_CORE, "_write_document", side_effect=fail_state):
            with contextlib.redirect_stderr(stderr), mock.patch("sys.stdin", io.StringIO(self._draft())):
                result = FOCUS_MAP.main(
                    [
                        "map",
                        "--workspace",
                        str(workspace),
                        "--source-id",
                        "Fixture-paper",
                        "--reinitialize",
                    ]
                )

        self.assertEqual(1, result)
        self.assertEqual(state_before, (workspace / "state.json").read_bytes())
        self.assertEqual(["plan-001"], sorted(path.name for path in old_plan.parent.iterdir()))
        self.assertEqual(old_before, {path.relative_to(old_plan): path.read_bytes() for path in old_plan.rglob("*") if path.is_file()})

    def test_mapping_rejects_split_protected_unit_without_changing_state(self):
        workspace, source_root = self._workspace()
        before = (workspace / "state.json").read_bytes()
        split_table = [
            {"section_path": ["Fixture Paper", "Method"], "source_lines": [1, 6], "images": []},
            {
                "section_path": ["Fixture Paper", "Method"],
                "source_lines": [7, 18],
                "images": ["images/image-001.png"],
            },
        ]
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), mock.patch("sys.stdin", io.StringIO(self._draft(split_table))):
            result = FOCUS_MAP.main(
                [
                    "map",
                    "--workspace",
                    str(workspace),
                    "--source-id",
                    "Fixture-paper",
                ]
            )

        self.assertEqual(1, result)
        self.assertEqual("reading_plan_invalid", json.loads(stderr.getvalue())["error_id"])
        self.assertEqual(before, (workspace / "state.json").read_bytes())
        self.assertFalse((source_root / "reading" / "plans").exists())

    def test_reuse_rejects_old_plan_shape_instead_of_converting_it(self):
        workspace, source_root = self._workspace()
        self._map(workspace, draft=self._draft())
        chunks_path = source_root / "reading" / "plans" / "plan-001" / "chunks.jsonl"
        chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
        chunks[0]["translation"] = "旧结构译文"
        chunks[0]["notes"] = []
        chunks_path.write_text(
            "".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks),
            encoding="utf-8",
        )
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            result = FOCUS_MAP.main(
                ["map", "--workspace", str(workspace), "--source-id", "Fixture-paper"]
            )

        self.assertEqual(1, result)
        self.assertEqual("reading_plan_invalid", json.loads(stderr.getvalue())["error_id"])
        self.assertEqual(["plan-001"], [path.name for path in chunks_path.parent.parent.iterdir()])


if __name__ == "__main__":
    unittest.main()
