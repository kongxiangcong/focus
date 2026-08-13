from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .contracts import (
    NODE_STATUSES,
    REMEDIATION_STATUSES,
    VERDICTS,
    contract_hash,
    load_guide_contracts,
    validate_claim_map,
    validate_knowledge_map,
    validate_question_set,
    validate_reading_plan,
    validate_source_map,
)
from .engine import load_route, verify_route
from .errors import FocusError
from .storage import (
    EVIDENCE_SCHEMA,
    atomic_write_text,
    atomic_write_yaml,
    ensure_list,
    ensure_nonempty_text,
    load_json_or_yaml,
    load_yaml,
    now_iso,
    portable_relative,
    read_jsonl,
    require_within,
    resolve_relative,
    sha256_value,
    validate_identifier,
    workspace_paths,
)
from .transaction import (
    copy_file,
    event_ledger_path,
    interview_ledger_path,
    prepare_transaction,
    repair_ingest,
    register_ingest,
    response_ledger_path,
    stage_path,
    transaction_path,
    finish_transaction,
)
from .workspace import load_paper


EVENT_TYPES = {
    "ingest-completed",
    "guide-installed",
    "plan-confirmed",
    "unit-presented",
    "answer-recorded",
    "self-reported",
    "node-skipped",
    "grill-started",
    "grill-answer-recorded",
    "grill-diagnosed",
    "remediation-presented",
}


def _event_header(event: dict[str, Any], event_type: str, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event_id": event["event_id"],
        "event_type": event_type,
        "paper_id": manifest["paper_id"],
        "recorded_at": now_iso(),
    }


def _require_route(route: dict[str, Any], target: str, modes: set[str] | None = None) -> None:
    if route.get("target_skill") != target:
        raise FocusError("ROUTE_TARGET_MISMATCH", "Event is not authorized for this stage", expected=route.get("target_skill"), actual=target)
    if modes is not None and route.get("mode") not in modes:
        raise FocusError("ROUTE_MODE_MISMATCH", "Event is not authorized in this route mode", mode=route.get("mode"), allowed=sorted(modes))


def _full_contract_hash(node: dict[str, Any]) -> str:
    return contract_hash(node)


def _find_node(nodes: dict[str, dict[str, Any]], node_id: object) -> tuple[str, dict[str, Any]]:
    identifier = validate_identifier(node_id, "node_id")
    if identifier not in nodes:
        raise FocusError("UNKNOWN_KNOWLEDGE_NODE", "Event references an unknown knowledge node", node_id=identifier)
    return identifier, nodes[identifier]


def _unit_nodes(units: dict[str, dict[str, Any]], unit_id: str) -> list[str]:
    if unit_id not in units:
        raise FocusError("UNKNOWN_READING_UNIT", "Event references an unknown reading unit", unit_id=unit_id)
    return [str(item) for item in units[unit_id].get("node_ids", [])]


def _refresh_completed_units(reading: dict[str, Any], units: dict[str, dict[str, Any]]) -> None:
    satisfied = {"provisional", "mastered", "skipped"}
    states = reading.get("node_states", {})
    reading["completed_units"] = sorted(
        unit_id
        for unit_id, unit in units.items()
        if all(states.get(str(node_id), {}).get("status") in satisfied for node_id in unit.get("node_ids", []))
    )


def _source_ref(workspace: Path, ledger: Path, record_id: str) -> str:
    return f"{portable_relative(ledger, workspace)}#{record_id}"


