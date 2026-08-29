from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


ARTICLE = load_module("journey_article", ROOT / ".agents/skills/article-parser/scripts/article_parser.py")
FOCUS_MAP = load_module("journey_article_map", ROOT / ".agents/skills/focus-map/scripts/focus_map.py")
FOCUS_READ = load_module("journey_article_read", ROOT / ".agents/skills/focus-read/scripts/focus_read.py")
BLOG = load_module("journey_article_blog", ROOT / ".agents/skills/paper2blog/scripts/paper2blog.py")


class ArticleReadingJourneyTests(unittest.TestCase):
    def setUp(self):
        runs = ROOT / "tmp" / "test-runs"
        runs.mkdir(parents=True, exist_ok=True)
        self.root = runs / f"a-{uuid.uuid4().hex[:8]}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    @staticmethod
    def _run(module, args, **kwargs):
        stdin = kwargs.pop("stdin", "")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), mock.patch("sys.stdin", io.StringIO(stdin)):
            code = module.main(args, **kwargs)
        text = stdout.getvalue() if code == 0 else stderr.getvalue()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = json.loads(text.splitlines()[-1])
        return code, payload

    def test_article_parse_map_read_note_search_continue_and_reinitialize_share_one_core(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        archive = self.root / "article.zip"
        with zipfile.ZipFile(archive, "w") as result:
            result.writestr(
                "result/full.md",
                "# 中文系统文章\n\n## 第一节\n第一段解释统一读写路径。\n\n## 第二节\n第二段解释游标推进。\n",
            )
            result.writestr("result/main.html", "<html lang='zh-CN'><body>中文系统文章</body></html>")

        class Hosted:
            @staticmethod
            def start_url(url):
                self.assertEqual("https://example.test/chinese", url)
                return "task_id", "journey-task"

            @staticmethod
            def complete(task, source, output, *, timeout, interval):
                self.assertIsNone(source)
                ARTICLE._normalize(
                    archive,
                    output,
                    reference_kind=task.reference_kind,
                    reference_id=task.reference_id,
                    source_url=task.source_url,
                )

        code, parsed = self._run(
            ARTICLE,
            [
                "parse-url",
                "https://example.test/chinese",
                "--workspace",
                str(workspace),
                "--title",
                "中文系统文章",
                "--short-name",
                "中文系统",
                "--topic",
                "系统",
            ],
            hosted=Hosted(),
        )
        self.assertEqual(0, code)
        source_id = parsed["source_id"]
        draft = json.dumps(
                {
                    "chunks": [
                        {"section_path": ["中文系统文章", "第一节"], "source_lines": [1, 5], "images": []},
                        {"section_path": ["中文系统文章", "第二节"], "source_lines": [6, 7], "images": []},
                    ],
                    "glossary": [],
                },
                ensure_ascii=False,
        )

        code, mapped = self._run(
            FOCUS_MAP,
            ["map", "--workspace", str(workspace), "--source-id", source_id],
            stdin=draft,
        )
        self.assertEqual((0, "plan-001"), (code, mapped["plan_id"]))
        code, current = self._run(FOCUS_READ, ["current", "--workspace", str(workspace)])
        self.assertEqual((0, "source_ready"), (code, current["status"]))
        self.assertIn("第一段解释统一读写路径", current["source_text"])
        self.assertIsNone(current["translation"])
        duplicate = self.root / "duplicate.txt"
        duplicate.write_text("第一段解释统一读写路径。", encoding="utf-8")
        code, rejected_translation = self._run(
            FOCUS_READ,
            [
                "retranslate",
                "--workspace",
                str(workspace),
                "--expected-plan-id",
                "plan-001",
                "--expected-chunk-id",
                "chunk-001",
                "--translation-file",
                str(duplicate),
            ],
        )
        self.assertEqual((1, "translation_not_applicable"), (code, rejected_translation["error_id"]))

        note = self.root / "note.txt"
        note.write_text("文章复用了同一个 Reading Core。", encoding="utf-8")
        code, saved = self._run(
            FOCUS_READ,
            [
                "append-note",
                "--workspace",
                str(workspace),
                "--expected-plan-id",
                "plan-001",
                "--expected-chunk-id",
                "chunk-001",
                "--kind",
                "thought",
                "--origin",
                "user",
                "--content-file",
                str(note),
            ],
        )
        self.assertEqual((0, "note_saved"), (code, saved["status"]))
        code, found = self._run(
            FOCUS_READ,
            ["search", "--workspace", str(workspace), "--query", "游标推进"],
        )
        self.assertEqual(1, len(found["matches"]))
        code, advanced = self._run(
            FOCUS_READ,
            [
                "continue",
                "--workspace",
                str(workspace),
                "--expected-plan-id",
                "plan-001",
                "--expected-chunk-id",
                "chunk-001",
            ],
        )
        self.assertEqual((0, "chunk-002"), (code, advanced["chunk_id"]))
        source_root = workspace / "sources" / source_id
        first_record = json.loads(
            (source_root / "reading/plans/plan-001/records/chunk-001.json").read_text(encoding="utf-8")
        )
        second_record = json.loads(
            (source_root / "reading/plans/plan-001/records/chunk-002.json").read_text(encoding="utf-8")
        )
        self.assertEqual(1, len(first_record["notes"]))
        self.assertIsNone(second_record["translation"])

        code, reused = self._run(
            FOCUS_MAP, ["map", "--workspace", str(workspace), "--source-id", source_id]
        )
        self.assertTrue(reused["reused"])
        code, rebuilt = self._run(
            FOCUS_MAP,
            [
                "map",
                "--workspace",
                str(workspace),
                "--source-id",
                source_id,
                "--reinitialize",
            ],
            stdin=draft,
        )
        self.assertEqual((0, "plan-002"), (code, rebuilt["plan_id"]))
        self.assertIsNone(
            json.loads(
                (source_root / "reading/plans/plan-002/records/chunk-001.json").read_text(encoding="utf-8")
            )["translation"]
        )

        code, rejected = self._run(
            BLOG,
            ["prepare", "--workspace", str(workspace), "--source-id", source_id],
        )
        self.assertEqual((1, "source_kind_unsupported"), (code, rejected["error_id"]))


if __name__ == "__main__":
    unittest.main()
