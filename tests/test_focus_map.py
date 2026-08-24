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
    "focus_map_cli",
    ROOT / ".agents" / "skills" / "focus-map" / "scripts" / "focus_map.py",
)


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
        paper_root = workspace / "papers" / "fixture-paper"
        bundle = paper_root / "parser-bundle"
        (bundle / "images").mkdir(parents=True)
        (paper_root / "paper.yaml").write_text(
            json.dumps({"paper_id": "fixture-paper", "title": "Fixture Paper", "topics": ["systems"]}),
            encoding="utf-8",
        )
        lines = [
            "# Fixture Paper",
            "",
            "## Method",
            "The design keeps source order.",
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
        (bundle / "paper.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (bundle / "metadata.json").write_text(
            '{"parser": "mineru-precision-api"}\n', encoding="utf-8"
        )
        (bundle / "validation.json").write_text('{"ok": true}\n', encoding="utf-8")
        (bundle / "images" / "image-001.png").write_bytes(b"image")
        (workspace / "pointers.yaml").write_text(
            json.dumps(
                {
                    "current_paper_id": "fixture-paper",
                    "papers": {
                        "fixture-paper": {
                            "current_plan_id": None,
                            "current_chunk_id": None,
                            "current_explanation_id": None,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return workspace, paper_root

    def _draft(self, chunks=None):
        draft = self.root / f"draft-{uuid.uuid4().hex}.json"
        draft.write_text(
            json.dumps(
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
            ),
            encoding="utf-8",
        )
        return draft

    def test_first_map_installs_ordered_source_anchored_plan_then_selects_first_chunk(self):
        workspace, paper_root = self._workspace()
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            result = FOCUS_MAP.main(
                [
                    "map",
                    "--workspace",
                    str(workspace),
                    "--paper-id",
                    "fixture-paper",
                    "--scope",
                    "main text",
                    "--draft",
                    str(self._draft()),
                ]
            )

        self.assertEqual(0, result)
        response = json.loads(stdout.getvalue())
        self.assertEqual("plan-001", response["plan_id"])
        self.assertEqual("chunk-001", response["chunk_id"])
        self.assertFalse(response["reused"])
        plan = paper_root / "reading" / "plans" / "plan-001"
        records = [json.loads(line) for line in (plan / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([f"chunk-{index:03d}" for index in range(1, 6)], [row["chunk_id"] for row in records])
        self.assertEqual([1, 2, 3, 4, 5], [row["index"] for row in records])
        self.assertEqual([[1, 5], [6, 8], [9, 13], [14, 16], [17, 18]], [row["source_lines"] for row in records])
        self.assertEqual(["images/image-001.png"], records[3]["images"])
        self.assertTrue(all(row["translation"] is None and row["notes"] == [] for row in records))
        self.assertEqual("array\t阵列\nsource order\t源顺序\n", (plan / "glossary.tsv").read_text(encoding="utf-8"))
        pointers = json.loads((workspace / "pointers.yaml").read_text(encoding="utf-8"))
        self.assertEqual("plan-001", pointers["papers"]["fixture-paper"]["current_plan_id"])
        self.assertEqual("chunk-001", pointers["papers"]["fixture-paper"]["current_chunk_id"])

    def test_repeated_map_reuses_plan_without_reading_draft_or_resetting_cursor(self):
        workspace, _ = self._workspace()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                0,
                FOCUS_MAP.main(
                    ["map", "--workspace", str(workspace), "--paper-id", "fixture-paper", "--draft", str(self._draft())]
                ),
            )
        pointers_path = workspace / "pointers.yaml"
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        pointers["papers"]["fixture-paper"]["current_chunk_id"] = "chunk-003"
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = FOCUS_MAP.main(
                ["map", "--workspace", str(workspace), "--paper-id", "fixture-paper"]
            )

        self.assertEqual(0, result)
        self.assertTrue(json.loads(stdout.getvalue())["reused"])
        restored = json.loads(pointers_path.read_text(encoding="utf-8"))
        self.assertEqual("chunk-003", restored["papers"]["fixture-paper"]["current_chunk_id"])
        self.assertEqual(["plan-001"], [path.name for path in (workspace / "papers" / "fixture-paper" / "reading" / "plans").iterdir()])

    def test_mapping_rejects_split_source_units_without_changing_pointers(self):
        workspace, paper_root = self._workspace()
        before = (workspace / "pointers.yaml").read_bytes()
        split_cases = {
            "table": [
                {"section_path": ["Method"], "source_lines": [1, 6], "images": []},
                {"section_path": ["Method"], "source_lines": [7, 18], "images": ["images/image-001.png"]},
            ],
            "equation": [
                {"section_path": ["Method"], "source_lines": [1, 10], "images": []},
                {"section_path": ["Method"], "source_lines": [11, 18], "images": ["images/image-001.png"]},
            ],
            "image-caption": [
                {"section_path": ["Method"], "source_lines": [1, 14], "images": ["images/image-001.png"]},
                {"section_path": ["Results"], "source_lines": [15, 18], "images": []},
            ],
        }

        for protected_unit, chunks in split_cases.items():
            with self.subTest(protected_unit=protected_unit):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = FOCUS_MAP.main(
                        ["map", "--workspace", str(workspace), "--paper-id", "fixture-paper", "--draft", str(self._draft(chunks))]
                    )
                self.assertEqual(1, result)
                self.assertEqual("reading_plan_invalid", json.loads(stderr.getvalue())["error_id"])
                self.assertEqual(before, (workspace / "pointers.yaml").read_bytes())
                self.assertFalse((paper_root / "reading" / "plans").exists())

    def test_mapping_rejects_section_path_that_is_not_anchored_to_source_headings(self):
        workspace, paper_root = self._workspace()
        before = (workspace / "pointers.yaml").read_bytes()
        chunks = [
            {"section_path": ["Invented", "Section"], "source_lines": [1, 18], "images": ["images/image-001.png"]}
        ]
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            result = FOCUS_MAP.main(
                ["map", "--workspace", str(workspace), "--paper-id", "fixture-paper", "--draft", str(self._draft(chunks))]
            )

        self.assertEqual(1, result)
        self.assertEqual("reading_plan_invalid", json.loads(stderr.getvalue())["error_id"])
        self.assertEqual(before, (workspace / "pointers.yaml").read_bytes())
        self.assertFalse((paper_root / "reading" / "plans").exists())

    def test_missing_paper_and_parser_bundle_return_structured_errors(self):
        workspace, paper_root = self._workspace()
        cases = [("missing-paper", "paper_missing")]
        (paper_root / "parser-bundle").rename(paper_root / "missing-bundle")
        cases.append(("fixture-paper", "parser_bundle_missing"))

        for paper_id, expected in cases:
            with self.subTest(error_id=expected):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = FOCUS_MAP.main(
                        ["map", "--workspace", str(workspace), "--paper-id", paper_id, "--draft", str(self._draft())]
                    )
                self.assertEqual(1, result)
                self.assertEqual(expected, json.loads(stderr.getvalue())["error_id"])

        (paper_root / "missing-bundle").rename(paper_root / "parser-bundle")
        (paper_root / "parser-bundle" / "validation.json").write_text('{"ok": false}\n', encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = FOCUS_MAP.main(
                ["map", "--workspace", str(workspace), "--paper-id", "fixture-paper", "--draft", str(self._draft())]
            )
        self.assertEqual(1, result)
        self.assertEqual("parser_bundle_invalid", json.loads(stderr.getvalue())["error_id"])


if __name__ == "__main__":
    unittest.main()