def _evidence_rows(
    *,
    event: dict[str, Any],
    manifest: dict[str, Any],
    node: dict[str, Any],
    verdict: str,
    node_state_after: str,
    source_artifact: str,
    candidates: object,
) -> list[dict[str, Any]]:
    raw = ensure_list(candidates, "evidence")
    if node_state_after not in NODE_STATUSES:
        raise FocusError("INVALID_NODE_STATE", "State service produced an unsupported post-evidence node state", status=node_state_after)
    if verdict in {"sufficient", "transfer"} and not raw:
        raise FocusError("EVIDENCE_REQUIRED", "A positive semantic verdict requires an evidence candidate")
    result: list[dict[str, Any]] = []
    for index, candidate in enumerate(raw, 1):
        if not isinstance(candidate, dict):
            raise FocusError("INVALID_EVIDENCE", "Evidence candidate must be an object", index=index)
        concept_id = str(node["concept_id"])
        if candidate.get("concept_id", concept_id) != concept_id:
            raise FocusError("CONCEPT_MISMATCH", "Evidence concept does not match the assessed node", expected=concept_id, actual=candidate.get("concept_id"))
        evidence_verdict = candidate.get("verdict", verdict)
        if evidence_verdict != verdict:
            raise FocusError("VERDICT_MISMATCH", "Evidence verdict must match the route-bound assessment", expected=verdict, actual=evidence_verdict)
        evidence_type = ensure_nonempty_text(candidate.get("evidence_type"), "evidence.evidence_type")
        level = candidate.get("level_candidate")
        if not isinstance(level, int) or not 0 <= level <= 4:
            raise FocusError("INVALID_EVIDENCE", "Evidence level_candidate must be 0 through 4")
        dimensions = [str(item) for item in ensure_list(candidate.get("dimensions", []), "evidence.dimensions")]
        if level >= 3 and "mechanism" not in dimensions:
            raise FocusError("LEVEL_GATE_FAILED", "Level 3+ evidence requires the mechanism dimension")
        if level == 4 and verdict != "transfer":
            raise FocusError("LEVEL_GATE_FAILED", "Level 4 evidence requires transfer")
        default_id = f"evidence-{sha256_value({'event_id': event['event_id'], 'node_id': node['id'], 'index': index})[:24]}"
        result.append(
            {
                "schema_version": EVIDENCE_SCHEMA,
                "event_id": validate_identifier(candidate.get("event_id", default_id), "evidence.event_id"),
                "paper_id": manifest["paper_id"],
                "concept_id": concept_id,
                "node_id": node["id"],
                "evidence_type": evidence_type,
                "verdict": verdict,
                "level_candidate": level,
                "confidence": candidate.get("confidence", "medium"),
                "dimensions": dimensions,
                "source_artifact": source_artifact,
                "rubric": ensure_nonempty_text(candidate.get("rubric"), "evidence.rubric"),
                "contract_hash": _full_contract_hash(node),
                "node_state_after": node_state_after,
                "map_revision": manifest["reading"]["map_revision"],
                "recorded_at": now_iso(),
                "supersedes": candidate.get("supersedes"),
            }
        )
    return result


def _self_report_evidence(event: dict[str, Any], manifest: dict[str, Any], node: dict[str, Any], source: str, node_state_after: str) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "event_id": f"{event['event_id']}-e1",
        "paper_id": manifest["paper_id"],
        "concept_id": node["concept_id"],
        "node_id": node["id"],
        "evidence_type": "self-report",
        "verdict": "self-reported",
        "level_candidate": 0,
        "confidence": "low",
        "dimensions": [],
        "source_artifact": source,
        "rubric": "Learner reported familiarity without an observable mastery response",
        "contract_hash": _full_contract_hash(node),
        "node_state_after": node_state_after,
        "map_revision": manifest["reading"]["map_revision"],
        "recorded_at": now_iso(),
        "supersedes": None,
    }


def _install_text(source: Path, destination: Path, history_dir: Path | None = None) -> None:
    text = source.read_text(encoding="utf-8")
    if destination.exists() and destination.read_text(encoding="utf-8") != text and history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        backup = history_dir / destination.name
        if not backup.exists():
            atomic_write_text(backup, destination.read_text(encoding="utf-8"))
    atomic_write_text(destination, text)


