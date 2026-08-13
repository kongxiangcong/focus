from __future__ import annotations

import json
import re
import shutil
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
    validate_manifest,
    validate_question_set,
    validate_reading_plan,
    validate_source_map,
)
from .errors import FocusError
from .profile import build_profile, ensure_profile_projection, rebuild_profile, validate_evidence_events
from .storage import (
    PAPER_SCHEMA,
    ROUTE_SCHEMA,
    acquire_lock,
    append_jsonl_rows,
    atomic_write_json,
    atomic_write_text,
    atomic_write_yaml,
    ensure_list,
    ensure_nonempty_text,
    load_json_or_yaml,
    load_yaml,
    new_id,
    now_iso,
    portable_relative,
    read_jsonl,
    release_lock,
    require_lock_owner,
    require_within,
    resolve_relative,
    route_path,
    safe_directory_name,
    safe_slug,
    sha256_file,
    validate_identifier,
    workspace_paths,
)
from .workspace import (
    find_paper_by_hash,
    list_papers,
    load_paper,
    load_registry,
    paper_directory,
    resolve_paper,
    save_registry,
    validate_source_identity,
    validate_workspace,
)


TARGETS = {"paper-ingest", "paper-guide", "paper-reader", "paper-grill", "cognitive-profile"}
ROUTE_MODES = {"normal", "confirmation", "resume", "remediation", "targeted", "diagnostic", "repair"}
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


def _paper_artifact(paper_dir: Path, manifest: dict[str, Any], field: str, default: str) -> Path:
    relative = manifest.get("artifacts", {}).get(field, default)
    if not isinstance(relative, str):
        raise FocusError("INVALID_ARTIFACT_PATH", f"artifacts.{field} must be a relative path")
    return require_within(paper_dir / relative, paper_dir)


def _require_ingest_artifacts(paper_dir: Path, manifest: dict[str, Any]) -> None:
    for field, default in (
        ("source_pdf", "source.pdf"),
        ("parsed_markdown", "paper.md"),
        ("parser_metadata", "metadata.json"),
        ("source_map", "ingest/source-map.yaml"),
        ("ingest_validation", "ingest/validation.json"),
    ):
        path = _paper_artifact(paper_dir, manifest, field, default)
        if not path.is_file():
            raise FocusError("INGEST_ARTIFACT_MISSING", "Required ingest artifact is missing", field=field, path=str(path))
    markdown = _paper_artifact(paper_dir, manifest, "parsed_markdown", "paper.md").read_text(encoding="utf-8")
    if not markdown.strip():
        raise FocusError("INGEST_QUALITY_BLOCKED", "Parsed Markdown is empty")
    metadata_path = _paper_artifact(paper_dir, manifest, "parser_metadata", "metadata.json")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FocusError("INGEST_QUALITY_BLOCKED", "Parser metadata is not valid JSON", cause=str(exc)) from exc
    if not isinstance(metadata, dict):
        raise FocusError("INGEST_QUALITY_BLOCKED", "Parser metadata root must be an object")
    validation_path = _paper_artifact(paper_dir, manifest, "ingest_validation", "ingest/validation.json")
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FocusError("INGEST_QUALITY_BLOCKED", "Ingest validation report is invalid", cause=str(exc)) from exc
    if validation.get("blocking_errors"):
        raise FocusError("INGEST_QUALITY_BLOCKED", "Ingest validation contains blocking errors", errors=validation["blocking_errors"])
    source_map = load_yaml(_paper_artifact(paper_dir, manifest, "source_map", "ingest/source-map.yaml"))
    validate_source_map(source_map, manifest["provenance"]["source_sha256"])


def _guide_artifacts_present(paper_dir: Path, manifest: dict[str, Any]) -> bool:
    fields = (
        ("overview", "guide/overview.md"),
        ("claim_map", "guide/claim-map.yaml"),
        ("knowledge_map", "guide/knowledge-map.yaml"),
        ("reading_plan", "guide/reading-plan.yaml"),
    )
    return all(_paper_artifact(paper_dir, manifest, field, default).is_file() for field, default in fields)


def _required_node_ids(units: dict[str, dict[str, Any]]) -> set[str]:
    return {
        str(node_id)
        for unit in units.values()
        if unit.get("required", True)
        for node_id in unit.get("node_ids", [])
    }


