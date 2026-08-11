from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .errors import FocusError
from .storage import (
    PAPER_SCHEMA,
    ensure_list,
    ensure_nonempty_text,
    load_yaml,
    sha256_value,
    validate_identifier,
)


PHASES = {"ingest", "guide", "read", "grill", "remediate", "complete"}
PAPER_STATUSES = {"ready", "running", "awaiting-user", "blocked", "complete"}
NODE_STATUSES = {
    "planned",
    "learning",
    "provisional",
    "mastered",
    "needs-remediation",
    "skipped",
    "stale",
}
REMEDIATION_STATUSES = {"pending", "teaching", "ready-for-regrill", "mastered", "waived"}
VERDICTS = {"no-evidence", "misconception", "partial", "sufficient", "transfer"}
CLAIM_KINDS = {"author-claim", "reported-evidence", "guide-inference", "open-question", "assumption", "limitation"}
PROBE_KINDS = {"reconstruct", "discriminate", "apply", "boundary", "transfer", "derive", "critique"}


def _unique_records(records: list[Any], field: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise FocusError("INVALID_CONTRACT", f"{label}[{index}] must be an object")
        identifier = validate_identifier(record.get(field), f"{label}[{index}].{field}")
        if identifier in result:
            raise FocusError("DUPLICATE_IDENTIFIER", f"Duplicate {label} identifier: {identifier}", identifier=identifier)
        result[identifier] = record
    return result


def assert_acyclic(nodes: set[str], edges: dict[str, list[str]], label: str) -> None:
    incoming = {node: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node, dependencies in edges.items():
        for dependency in dependencies:
            if dependency not in nodes:
                raise FocusError(
                    "UNKNOWN_DEPENDENCY",
                    f"{label} references unknown dependency {dependency}",
                    node=node,
                    dependency=dependency,
                )
            outgoing[dependency].append(node)
            incoming[node] += 1
    queue = deque(sorted(node for node, degree in incoming.items() if degree == 0))
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for consumer in sorted(outgoing[node]):
            incoming[consumer] -= 1
            if incoming[consumer] == 0:
                queue.append(consumer)
    if visited != len(nodes):
        cycle_nodes = sorted(node for node, degree in incoming.items() if degree > 0)
        raise FocusError("DEPENDENCY_CYCLE", f"{label} contains a cycle", nodes=cycle_nodes)


def validate_source_map(value: dict[str, Any], source_hash: str) -> set[str]:
    if value.get("schema_version") != 1:
        raise FocusError("UNSUPPORTED_SOURCE_MAP", "source-map.yaml must use schema_version 1")
    if value.get("source_sha256") != source_hash:
        raise FocusError("SOURCE_HASH_MISMATCH", "Source map is bound to a different source")
    anchors = _unique_records(ensure_list(value.get("anchors"), "anchors"), "id", "anchors")
    for anchor_id, anchor in anchors.items():
        ensure_nonempty_text(anchor.get("kind"), f"anchors[{anchor_id}].kind")
        has_locator = any(anchor.get(field) not in (None, "") for field in ("markdown_heading", "page", "asset", "occurrence"))
        if not has_locator:
            raise FocusError("INVALID_SOURCE_ANCHOR", "Source anchor has no stable locator", anchor_id=anchor_id)
    return set(anchors)


def validate_claim_map(value: dict[str, Any], anchor_ids: set[str]) -> set[str]:
    if value.get("schema_version") != 1:
        raise FocusError("UNSUPPORTED_CLAIM_MAP", "claim-map.yaml must use schema_version 1")
    claims = _unique_records(ensure_list(value.get("claims"), "claims"), "id", "claims")
    if not claims:
        raise FocusError("INVALID_CLAIM_MAP", "claim-map.yaml must contain at least one claim")
    for claim_id, claim in claims.items():
        if claim.get("kind") not in CLAIM_KINDS:
            raise FocusError("INVALID_CLAIM_KIND", "Unsupported claim kind", claim_id=claim_id, kind=claim.get("kind"))
        ensure_nonempty_text(claim.get("statement"), f"claims[{claim_id}].statement")
        sources = ensure_list(claim.get("source_anchors", []), f"claims[{claim_id}].source_anchors")
        if claim.get("kind") != "open-question" and not sources:
            raise FocusError("MISSING_SOURCE_ANCHOR", "Claim must cite at least one source anchor", claim_id=claim_id)
        unknown = sorted(set(map(str, sources)) - anchor_ids)
        if unknown:
            raise FocusError("UNKNOWN_SOURCE_ANCHOR", "Claim cites unknown source anchors", claim_id=claim_id, anchors=unknown)
        for field in ("supported_by", "assumptions", "limitations"):
            references = ensure_list(claim.get(field, []), f"claims[{claim_id}].{field}")
            missing = sorted(set(map(str, references)) - set(claims))
            if missing:
                raise FocusError("UNKNOWN_CLAIM_REFERENCE", f"{field} contains undefined IDs", claim_id=claim_id, ids=missing)
    return set(claims)


def validate_knowledge_map(value: dict[str, Any], anchor_ids: set[str]) -> dict[str, dict[str, Any]]:
    if value.get("schema_version") != 1:
        raise FocusError("UNSUPPORTED_KNOWLEDGE_MAP", "knowledge-map.yaml must use schema_version 1")
    nodes = _unique_records(ensure_list(value.get("nodes"), "nodes"), "id", "nodes")
    if not nodes:
        raise FocusError("INVALID_KNOWLEDGE_MAP", "knowledge-map.yaml must contain at least one node")
    concept_ids: set[str] = set()
    hard_edges: dict[str, list[str]] = {}
    for node_id, node in nodes.items():
        concept_id = validate_identifier(node.get("concept_id"), f"nodes[{node_id}].concept_id")
        if concept_id in concept_ids:
            raise FocusError("DUPLICATE_CONCEPT_ID", "concept_id must be unique within a map", concept_id=concept_id)
        concept_ids.add(concept_id)
        ensure_nonempty_text(node.get("title"), f"nodes[{node_id}].title")
        ensure_nonempty_text(node.get("type"), f"nodes[{node_id}].type")
        ensure_nonempty_text(node.get("objective"), f"nodes[{node_id}].objective")
        if not isinstance(node.get("order"), (int, float)):
            raise FocusError("INVALID_NODE_ORDER", "Node order must be numeric", node_id=node_id)
        parent = node.get("tree_parent")
        if parent is not None and parent not in nodes:
            raise FocusError("UNKNOWN_TREE_PARENT", "Node tree_parent does not exist", node_id=node_id, tree_parent=parent)
        if parent == node_id:
            raise FocusError("TREE_SELF_PARENT", "Node cannot be its own tree parent", node_id=node_id)
        sources = ensure_list(node.get("source_anchors"), f"nodes[{node_id}].source_anchors")
        unknown_sources = sorted(set(map(str, sources)) - anchor_ids)
        if unknown_sources:
            raise FocusError("UNKNOWN_SOURCE_ANCHOR", "Knowledge node cites unknown source anchors", node_id=node_id, anchors=unknown_sources)
        requires = node.get("requires", {})
        if not isinstance(requires, dict):
            raise FocusError("INVALID_NODE_DEPENDENCY", "Node requires must be an object", node_id=node_id)
        hard = [str(item) for item in ensure_list(requires.get("hard", []), f"nodes[{node_id}].requires.hard")]
        soft = [str(item) for item in ensure_list(requires.get("soft", []), f"nodes[{node_id}].requires.soft")]
        unknown_dependencies = sorted((set(hard) | set(soft)) - set(nodes))
        if unknown_dependencies:
            raise FocusError("UNKNOWN_DEPENDENCY", "Knowledge node has unknown prerequisites", node_id=node_id, dependencies=unknown_dependencies)
        hard_edges[node_id] = hard
        contract = node.get("mastery_contract")
        if not isinstance(contract, dict):
            raise FocusError("INVALID_MASTERY_CONTRACT", "Node must define mastery_contract", node_id=node_id)
        must_show = ensure_list(contract.get("must_show"), f"nodes[{node_id}].mastery_contract.must_show")
        probes = ensure_list(contract.get("probes"), f"nodes[{node_id}].mastery_contract.probes")
        critical = ensure_list(contract.get("critical_errors"), f"nodes[{node_id}].mastery_contract.critical_errors")
        if not must_show or not probes:
            raise FocusError("INVALID_MASTERY_CONTRACT", "mastery_contract needs must_show and probes", node_id=node_id)
        invalid_probes = sorted(set(map(str, probes)) - PROBE_KINDS)
        if invalid_probes:
            raise FocusError("INVALID_PROBE_KIND", "Unsupported mastery probe", node_id=node_id, probes=invalid_probes)
        if any(not isinstance(item, str) or not item.strip() for item in must_show + critical):
            raise FocusError("INVALID_MASTERY_CONTRACT", "Mastery rubric entries must be non-empty text", node_id=node_id)
    assert_acyclic(set(nodes), hard_edges, "knowledge prerequisites")
    return nodes


def validate_reading_plan(
    value: dict[str, Any],
    paper_id: str,
    node_ids: set[str],
    anchor_ids: set[str],
    expected_revision: int,
) -> dict[str, dict[str, Any]]:
    if value.get("schema_version") != 1:
        raise FocusError("UNSUPPORTED_READING_PLAN", "reading-plan.yaml must use schema_version 1")
    if value.get("paper_id") != paper_id:
        raise FocusError("PAPER_MISMATCH", "Reading plan is bound to another paper")
    if value.get("plan_revision") != expected_revision:
        raise FocusError("PLAN_REVISION_MISMATCH", "Reading plan revision is not the expected next revision")
    units = _unique_records(ensure_list(value.get("units"), "units"), "id", "units")
    if not units:
        raise FocusError("INVALID_READING_PLAN", "Reading plan must contain at least one unit")
    dependency_edges: dict[str, list[str]] = {}
    scheduled_nodes: list[str] = []
    for unit_id, unit in units.items():
        ensure_nonempty_text(unit.get("title"), f"units[{unit_id}].title")
        ensure_nonempty_text(unit.get("objective"), f"units[{unit_id}].objective")
        dependencies = [str(item) for item in ensure_list(unit.get("depends_on", []), f"units[{unit_id}].depends_on")]
        dependency_edges[unit_id] = dependencies
        unit_nodes = [str(item) for item in ensure_list(unit.get("node_ids"), f"units[{unit_id}].node_ids")]
        if not unit_nodes:
            raise FocusError("INVALID_READING_PLAN", "Every unit must schedule at least one knowledge node", unit_id=unit_id)
        unknown_nodes = sorted(set(unit_nodes) - node_ids)
        if unknown_nodes:
            raise FocusError("UNKNOWN_KNOWLEDGE_NODE", "Unit references unknown knowledge nodes", unit_id=unit_id, nodes=unknown_nodes)
        scheduled_nodes.extend(unit_nodes)
        sources = ensure_list(unit.get("source_anchors"), f"units[{unit_id}].source_anchors")
        unknown_sources = sorted(set(map(str, sources)) - anchor_ids)
        if unknown_sources:
            raise FocusError("UNKNOWN_SOURCE_ANCHOR", "Unit cites unknown source anchors", unit_id=unit_id, anchors=unknown_sources)
        if unit.get("required", True):
            exit_criteria = ensure_list(unit.get("exit_criteria"), f"units[{unit_id}].exit_criteria")
            if not exit_criteria:
                raise FocusError("MISSING_EXIT_CRITERIA", "Required unit needs exit criteria", unit_id=unit_id)
    assert_acyclic(set(units), dependency_edges, "reading-plan units")
    duplicates = sorted({node for node in scheduled_nodes if scheduled_nodes.count(node) > 1})
    if duplicates:
        raise FocusError("DUPLICATE_NODE_SCHEDULE", "Knowledge nodes may appear in only one unit", nodes=duplicates)
    missing_nodes = sorted(node_ids - set(scheduled_nodes))
    if missing_nodes:
        raise FocusError("UNSCHEDULED_KNOWLEDGE_NODE", "Every knowledge node must be scheduled", nodes=missing_nodes)
    return units


def validate_question_set(
    value: dict[str, Any],
    manifest: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    anchor_ids: set[str],
    mode: str,
) -> dict[str, dict[str, Any]]:
    if value.get("schema_version") != 1:
        raise FocusError("UNSUPPORTED_QUESTION_SET", "Question set must use schema_version 1")
    if value.get("paper_id") != manifest.get("paper_id"):
        raise FocusError("PAPER_MISMATCH", "Question set is bound to another paper")
    reading = manifest["reading"]
    if value.get("plan_revision") != reading.get("plan_revision"):
        raise FocusError("PLAN_REVISION_MISMATCH", "Question set is bound to another plan revision")
    if value.get("source_sha256") != manifest.get("provenance", {}).get("source_sha256"):
        raise FocusError("SOURCE_HASH_MISMATCH", "Question set is bound to another source")
    if value.get("mode") != mode:
        raise FocusError("ROUTE_MODE_MISMATCH", "Question set mode does not match route", expected=mode, actual=value.get("mode"))
    questions = _unique_records(ensure_list(value.get("questions"), "questions"), "id", "questions")
    if not questions:
        raise FocusError("EMPTY_QUESTION_SET", "Question set must contain at least one question")
    for question_id, question in questions.items():
        ensure_nonempty_text(question.get("text"), f"questions[{question_id}].text")
        expected = ensure_list(question.get("expected_points"), f"questions[{question_id}].expected_points")
        if not expected:
            raise FocusError("INVALID_QUESTION_RUBRIC", "Question needs expected points", question_id=question_id)
        ensure_list(question.get("critical_errors", []), f"questions[{question_id}].critical_errors")
        question_nodes = [str(item) for item in ensure_list(question.get("node_ids"), f"questions[{question_id}].node_ids")]
        unknown_nodes = sorted(set(question_nodes) - set(nodes))
        if unknown_nodes:
            raise FocusError("UNKNOWN_KNOWLEDGE_NODE", "Question references unknown nodes", question_id=question_id, nodes=unknown_nodes)
        sources = ensure_list(question.get("source_anchors"), f"questions[{question_id}].source_anchors")
        unknown_sources = sorted(set(map(str, sources)) - anchor_ids)
        if unknown_sources:
            raise FocusError("UNKNOWN_SOURCE_ANCHOR", "Question cites unknown source anchors", question_id=question_id, anchors=unknown_sources)
    if mode == "targeted":
        target_ids = ensure_list(value.get("target_ids"), "target_ids")
        if not target_ids:
            raise FocusError("MISSING_REMEDIATION_TARGET", "Targeted question set needs target_ids")
    return questions


def contract_hash(node: dict[str, Any]) -> str:
    return sha256_value(
        {
            "type": node.get("type"),
            "objective": node.get("objective"),
            "requires": node.get("requires"),
            "source_anchors": node.get("source_anchors"),
            "mastery_contract": node.get("mastery_contract"),
        }
    )


def validate_manifest(value: dict[str, Any]) -> None:
    if value.get("schema_version") != PAPER_SCHEMA:
        raise FocusError("MIGRATION_REQUIRED", "paper.yaml must use schema_version 2", actual=value.get("schema_version"))
    validate_identifier(value.get("paper_id"), "paper_id")
    ensure_nonempty_text(value.get("title"), "title")
    provenance = value.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("source_sha256"), str):
        raise FocusError("INVALID_PAPER", "Paper provenance must contain source_sha256")
    reading = value.get("reading")
    if not isinstance(reading, dict):
        raise FocusError("INVALID_PAPER", "Paper reading state must be an object")
    if reading.get("phase") not in PHASES:
        raise FocusError("INVALID_PHASE", "Unsupported reading phase", phase=reading.get("phase"))
    if reading.get("status") not in PAPER_STATUSES:
        raise FocusError("INVALID_STATUS", "Unsupported reading status", status=reading.get("status"))
    if not isinstance(reading.get("revision"), int) or reading["revision"] < 0:
        raise FocusError("INVALID_REVISION", "reading.revision must be a non-negative integer")
    for field in ("plan_revision", "map_revision", "assessment_round"):
        if not isinstance(reading.get(field), int) or reading[field] < 0:
            raise FocusError("INVALID_REVISION", f"reading.{field} must be a non-negative integer")
    node_states = reading.get("node_states", {})
    if not isinstance(node_states, dict):
        raise FocusError("INVALID_NODE_STATE", "reading.node_states must be an object")
    for node_id, state in node_states.items():
        validate_identifier(node_id, "node_id")
        if not isinstance(state, dict) or state.get("status") not in NODE_STATUSES:
            raise FocusError("INVALID_NODE_STATE", "Unsupported knowledge-node state", node_id=node_id, state=state)
    targets = reading.get("remediation_targets", [])
    if not isinstance(targets, list):
        raise FocusError("INVALID_REMEDIATION", "reading.remediation_targets must be a list")
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise FocusError("INVALID_REMEDIATION", "Remediation target must be an object")
        target_id = validate_identifier(target.get("id"), "remediation_target.id")
        if target_id in seen:
            raise FocusError("DUPLICATE_IDENTIFIER", "Duplicate remediation target", target_id=target_id)
        seen.add(target_id)
        if target.get("status") not in REMEDIATION_STATUSES:
            raise FocusError("INVALID_REMEDIATION", "Unsupported remediation status", target_id=target_id)


def load_guide_contracts(paper_dir: Path, manifest: dict[str, Any]) -> tuple[set[str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    artifacts = manifest.get("artifacts", {})
    source_map = load_yaml(paper_dir / artifacts.get("source_map", "ingest/source-map.yaml"))
    anchor_ids = validate_source_map(source_map, manifest["provenance"]["source_sha256"])
    knowledge_map = load_yaml(paper_dir / artifacts.get("knowledge_map", "guide/knowledge-map.yaml"))
    nodes = validate_knowledge_map(knowledge_map, anchor_ids)
    reading_plan = load_yaml(paper_dir / artifacts.get("reading_plan", "guide/reading-plan.yaml"))
    units = validate_reading_plan(reading_plan, manifest["paper_id"], set(nodes), anchor_ids, manifest["reading"]["plan_revision"])
    return anchor_ids, nodes, units
