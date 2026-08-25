from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"


def is_git_ignored(candidate: Path) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "--quiet", str(candidate)],
        cwd=ROOT,
        check=False,
    )
    return completed.returncode == 0


class RepositoryBoundaryTests(unittest.TestCase):
    @staticmethod
    def _tracked_paths():
        return subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()

    def test_active_skill_surface_retires_paper_companion(self) -> None:
        retired = ("ask-paper", "paper-map", "paper-study", "paper-assess")
        retained = ("paper-parser", "paper2blog", "focus-map", "focus-guide", "focus-explain")

        for skill_name in retired:
            with self.subTest(skill=skill_name):
                skill_root = SKILLS / skill_name
                self.assertFalse((skill_root / "SKILL.md").exists())
                self.assertFalse(any(skill_root.rglob("*.py")))

        for skill_name in retained:
            with self.subTest(skill=skill_name):
                self.assertTrue((SKILLS / skill_name / "SKILL.md").is_file())

    def test_private_workspace_root_is_ignored(self) -> None:
        candidate = ROOT / "workspace" / "pointers.yaml"
        self.assertTrue(is_git_ignored(candidate))

    def test_private_workspace_artifacts_are_not_tracked(self) -> None:
        tracked = self._tracked_paths()
        private_filenames = {"pointers.yaml", "chunks.jsonl", "glossary.tsv"}
        prohibited = [
            path
            for path in tracked
            if path.startswith("workspace/")
            or (path.lower().endswith(".pdf") and not path.startswith("tests/fixtures/"))
            or re.search(r"(^|/)papers/[^/]+/(parser-bundle|blog|reading)(/|$)", path)
            or Path(path).name in private_filenames
            or re.fullmatch(r"explanation-\d+\.jsonl", Path(path).name)
            or Path(path).name == ".env"
            or Path(path).suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
        ]

        self.assertEqual([], prohibited)

    def test_tracked_text_contains_no_live_credentials_or_signed_urls(self) -> None:
        findings = []
        long_token = re.compile(r"MINERU_API_TOKEN\s*=\s*[A-Za-z0-9_-]{24,}")
        signed_url = re.compile(
            r"https://(?![^/]*(?:example|example\.test)(?:/|$))[^\s\"']+"
            r"(?:X-Amz-Signature|signature|token)=[A-Za-z0-9%_-]{16,}",
            re.IGNORECASE,
        )
        for relative in self._tracked_paths():
            path = ROOT / relative
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if long_token.search(content) or signed_url.search(content):
                findings.append(relative)
        self.assertEqual([], findings)

    def test_active_python_surface_contains_no_retired_learning_or_hash_runtime(self) -> None:
        forbidden = re.compile(
            r"\b(?:Scout|Study|Mastery|assessment|cognitive[_ -]?profile|retention|"
            r"ask-paper|paper-study|paper-assess|content[_ -]?hash|hashlib|sha256)\b",
            re.IGNORECASE,
        )
        findings = []
        roots = (ROOT / ".agents", ROOT / "tests")
        for root in roots:
            for path in root.rglob("*.py"):
                if path.name == "test_repository_boundaries.py":
                    continue
                if forbidden.search(path.read_text(encoding="utf-8")):
                    findings.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], findings)

    def test_synthetic_fixtures_remain_trackable(self) -> None:
        candidate = ROOT / "tests" / "fixtures" / "synthetic-paper.pdf"
        self.assertFalse(is_git_ignored(candidate))


if __name__ == "__main__":
    unittest.main()