def _unit_for_node(units: dict[str, dict[str, Any]], node_id: str) -> str:
    for unit_id, unit in units.items():
        if node_id in unit.get("node_ids", []):
            return unit_id
    raise FocusError("UNSCHEDULED_KNOWLEDGE_NODE", "Node is not scheduled in a reading unit", node_id=node_id)


def _ready_node(nodes: dict[str, dict[str, Any]], node_states: dict[str, Any]) -> str | None:
    satisfied = {"provisional", "mastered", "skipped"}
    candidates: list[tuple[float, str]] = []
    for node_id, node in nodes.items():
        status = node_states.get(node_id, {}).get("status", "planned")
        if status not in {"planned", "learning", "needs-remediation", "stale"}:
            continue
        hard = node.get("requires", {}).get("hard", [])
        if all(node_states.get(str(dep), {}).get("status") in satisfied for dep in hard):
            candidates.append((float(node.get("order", 0)), node_id))
    return min(candidates, default=(0, None))[1]


def compute_route_spec(paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    validate_manifest(manifest)
    reading = manifest["reading"]
    try:
        _require_ingest_artifacts(paper_dir, manifest)
    except FocusError as exc:
        return {
            "target": "paper-ingest",
            "mode": "repair",
            "reason": "generated ingest artifacts need same-source repair",
            "blocking_error": exc.code,
        }
    if reading.get("status") == "blocked" or reading.get("blocked_reason"):
        raise FocusError("PAPER_BLOCKED", "Paper cannot advance until its blocker is repaired", blocker=reading.get("blocked_reason"))

    guide_present = _guide_artifacts_present(paper_dir, manifest)
    if not guide_present:
        mode = "repair" if reading.get("plan_revision", 0) > 0 or reading.get("phase") not in {"ingest", "guide"} else "normal"
        return {"target": "paper-guide", "mode": mode, "reason": "guide artifacts are absent or invalid"}
    try:
        _, nodes, units = load_guide_contracts(paper_dir, manifest)
    except FocusError:
        return {"target": "paper-guide", "mode": "repair", "reason": "guide contracts do not validate"}

    if reading.get("plan_revision", 0) == 0:
        return {"target": "paper-guide", "mode": "normal", "reason": "no reading plan is installed"}
    if reading.get("confirmed_plan_revision") != reading.get("plan_revision"):
        return {"target": "paper-guide", "mode": "confirmation", "reason": "the reading plan awaits confirmation"}

    pending = reading.get("pending_interaction")
    if isinstance(pending, dict):
        kind = pending.get("kind")
        if kind == "plan-confirmation":
            return {"target": "paper-guide", "mode": "confirmation", "reason": "the reading plan awaits confirmation", "prompt_id": pending.get("prompt_id")}
        if kind == "unit-checkpoint":
            return {
                "target": "paper-reader",
                "mode": "resume",
                "reason": "a checkpoint answer is pending",
                "unit_id": pending.get("unit_id"),
                "node_id": pending.get("node_id"),
                "prompt_id": pending.get("prompt_id"),
            }
        if kind == "remediation-checkpoint":
            return {
                "target": "paper-reader",
                "mode": "remediation",
                "reason": "a remediation checkpoint answer is pending",
                "target_id": pending.get("target_id"),
                "prompt_id": pending.get("prompt_id"),
            }
        if kind == "grill-question":
            mode = "targeted" if pending.get("assessment_mode") == "targeted" else "resume"
            return {
                "target": "paper-grill",
                "mode": mode,
                "reason": "an assessment answer is pending",
                "question_id": pending.get("question_id"),
                "prompt_id": pending.get("prompt_id"),
            }
        raise FocusError("INVALID_PENDING_INTERACTION", "Unknown pending interaction kind", kind=kind)

    if reading.get("phase") == "complete":
        return None

    if reading.get("phase") == "grill" and reading.get("status") == "running":
        mode = "targeted" if reading.get("assessment_mode") == "targeted" else "normal"
        return {"target": "paper-grill", "mode": mode, "operation": "diagnose", "reason": "the frozen assessment is ready for diagnosis"}

    targets = reading.get("remediation_targets", [])
    pending_targets = [item for item in targets if item.get("status") in {"pending", "teaching"}]
    if pending_targets:
        target = sorted(pending_targets, key=lambda item: str(item.get("id")))[0]
        return {"target": "paper-reader", "mode": "remediation", "reason": "a diagnosed gap needs focused teaching", "target_id": target["id"]}
    regrill_targets = [item for item in targets if item.get("status") == "ready-for-regrill"]
    if regrill_targets:
        return {
            "target": "paper-grill",
            "mode": "targeted",
            "reason": "remediation evidence is ready for closed-book re-test",
            "target_ids": [item["id"] for item in regrill_targets],
        }

    node_states = reading.get("node_states", {})
    next_node = _ready_node(nodes, node_states)
    required_nodes = _required_node_ids(units)
    learning_complete = all(node_states.get(node_id, {}).get("status") in {"provisional", "mastered", "skipped"} for node_id in required_nodes)
    if not learning_complete:
        if next_node is None:
            raise FocusError("LEARNING_FRONTIER_BLOCKED", "No knowledge node is ready although required nodes remain")
        return {
            "target": "paper-reader",
            "mode": "normal",
            "reason": "the next prerequisite-ready knowledge node is unfinished",
            "node_id": next_node,
            "unit_id": _unit_for_node(units, next_node),
        }

    return {"target": "paper-grill", "mode": "normal", "reason": "all required learning nodes are ready for closed-book verification"}


def _route_lock_key(route: dict[str, Any]) -> str:
    if route.get("paper_id"):
        return str(route["paper_id"])
    source_hash = str(route.get("input_sha256", ""))
    return f"input-{source_hash[:16]}"


def _issue_route(workspace: Path, spec: dict[str, Any], *, paper_id: str | None, manifest: dict[str, Any] | None, input_path: Path | None = None, input_hash: str | None = None) -> dict[str, Any]:
    marker = validate_workspace(workspace)
    target = spec.get("target")
    mode = spec.get("mode", "normal")
    if target not in TARGETS or mode not in ROUTE_MODES:
        raise FocusError("INVALID_ROUTE", "Router produced an unsupported target or mode", target=target, mode=mode)
    route_id = new_id("route")
    route: dict[str, Any] = {
        "schema_version": ROUTE_SCHEMA,
        "route_id": route_id,
        "workspace_id": marker["workspace_id"],
        "target_skill": target,
        "allowed_helpers": ["cognitive-profile"] if target in {"paper-reader", "paper-grill"} else [],
        "mode": mode,
        "paper_id": paper_id,
        "input_path": str(input_path.resolve()) if input_path else None,
        "input_sha256": input_hash,
        "expected_revision": manifest.get("reading", {}).get("revision") if manifest else None,
        "status": "issued",
        "issued_at": now_iso(),
        "context": {key: value for key, value in spec.items() if key not in {"target", "mode"}},
    }
    lock_key = _route_lock_key(route)
    route["lock_key"] = lock_key
    acquire_lock(workspace, lock_key, route_id)
    try:
        run_dir = workspace_paths(workspace)["runs"] / route_id
        run_dir.mkdir(parents=True, exist_ok=False)
        route["run_dir"] = portable_relative(run_dir, workspace)
        atomic_write_yaml(route_path(workspace, route_id), route)
    except Exception:
        release_lock(workspace, lock_key, route_id)
        raise
    return route


def issue_next_route(workspace: Path, *, selector: str | None = None, input_path: Path | None = None) -> dict[str, Any]:
    validate_workspace(workspace)
    if input_path is not None:
        source = input_path.resolve()
        source_hash = sha256_file(source)
        duplicate = find_paper_by_hash(workspace, source_hash)
        if duplicate is None:
            spec = {"target": "paper-ingest", "mode": "normal", "reason": "a new source needs immutable claim and extraction validation"}
            return _issue_route(workspace, spec, paper_id=None, manifest=None, input_path=source, input_hash=source_hash)
        selector = duplicate

    paper_id, paper_dir, manifest = resolve_paper(workspace, selector)
    if manifest.get("schema_version") != PAPER_SCHEMA:
        raise FocusError("MIGRATION_REQUIRED", "This paper needs an additive v1 to v2 migration", paper_id=paper_id)
    validate_source_identity(paper_dir, manifest)
    spec = compute_route_spec(paper_dir, manifest)
    if spec is None:
        return {
            "ok": True,
            "complete": True,
            "paper_id": paper_id,
            "outcome": manifest["reading"].get("outcome", "complete"),
            "message": "The paper learning workflow is complete; no new route was issued.",
        }
    route = _issue_route(workspace, spec, paper_id=paper_id, manifest=manifest)
    registry = load_registry(workspace)
    registry["last_used_paper"] = paper_id
    save_registry(workspace, registry)
    return route


def load_route(workspace: Path, route_id: str) -> dict[str, Any]:
    validate_workspace(workspace)
    route = load_yaml(route_path(workspace, route_id), code="INVALID_ROUTE")
    if route.get("schema_version") != ROUTE_SCHEMA or route.get("route_id") != route_id:
        raise FocusError("INVALID_ROUTE", "Route file identity or schema is invalid", route_id=route_id)
    return route


def verify_route(workspace: Path, route_id: str, *, target: str | None = None, helper: bool = False) -> dict[str, Any]:
    marker = validate_workspace(workspace)
    route = load_route(workspace, route_id)
    if route.get("workspace_id") != marker.get("workspace_id"):
        raise FocusError("WORKSPACE_MISMATCH", "Route belongs to a different workspace", route_id=route_id)
    if route.get("status") != "issued":
        raise FocusError("ROUTE_NOT_ISSUED", "Route is not available for execution", route_id=route_id, status=route.get("status"))
    if target:
        allowed = route.get("allowed_helpers", []) if helper else []
        if route.get("target_skill") != target and target not in allowed:
            raise FocusError("ROUTE_TARGET_MISMATCH", "Route does not authorize the requested skill", expected=route.get("target_skill"), actual=target)
    require_lock_owner(workspace, str(route["lock_key"]), route_id)
    paper_id = route.get("paper_id")
    if paper_id:
        paper_dir, manifest = load_paper(workspace, str(paper_id))
        validate_source_identity(paper_dir, manifest)
        if manifest["reading"]["revision"] != route.get("expected_revision"):
            raise FocusError(
                "REVISION_CONFLICT",
                "Paper state changed after this route was issued",
                expected=route.get("expected_revision"),
                actual=manifest["reading"]["revision"],
            )
    elif route.get("input_path"):
        actual_hash = sha256_file(Path(str(route["input_path"])))
        if actual_hash != route.get("input_sha256"):
            raise FocusError("SOURCE_HASH_MISMATCH", "Input changed after the ingest route was issued")
    return route


def cancel_route(workspace: Path, route_id: str, reason: str) -> dict[str, Any]:
    route = load_route(workspace, route_id)
    if route.get("status") == "consumed":
        raise FocusError("ROUTE_CONSUMED", "A consumed route cannot be cancelled", route_id=route_id)
    if route.get("status") == "cancelled":
        return route
    require_lock_owner(workspace, str(route["lock_key"]), route_id)
    route["status"] = "cancelled"
    route["cancelled_at"] = now_iso()
    route["cancel_reason"] = ensure_nonempty_text(reason, "reason")
    atomic_write_yaml(route_path(workspace, route_id), route)
    release_lock(workspace, str(route["lock_key"]), route_id)
    return route


def inspect_workspace(workspace: Path, selector: str | None = None) -> dict[str, Any]:
    marker = validate_workspace(workspace)
    result: dict[str, Any] = {
        "ok": True,
        "workspace": str(workspace.resolve()),
        "workspace_id": marker["workspace_id"],
        "papers": list_papers(workspace),
    }
    paths = workspace_paths(workspace)
    try:
        projection = ensure_profile_projection(workspace, paths["profile_evidence"], paths["profile"], paths["profile_history"])
        result["profile_projection"] = {"available": True, "recovered": projection["recovered"]}
    except FocusError as exc:
        result["profile_projection"] = {
            "available": False,
            "recovered": False,
            "warning": exc.as_dict(),
            "fallback": "read evidence ledger directly",
        }
    if selector:
        paper_id, paper_dir, manifest = resolve_paper(workspace, selector, include_complete=True)
        result["paper"] = {
            "paper_id": paper_id,
            "title": manifest.get("title"),
            "learning_goal": manifest.get("learning_goal"),
            "reading": manifest.get("reading"),
            "directory": str(paper_dir),
        }
        try:
            validate_source_identity(paper_dir, manifest)
            spec = compute_route_spec(paper_dir, manifest)
            result["paper"]["next"] = spec
        except FocusError as exc:
            result["paper"]["problem"] = exc.as_dict()
    return result
