"""Independent Runtime capability, verified on its own boundary.

These tests never touch default ingestion: they assert the bounded inspection
contract (read-only, ephemeral, bounded excerpt, no tools) and that a candidate
without figures is inspected without one. No real Codex process is started; the
transport seam below the adapter is replaced with a recording double.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from host.codex_ingestion import CodexIngestionRuntime


class RecordingCodex:
    """Stands in for the Codex CLI: records the command and writes the result file."""

    def __init__(self, result=None, returncode=0) -> None:
        self.commands: list[list[str]] = []
        self.attached: list[tuple[Path, bool, Path, bool]] = []
        self.returncode = returncode
        self.result = result if result is not None else {
            "title_matches": True, "image_observed": False, "notes": "no figure attached",
        }

    def __call__(self, command, **kwargs):
        command = list(command)
        self.commands.append(command)
        if "--image" in command:
            image = Path(command[command.index("--image") + 1])
            schema = Path(command[command.index("--output-schema") + 1])
            # Observed at call time: the isolated directory is removed afterwards.
            self.attached.append((image, image.is_file(), schema.parent, schema.is_file()))
        Path(command[command.index("--output-last-message") + 1]).write_text(
            json.dumps(self.result), encoding="utf-8"
        )
        process = MagicMock()
        process.returncode = self.returncode
        process.communicate.return_value = ("", "")
        process.poll.return_value = 0
        return process


class IngestionRuntimeCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.binary = self.root / "codex-fixture"
        self.binary.write_bytes(b"fixture")
        self.runtime = CodexIngestionRuntime(self.binary, model="fixture-model")

    def tearDown(self):
        self.temporary.cleanup()

    def candidate(self, *, images: int = 0) -> Path:
        bundle = self.root / "candidate"
        bundle.mkdir(exist_ok=True)
        (bundle / "source.pdf").write_bytes(b"%PDF-1.4\npaper\n")
        (bundle / "content.md").write_text("# Stored Paper\n\nBody.\n", encoding="utf-8")
        (bundle / "metadata.json").write_text(
            json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "article-parser",
                        "batch_id": "fixture-batch"}),
            encoding="utf-8",
        )
        for index in range(1, images + 1):
            (bundle / "images").mkdir(exist_ok=True)
            (bundle / "images" / f"image-{index:03d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        return bundle

    def test_missing_binary_and_invalid_candidates_never_reach_the_runtime(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            CodexIngestionRuntime(self.root / "absent", model="fixture-model")

        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(RuntimeError, "inspection inputs"):
            self.runtime.inspect(empty)

        untitled = self.candidate()
        (untitled / "content.md").write_text("Body without a title.\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "inspectable title"):
            self.runtime.inspect(untitled)

        wrong_provenance = self.candidate()
        (wrong_provenance / "metadata.json").write_text(
            json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "other"}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "provenance"):
            self.runtime.inspect(wrong_provenance)

    def test_inspection_is_bounded_and_does_not_require_a_figure(self):
        codex = RecordingCodex()
        with patch("host.codex_ingestion.subprocess.Popen", codex):
            result = self.runtime.inspect(self.candidate())

        self.assertEqual(
            {"title_matches": True, "image_observed": False, "notes": "no figure attached"}, result
        )
        command = codex.commands[0]
        self.assertNotIn("--image", command)
        self.assertEqual(str(self.binary), command[0])
        for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check"):
            self.assertIn(flag, command)
        self.assertEqual("read-only", command[command.index("--sandbox") + 1])
        self.assertEqual("fixture-model", command[command.index("-m") + 1])
        self.assertEqual("-", command[-1])

    def test_existing_figure_is_attached_within_the_isolated_directory(self):
        codex = RecordingCodex({"title_matches": True, "image_observed": True, "notes": "figure"})
        with patch("host.codex_ingestion.subprocess.Popen", codex):
            result = self.runtime.inspect(self.candidate(images=1))

        self.assertTrue(result["image_observed"])
        command = codex.commands[0]
        self.assertEqual(str(self.binary), command[0])
        image, existed, isolated, schema_existed = codex.attached[0]
        self.assertTrue(existed)
        self.assertTrue(schema_existed)
        self.assertTrue(image.parent == isolated)
        self.assertNotIn(self.root, image.parents)
        self.assertEqual("-", command[-1])

    def test_runtime_failures_are_reported_instead_of_silently_accepted(self):
        with patch("host.codex_ingestion.subprocess.Popen", RecordingCodex(returncode=3)):
            with self.assertRaisesRegex(RuntimeError, "exit code 3"):
                self.runtime.inspect(self.candidate())

        with patch("host.codex_ingestion.subprocess.Popen",
                   RecordingCodex({"title_matches": True, "image_observed": False})):
            with self.assertRaisesRegex(RuntimeError, "result shape is invalid"):
                self.runtime.inspect(self.candidate())

    def test_cancel_without_a_running_process_reports_no_stop(self):
        self.assertFalse(self.runtime.cancel())


if __name__ == "__main__":
    unittest.main()
