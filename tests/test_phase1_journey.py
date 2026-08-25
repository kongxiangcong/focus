from __future__ import annotations

import contextlib
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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PARSER = load_module(
    "journey_parser",
    ROOT / ".agents" / "skills" / "paper-parser" / "scripts" / "mineru_precision.py",
)
BLOG = load_module(
    "journey_blog",
    ROOT / ".agents" / "skills" / "paper2blog" / "scripts" / "paper2blog.py",
)
FOCUS_MAP = load_module(
    "journey_map",
    ROOT / ".agents" / "skills" / "focus-map" / "scripts" / "focus_map.py",
)
FOCUS_GUIDE = load_module(
    "journey_guide",
    ROOT / ".agents" / "skills" / "focus-guide" / "scripts" / "focus_guide.py",
)
FOCUS_EXPLAIN = load_module(
    "journey_explain",
    ROOT / ".agents" / "skills" / "focus-explain" / "scripts" / "focus_explain.py",
)
GUIDE_SCRIPT = ROOT / ".agents" / "skills" / "focus-guide" / "scripts" / "focus_guide.py"
EXPLAIN_SCRIPT = ROOT / ".agents" / "skills" / "focus-explain" / "scripts" / "focus_explain.py"


class Phase1JourneyTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"phase1-journey-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    @staticmethod
    def _invoke(module, argv):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = module.main(argv)
        return result, json.loads(stdout.getvalue())

    @staticmethod
    def _invoke_error(module, argv):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = module.main(argv)
        return result, json.loads(stderr.getvalue())

    @staticmethod
    def _reading_snapshot(paper_root: Path):
        reading = paper_root / "reading"
        return {
            path.relative_to(reading).as_posix(): path.read_bytes()
            for path in reading.rglob("*")
            if path.is_file()
        }

    @staticmethod
    def _paper_cursor(workspace: Path, paper_id: str = "synthetic-systems-paper"):
        pointers = json.loads((workspace / "pointers.yaml").read_text(encoding="utf-8"))
        return pointers["papers"][paper_id]["current_chunk_id"]

    def _draft(self, name: str, glossary: str):
        path = self.root / name
        path.write_text(
            json.dumps(
                {
                    "chunks": [
                        {
                            "section_path": ["Synthetic Systems Paper", "Method"],
                            "source_lines": [1, 7],
                            "images": ["images/image-001.png"],
                        },
                        {
                            "section_path": ["Synthetic Systems Paper", "Results"],
                            "source_lines": [8, 12],
                            "images": [],
                        },
                    ],
                    "glossary": [["ACT layout", glossary]],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_complete_deterministic_private_workspace_journey(self):
        source = self.root / "synthetic-paper.pdf"
        source.write_bytes(b"%PDF-1.4\nsynthetic phase 1 fixture\n")
        workspace = self.root / "workspace"
        workspace.mkdir()

        class HostedParserFixture:
            def start(self, source, *, model, language, ocr):
                return "batch-phase1-journey"

            def complete(self, source, output, *, batch_id, **kwargs):
                (output / "images").mkdir(parents=True)
                shutil.copy2(source, output / "source.pdf")
                (output / "paper.md").write_text(
                    "# Synthetic Systems Paper\n\n"
                    "## Method\nThe ACT layout moves data between adjacent units.\n"
                    "![Architecture](images/image-001.png)\n"
                    "Figure 1: ACT architecture.\n\n"
                    "## Results\n| Metric | Value |\n|---|---|\n| Throughput | 2.0 |\n"
                    "The result supports the mechanism.\n",
                    encoding="utf-8",
                )
                (output / "images" / "image-001.png").write_bytes(b"image")
                (output / "metadata.json").write_text(
                    json.dumps(
                        {
                            "title": "Synthetic Systems Paper",
                            "parser": "mineru-precision-api",
                            "batch_id": batch_id,
                        }
                    ),
                    encoding="utf-8",
                )
                (output / "validation.json").write_text('{"ok":true}\n', encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = PARSER.main(
                [
                    "parse",
                    str(source),
                    "--workspace",
                    str(workspace),
                    "--title",
                    "Synthetic Systems Paper",
                    "--topic",
                    "Dataflow Systems",
                    "--authorize-upload",
                ],
                hosted=HostedParserFixture(),
            )
        parsed = json.loads(stdout.getvalue().splitlines()[-1])
        self.assertEqual(0, result)
        self.assertEqual("synthetic-systems-paper", parsed["paper_id"])
        paper_root = workspace / "papers" / parsed["paper_id"]

        result, mapped = self._invoke(
            FOCUS_MAP,
            [
                "map",
                "--workspace",
                str(workspace),
                "--paper-id",
                parsed["paper_id"],
                "--draft",
                str(self._draft("plan-001.json", "ACT 布局")),
            ],
        )
        self.assertEqual(0, result)
        self.assertEqual(("plan-001", "chunk-001"), (mapped["plan_id"], mapped["chunk_id"]))

        translation_one = self.root / "translation-001.txt"
        translation_one.write_text("# 合成系统论文\n\n## 方法\nACT 布局在相邻单元之间移动数据。", encoding="utf-8")
        self.assertEqual(
            0,
            self._invoke(
                FOCUS_GUIDE,
                ["present", "--workspace", str(workspace), "--translation-file", str(translation_one)],
            )[0],
        )
        cursor_before_notes = self._paper_cursor(workspace)
        reader_note = self.root / "reader-note.txt"
        question = self.root / "discussion-question.txt"
        discussion_answer = self.root / "discussion-answer.txt"
        emphasis = self.root / "emphasis.txt"
        reader_note.write_text("对照图 1 检查相邻单元。", encoding="utf-8")
        question.write_text("ACT 指什么？", encoding="utf-8")
        discussion_answer.write_text("ACT 指论文中的数据布局。", encoding="utf-8")
        emphasis.write_text("数据只在相邻单元之间移动。", encoding="utf-8")
        note_operations = [
            ["save-note", "--workspace", str(workspace), "--content-file", str(reader_note)],
            [
                "record-discussion",
                "--workspace",
                str(workspace),
                "--question-file",
                str(question),
                "--answer-file",
                str(discussion_answer),
            ],
            ["emphasize", "--workspace", str(workspace), "--content-file", str(emphasis)],
        ]
        for operation in note_operations:
            self.assertEqual(0, self._invoke(FOCUS_GUIDE, operation)[0])
            self.assertEqual(cursor_before_notes, self._paper_cursor(workspace))

        translation_two = self.root / "translation-002.txt"
        translation_two.write_text("## 结果\n吞吐量结果支持该机制。", encoding="utf-8")
        self.assertEqual(
            0,
            self._invoke(
                FOCUS_GUIDE,
                ["continue", "--workspace", str(workspace), "--translation-file", str(translation_two)],
            )[0],
        )
        self.assertEqual("chunk-002", self._paper_cursor(workspace))

        explanation_question = self.root / "explanation-question.txt"
        explanation_answer = self.root / "explanation-answer.txt"
        explanation_query = self.root / "explanation-query.txt"
        explanation_question.write_text("ACT layout 为什么有效？", encoding="utf-8")
        explanation_answer.write_text("它通过局部相邻传递减少全局搬运。", encoding="utf-8")
        explanation_query.write_text("ACT layout adjacent", encoding="utf-8")
        chunks_before_explanation = (paper_root / "reading" / "plans" / "plan-001" / "chunks.jsonl").read_bytes()
        cursor_before_explanation = self._paper_cursor(workspace)
        self.assertEqual(
            0,
            self._invoke(
                FOCUS_EXPLAIN,
                ["new", "--workspace", str(workspace), "--question-file", str(explanation_question)],
            )[0],
        )
        research = self._invoke(
            FOCUS_EXPLAIN,
            ["research", "--workspace", str(workspace), "--query-file", str(explanation_query)],
        )[1]
        self.assertEqual("paper_evidence_found", research["status"])
        self.assertEqual(
            0,
            self._invoke(
                FOCUS_EXPLAIN,
                ["answer", "--workspace", str(workspace), "--answer-file", str(explanation_answer)],
            )[0],
        )
        self.assertEqual(cursor_before_explanation, self._paper_cursor(workspace))
        self.assertEqual(
            chunks_before_explanation,
            (paper_root / "reading" / "plans" / "plan-001" / "chunks.jsonl").read_bytes(),
        )

        protected_reading = self._reading_snapshot(paper_root)
        pointers_before_blog = (workspace / "pointers.yaml").read_bytes()
        self.assertEqual(
            0,
            self._invoke(
                BLOG,
                ["prepare", "--workspace", str(workspace), "--paper-id", parsed["paper_id"]],
            )[0],
        )
        blog = paper_root / "blog"
        (blog / "evidence-map.md").write_text("# Evidence Map\n\nACT evidence complete.\n", encoding="utf-8")
        (blog / "blog.md").write_text(
            "# 技术博客\n\n## 方法与设计\n\n## 实验与证据\n\n## 局限与边界\n\n"
            "![Figure](assets/image-001.png)\n\n## 参考文献\n\n" + "因果证据。" * 500,
            encoding="utf-8",
        )
        with mock.patch.object(
            BLOG,
            "_render_markdown",
            return_value='<h1>技术博客</h1><img src="assets/image-001.png"><p>因果证据</p>',
        ):
            self.assertEqual(0, self._invoke(BLOG, ["render", str(blog)])[0])
        self.assertEqual(0, self._invoke(BLOG, ["check", str(blog)])[0])
        self.assertEqual(protected_reading, self._reading_snapshot(paper_root))
        self.assertEqual(pointers_before_blog, (workspace / "pointers.yaml").read_bytes())

        pointers_path = workspace / "pointers.yaml"
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        pointers["papers"]["other-paper"] = {
            "current_plan_id": "plan-009",
            "current_chunk_id": "chunk-004",
            "current_explanation_id": "explanation-006",
        }
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        old_plan = paper_root / "reading" / "plans" / "plan-001"
        old_plan_before = {
            path.name: path.read_bytes() for path in old_plan.iterdir() if path.is_file()
        }
        explanation_path = paper_root / "reading" / "explanations" / "explanation-001.jsonl"
        explanation_before = explanation_path.read_bytes()
        other_pointer_before = dict(pointers["papers"]["other-paper"])
        result, reinitialized = self._invoke(
            FOCUS_MAP,
            [
                "map",
                "--workspace",
                str(workspace),
                "--paper-id",
                parsed["paper_id"],
                "--reinitialize",
                "--draft",
                str(self._draft("plan-002.json", "ACT 数据布局")),
            ],
        )
        self.assertEqual(0, result)
        self.assertEqual("plan-002", reinitialized["plan_id"])
        for filename, prior_bytes in old_plan_before.items():
            self.assertEqual(prior_bytes, (old_plan / filename).read_bytes())
        self.assertEqual(explanation_before, explanation_path.read_bytes())
        current_pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        self.assertEqual("explanation-001", current_pointers["papers"][parsed["paper_id"]]["current_explanation_id"])
        self.assertEqual(other_pointer_before, current_pointers["papers"]["other-paper"])

        plan_two_translation = self.root / "plan-two-translation.txt"
        plan_two_note = self.root / "plan-two-note.txt"
        plan_two_translation.write_text("新计划缓存译文。", encoding="utf-8")
        plan_two_note.write_text("新计划恢复备注。", encoding="utf-8")
        self.assertEqual(
            0,
            self._invoke(
                FOCUS_GUIDE,
                ["present", "--workspace", str(workspace), "--translation-file", str(plan_two_translation)],
            )[0],
        )
        self.assertEqual(
            0,
            self._invoke(
                FOCUS_GUIDE,
                ["save-note", "--workspace", str(workspace), "--content-file", str(plan_two_note)],
            )[0],
        )
        restored = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(GUIDE_SCRIPT), "restore", "--workspace", str(workspace)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, restored.returncode, restored.stderr)
        restored_chunk = json.loads(restored.stdout)
        self.assertEqual(("plan-002", "chunk-001"), (restored_chunk["plan_id"], restored_chunk["chunk_id"]))
        self.assertEqual("新计划缓存译文。", restored_chunk["translation"])
        self.assertEqual(
            [{"kind": "reader", "content": "新计划恢复备注。"}], restored_chunk["notes"]
        )
        resumed = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(EXPLAIN_SCRIPT), "resume", "--workspace", str(workspace)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, resumed.returncode, resumed.stderr)
        resumed_session = json.loads(resumed.stdout)
        self.assertEqual("explanation-001", resumed_session["explanation_id"])
        self.assertEqual("ACT layout 为什么有效？", resumed_session["history"][0]["content"])

    def test_public_skill_seams_distinguish_required_workspace_errors_and_completion(self):
        missing_workspace = self.root / "missing-workspace"
        result, error = self._invoke_error(
            PARSER,
            [
                "reuse",
                "--workspace",
                str(missing_workspace),
                "--paper-id",
                "missing-paper",
                "--topic",
                "Missing Topic",
            ],
        )
        self.assertEqual(1, result)
        self.assertEqual("workspace_missing", error["error_id"])

        workspace = self.root / "error-workspace"
        paper_root = workspace / "papers" / "valid-paper"
        bundle = paper_root / "parser-bundle"
        plan = paper_root / "reading" / "plans" / "plan-001"
        (bundle / "images").mkdir(parents=True)
        plan.mkdir(parents=True)
        (paper_root / "paper.yaml").write_text(
            json.dumps({"paper_id": "valid-paper", "title": "Valid Paper", "topics": []}),
            encoding="utf-8",
        )
        (bundle / "source.pdf").write_bytes(b"%PDF fixture")
        (bundle / "paper.md").write_text("# Valid Paper\n", encoding="utf-8")
        (bundle / "metadata.json").write_text('{"parser":"mineru-precision-api"}\n', encoding="utf-8")
        (bundle / "validation.json").write_text('{"ok":true}\n', encoding="utf-8")
        record = {
            "chunk_id": "chunk-001",
            "index": 1,
            "section_path": ["Valid Paper"],
            "source_lines": [1, 1],
            "images": [],
            "translation": "有效论文。",
            "notes": [],
        }
        (plan / "chunks.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
        (plan / "glossary.tsv").write_text("", encoding="utf-8")
        pointers_path = workspace / "pointers.yaml"
        pointers = {
            "current_paper_id": "valid-paper",
            "papers": {
                "valid-paper": {
                    "current_plan_id": "plan-001",
                    "current_chunk_id": "chunk-001",
                    "current_explanation_id": None,
                }
            },
        }
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")

        error_cases = []
        result, error = self._invoke_error(
            PARSER,
            [
                "reuse",
                "--workspace",
                str(workspace),
                "--paper-id",
                "valid-paper",
                "--existing-topic-id",
                "missing-topic",
            ],
        )
        error_cases.append((result, error["error_id"], "topic_missing"))
        result, error = self._invoke_error(
            FOCUS_MAP,
            ["map", "--workspace", str(workspace), "--paper-id", "missing-paper"],
        )
        error_cases.append((result, error["error_id"], "paper_missing"))

        no_bundle = workspace / "papers" / "no-bundle"
        no_bundle.mkdir()
        (no_bundle / "paper.yaml").write_text(
            json.dumps({"paper_id": "no-bundle", "title": "No Bundle", "topics": []}),
            encoding="utf-8",
        )
        result, error = self._invoke_error(
            FOCUS_MAP,
            ["map", "--workspace", str(workspace), "--paper-id", "no-bundle"],
        )
        error_cases.append((result, error["error_id"], "parser_bundle_missing"))

        pointers["papers"]["valid-paper"]["current_plan_id"] = None
        pointers["papers"]["valid-paper"]["current_chunk_id"] = None
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        result, error = self._invoke_error(
            FOCUS_GUIDE, ["present", "--workspace", str(workspace)]
        )
        error_cases.append((result, error["error_id"], "reading_plan_missing"))

        pointers["papers"]["valid-paper"]["current_plan_id"] = "plan-001"
        pointers["papers"]["valid-paper"]["current_chunk_id"] = "chunk-999"
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        result, error = self._invoke_error(
            FOCUS_GUIDE, ["present", "--workspace", str(workspace)]
        )
        error_cases.append((result, error["error_id"], "reading_chunk_missing"))

        pointers["papers"]["valid-paper"]["current_chunk_id"] = "chunk-001"
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        result, error = self._invoke_error(
            FOCUS_EXPLAIN,
            [
                "select",
                "--workspace",
                str(workspace),
                "--explanation-id",
                "explanation-999",
            ],
        )
        error_cases.append((result, error["error_id"], "explanation_session_missing"))

        for result, actual, expected in error_cases:
            with self.subTest(error_id=expected):
                self.assertEqual(1, result)
                self.assertEqual(expected, actual)

        pointers["papers"]["valid-paper"]["current_chunk_id"] = None
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        result, completed = self._invoke(
            FOCUS_GUIDE, ["present", "--workspace", str(workspace)]
        )
        self.assertEqual(0, result)
        self.assertEqual("reading_completed", completed["status"])


if __name__ == "__main__":
    unittest.main()
