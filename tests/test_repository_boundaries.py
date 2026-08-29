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

    def test_active_skill_surface_contains_only_five_public_skills(self) -> None:
        active = sorted(
            path.parent.name for path in SKILLS.glob("*/SKILL.md") if path.is_file()
        )
        self.assertEqual(["article-parser", "focus-map", "focus-read", "paper-parser", "paper2blog"], active)

    def test_article_parser_has_no_publisher_or_capture_adapter(self) -> None:
        script = (SKILLS / "article-parser" / "scripts" / "article_parser.py").read_text(encoding="utf-8")
        prohibited = re.compile(r"zhihu|wechat|weixin|mhtml|playwright|selenium|print[-_ ]?pdf", re.IGNORECASE)
        self.assertIsNone(prohibited.search(script))

    def test_private_workspace_root_is_ignored(self) -> None:
        candidate = ROOT / "workspace" / "state.json"
        self.assertTrue(is_git_ignored(candidate))

    def test_private_workspace_artifacts_are_not_tracked(self) -> None:
        tracked = self._tracked_paths()
        private_filenames = {"state.json", "chunks.jsonl", "glossary.tsv"}
        prohibited = [
            path
            for path in tracked
            if path.startswith("workspace/")
            or (path.lower().endswith(".pdf") and not path.startswith("tests/fixtures/"))
            or re.search(r"(^|/)papers/[^/]+/(parser-bundle|blog|reading)(/|$)", path)
            or Path(path).name in private_filenames
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

    def test_active_surface_contains_no_retired_modes_learning_or_hash_runtime(self) -> None:
        retired_names = (
            "focus" + "-guide",
            "focus" + "-explain",
            "Explanation" + "WorkspaceCore",
            "current" + "_explanation_id",
            "Continue" + " Explanation",
            "Explanation" + " Session",
        )
        retired = re.compile(
            r"\b(?:" + "|".join(re.escape(name) for name in retired_names) + r")\b",
            re.IGNORECASE,
        )
        python_only = re.compile(
            r"\b(?:Scout|Study|Mastery|assessment|cognitive[_ -]?profile|retention|"
            r"ask-paper|paper-study|paper-assess|content[_ -]?hash|hashlib|sha256)\b",
            re.IGNORECASE,
        )
        findings = []
        roots = (ROOT / ".agents", ROOT / "tests", ROOT / "README.md", ROOT / "CONTEXT.md")
        for root in roots:
            paths = root.rglob("*") if root.is_dir() else (root,)
            for path in paths:
                if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".yaml"}:
                    continue
                if path.name == "test_repository_boundaries.py":
                    continue
                content = path.read_text(encoding="utf-8")
                if retired.search(content) or (path.suffix.lower() == ".py" and python_only.search(content)):
                    findings.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], findings)

    def test_synthetic_fixtures_remain_trackable(self) -> None:
        candidate = ROOT / "tests" / "fixtures" / "synthetic-paper.pdf"
        self.assertFalse(is_git_ignored(candidate))

    def test_replaced_source_and_mapping_contracts_have_no_legacy_surface(self) -> None:
        tracked_surface = [
            *ROOT.joinpath(".agents").rglob("*.py"),
            *ROOT.joinpath(".agents").rglob("SKILL.md"),
            *ROOT.joinpath("docs").rglob("*.md"),
        ]
        forbidden = (
            "--authorize-" + "upload",
            "--authorize-" + "cloud-fetch",
            "--" + "draft",
            '"topics": [',
        )
        findings = []
        for path in tracked_surface:
            text = path.read_text(encoding="utf-8")
            if any(value in text for value in forbidden):
                findings.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], findings)


if __name__ == "__main__":
    unittest.main()