def _guide_installed(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-guide", {"normal", "repair", "confirmation"})
    overview_path = stage_path(workspace, route, event.get("overview"), "overview")
    claim_path = stage_path(workspace, route, event.get("claim_map"), "claim_map")
    map_path = stage_path(workspace, route, event.get("knowledge_map"), "knowledge_map")
    plan_path = stage_path(workspace, route, event.get("reading_plan"), "reading_plan")
    source_map = load_yaml(paper_dir / manifest["artifacts"]["source_map"])
    anchors = validate_source_map(source_map, manifest["provenance"]["source_sha256"])
    claims = load_yaml(claim_path)
    validate_claim_map(claims, anchors)
    knowledge_map = load_yaml(map_path)
    nodes = validate_knowledge_map(knowledge_map, anchors)
    next_plan_revision = int(manifest["reading"]["plan_revision"]) + 1
    plan = load_yaml(plan_path)
    units = validate_reading_plan(plan, manifest["paper_id"], set(nodes), anchors, next_plan_revision)
    history = paper_dir / "guide" / "history" / f"revision-{manifest['reading']['plan_revision']}"
    _install_text(overview_path, paper_dir / manifest["artifacts"]["overview"], history)
    _install_text(claim_path, paper_dir / manifest["artifacts"]["claim_map"], history)
    _install_text(map_path, paper_dir / manifest["artifacts"]["knowledge_map"], history)
    _install_text(plan_path, paper_dir / manifest["artifacts"]["reading_plan"], history)

    reading = manifest["reading"]
    previous_states = reading.get("node_states", {})
    new_states: dict[str, Any] = {}
    for node_id, node in nodes.items():
        fingerprint = _full_contract_hash(node)
        old = previous_states.get(node_id, {})
        if old.get("contract_hash") == fingerprint:
            new_states[node_id] = deepcopy(old)
        else:
            new_states[node_id] = {
                "status": "stale" if old else "planned",
                "contract_hash": fingerprint,
                "last_event_id": event["event_id"],
            }
    reading.update(
        {
            "phase": "guide",
            "status": "awaiting-user",
            "plan_revision": next_plan_revision,
            "map_revision": int(reading["map_revision"]) + 1,
            "confirmed_plan_revision": None,
            "node_states": new_states,
            "completed_units": [],
            "current_unit": None,
            "current_question": None,
            "assessment_mode": None,
            "assessment_file": None,
            "remediation_targets": [],
            "pending_interaction": {
                "kind": "plan-confirmation",
                "prompt_id": validate_identifier(event.get("prompt_id"), "prompt_id"),
                "plan_revision": next_plan_revision,
            },
            "outcome": None,
        }
    )
    if event.get("learning_goal"):
        goal = event["learning_goal"]
        if not isinstance(goal, dict) or goal.get("mode") not in {"scout", "study", "mastery", "overview", "deep_understanding", "reproduction", "critique", "research_extension"}:
            raise FocusError("INVALID_LEARNING_GOAL", "Unsupported learning goal")
        manifest["learning_goal"] = goal
        mode = str(goal.get("mode"))
        manifest["reading_mode"] = {
            "overview": "scout",
            "critique": "study",
            "deep_understanding": "mastery",
            "reproduction": "mastery",
            "research_extension": "study",
        }.get(mode, mode)
    row = {**_event_header(event, "guide-installed", manifest), "plan_revision": next_plan_revision, "node_count": len(nodes), "unit_count": len(units)}
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row])


def _plan_confirmed(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-guide", {"confirmation"})
    reading = manifest["reading"]
    pending = reading.get("pending_interaction")
    if not isinstance(pending, dict) or pending.get("kind") != "plan-confirmation":
        raise FocusError("NO_PLAN_CONFIRMATION_PENDING", "No reading plan confirmation is pending")
    requested = event.get("plan_revision")
    if requested != reading["plan_revision"] or pending.get("plan_revision") != requested:
        raise FocusError("PLAN_REVISION_MISMATCH", "Confirmation does not match the current plan revision")
    reading.update({"phase": "read", "status": "ready", "confirmed_plan_revision": requested, "pending_interaction": None})
    row = {**_event_header(event, "plan-confirmed", manifest), "plan_revision": requested}
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row])


def _unit_presented(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-reader", {"normal"})
    _, nodes, units = load_guide_contracts(paper_dir, manifest)
    node_id, _ = _find_node(nodes, event.get("node_id"))
    unit_id = validate_identifier(event.get("unit_id"), "unit_id")
    if node_id not in _unit_nodes(units, unit_id):
        raise FocusError("UNIT_NODE_MISMATCH", "The routed node is not part of this unit")
    context = route.get("context", {})
    if context.get("node_id") != node_id or context.get("unit_id") != unit_id:
        raise FocusError("ROUTE_CONTEXT_MISMATCH", "Event does not match the node selected by ask-paper")
    artifact = stage_path(workspace, route, event.get("unit_artifact"), "unit_artifact")
    _install_text(artifact, paper_dir / "reading" / "units" / f"{unit_id}.md")
    prompt_id = validate_identifier(event.get("prompt_id"), "prompt_id")
    reading = manifest["reading"]
    reading["node_states"][node_id].update({"status": "learning", "last_event_id": event["event_id"]})
    reading.update(
        {
            "phase": "read",
            "status": "awaiting-user",
            "current_unit": unit_id,
            "pending_interaction": {
                "kind": "unit-checkpoint",
                "prompt_id": prompt_id,
                "unit_id": unit_id,
                "node_id": node_id,
                "plan_revision": reading["plan_revision"],
            },
        }
    )
    row = {**_event_header(event, "unit-presented", manifest), "unit_id": unit_id, "node_id": node_id, "prompt_id": prompt_id}
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row])


