from __future__ import annotations

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
    def test_active_skill_surface_retires_paper_companion(self) -> None:
        retired = ("ask-paper", "paper-map", "paper-study", "paper-assess")
        retained = ("paper-parser", "paper2blog", "focus-map")

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
        tracked = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        prohibited = [
            path
            for path in tracked
            if path.startswith("workspace/")
            or (path.lower().endswith(".pdf") and not path.startswith("tests/fixtures/"))
        ]

        self.assertEqual([], prohibited)

    def test_synthetic_fixtures_remain_trackable(self) -> None:
        candidate = ROOT / "tests" / "fixtures" / "synthetic-paper.pdf"
        self.assertFalse(is_git_ignored(candidate))


if __name__ == "__main__":
    unittest.main()
