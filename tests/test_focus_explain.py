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


ROOT = Path(__file__).resolve().parents[1]
EXPLAIN_SCRIPT = ROOT / ".agents" / "skills" / "focus-explain" / "scripts" / "focus_explain.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


FOCUS_EXPLAIN = load_module("focus_explain_cli", EXPLAIN_SCRIPT)


class FocusExplainTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"focus-explain-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def _invoke(self, argv):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = FOCUS_EXPLAIN.main(argv)
        return result, json.loads(stdout.getvalue()) if stdout.getvalue() else None

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
            "Preface-only permutation note.\n"
            "# Current\nUnrelated opening text.\n"
            "## Results\nThe remote ACT layout uses $Z = XW$.\n"
            "| layout | cost |\n| ACT | low |\n"
            "![ACT flow](images/image-001.png)\nFigure 2: ACT dataflow.\n"
            "## Appendix\nThe rare permutation appears only in this appendix.\n",
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
                "source_lines": [1, 2],
                "images": [],
                "translation": "方法译文。",
                "notes": [],
            }
        ]
        (plan / "chunks.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records),
            encoding="utf-8",
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
                            "current_explanation_id": None,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        return workspace, paper_root, plan

    def test_explicit_request_creates_and_selects_sequential_role_content_only_session(self):
        workspace, paper_root, plan = self._workspace()
        pointers_path = workspace / "pointers.yaml"
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        question = self.root / "question.txt"
        question.write_text("为什么这里要重新排列 ACT？", encoding="utf-8")
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            result = FOCUS_EXPLAIN.main(
                ["new", "--workspace", str(workspace), "--question-file", str(question)]
            )

        self.assertEqual(0, result)
        response = json.loads(stdout.getvalue())
        self.assertEqual("response_required", response["status"])
        self.assertEqual("explanation-001", response["explanation_id"])
        rows = [
            json.loads(line)
            for line in (paper_root / "reading" / "explanations" / "explanation-001.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual([{"role": "user", "content": "为什么这里要重新排列 ACT？"}], rows)
        self.assertEqual({"role", "content"}, set(rows[0]))
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        self.assertEqual(
            "explanation-001", pointers["papers"]["fixture-paper"]["current_explanation_id"]
        )
        self.assertEqual("chunk-001", pointers["papers"]["fixture-paper"]["current_chunk_id"])
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())

        preface_query = self.root / "preface-query.txt"
        preface_query.write_text("Preface-only", encoding="utf-8")
        result, preface = self._invoke(
            ["research", "--workspace", str(workspace), "--query-file", str(preface_query)]
        )
        self.assertEqual(0, result)
        self.assertEqual("paper_evidence_found", preface["status"])
        self.assertIn("Preface-only permutation note.", preface["matches"][0]["content"])

    def test_answers_follow_ups_continue_and_explicit_new_session_append_without_overwrite(self):
        workspace, paper_root, plan = self._workspace()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        pointers_path = workspace / "pointers.yaml"
        question = self.root / "question.txt"
        answer = self.root / "answer.txt"
        follow_up = self.root / "follow-up.txt"
        continuation = self.root / "continue.txt"
        question.write_text("为什么重新排列 ACT？", encoding="utf-8")
        answer.write_text("为了匹配后续计算的数据布局。", encoding="utf-8")
        follow_up.write_text("它与张量形状有什么关系？", encoding="utf-8")
        continuation.write_text("继续解释数据布局的关系。", encoding="utf-8")

        self.assertEqual(
            0,
            self._invoke(["new", "--workspace", str(workspace), "--question-file", str(question)])[0],
        )
        self.assertEqual(
            0,
            self._invoke(["answer", "--workspace", str(workspace), "--answer-file", str(answer)])[0],
        )
        self.assertEqual(
            0,
            self._invoke(["ask", "--workspace", str(workspace), "--question-file", str(follow_up)])[0],
        )
        answer.write_text("张量形状决定目标布局。", encoding="utf-8")
        self.assertEqual(
            0,
            self._invoke(["answer", "--workspace", str(workspace), "--answer-file", str(answer)])[0],
        )
        self.assertEqual(
            0,
            self._invoke(
                ["continue", "--workspace", str(workspace), "--content-file", str(continuation)]
            )[0],
        )
        answer.write_text("布局一致后可避免额外转换。", encoding="utf-8")
        self.assertEqual(
            0,
            self._invoke(["answer", "--workspace", str(workspace), "--answer-file", str(answer)])[0],
        )

        first_path = paper_root / "reading" / "explanations" / "explanation-001.jsonl"
        first_rows = [json.loads(line) for line in first_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(
            [
                {"role": "user", "content": "为什么重新排列 ACT？"},
                {"role": "assistant", "content": "为了匹配后续计算的数据布局。"},
                {"role": "user", "content": "它与张量形状有什么关系？"},
                {"role": "assistant", "content": "张量形状决定目标布局。"},
                {"role": "user", "content": "继续解释数据布局的关系。"},
                {"role": "assistant", "content": "布局一致后可避免额外转换。"},
            ],
            first_rows,
        )

        question.write_text("请从另一个角度重新解释。", encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(
                0,
                FOCUS_EXPLAIN.main(
                    ["new", "--workspace", str(workspace), "--question-file", str(question)]
                ),
            )
        self.assertEqual("explanation-002", json.loads(stdout.getvalue())["explanation_id"])
        self.assertEqual(first_rows, [json.loads(line) for line in first_path.read_text(encoding="utf-8").splitlines()])
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        self.assertEqual(
            "explanation-002", pointers["papers"]["fixture-paper"]["current_explanation_id"]
        )
        self.assertEqual("chunk-001", pointers["papers"]["fixture-paper"]["current_chunk_id"])
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())

    def test_select_and_cross_process_resume_use_saved_history_after_cursor_moves(self):
        workspace, _, plan = self._workspace()
        question = self.root / "question.txt"
        answer = self.root / "answer.txt"
        question.write_text("旧会话问题", encoding="utf-8")
        answer.write_text("旧会话回答", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                0,
                FOCUS_EXPLAIN.main(
                    ["new", "--workspace", str(workspace), "--question-file", str(question)]
                ),
            )
            self.assertEqual(
                0,
                FOCUS_EXPLAIN.main(
                    ["answer", "--workspace", str(workspace), "--answer-file", str(answer)]
                ),
            )
            question.write_text("新会话问题", encoding="utf-8")
            self.assertEqual(
                0,
                FOCUS_EXPLAIN.main(
                    ["new", "--workspace", str(workspace), "--question-file", str(question)]
                ),
            )

        pointers_path = workspace / "pointers.yaml"
        pointers = json.loads(pointers_path.read_text(encoding="utf-8"))
        pointers["papers"]["fixture-paper"]["current_chunk_id"] = None
        pointers_path.write_text(json.dumps(pointers), encoding="utf-8")
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(
                0,
                FOCUS_EXPLAIN.main(
                    [
                        "select",
                        "--workspace",
                        str(workspace),
                        "--explanation-id",
                        "explanation-001",
                    ]
                ),
            )
        self.assertEqual("explanation_selected", json.loads(stdout.getvalue())["status"])

        resumed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(EXPLAIN_SCRIPT),
                "resume",
                "--workspace",
                str(workspace),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, resumed.returncode, resumed.stderr)
        response = json.loads(resumed.stdout)
        self.assertEqual(
            [
                {"role": "user", "content": "旧会话问题"},
                {"role": "assistant", "content": "旧会话回答"},
            ],
            response["history"],
        )
        current = json.loads(pointers_path.read_text(encoding="utf-8"))
        self.assertIsNone(current["papers"]["fixture-paper"]["current_chunk_id"])
        self.assertEqual(
            "explanation-001", current["papers"]["fixture-paper"]["current_explanation_id"]
        )
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())

    def test_failed_response_and_missing_selection_preserve_reading_and_retry_context(self):
        workspace, _, plan = self._workspace()
        pointers_path = workspace / "pointers.yaml"
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        question = self.root / "question.txt"
        question.write_text("这个公式为什么成立？", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                0,
                FOCUS_EXPLAIN.main(
                    ["new", "--workspace", str(workspace), "--question-file", str(question)]
                ),
            )

        pending = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(EXPLAIN_SCRIPT),
                "resume",
                "--workspace",
                str(workspace),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, pending.returncode, pending.stderr)
        pending_response = json.loads(pending.stdout)
        self.assertEqual("response_pending", pending_response["status"])
        self.assertEqual(
            [{"role": "user", "content": "这个公式为什么成立？"}],
            pending_response["history"],
        )

        pointer_before_missing = pointers_path.read_bytes()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = FOCUS_EXPLAIN.main(
                [
                    "select",
                    "--workspace",
                    str(workspace),
                    "--explanation-id",
                    "explanation-999",
                ]
            )
        self.assertEqual(1, result)
        self.assertEqual("explanation_session_missing", json.loads(stderr.getvalue())["error_id"])
        self.assertEqual(pointer_before_missing, pointers_path.read_bytes())
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())

        forbidden = {
            "present_current_chunk",
            "continue_reading",
            "append_current_note",
            "correct_current_term",
            "retranslate_current_chunk",
            "switch_paper",
        }
        self.assertTrue(forbidden.isdisjoint(dir(FOCUS_EXPLAIN.ExplanationWorkspaceCore)))

    def test_session_sequence_continues_past_three_digits_without_overwrite(self):
        workspace, paper_root, _ = self._workspace()
        explanations = paper_root / "reading" / "explanations"
        explanations.mkdir(parents=True)
        for number in (999, 1000):
            (explanations / f"explanation-{number:03d}.jsonl").write_text(
                json.dumps({"role": "user", "content": f"question-{number}"}) + "\n",
                encoding="utf-8",
            )
        thousand_before = (explanations / "explanation-1000.jsonl").read_bytes()
        question = self.root / "question.txt"
        question.write_text("question-1001", encoding="utf-8")

        result, response = self._invoke(
            ["new", "--workspace", str(workspace), "--question-file", str(question)]
        )

        self.assertEqual(0, result)
        self.assertEqual("explanation-1001", response["explanation_id"])
        self.assertEqual(thousand_before, (explanations / "explanation-1000.jsonl").read_bytes())

    def test_research_searches_full_paper_and_returns_scientific_structures_outside_current_chunk(self):
        workspace, _, plan = self._workspace()
        pointers_before = (workspace / "pointers.yaml").read_bytes()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        query = self.root / "query.txt"
        query.write_text("ACT layout", encoding="utf-8")

        result, response = self._invoke(
            ["research", "--workspace", str(workspace), "--query-file", str(query)]
        )

        self.assertEqual(0, result)
        self.assertEqual("paper_evidence_found", response["status"])
        self.assertTrue(any(match["source_lines"][0] > 2 for match in response["matches"]))
        evidence = "\n".join(match["content"] for match in response["matches"])
        self.assertIn("$Z = XW$", evidence)
        self.assertIn("| layout | cost |", evidence)
        self.assertIn("Figure 2: ACT dataflow.", evidence)
        images = [image for match in response["matches"] for image in match["images"]]
        self.assertEqual("Figure 2: ACT dataflow.", images[0]["caption"])
        self.assertTrue(Path(images[0]["path"]).is_file())
        self.assertEqual(pointers_before, (workspace / "pointers.yaml").read_bytes())
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())

    def test_insufficient_evidence_requests_external_research_and_clear_refusal_is_persisted(self):
        workspace, paper_root, plan = self._workspace()
        question = self.root / "question.txt"
        question.write_text("解释量子香蕉效应。", encoding="utf-8")
        self.assertEqual(
            0,
            self._invoke(["new", "--workspace", str(workspace), "--question-file", str(question)])[0],
        )
        pointers_after_new = (workspace / "pointers.yaml").read_bytes()
        chunks_before = (plan / "chunks.jsonl").read_bytes()

        result, research = self._invoke(
            ["research", "--workspace", str(workspace), "--query-file", str(question)]
        )
        self.assertEqual(0, result)
        self.assertEqual("external_research_required", research["status"])
        self.assertEqual([], research["matches"])
        self.assertEqual(pointers_after_new, (workspace / "pointers.yaml").read_bytes())

        external = self.root / "external-insufficient.json"
        external.write_text(
            json.dumps(
                {
                    "sources": [],
                    "insufficient_reason": "No primary source defines the claimed effect.",
                }
            ),
            encoding="utf-8",
        )
        result, external_result = self._invoke(
            [
                "external-research",
                "--workspace",
                str(workspace),
                "--evidence-file",
                str(external),
            ]
        )
        self.assertEqual(0, result)
        self.assertEqual("external_evidence_insufficient", external_result["status"])

        reason = self.root / "reason.txt"
        reason.write_text("论文与可取得的一手资料均未定义该效应。", encoding="utf-8")
        result, refused = self._invoke(
            ["refuse", "--workspace", str(workspace), "--reason-file", str(reason)]
        )
        self.assertEqual(0, result)
        self.assertEqual("refused", refused["status"])
        rows = [
            json.loads(line)
            for line in (paper_root / "reading" / "explanations" / "explanation-001.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertTrue(rows[-1]["content"].startswith("无法提供可靠解释："))
        self.assertEqual({"role", "content"}, set(rows[-1]))
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())
        self.assertEqual(pointers_after_new, (workspace / "pointers.yaml").read_bytes())
        self.assertEqual(
            ["explanation-001.jsonl"],
            sorted(path.name for path in (paper_root / "reading" / "explanations").iterdir()),
        )

    def test_direct_answer_and_requested_sources_remain_visible_content_without_source_ledger(self):
        workspace, paper_root, plan = self._workspace()
        question = self.root / "question.txt"
        answer = self.root / "answer.txt"
        question.write_text("解释 ACT layout，并给出来源。", encoding="utf-8")
        self.assertEqual(
            0,
            self._invoke(["new", "--workspace", str(workspace), "--question-file", str(question)])[0],
        )
        pointers_after_new = (workspace / "pointers.yaml").read_bytes()
        chunks_before = (plan / "chunks.jsonl").read_bytes()
        external = self.root / "external-primary.json"
        external.write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "source_type": "official_specification",
                            "title": "ACT Layout Specification",
                            "url": "https://example.test/act-spec",
                            "content": "The ACT layout aligns tensor dimensions before execution.",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        result, external_result = self._invoke(
            [
                "external-research",
                "--workspace",
                str(workspace),
                "--evidence-file",
                str(external),
            ]
        )
        self.assertEqual(0, result)
        self.assertEqual("external_evidence_found", external_result["status"])
        self.assertEqual("official_specification", external_result["sources"][0]["source_type"])
        answer.write_text(
            "ACT layout 通过匹配张量布局减少转换。来源：[ACT Layout Specification](https://example.test/act-spec)。",
            encoding="utf-8",
        )

        result, response = self._invoke(
            ["answer", "--workspace", str(workspace), "--answer-file", str(answer)]
        )

        self.assertEqual(0, result)
        self.assertEqual("answered", response["status"])
        session_root = paper_root / "reading" / "explanations"
        rows = [
            json.loads(line)
            for line in (session_root / "explanation-001.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertIn("来源：", rows[-1]["content"])
        self.assertEqual({"role", "content"}, set(rows[-1]))
        self.assertEqual(["explanation-001.jsonl"], sorted(path.name for path in session_root.iterdir()))
        self.assertEqual(pointers_after_new, (workspace / "pointers.yaml").read_bytes())
        self.assertEqual(chunks_before, (plan / "chunks.jsonl").read_bytes())


if __name__ == "__main__":
    unittest.main()