def _answer_recorded(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-reader", {"resume", "remediation"})
    anchors, nodes, units = load_guide_contracts(paper_dir, manifest)
    reading = manifest["reading"]
    pending = reading.get("pending_interaction")
    if not isinstance(pending, dict) or pending.get("kind") not in {"unit-checkpoint", "remediation-checkpoint"}:
        raise FocusError("NO_CHECKPOINT_PENDING", "No reader checkpoint is waiting for an answer")
    prompt_id = validate_identifier(event.get("prompt_id"), "prompt_id")
    if prompt_id != pending.get("prompt_id"):
        raise FocusError("PROMPT_MISMATCH", "Answer does not match the persisted checkpoint")
    response_id = validate_identifier(event.get("response_id"), "response_id")
    answer = ensure_nonempty_text(event.get("answer"), "answer")
    verdict = event.get("verdict")
    if verdict not in VERDICTS:
        raise FocusError("INVALID_VERDICT", "Unsupported checkpoint verdict", verdict=verdict)
    rubric_results = ensure_list(event.get("rubric_results"), "rubric_results")
    if verdict in {"sufficient", "transfer"} and not rubric_results:
        raise FocusError("RUBRIC_REQUIRED", "A positive verdict needs itemized rubric results")
    response = {
        "schema_version": 1,
        "response_id": response_id,
        "event_id": event["event_id"],
        "paper_id": manifest["paper_id"],
        "prompt_id": prompt_id,
        "answer": answer,
        "verdict": verdict,
        "rubric_results": rubric_results,
        "recorded_at": now_iso(),
    }
    source = _source_ref(workspace, response_ledger_path(paper_dir), response_id)
    if pending["kind"] == "unit-checkpoint":
        node_id, node = _find_node(nodes, pending.get("node_id"))
        unit_id = str(pending["unit_id"])
        status = {
            "no-evidence": "learning",
            "partial": "learning",
            "misconception": "needs-remediation",
            "sufficient": "provisional",
            "transfer": "mastered",
        }[str(verdict)]
        reading["node_states"][node_id].update({"status": status, "last_event_id": event["event_id"]})
        reading.update({"phase": "read", "status": "ready", "current_unit": None, "pending_interaction": None})
        _refresh_completed_units(reading, units)
        response.update({"interaction_kind": "unit-checkpoint", "unit_id": unit_id, "node_id": node_id})
    else:
        target_id = str(pending["target_id"])
        target = next((item for item in reading["remediation_targets"] if item.get("id") == target_id), None)
        if target is None:
            raise FocusError("UNKNOWN_REMEDIATION_TARGET", "Pending remediation target no longer exists", target_id=target_id)
        node_id, node = _find_node(nodes, target.get("node_id"))
        positive = verdict in {"sufficient", "transfer"}
        target["status"] = "ready-for-regrill" if positive else "pending"
        target["last_event_id"] = event["event_id"]
        status = "provisional" if positive else "needs-remediation"
        reading["node_states"][node_id].update({"status": status, "last_event_id": event["event_id"]})
        reading.update({"phase": "remediate", "status": "ready", "pending_interaction": None})
        response.update({"interaction_kind": "remediation-checkpoint", "target_id": target_id, "node_id": node_id})
    evidence = _evidence_rows(
        event=event,
        manifest=manifest,
        node=node,
        verdict=str(verdict),
        node_state_after=status,
        source_artifact=source,
        candidates=event.get("evidence", []),
    )
    row = {**_event_header(event, "answer-recorded", manifest), "response_id": response_id, "verdict": verdict, "node_id": node_id}
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row], response_rows=[response], evidence_rows=evidence)


def _self_reported(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-reader", {"resume", "remediation"})
    _, nodes, _ = load_guide_contracts(paper_dir, manifest)
    pending = manifest["reading"].get("pending_interaction")
    if not isinstance(pending, dict) or pending.get("kind") not in {"unit-checkpoint", "remediation-checkpoint"}:
        raise FocusError("NO_CHECKPOINT_PENDING", "Self-report requires a persisted checkpoint")
    prompt_id = validate_identifier(event.get("prompt_id"), "prompt_id")
    if prompt_id != pending.get("prompt_id"):
        raise FocusError("PROMPT_MISMATCH", "Self-report does not match the persisted checkpoint")
    response_id = validate_identifier(event.get("response_id"), "response_id")
    node_id = pending.get("node_id")
    if node_id is None and pending.get("target_id"):
        target = next((item for item in manifest["reading"]["remediation_targets"] if item.get("id") == pending["target_id"]), None)
        node_id = target.get("node_id") if target else None
    node_id, node = _find_node(nodes, node_id)
    response = {
        "schema_version": 1,
        "response_id": response_id,
        "event_id": event["event_id"],
        "paper_id": manifest["paper_id"],
        "prompt_id": prompt_id,
        "answer": ensure_nonempty_text(event.get("statement"), "statement"),
        "verdict": "self-reported",
        "node_id": node_id,
        "recorded_at": now_iso(),
    }
    source = _source_ref(workspace, response_ledger_path(paper_dir), response_id)
    state_after = str(manifest["reading"]["node_states"].get(node_id, {}).get("status", "planned"))
    evidence = [_self_report_evidence(event, manifest, node, source, state_after)]
    row = {**_event_header(event, "self-reported", manifest), "response_id": response_id, "node_id": node_id, "prompt_id": prompt_id}
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row], response_rows=[response], evidence_rows=evidence)


