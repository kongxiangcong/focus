from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READER_UI = ROOT / "ui" / "packages" / "reader-ui"


class ReaderUiBoundaryTests(unittest.TestCase):
    def test_reader_ui_depends_only_on_contracts_and_react(self) -> None:
        package = (READER_UI / "package.json").read_text(encoding="utf-8")
        self.assertIn('"@focus/reader-contracts"', package)
        self.assertIn('"react"', package)
        self.assertNotIn('"@focus/standalone"', package)
        self.assertNotIn('"@deepseek', package)

    def test_reader_ui_contains_no_host_or_workspace_imports(self) -> None:
        prohibited = re.compile(
            r"from\s+[\"'](?:node:|.*(?:standalone|adapters|workspace|deepseek|dsh))",
            re.IGNORECASE,
        )
        findings = []
        for path in (READER_UI / "src").rglob("*"):
            if path.suffix not in {".ts", ".tsx"} or path.name.endswith(".test.tsx"):
                continue
            if prohibited.search(path.read_text(encoding="utf-8")):
                findings.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], findings)

    def test_visual_prototype_has_not_been_started(self) -> None:
        prototype_markers = [
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "ui").rglob("*")
            if path.is_file() and re.search(r"(?:variant-[a-z]|prototype-switcher)", path.name, re.IGNORECASE)
        ]
        self.assertEqual([], prototype_markers)


if __name__ == "__main__":
    unittest.main()
