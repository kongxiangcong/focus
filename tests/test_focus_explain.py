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
        plan = paper_root / "reading" / "plans" / "plan-001"
        plan.mkdir(parents=True)
        (paper_root / "paper.yaml").write_text(
            json.dumps({"paper_id": "fixture-paper", "title": "Fixture Paper", "topics": ["systems"]}),
            encoding="utf-8",
        )
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


if __name__ == "__main__":
    unittest.main()