def _node_skipped(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-reader", {"normal", "resume"})
    _, nodes, units = load_guide_contracts(paper_dir, manifest)
    node_id, node = _find_node(nodes, event.get("node_id"))
    if route.get("context", {}).get("node_id") != node_id:
        raise FocusError("ROUTE_CONTEXT_MISMATCH", "Skip does not match the knowledge node authorized by this route", expected=route.get("context", {}).get("node_id"), actual=node_id)
    response_id = validate_identifier(event.get("response_id"), "response_id")
    reason = ensure_nonempty_text(event.get("reason"), "reason")
    reading = manifest["reading"]
    pending = reading.get("pending_interaction")
    if pending and pending.get("node_id") != node_id:
        raise FocusError("ROUTE_CONTEXT_MISMATCH", "Skip does not match the pending knowledge node")
    reading["node_states"][node_id].update({"status": "skipped", "last_event_id": event["event_id"]})
    reading.update({"phase": "read", "status": "ready", "current_unit": None, "pending_interaction": None})
    _refresh_completed_units(reading, units)
    response = {
        "schema_version": 1,
        "response_id": response_id,
        "event_id": event["event_id"],
        "paper_id": manifest["paper_id"],
        "answer": reason,
        "verdict": "skipped",
        "node_id": node_id,
        "recorded_at": now_iso(),
    }
    source = _source_ref(workspace, response_ledger_path(paper_dir), response_id)
    evidence = [
        {
            "schema_version": EVIDENCE_SCHEMA,
            "event_id": f"{event['event_id']}-e1",
            "paper_id": manifest["paper_id"],
            "concept_id": node["concept_id"],
            "node_id": node_id,
            "evidence_type": "skip",
            "verdict": "skipped",
            "level_candidate": 0,
            "confidence": "low",
            "dimensions": [],
            "source_artifact": source,
            "rubric": "Learner explicitly skipped this knowledge node",
            "contract_hash": _full_contract_hash(node),
            "node_state_after": "skipped",
            "map_revision": reading["map_revision"],
            "recorded_at": now_iso(),
            "supersedes": None,
        }
    ]
    row = {**_event_header(event, "node-skipped", manifest), "response_id": response_id, "node_id": node_id, "reason": reason}
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row], response_rows=[response], evidence_rows=evidence)


def _grill_started(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-grill", {"normal", "targeted"})
    assessment_mode = event.get("mode")
    expected_mode = "targeted" if route.get("mode") == "targeted" else "full"
    if assessment_mode != expected_mode:
        raise FocusError("ROUTE_MODE_MISMATCH", "Assessment mode does not match the route", expected=expected_mode, actual=assessment_mode)
    anchors, nodes, units = load_guide_contracts(paper_dir, manifest)
    question_path = stage_path(workspace, route, event.get("questions"), "questions")
    question_set = load_yaml(question_path)
    questions = validate_question_set(question_set, manifest, nodes, anchors, assessment_mode)
    if assessment_mode == "targeted":
        ready = {item["id"] for item in manifest["reading"]["remediation_targets"] if item.get("status") == "ready-for-regrill"}
        requested = set(map(str, question_set.get("target_ids", [])))
        if requested != ready:
            raise FocusError("REMEDIATION_TARGET_MISMATCH", "Targeted question set must cover exactly the ready targets", expected=sorted(ready), actual=sorted(requested))
    round_number = int(manifest["reading"]["assessment_round"]) + 1
    destination = paper_dir / "assessment" / f"questions-r{round_number}.yaml"
    _install_text(question_path, destination)
    first_question = next(iter(questions))
    prompt_id = validate_identifier(event.get("prompt_id"), "prompt_id")
    reading = manifest["reading"]
    reading.update(
        {
            "phase": "grill",
            "status": "awaiting-user",
            "assessment_round": round_number,
            "assessment_mode": assessment_mode,
            "assessment_file": portable_relative(destination, paper_dir),
            "current_question": first_question,
            "pending_interaction": {
                "kind": "grill-question",
                "assessment_mode": assessment_mode,
                "question_id": first_question,
                "prompt_id": prompt_id,
                "assessment_round": round_number,
            },
        }
    )
    row = {**_event_header(event, "grill-started", manifest), "assessment_round": round_number, "assessment_mode": assessment_mode, "question_id": first_question, "prompt_id": prompt_id}
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row])


