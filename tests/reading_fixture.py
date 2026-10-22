"""Synthetic Reading Workspace shared by Core and Host tests.

The fixture writes the same on-disk shape the product uses: one registered
Paper Source with a Parser Bundle, a three-chunk Reading Plan, a Plan Glossary
and Cursor State. Tests drive `core.WorkspaceCore` directly; the retired skill
CLIs are not involved.
"""
from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / ".agents") not in sys.path:
    sys.path.insert(0, str(ROOT / ".agents"))


class ReadingFixture:
    """Own a temporary Workspace root and build its fixture data."""

    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"reading-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

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
        (bundle / "metadata.json").write_text('{"source_kind":"paper_pdf","language":"en","parser":"article-parser","batch_id":"fixture-batch"}\n', encoding="utf-8")
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

    def _text(self, name: str, value: str) -> Path:
        path = self.root / name
        path.write_text(value, encoding="utf-8")
        return path

    @staticmethod
    def core(workspace: Path):
        """Return the Workspace Core for this fixture without any CLI indirection."""
        from core.reading_workspace import WorkspaceCore

        return WorkspaceCore(workspace)
