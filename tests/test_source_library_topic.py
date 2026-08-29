import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents"))
import core as CORE


class SourceLibraryTopicTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.library = CORE.SourceLibrary(self.workspace)
        self.core = CORE.WorkspaceCore(self.workspace)

    def tearDown(self):
        self.temporary.cleanup()

    def _bundle(self, name: str, *, kind: str = "paper_pdf", text: str = "# Source\n\nEvidence one.\n\nEvidence two.") -> Path:
        bundle = self.root / name
        bundle.mkdir()
        (bundle / "images").mkdir()
        (bundle / "content.md").write_text(text, encoding="utf-8")
        original = "source.pdf" if kind == "paper_pdf" else "source.html"
        (bundle / original).write_bytes(b"fixture")
        reference = {"batch_id": f"batch-{name}"} if kind == "paper_pdf" else {"task_id": f"task-{name}"}
        (bundle / "metadata.json").write_text(
            json.dumps(
                {
                    "source_kind": kind,
                    "language": "en" if kind == "paper_pdf" else "zh",
                    "parser": "paper-parser" if kind == "paper_pdf" else "article-parser",
                    **reference,
                }
            ),
            encoding="utf-8",
        )
        (bundle / "validation.json").write_text(
            json.dumps({"ok": True, "warnings": []}), encoding="utf-8"
        )
        return bundle

    def _register(self, name: str, *, short_name: str, identity: str, topic: str | None = None, published_at: str | None = None):
        return self.library.register(
            self._bundle(name),
            source_kind="paper_pdf",
            title=f"Complete title for {name}",
            short_name=short_name,
            identity=identity,
            published_at=published_at,
            topic_title=topic,
        )

    def _map(self, source_id: str):
        return self.core.map_reading_plan(
            source_id,
            draft={
                "chunks": [
                    {"section_path": ["Source"], "source_lines": [1, 3], "images": []},
                    {"section_path": ["Source"], "source_lines": [4, 5], "images": []},
                ],
                "glossary": [],
            },
        )

    def test_source_library_registers_without_topic_reuses_identity_and_attaches_ordered_topics(self):
        first = self._register("first", short_name="DeepStack", identity="paper:deepstack")
        self.assertEqual("DeepStack-paper", first["source_id"])
        source = json.loads((self.workspace / "sources" / first["source_id"] / "source.yaml").read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "source_id": "DeepStack-paper",
                "source_kind": "paper_pdf",
                "title": "Complete title for first",
                "short_name": "DeepStack",
                "identity": "paper:deepstack",
            },
            source,
        )
        duplicate = self.library.register(
            self._bundle("duplicate"),
            source_kind="paper_pdf",
            title="A later title must not rename the Source",
            short_name="Different suggestion",
            identity="paper:deepstack",
        )
        self.assertTrue(duplicate["reused"])
        self.assertEqual(first["source_id"], duplicate["source_id"])
        self.assertFalse((self.workspace / "sources" / "Different suggestion-paper").exists())

        second = self._register("second", short_name="Second Work", identity="paper:second")
        self.library.attach(first["source_id"], topic_title="Systems", topic_id="systems")
        self.library.attach(second["source_id"], existing_topic_id="systems")
        self.library.attach(first["source_id"], topic_title="AI", topic_id="ai")
        topic = json.loads((self.workspace / "topics" / "systems" / "topic.yaml").read_text(encoding="utf-8"))
        self.assertEqual([first["source_id"], second["source_id"]], topic["sources"])
        self.assertNotIn("topics", source)

    def test_source_ids_preserve_readable_short_names_and_use_date_then_numeric_collisions(self):
        first = self._register("a", short_name="Model: A/B", identity="paper:a")
        dated = self._register(
            "b", short_name="Model: A/B", identity="paper:b", published_at="2017-05-01"
        )
        numbered = self._register("c", short_name="Model: A/B", identity="paper:c")
        self.assertEqual("Model： A／B-paper", first["source_id"])
        self.assertEqual("Model： A／B-2017-paper", dated["source_id"])
        self.assertEqual("Model： A／B-2-paper", numbered["source_id"])

    def test_source_library_rejects_the_removed_topic_membership_shape(self):
        registered = self._register("legacy", short_name="Legacy", identity="paper:legacy")
        source_path = self.workspace / "sources" / registered["source_id"] / "source.yaml"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source["topics"] = ["removed"]
        source_path.write_text(json.dumps(source), encoding="utf-8")
        with self.assertRaises(CORE.WorkspaceError) as caught:
            self.library.get(registered["source_id"])
        self.assertEqual("source_invalid", caught.exception.error_id)

    def test_topic_reading_crosses_sources_and_skips_a_source_completed_elsewhere(self):
        first = self._register("one", short_name="One", identity="paper:one", topic="Topic")
        second = self._register("two", short_name="Two", identity="paper:two", topic="Topic")
        self._map(first["source_id"])
        self._map(second["source_id"])
        selected = self.core.select_topic("topic")
        self.assertEqual(first["source_id"], selected["source_id"])
        first_receipt = self.core.get_reading_state()
        self.core.continue_reading(
            expected_plan_id=first_receipt["plan_id"], expected_chunk_id=first_receipt["chunk_id"]
        )
        first_receipt = self.core.get_reading_state()
        crossed = self.core.continue_reading(
            expected_plan_id=first_receipt["plan_id"], expected_chunk_id=first_receipt["chunk_id"]
        )
        self.assertEqual("topic_source_advanced", crossed["status"])
        self.assertEqual(second["source_id"], crossed["source_id"])
        state = json.loads((self.workspace / "state.json").read_text(encoding="utf-8"))
        self.assertEqual("topic", state["current_topic_id"])

        self.library.attach(first["source_id"], topic_title="Other", topic_id="other")
        completed = self.core.select_topic("other")
        self.assertEqual("topic_completed", completed["status"])

    def test_topic_search_and_synthesis_are_bounded_and_source_anchored(self):
        first = self._register("alpha", short_name="Alpha", identity="paper:alpha", topic="Topic")
        second = self._register("beta", short_name="Beta", identity="paper:beta", topic="Topic")
        self._map(first["source_id"])
        self._map(second["source_id"])
        self.core.switch_source(first["source_id"])
        receipt = self.core.get_reading_state()
        self.core.append_note(
            expected_plan_id=receipt["plan_id"],
            expected_chunk_id=receipt["chunk_id"],
            kind="clarification",
            origin="dialogue",
            content="Evidence one is the stable conclusion.",
            anchor={"source_lines": [3, 3], "quote": "Evidence one."},
        )

        matches = self.core.search_topic(topic_id="topic", query="Evidence", limit=3)
        self.assertEqual(3, len(matches["matches"]))
        self.assertTrue(all(hit["source_id"] in {first["source_id"], second["source_id"]} for hit in matches["matches"]))
        result = self.core.synthesize_topic(
            "topic",
            {
                "selected_ranges": [{"source_id": second["source_id"], "source_lines": [3, 3]}],
                "claims": [
                    {
                        "text": "Both sources present evidence.",
                        "anchors": [
                            {"source_id": first["source_id"], "source_lines": [3, 3]},
                            {"source_id": second["source_id"], "source_lines": [3, 3]},
                        ],
                    }
                ],
            },
        )
        self.assertEqual("synthesis-001", result["synthesis_id"])
        synthesis = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(["topic_id", "synthesis_id", "claims"], list(synthesis))
        self.assertFalse(any(path.name == "parser-bundle" for path in (self.workspace / "topics" / "topic").rglob("*")))

        with self.assertRaises(CORE.WorkspaceError) as caught:
            self.core.synthesize_topic(
                "topic",
                {"selected_ranges": [], "claims": [{"text": "Unsupported", "anchors": []}]},
            )
        self.assertEqual("topic_synthesis_invalid", caught.exception.error_id)

    def test_topic_reading_identifies_a_missing_ordered_source_entry(self):
        self._register("only", short_name="Only", identity="paper:only", topic="Topic")
        topic_path = self.workspace / "topics" / "topic" / "topic.yaml"
        topic = json.loads(topic_path.read_text(encoding="utf-8"))
        topic["sources"].append("Missing-paper")
        topic_path.write_text(json.dumps(topic), encoding="utf-8")
        with self.assertRaises(CORE.WorkspaceError) as caught:
            self.core.select_topic("topic")
        self.assertEqual("topic_source_missing", caught.exception.error_id)
        self.assertIn("entry 2", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