def _grill_answer_recorded(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-grill", {"resume", "targeted"})
    reading = manifest["reading"]
    pending = reading.get("pending_interaction")
    if not isinstance(pending, dict) or pending.get("kind") != "grill-question":
        raise FocusError("NO_GRILL_QUESTION_PENDING", "No frozen grill question is waiting for an answer")
    prompt_id = validate_identifier(event.get("prompt_id"), "prompt_id")
    if prompt_id != pending.get("prompt_id"):
        raise FocusError("PROMPT_MISMATCH", "Answer does not match the frozen grill question")
    answer_id = validate_identifier(event.get("answer_id"), "answer_id")
    answer = ensure_nonempty_text(event.get("answer"), "answer")
    question_id = str(pending["question_id"])
    question_set = load_yaml(paper_dir / str(reading["assessment_file"]))
    questions = question_set.get("questions", [])
    question_ids = [str(item["id"]) for item in questions]
    if question_id not in question_ids:
        raise FocusError("QUESTION_SET_MISMATCH", "Pending question is absent from frozen assessment")
    existing_answers = [row for row in read_jsonl(interview_ledger_path(paper_dir)) if row.get("assessment_round") == reading["assessment_round"]]
    answered = {str(row.get("question_id")) for row in existing_answers} | {question_id}
    remaining = [identifier for identifier in question_ids if identifier not in answered]
    interview = {
        "schema_version": 1,
        "answer_id": answer_id,
        "event_id": event["event_id"],
        "paper_id": manifest["paper_id"],
        "assessment_round": reading["assessment_round"],
        "assessment_mode": reading["assessment_mode"],
        "question_id": question_id,
        "prompt_id": prompt_id,
        "answer": answer,
        "recorded_at": now_iso(),
    }
    if remaining:
        next_prompt = validate_identifier(event.get("next_prompt_id"), "next_prompt_id")
        reading.update(
            {
                "status": "awaiting-user",
                "current_question": remaining[0],
                "pending_interaction": {
                    "kind": "grill-question",
                    "assessment_mode": reading["assessment_mode"],
                    "question_id": remaining[0],
                    "prompt_id": next_prompt,
                    "assessment_round": reading["assessment_round"],
                },
            }
        )
    else:
        reading.update({"status": "running", "current_question": None, "pending_interaction": None})
    row = {**_event_header(event, "grill-answer-recorded", manifest), "assessment_round": reading["assessment_round"], "question_id": question_id, "answer_id": answer_id}
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row], interview_rows=[interview])


