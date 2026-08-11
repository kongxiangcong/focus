from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / ".agents" / "skills" / "ask-paper" / "scripts" / "focus_state.py"
CORE_SCRIPTS = CLI.parent
if os.fspath(CORE_SCRIPTS) not in os.sys.path:
    os.sys.path.insert(0, os.fspath(CORE_SCRIPTS))

from focus_core.contracts import contract_hash


class FocusStateAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"run-{uuid.uuid4().hex}"
        self.root.mkdir()
        self.workspace = self.root / "knowledge-base"

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def run_cli(self, *arguments: str, expected: int = 0) -> dict:
        environment = os.environ.copy()
        environment.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        completed = subprocess.run(
            [os.fspath(Path(os.sys.executable)), "-B", "-X", "utf8", os.fspath(CLI), *arguments],
            cwd=self.root,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, completed.returncode, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def run_cli_text(self, *arguments: str, expected: int = 0) -> str:
        environment = os.environ.copy()
        environment.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        completed = subprocess.run(
            [os.fspath(Path(os.sys.executable)), "-B", "-X", "utf8", os.fspath(CLI), *arguments],
            cwd=self.root,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(expected, completed.returncode, completed.stdout + completed.stderr)
        return completed.stdout

    def write_event(self, route: dict, name: str, value: dict) -> Path:
        path = self.workspace / route["run_dir"] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def commit(self, route: dict, event: dict) -> dict:
        path = self.write_event(route, f"{event['event_id']}.json", event)
        return self.run_cli(
            "commit",
            "--workspace",
            os.fspath(self.workspace),
            "--route-id",
            route["route_id"],
            "--event",
            os.fspath(path),
        )

    def initialize(self) -> None:
        result = self.run_cli("resolve", "--workspace", os.fspath(self.workspace))
        self.assertTrue(result["created"])

    def ingest_fixture(self, title: str = "Fixture Paper") -> tuple[str, Path]:
        source = self.root / "fixture.pdf"
        source.write_bytes(b"%PDF-fixture-content\n")
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--input", os.fspath(source))
        run = self.workspace / route["run_dir"] / "candidate"
        run.mkdir(parents=True)
        (run / "paper.md").write_text("# Fixture Paper\n\n## Method\n\nA deterministic fixture body with enough text for validation.\n", encoding="utf-8")
        (run / "metadata.json").write_text(json.dumps({"title": title}), encoding="utf-8")
        result = self.commit(
            route,
            {
                "event_id": "ev-ingest-001",
                "type": "ingest-completed",
                "title": title,
                "aliases": ["fixture"],
                "parsed_markdown": "candidate/paper.md",
                "metadata": "candidate/metadata.json",
                "parser": {"name": "fixture", "version": "1"},
            },
        )
        paper_id = result["paper_id"]
        registry = yaml.safe_load((self.workspace / "reading-registry.yaml").read_text(encoding="utf-8"))
        paper_dir = self.workspace / "research-corpus" / registry["papers"][paper_id]["directory"]
        return paper_id, paper_dir

    def install_guide(self, paper_id: str, paper_dir: Path) -> None:
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("paper-guide", route["target_skill"])
        source_map = yaml.safe_load((paper_dir / "ingest" / "source-map.yaml").read_text(encoding="utf-8"))
        anchors = [item["id"] for item in source_map["anchors"]]
        first, second = anchors[:2]
        run = self.workspace / route["run_dir"] / "guide"
        run.mkdir(parents=True)
        (run / "overview.md").write_text("# Overview\n\nProblem -> mechanism -> evidence.\n", encoding="utf-8")
        claim_map = {
            "schema_version": 1,
            "claims": [
                {"id": "C01", "kind": "author-claim", "statement": "The mechanism addresses the problem.", "source_anchors": [first], "supported_by": [], "assumptions": [], "limitations": []}
            ],
        }
        knowledge_map = {
            "schema_version": 1,
            "nodes": [
                {
                    "id": "N01",
                    "concept_id": "architecture.flex_mode",
                    "title": "Flexible mode",
                    "type": "mechanism",
                    "tree_parent": None,
                    "requires": {"hard": [], "soft": []},
                    "objective": "Explain why flexible mode improves utilization.",
                    "order": 1,
                    "source_anchors": [first],
                    "mastery_contract": {"must_show": ["causal chain"], "probes": ["reconstruct", "discriminate"], "critical_errors": ["utilization is free"]},
                },
                {
                    "id": "N02",
                    "concept_id": "architecture.data_reuse",
                    "title": "Data reuse tradeoff",
                    "type": "tradeoff",
                    "tree_parent": "N01",
                    "requires": {"hard": ["N01"], "soft": []},
                    "objective": "Apply the reuse tradeoff to a changed tensor shape.",
                    "order": 2,
                    "source_anchors": [second],
                    "mastery_contract": {"must_show": ["reuse", "bandwidth"], "probes": ["transfer", "boundary"], "critical_errors": ["splitting always improves reuse"]},
                },
            ],
        }
        plan = {
            "schema_version": 1,
            "paper_id": paper_id,
            "plan_revision": 1,
            "units": [
                {"id": "U01", "title": "Flexible mode", "required": True, "node_ids": ["N01"], "depends_on": [], "objective": "Reconstruct the mechanism.", "source_anchors": [first], "exit_criteria": ["causal chain"]},
                {"id": "U02", "title": "Reuse", "required": True, "node_ids": ["N02"], "depends_on": ["U01"], "objective": "Apply the tradeoff.", "source_anchors": [second], "exit_criteria": ["transfer"]},
            ],
        }
        for name, value in (("claim-map.yaml", claim_map), ("knowledge-map.yaml", knowledge_map), ("reading-plan.yaml", plan)):
            (run / name).write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
        self.commit(
            route,
            {
                "event_id": "ev-guide-001",
                "type": "guide-installed",
                "overview": "guide/overview.md",
                "claim_map": "guide/claim-map.yaml",
                "knowledge_map": "guide/knowledge-map.yaml",
                "reading_plan": "guide/reading-plan.yaml",
                "prompt_id": "prompt-plan-001",
                "learning_goal": {"mode": "deep_understanding", "statement": "Explain and transfer the mechanism."},
            },
        )

    def confirm_plan(self, paper_id: str) -> None:
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("confirmation", route["mode"])
        self.commit(route, {"event_id": "ev-plan-001", "type": "plan-confirmed", "plan_revision": 1})

    def present_and_answer(self, paper_id: str, sequence: int, verdict: str) -> None:
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        node_id = route["context"]["node_id"]
        unit_id = route["context"]["unit_id"]
        run = self.workspace / route["run_dir"]
        (run / "unit.md").write_text(f"# {unit_id}\n\n## Checkpoint\nExplain {node_id}.\n", encoding="utf-8")
        prompt_id = f"prompt-unit-{sequence}"
        self.commit(
            route,
            {"event_id": f"ev-present-{sequence}", "type": "unit-presented", "node_id": node_id, "unit_id": unit_id, "unit_artifact": "unit.md", "prompt_id": prompt_id},
        )
        resume = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        level = 4 if verdict == "transfer" else 3
        dimensions = ["mechanism", "transfer"] if verdict == "transfer" else ["mechanism"]
        self.commit(
            resume,
            {
                "event_id": f"ev-answer-{sequence}",
                "type": "answer-recorded",
                "prompt_id": prompt_id,
                "response_id": f"resp-{sequence}",
                "answer": "The mechanism changes utilization and reuse under a constrained shape.",
                "verdict": verdict,
                "rubric_results": [{"criterion": "causal chain", "passed": True}],
                "evidence": [{"evidence_type": "checkpoint-answer", "level_candidate": level, "confidence": "medium", "dimensions": dimensions, "rubric": "Reconstructed the mechanism and its tradeoff"}],
            },
        )

    def test_workspace_resolution_adoption_and_nearest_ancestor(self) -> None:
        candidate = self.root / "project" / "knowledge-base"
        candidate.mkdir(parents=True)
        sentinel = candidate / "existing.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        blocked = self.run_cli("resolve", "--workspace", os.fspath(candidate), expected=2)
        self.assertEqual("WORKSPACE_ADOPTION_REQUIRED", blocked["error"])
        adopted = self.run_cli("resolve", "--workspace", os.fspath(candidate), "--adopt")
        self.assertTrue(adopted["adopted"])
        nested = self.root / "project" / "sub" / "deep"
        nested.mkdir(parents=True)
        found = self.run_cli("resolve", "--start", os.fspath(nested), "--no-create")
        self.assertEqual(candidate.resolve(), Path(found["workspace"]))
        self.assertEqual("preserve", sentinel.read_text(encoding="utf-8"))

    def test_route_lock_and_exactly_once_ingest(self) -> None:
        self.initialize()
        source = self.root / "one.pdf"
        source.write_bytes(b"one")
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--input", os.fspath(source))
        second = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--input", os.fspath(source), expected=2)
        self.assertEqual("LOCK_HELD", second["error"])
        run = self.workspace / route["run_dir"]
        (run / "paper.md").write_text("# One\n\nA long enough fixture body for deterministic ingestion validation.\n", encoding="utf-8")
        (run / "metadata.json").write_text("{}", encoding="utf-8")
        event = {"event_id": "ev-once-001", "type": "ingest-completed", "title": "One", "parsed_markdown": "paper.md", "metadata": "metadata.json", "parser": {"name": "fixture"}}
        first = self.commit(route, event)
        event_path = self.write_event(route, "ev-once-retry.json", event)
        replay = self.run_cli("commit", "--workspace", os.fspath(self.workspace), "--route-id", route["route_id"], "--event", os.fspath(event_path))
        self.assertTrue(replay["idempotent"])
        self.assertEqual(first["paper_id"], replay["paper_id"])

        conflicting = {**event, "title": "A conflicting replay"}
        conflict_path = self.write_event(route, "ev-once-conflict.json", conflicting)
        conflict = self.run_cli(
            "commit", "--workspace", os.fspath(self.workspace), "--route-id", route["route_id"],
            "--event", os.fspath(conflict_path), expected=2,
        )
        self.assertEqual("IDEMPOTENCY_CONFLICT", conflict["error"])

        lock_path = self.workspace / ".paper-companion" / "locks" / f"{route['lock_key']}.lock"
        lock_path.write_text(yaml.safe_dump({"schema_version": 1, "lock_key": route["lock_key"], "owner_route_id": route["route_id"], "acquired_at": "crash-simulation"}), encoding="utf-8")
        recovered = self.run_cli("commit", "--workspace", os.fspath(self.workspace), "--route-id", route["route_id"], "--event", os.fspath(event_path))
        self.assertTrue(recovered["idempotent"])
        self.assertFalse(lock_path.exists())

    def test_event_payload_must_be_inside_route_run_directory(self) -> None:
        self.initialize()
        source = self.root / "outside.pdf"
        source.write_bytes(b"outside")
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--input", os.fspath(source))
        run = self.workspace / route["run_dir"]
        (run / "paper.md").write_text("# Outside\n\nValid staged content remains in the authorized run.\n", encoding="utf-8")
        (run / "metadata.json").write_text("{}", encoding="utf-8")
        outside_event = self.root / "outside-event.json"
        outside_event.write_text(json.dumps({
            "event_id": "ev-outside-001", "type": "ingest-completed", "title": "Outside",
            "parsed_markdown": "paper.md", "metadata": "metadata.json", "parser": {"name": "fixture"},
        }), encoding="utf-8")
        rejected = self.run_cli(
            "commit", "--workspace", os.fspath(self.workspace), "--route-id", route["route_id"],
            "--event", os.fspath(outside_event), expected=2,
        )
        self.assertEqual("EVENT_PATH_ESCAPE", rejected["error"])
        verified = self.run_cli("verify-route", "--workspace", os.fspath(self.workspace), "--route-id", route["route_id"], "--target", "paper-ingest")
        self.assertEqual("issued", verified["status"])
        registry = yaml.safe_load((self.workspace / "reading-registry.yaml").read_text(encoding="utf-8"))
        self.assertEqual({}, registry["papers"])

    def test_contract_hash_covers_the_full_learning_contract(self) -> None:
        base = {
            "type": "mechanism", "objective": "Explain the mechanism.",
            "requires": {"hard": ["N00"], "soft": []},
            "source_anchors": ["sha256:abc#block-1"],
            "mastery_contract": {"must_show": ["cause"], "probes": ["transfer"], "critical_errors": []},
        }
        baseline = contract_hash(base)
        changes = [
            {"type": "tradeoff"},
            {"objective": "Apply the mechanism."},
            {"requires": {"hard": [], "soft": ["N00"]}},
            {"source_anchors": ["sha256:abc#block-2"]},
            {"mastery_contract": {"must_show": ["boundary"], "probes": ["transfer"], "critical_errors": []}},
        ]
        for change in changes:
            with self.subTest(change=change):
                self.assertNotEqual(baseline, contract_hash({**base, **change}))

    def test_invalid_evidence_batch_does_not_poison_ledger_or_profile(self) -> None:
        self.initialize()
        paper_id, paper_dir = self.ingest_fixture("Evidence Atomicity")
        self.install_guide(paper_id, paper_dir)
        self.confirm_plan(paper_id)
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        node_id, unit_id = route["context"]["node_id"], route["context"]["unit_id"]
        run = self.workspace / route["run_dir"]
        (run / "unit.md").write_text("# Unit\n\n## Checkpoint\nExplain it.\n", encoding="utf-8")
        self.commit(route, {"event_id": "ev-atomic-present", "type": "unit-presented", "node_id": node_id, "unit_id": unit_id, "unit_artifact": "unit.md", "prompt_id": "prompt-atomic"})
        answer_route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        evidence_path = self.workspace / "cognitive-profile" / "evidence.jsonl"
        profile_path = self.workspace / "cognitive-profile" / "profile.yaml"
        evidence_before, profile_before = evidence_path.read_bytes(), profile_path.read_bytes()
        event = {
            "event_id": "ev-atomic-answer", "type": "answer-recorded", "prompt_id": "prompt-atomic",
            "response_id": "resp-atomic", "answer": "A mechanism answer.", "verdict": "sufficient",
            "rubric_results": [{"criterion": "cause", "passed": True}],
            "evidence": [
                {"event_id": "duplicate-evidence", "evidence_type": "checkpoint-answer", "level_candidate": 3, "confidence": "medium", "dimensions": ["mechanism"], "rubric": "First"},
                {"event_id": "duplicate-evidence", "evidence_type": "checkpoint-answer", "level_candidate": 3, "confidence": "medium", "dimensions": ["mechanism"], "rubric": "Second"},
            ],
        }
        path = self.write_event(answer_route, "invalid-evidence.json", event)
        rejected = self.run_cli("commit", "--workspace", os.fspath(self.workspace), "--route-id", answer_route["route_id"], "--event", os.fspath(path), expected=2)
        self.assertEqual("DUPLICATE_EVIDENCE", rejected["error"])
        self.assertEqual(evidence_before, evidence_path.read_bytes())
        self.assertEqual(profile_before, profile_path.read_bytes())
        verified = self.run_cli("verify-route", "--workspace", os.fspath(self.workspace), "--route-id", answer_route["route_id"], "--target", "paper-reader")
        self.assertEqual("issued", verified["status"])

    def test_confirmation_route_can_install_a_revised_guide(self) -> None:
        self.initialize()
        paper_id, paper_dir = self.ingest_fixture("Revision Paper")
        self.install_guide(paper_id, paper_dir)
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("confirmation", route["mode"])
        source_map = yaml.safe_load((paper_dir / "ingest" / "source-map.yaml").read_text(encoding="utf-8"))
        anchors = [item["id"] for item in source_map["anchors"]]
        first, second = anchors[:2]
        run = self.workspace / route["run_dir"] / "revision"
        run.mkdir(parents=True)
        (run / "overview.md").write_text("# Revised overview\n", encoding="utf-8")
        (run / "claim.yaml").write_text(yaml.safe_dump({"schema_version": 1, "claims": [{"id": "C01", "kind": "author-claim", "statement": "Revised claim", "source_anchors": [first], "supported_by": [], "assumptions": [], "limitations": []}]}), encoding="utf-8")
        nodes = [
            {"id": "N01", "concept_id": "architecture.flex_mode", "title": "Flexible mode", "type": "mechanism", "tree_parent": None, "requires": {"hard": [], "soft": []}, "objective": "Explain the revised mechanism.", "order": 1, "source_anchors": [first], "mastery_contract": {"must_show": ["causal chain"], "probes": ["reconstruct"], "critical_errors": []}},
            {"id": "N02", "concept_id": "architecture.data_reuse", "title": "Reuse", "type": "tradeoff", "tree_parent": "N01", "requires": {"hard": ["N01"], "soft": []}, "objective": "Apply reuse.", "order": 2, "source_anchors": [second], "mastery_contract": {"must_show": ["boundary"], "probes": ["transfer"], "critical_errors": []}},
        ]
        (run / "map.yaml").write_text(yaml.safe_dump({"schema_version": 1, "nodes": nodes}), encoding="utf-8")
        (run / "plan.yaml").write_text(yaml.safe_dump({"schema_version": 1, "paper_id": paper_id, "plan_revision": 2, "units": [{"id": "U01", "title": "Revised", "required": True, "node_ids": ["N01", "N02"], "depends_on": [], "objective": "Revised", "source_anchors": [first], "exit_criteria": ["causal chain"]}]}), encoding="utf-8")
        result = self.commit(route, {"event_id": "ev-guide-revision", "type": "guide-installed", "overview": "revision/overview.md", "claim_map": "revision/claim.yaml", "knowledge_map": "revision/map.yaml", "reading_plan": "revision/plan.yaml", "prompt_id": "prompt-plan-002"})
        self.assertTrue(result["ok"])
        manifest = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual(2, manifest["reading"]["plan_revision"])
        self.assertIsNone(manifest["reading"]["confirmed_plan_revision"])
        self.assertEqual("confirmation", manifest["reading"]["next_route"]["mode"])

    def test_skip_is_bound_to_the_routed_node(self) -> None:
        self.initialize()
        paper_id, paper_dir = self.ingest_fixture("Skip Binding")
        self.install_guide(paper_id, paper_dir)
        self.confirm_plan(paper_id)
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("N01", route["context"]["node_id"])
        event = {"event_id": "ev-skip-wrong", "type": "node-skipped", "node_id": "N02", "response_id": "resp-skip-wrong", "reason": "I claim to know another node"}
        path = self.write_event(route, "wrong-skip.json", event)
        rejected = self.run_cli("commit", "--workspace", os.fspath(self.workspace), "--route-id", route["route_id"], "--event", os.fspath(path), expected=2)
        self.assertEqual("ROUTE_CONTEXT_MISMATCH", rejected["error"])
        manifest = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual("planned", manifest["reading"]["node_states"]["N02"]["status"])
        self.assertEqual("issued", self.run_cli("verify-route", "--workspace", os.fspath(self.workspace), "--route-id", route["route_id"], "--target", "paper-reader")["status"])

    def test_full_resumable_learning_remediation_and_profile_rebuild(self) -> None:
        self.initialize()
        paper_id, paper_dir = self.ingest_fixture()
        self.install_guide(paper_id, paper_dir)
        before = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("confirmation", before["mode"])
        self.run_cli("cancel-route", "--workspace", os.fspath(self.workspace), "--route-id", before["route_id"], "--reason", "test re-entry")
        self.confirm_plan(paper_id)
        self.present_and_answer(paper_id, 1, "sufficient")
        manifest = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual("provisional", manifest["reading"]["node_states"]["N01"]["status"])
        profile_after_checkpoint = yaml.safe_load((self.workspace / "cognitive-profile" / "profile.yaml").read_text(encoding="utf-8"))
        self.assertEqual(2, profile_after_checkpoint["domains"]["architecture"]["concepts"]["flex_mode"]["level"])
        evidence_after_checkpoint = [json.loads(line) for line in (self.workspace / "cognitive-profile" / "evidence.jsonl").read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual("provisional", evidence_after_checkpoint[-1]["node_state_after"])
        self.present_and_answer(paper_id, 2, "transfer")

        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("paper-grill", route["target_skill"])
        run = self.workspace / route["run_dir"]
        source_hash = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))["provenance"]["source_sha256"]
        source_map = yaml.safe_load((paper_dir / "ingest" / "source-map.yaml").read_text(encoding="utf-8"))
        anchor = source_map["anchors"][0]["id"]
        questions = {
            "schema_version": 1,
            "paper_id": paper_id,
            "mode": "full",
            "plan_revision": 1,
            "source_sha256": source_hash,
            "questions": [
                {"id": "Q01", "text": "Reconstruct the flexible mode.", "node_ids": ["N01"], "source_anchors": [anchor], "expected_points": ["causal chain"], "critical_errors": [], "required": True},
                {"id": "Q02", "text": "Apply the reuse tradeoff.", "node_ids": ["N02"], "source_anchors": [anchor], "expected_points": ["boundary"], "critical_errors": ["always better"], "required": True},
            ],
        }
        (run / "questions.yaml").write_text(yaml.safe_dump(questions, sort_keys=False), encoding="utf-8")
        self.commit(route, {"event_id": "ev-grill-start-1", "type": "grill-started", "mode": "full", "questions": "questions.yaml", "prompt_id": "prompt-q1"})
        for index, prompt in ((1, "prompt-q1"), (2, "prompt-q2")):
            resume = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
            event = {"event_id": f"ev-grill-answer-{index}", "type": "grill-answer-recorded", "prompt_id": prompt, "answer_id": f"answer-{index}", "answer": "Closed-book response."}
            if index == 1:
                event["next_prompt_id"] = "prompt-q2"
            self.commit(resume, event)
        diagnosis_route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        run = self.workspace / diagnosis_route["run_dir"]
        (run / "diagnosis.md").write_text("# Diagnosis\n\nN02 has a boundary misconception.\n", encoding="utf-8")
        self.commit(
            diagnosis_route,
            {
                "event_id": "ev-diagnosis-1",
                "type": "grill-diagnosed",
                "diagnosis": "diagnosis.md",
                "verdicts": [
                    {"node_id": "N01", "verdict": "sufficient", "answer_id": "answer-1", "evidence": [{"evidence_type": "grill-answer", "level_candidate": 3, "confidence": "high", "dimensions": ["mechanism"], "rubric": "Closed-book mechanism reconstruction"}]},
                    {"node_id": "N02", "verdict": "misconception", "answer_id": "answer-2", "evidence": [{"evidence_type": "grill-answer", "level_candidate": 0, "confidence": "high", "dimensions": [], "rubric": "Critical boundary error"}]},
                ],
                "remediation_targets": [{"id": "R01", "node_id": "N02", "diagnosis": "Boundary condition is missing.", "answer_id": "answer-2"}],
            },
        )
        remediation = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        run = self.workspace / remediation["run_dir"]
        (run / "remediation.md").write_text("# Boundary remediation\n\n## Checkpoint\nApply the boundary.\n", encoding="utf-8")
        self.commit(remediation, {"event_id": "ev-rem-present", "type": "remediation-presented", "target_id": "R01", "unit_artifact": "remediation.md", "prompt_id": "prompt-rem"})
        rem_answer = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.commit(
            rem_answer,
            {"event_id": "ev-rem-answer", "type": "answer-recorded", "prompt_id": "prompt-rem", "response_id": "resp-rem", "answer": "The tradeoff changes at the capacity boundary.", "verdict": "sufficient", "rubric_results": [{"criterion": "boundary", "passed": True}], "evidence": [{"evidence_type": "remediation-answer", "level_candidate": 3, "confidence": "medium", "dimensions": ["mechanism"], "rubric": "Explained the missing boundary"}]},
        )
        remediated_manifest = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual("provisional", remediated_manifest["reading"]["node_states"]["N02"]["status"])

        targeted = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        run = self.workspace / targeted["run_dir"]
        targeted_questions = {
            "schema_version": 1,
            "paper_id": paper_id,
            "mode": "targeted",
            "plan_revision": 1,
            "source_sha256": source_hash,
            "target_ids": ["R01"],
            "questions": [{"id": "T01", "text": "Transfer the boundary.", "node_ids": ["N02"], "source_anchors": [anchor], "expected_points": ["new context"], "critical_errors": [], "required": True}],
        }
        (run / "questions.yaml").write_text(yaml.safe_dump(targeted_questions, sort_keys=False), encoding="utf-8")
        self.commit(targeted, {"event_id": "ev-target-start", "type": "grill-started", "mode": "targeted", "questions": "questions.yaml", "prompt_id": "prompt-t1"})
        targeted_answer = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.commit(targeted_answer, {"event_id": "ev-target-answer", "type": "grill-answer-recorded", "prompt_id": "prompt-t1", "answer_id": "answer-t1", "answer": "Transfer response with a new capacity boundary."})
        after_targeted_answer = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual("targeted", after_targeted_answer["reading"]["next_route"]["mode"])
        self.assertEqual("diagnose", after_targeted_answer["reading"]["next_route"]["operation"])
        targeted_diagnosis = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("targeted", targeted_diagnosis["mode"])
        run = self.workspace / targeted_diagnosis["run_dir"]
        (run / "diagnosis.md").write_text("# Targeted diagnosis\n\nBoundary transfer passed.\n", encoding="utf-8")
        self.commit(
            targeted_diagnosis,
            {"event_id": "ev-target-diagnosis", "type": "grill-diagnosed", "diagnosis": "diagnosis.md", "verdicts": [{"node_id": "N02", "verdict": "transfer", "answer_id": "answer-t1", "evidence": [{"evidence_type": "targeted-grill", "level_candidate": 4, "confidence": "high", "dimensions": ["mechanism", "transfer"], "rubric": "Transferred the corrected boundary model"}]}]},
        )
        final = self.run_cli("inspect", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("complete", final["paper"]["reading"]["phase"])
        self.assertEqual("complete", final["paper"]["reading"]["outcome"])
        final_profile = yaml.safe_load((self.workspace / "cognitive-profile" / "profile.yaml").read_text(encoding="utf-8"))
        self.assertEqual(4, final_profile["domains"]["architecture"]["concepts"]["data_reuse"]["level"])
        profile_before = (self.workspace / "cognitive-profile" / "profile.yaml").read_bytes()
        self.run_cli("rebuild-profile", "--workspace", os.fspath(self.workspace))
        self.assertEqual(profile_before, (self.workspace / "cognitive-profile" / "profile.yaml").read_bytes())

    def test_cycle_is_rejected_without_consuming_route(self) -> None:
        self.initialize()
        paper_id, paper_dir = self.ingest_fixture("Cycle Paper")
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        source_map = yaml.safe_load((paper_dir / "ingest" / "source-map.yaml").read_text(encoding="utf-8"))
        anchor = source_map["anchors"][0]["id"]
        run = self.workspace / route["run_dir"]
        (run / "overview.md").write_text("# Overview", encoding="utf-8")
        (run / "claim.yaml").write_text(yaml.safe_dump({"schema_version": 1, "claims": [{"id": "C1", "kind": "author-claim", "statement": "Claim", "source_anchors": [anchor], "supported_by": [], "assumptions": [], "limitations": []}]}), encoding="utf-8")
        nodes = []
        for node_id, dependency in (("N1", "N2"), ("N2", "N1")):
            nodes.append({"id": node_id, "concept_id": f"cycle.{node_id.lower()}", "title": node_id, "type": "mechanism", "tree_parent": None, "requires": {"hard": [dependency], "soft": []}, "objective": "Explain cycle.", "order": 1, "source_anchors": [anchor], "mastery_contract": {"must_show": ["x"], "probes": ["reconstruct"], "critical_errors": []}})
        (run / "map.yaml").write_text(yaml.safe_dump({"schema_version": 1, "nodes": nodes}), encoding="utf-8")
        (run / "plan.yaml").write_text(yaml.safe_dump({"schema_version": 1, "paper_id": paper_id, "plan_revision": 1, "units": [{"id": "U1", "title": "Cycle", "required": True, "node_ids": ["N1", "N2"], "depends_on": [], "objective": "Cycle", "source_anchors": [anchor], "exit_criteria": ["x"]}]}), encoding="utf-8")
        event = {"event_id": "ev-cycle", "type": "guide-installed", "overview": "overview.md", "claim_map": "claim.yaml", "knowledge_map": "map.yaml", "reading_plan": "plan.yaml", "prompt_id": "prompt-cycle"}
        path = self.write_event(route, "cycle.json", event)
        failed = self.run_cli("commit", "--workspace", os.fspath(self.workspace), "--route-id", route["route_id"], "--event", os.fspath(path), expected=2)
        self.assertEqual("DEPENDENCY_CYCLE", failed["error"])
        manifest = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual(1, manifest["reading"]["revision"])
        self.assertFalse((paper_dir / "guide" / "overview.md").exists())
        self.assertNotIn("ev-cycle", (paper_dir / "reading" / "events.jsonl").read_text(encoding="utf-8"))
        self.assertFalse((self.workspace / ".paper-companion" / "transactions" / "ev-cycle.yaml").exists())
        verified = self.run_cli("verify-route", "--workspace", os.fspath(self.workspace), "--route-id", route["route_id"], "--target", "paper-guide")
        self.assertEqual("issued", verified["status"])

    def test_same_source_ingest_repair_preserves_learning_records(self) -> None:
        self.initialize()
        paper_id, paper_dir = self.ingest_fixture("Repair Paper")
        self.install_guide(paper_id, paper_dir)
        self.confirm_plan(paper_id)
        self.present_and_answer(paper_id, 1, "sufficient")
        note = paper_dir / "notes" / "learner.md"
        note.write_text("preserve my note", encoding="utf-8")
        assessment = paper_dir / "assessment" / "manual.txt"
        assessment.write_text("preserve assessment", encoding="utf-8")
        responses_before = (paper_dir / "reading" / "responses.jsonl").read_bytes()
        evidence_before = (self.workspace / "cognitive-profile" / "evidence.jsonl").read_bytes()
        profile_before = (self.workspace / "cognitive-profile" / "profile.yaml").read_bytes()
        restored_markdown = "# Fixture Paper\n\n## Method\n\nA deterministic fixture body with enough text for validation.\n"
        (paper_dir / "paper.md").write_text("", encoding="utf-8")

        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("paper-ingest", route["target_skill"])
        self.assertEqual("repair", route["mode"])
        manifest_before = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual(manifest_before["provenance"]["source_sha256"], route["input_sha256"])
        run = self.workspace / route["run_dir"] / "repair"
        run.mkdir(parents=True)
        (run / "paper.md").write_text(restored_markdown, encoding="utf-8")
        (run / "metadata.json").write_text(json.dumps({"title": "Repair Paper"}), encoding="utf-8")
        (run / "source-map.yaml").write_text((paper_dir / "ingest" / "source-map.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        result = self.commit(route, {
            "event_id": "ev-ingest-repair", "type": "ingest-completed", "title": "Repair Paper",
            "parsed_markdown": "repair/paper.md", "metadata": "repair/metadata.json",
            "source_map": "repair/source-map.yaml", "parser": {"name": "fixture", "version": "2"},
        })
        self.assertTrue(result["repaired"])
        self.assertEqual(restored_markdown, (paper_dir / "paper.md").read_text(encoding="utf-8"))
        self.assertEqual("preserve my note", note.read_text(encoding="utf-8"))
        self.assertEqual("preserve assessment", assessment.read_text(encoding="utf-8"))
        self.assertEqual(responses_before, (paper_dir / "reading" / "responses.jsonl").read_bytes())
        self.assertEqual(evidence_before, (self.workspace / "cognitive-profile" / "evidence.jsonl").read_bytes())
        self.assertEqual(profile_before, (self.workspace / "cognitive-profile" / "profile.yaml").read_bytes())
        repaired_manifest = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual("read", repaired_manifest["reading"]["phase"])
        self.assertEqual("provisional", repaired_manifest["reading"]["node_states"]["N01"]["status"])
        next_route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        self.assertEqual("paper-reader", next_route["target_skill"])
        self.assertEqual("N02", next_route["context"]["node_id"])

    def test_same_source_repair_with_incompatible_anchors_fails_closed_to_guide(self) -> None:
        self.initialize()
        paper_id, paper_dir = self.ingest_fixture("Anchor Drift")
        self.install_guide(paper_id, paper_dir)
        self.confirm_plan(paper_id)
        (paper_dir / "paper.md").write_text("", encoding="utf-8")
        route = self.run_cli("next", "--workspace", os.fspath(self.workspace), "--paper", paper_id)
        source_hash = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))["provenance"]["source_sha256"]
        run = self.workspace / route["run_dir"] / "repair"
        run.mkdir(parents=True)
        (run / "paper.md").write_text("# A structurally different extraction\n\nEnough deterministic body text to pass the quality gate while changing all anchors.\n", encoding="utf-8")
        (run / "metadata.json").write_text("{}", encoding="utf-8")
        (run / "source-map.yaml").write_text(yaml.safe_dump({"schema_version": 1, "source_sha256": source_hash, "anchors": [{"id": "replacement-body", "kind": "body", "occurrence": 1, "page": None}]}), encoding="utf-8")
        result = self.commit(route, {"event_id": "ev-anchor-repair", "type": "ingest-completed", "title": "Anchor Drift", "parsed_markdown": "repair/paper.md", "metadata": "repair/metadata.json", "source_map": "repair/source-map.yaml", "parser": {"name": "fixture", "version": "2"}})
        self.assertFalse(result["guide_compatible"])
        manifest = yaml.safe_load((paper_dir / "paper.yaml").read_text(encoding="utf-8"))
        self.assertEqual("guide", manifest["reading"]["phase"])
        self.assertIsNone(manifest["reading"]["confirmed_plan_revision"])
        self.assertTrue(all(state["status"] == "stale" for state in manifest["reading"]["node_states"].values()))
        self.assertEqual("paper-guide", manifest["reading"]["next_route"]["target"])
        self.assertEqual("repair", manifest["reading"]["next_route"]["mode"])

    def test_markdown_status_projects_pending_confirmation_for_a_learner(self) -> None:
        self.initialize()
        paper_id, paper_dir = self.ingest_fixture("Status Paper")
        self.install_guide(paper_id, paper_dir)
        rendered = self.run_cli_text("inspect", "--workspace", os.fspath(self.workspace), "--paper", paper_id, "--format", "markdown")
        self.assertIn("## 学习目标", rendered)
        self.assertIn("Explain and transfer the mechanism.", rendered)
        self.assertIn("## 学习进度", rendered)
        self.assertIn("图例：✓ 已掌握 · ◐ 初步掌握 · ▶ 学习中 · ! 待补缺口 · ○ 待开始 · ↷ 已跳过 · ↺ 需重学", rendered)
        self.assertIn("○ Flexible mode", rendered)
        self.assertIn("└─ ○ Data reuse tradeoff", rendered)
        self.assertIn("论文拆解和学习路线已经准备好，但还需要你确认是否按这条路线学习。", rendered)
        self.assertEqual(1, rendered.count("## 现在只做一件事"))
        self.assertTrue(rendered.rstrip().endswith("请回复：确认按这套 2 节点路线开始学习。"))
        for hidden in (paper_id, "N01", "N02", "schema_version", "source_sha256", "当前阶段", "confirmation", "the reading plan awaits confirmation"):
            with self.subTest(hidden=hidden):
                self.assertNotIn(hidden, rendered)

    def test_markdown_status_projects_progress_and_one_next_action(self) -> None:
        self.initialize()
        paper_id, paper_dir = self.ingest_fixture("Progress Paper")
        self.install_guide(paper_id, paper_dir)
        self.confirm_plan(paper_id)
        self.present_and_answer(paper_id, 1, "sufficient")
        rendered = self.run_cli_text("inspect", "--workspace", os.fspath(self.workspace), "--paper", paper_id, "--format", "markdown")
        self.assertIn("进度：已掌握 0/2；◐ 初步掌握 1 · ○ 待开始 1。", rendered)
        self.assertIn("◐ Flexible mode", rendered)
        self.assertIn("└─ ○ Data reuse tradeoff", rendered)
        self.assertIn("“Data reuse tradeoff”的前置内容已经达到继续学习的条件，现在轮到这个节点。", rendered)
        self.assertEqual(1, rendered.count("## 现在只做一件事"))
        self.assertTrue(rendered.rstrip().endswith("请开始学习“Data reuse tradeoff”。"))
        for hidden in (paper_id, "N01", "N02", "schema_version", "source_sha256", "当前阶段", "paper-reader", "the next prerequisite-ready knowledge node is unfinished"):
            with self.subTest(hidden=hidden):
                self.assertNotIn(hidden, rendered)


if __name__ == "__main__":
    unittest.main()