def _grill_diagnosed(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-grill", {"normal", "targeted"})
    if route.get("context", {}).get("operation") != "diagnose":
        raise FocusError("ROUTE_CONTEXT_MISMATCH", "grill-diagnosed requires a diagnosis route")
    anchors, nodes, units = load_guide_contracts(paper_dir, manifest)
    reading = manifest["reading"]
    question_set = load_yaml(paper_dir / str(reading["assessment_file"]))
    round_answers = [row for row in read_jsonl(interview_ledger_path(paper_dir)) if row.get("assessment_round") == reading["assessment_round"]]
    answered = {str(row.get("question_id")) for row in round_answers}
    required_questions = {str(item["id"]) for item in question_set.get("questions", []) if item.get("required", True)}
    if required_questions - answered:
        raise FocusError("ASSESSMENT_INCOMPLETE", "Diagnosis cannot run before all required frozen questions are answered", questions=sorted(required_questions - answered))
    diagnosis_path = stage_path(workspace, route, event.get("diagnosis"), "diagnosis")
    destination = paper_dir / "assessment" / f"diagnosis-r{reading['assessment_round']}.md"
    _install_text(diagnosis_path, destination)
    verdict_items = ensure_list(event.get("verdicts"), "verdicts")
    verdict_by_node: dict[str, dict[str, Any]] = {}
    evidence_rows: list[dict[str, Any]] = []
    for item in verdict_items:
        if not isinstance(item, dict):
            raise FocusError("INVALID_DIAGNOSIS", "Each diagnosis verdict must be an object")
        node_id, node = _find_node(nodes, item.get("node_id"))
        if node_id in verdict_by_node:
            raise FocusError("DUPLICATE_IDENTIFIER", "Diagnosis contains duplicate node verdict", node_id=node_id)
        verdict = item.get("verdict")
        if verdict not in VERDICTS:
            raise FocusError("INVALID_VERDICT", "Diagnosis uses an unsupported verdict", node_id=node_id, verdict=verdict)
        answer_id = validate_identifier(item.get("answer_id"), "answer_id")
        if answer_id not in {str(row.get("answer_id")) for row in round_answers}:
            raise FocusError("EVIDENCE_SOURCE_MISSING", "Diagnosis cites an answer outside this frozen round", answer_id=answer_id)
        source = _source_ref(workspace, interview_ledger_path(paper_dir), answer_id)
        status = "mastered" if verdict in {"sufficient", "transfer"} else "needs-remediation"
        reading["node_states"][node_id].update({"status": status, "last_event_id": event["event_id"]})
        evidence_rows.extend(
            _evidence_rows(
                event=event,
                manifest=manifest,
                node=node,
                verdict=str(verdict),
                node_state_after=status,
                source_artifact=source,
                candidates=item.get("evidence", []),
            )
        )
        verdict_by_node[node_id] = item

    mode = str(reading.get("assessment_mode"))
    if mode == "full":
        required_nodes = {str(node_id) for unit in units.values() if unit.get("required", True) for node_id in unit.get("node_ids", [])}
        if required_nodes - set(verdict_by_node):
            raise FocusError("ASSESSMENT_COVERAGE_MISSING", "Full diagnosis must cover every required knowledge node", nodes=sorted(required_nodes - set(verdict_by_node)))
        raw_targets = ensure_list(event.get("remediation_targets", []), "remediation_targets")
        targets: list[dict[str, Any]] = []
        for item in raw_targets:
            if not isinstance(item, dict):
                raise FocusError("INVALID_REMEDIATION", "Remediation target must be an object")
            target_id = validate_identifier(item.get("id"), "remediation_target.id")
            node_id, _ = _find_node(nodes, item.get("node_id"))
            if verdict_by_node.get(node_id, {}).get("verdict") in {"sufficient", "transfer"}:
                raise FocusError("INVALID_REMEDIATION", "Passing node cannot receive a remediation target", node_id=node_id)
            targets.append(
                {
                    "id": target_id,
                    "node_id": node_id,
                    "status": "pending",
                    "diagnosis": ensure_nonempty_text(item.get("diagnosis"), "remediation_target.diagnosis"),
                    "source_answer_id": validate_identifier(item.get("answer_id"), "remediation_target.answer_id"),
                    "last_event_id": event["event_id"],
                }
            )
        failed_nodes = {node_id for node_id, item in verdict_by_node.items() if item.get("verdict") not in {"sufficient", "transfer"}}
        if failed_nodes - {item["node_id"] for item in targets}:
            raise FocusError("REMEDIATION_REQUIRED", "Every failed required node needs a remediation target", nodes=sorted(failed_nodes - {item["node_id"] for item in targets}))
        reading["remediation_targets"] = targets
    else:
        targets = reading["remediation_targets"]
        target_nodes = {item["node_id"]: item for item in targets if item.get("status") == "ready-for-regrill"}
        if set(verdict_by_node) != set(target_nodes):
            raise FocusError("REMEDIATION_TARGET_MISMATCH", "Targeted diagnosis must cover every and only ready remediation node")
        for node_id, target in target_nodes.items():
            target["status"] = "mastered" if verdict_by_node[node_id]["verdict"] in {"sufficient", "transfer"} else "pending"
            target["last_event_id"] = event["event_id"]

    unresolved = [item for item in reading["remediation_targets"] if item.get("status") in {"pending", "teaching", "ready-for-regrill"}]
    if unresolved:
        reading.update({"phase": "remediate", "status": "ready", "outcome": None})
    else:
        required_nodes = {str(node_id) for unit in units.values() if unit.get("required", True) for node_id in unit.get("node_ids", [])}
        all_mastered = all(reading["node_states"].get(node_id, {}).get("status") == "mastered" for node_id in required_nodes)
        reading.update({"phase": "complete", "status": "complete", "outcome": "complete" if all_mastered else "completed_with_gaps"})
    reading.update({"pending_interaction": None, "current_question": None})
    row = {
        **_event_header(event, "grill-diagnosed", manifest),
        "assessment_round": reading["assessment_round"],
        "assessment_mode": mode,
        "diagnosis": portable_relative(destination, paper_dir),
        "outcome": reading.get("outcome"),
    }
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row], evidence_rows=evidence_rows)


def _remediation_presented(workspace: Path, route: dict[str, Any], event: dict[str, Any], paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _require_route(route, "paper-reader", {"remediation"})
    _, nodes, _ = load_guide_contracts(paper_dir, manifest)
    target_id = validate_identifier(event.get("target_id"), "target_id")
    target = next((item for item in manifest["reading"]["remediation_targets"] if item.get("id") == target_id), None)
    if target is None or target.get("status") not in {"pending", "teaching"}:
        raise FocusError("INVALID_REMEDIATION", "Target is not ready for remediation teaching", target_id=target_id)
    if route.get("context", {}).get("target_id") != target_id:
        raise FocusError("ROUTE_CONTEXT_MISMATCH", "Event does not match the routed remediation target")
    node_id, _ = _find_node(nodes, target.get("node_id"))
    artifact = stage_path(workspace, route, event.get("unit_artifact"), "unit_artifact")
    destination = paper_dir / "reading" / "units" / f"REM-{target_id}.md"
    _install_text(artifact, destination)
    prompt_id = validate_identifier(event.get("prompt_id"), "prompt_id")
    target.update({"status": "teaching", "last_event_id": event["event_id"]})
    manifest["reading"].update(
        {
            "phase": "remediate",
            "status": "awaiting-user",
            "pending_interaction": {
                "kind": "remediation-checkpoint",
                "target_id": target_id,
                "node_id": node_id,
                "prompt_id": prompt_id,
            },
        }
    )
    row = {**_event_header(event, "remediation-presented", manifest), "target_id": target_id, "node_id": node_id, "prompt_id": prompt_id}
    return prepare_transaction(workspace, route, event, paper_dir, manifest, event_rows=[row])


HANDLERS = {
    "guide-installed": _guide_installed,
    "plan-confirmed": _plan_confirmed,
    "unit-presented": _unit_presented,
    "answer-recorded": _answer_recorded,
    "self-reported": _self_reported,
    "node-skipped": _node_skipped,
    "grill-started": _grill_started,
    "grill-answer-recorded": _grill_answer_recorded,
    "grill-diagnosed": _grill_diagnosed,
    "remediation-presented": _remediation_presented,
}


def commit_event(workspace: Path, route_id: str, event_path: Path) -> dict[str, Any]:
    route = load_route(workspace, route_id)
    run_dir = resolve_relative(workspace, str(route["run_dir"]))
    authorized_event_path = require_within(event_path, run_dir, code="EVENT_PATH_ESCAPE")
    event = load_json_or_yaml(authorized_event_path)
    event_id = validate_identifier(event.get("event_id"), "event_id")
    event_type = event.get("type")
    if event_type not in EVENT_TYPES:
        raise FocusError("UNSUPPORTED_EVENT", "Event type is not part of the paper companion protocol", event_type=event_type)
    if route.get("status") == "consumed" and route.get("transaction_id") == event_id:
        transaction = load_yaml(transaction_path(workspace, event_id), code="INVALID_TRANSACTION")
        expected_hash = transaction.get("event_hash")
        if expected_hash is not None and expected_hash != sha256_value(event):
            raise FocusError("IDEMPOTENCY_CONFLICT", "The same event ID was replayed with a different payload", event_id=event_id)
        result = finish_transaction(workspace, transaction)
        return {**result, "idempotent": True}
    route = verify_route(workspace, route_id)
    if event_type == "ingest-completed":
        if route.get("paper_id") is None:
            return register_ingest(workspace, route, event)
        return repair_ingest(workspace, route, event)
    if route.get("paper_id") is None:
        raise FocusError("PAPER_REQUIRED", "Only ingest-completed may consume a new-input route")
    paper_dir, manifest = load_paper(workspace, str(route["paper_id"]))
    if manifest["reading"]["revision"] != route.get("expected_revision"):
        raise FocusError("REVISION_CONFLICT", "Paper revision changed before event commit")
    if any(row.get("event_id") == event_id for row in read_jsonl(event_ledger_path(paper_dir))):
        raise FocusError("DUPLICATE_EVENT", "Event ID already exists in this paper ledger", event_id=event_id)
    handler = HANDLERS.get(str(event_type))
    if handler is None:
        raise FocusError("UNSUPPORTED_EVENT", "No handler exists for this event", event_type=event_type)
    return handler(workspace, route, event, paper_dir, deepcopy(manifest))
