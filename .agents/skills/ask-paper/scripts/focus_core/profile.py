from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .errors import FocusError
from .storage import EVIDENCE_SCHEMA, atomic_write_text, atomic_write_yaml, new_id, read_jsonl, require_within, validate_identifier


POSITIVE_VERDICTS = {"sufficient", "transfer"}
NEGATIVE_VERDICTS = {"no-evidence", "misconception", "partial"}
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
NODE_STATES = {"planned", "learning", "provisional", "mastered", "needs-remediation", "skipped", "stale"}


def _reference_exists(workspace: Path, reference: str, pending_sources: set[str] | None = None) -> bool:
    if pending_sources and reference in pending_sources:
        return True
    path_text, separator, anchor = reference.partition("#")
    candidate = require_within(workspace / path_text, workspace, code="EVIDENCE_PATH_ESCAPE")
    if not candidate.is_file():
        return False
    if not separator or not anchor:
        return True
    if candidate.suffix.lower() != ".jsonl":
        return True
    for row in read_jsonl(candidate):
        if anchor in {str(row.get("event_id")), str(row.get("response_id")), str(row.get("answer_id"))}:
            return True
    return False


def validate_evidence_events(workspace: Path, events: list[dict[str, Any]], *, pending_sources: set[str] | None = None) -> None:
    by_id: dict[str, dict[str, Any]] = {}
    for index, event in enumerate(events):
        if event.get("schema_version") != EVIDENCE_SCHEMA:
            raise FocusError("INVALID_EVIDENCE", "Evidence must use schema_version 1", index=index)
        event_id = validate_identifier(event.get("event_id"), "evidence.event_id")
        if event_id in by_id:
            raise FocusError("DUPLICATE_EVIDENCE", "Evidence event IDs must be unique", event_id=event_id)
        validate_identifier(event.get("paper_id"), "evidence.paper_id")
        validate_identifier(event.get("concept_id"), "evidence.concept_id")
        evidence_type = event.get("evidence_type")
        if not isinstance(evidence_type, str) or not evidence_type:
            raise FocusError("INVALID_EVIDENCE", "Evidence type must be non-empty", event_id=event_id)
        verdict = event.get("verdict")
        if verdict not in {"no-evidence", "misconception", "partial", "sufficient", "transfer", "self-reported", "skipped", "stale"}:
            raise FocusError("INVALID_EVIDENCE", "Unsupported evidence verdict", event_id=event_id, verdict=verdict)
        level = event.get("level_candidate")
        if not isinstance(level, int) or not 0 <= level <= 4:
            raise FocusError("INVALID_EVIDENCE", "level_candidate must be an integer from 0 to 4", event_id=event_id)
        if verdict in {"self-reported", "skipped", "stale"} and level != 0:
            raise FocusError("INVALID_EVIDENCE", "Self-report, skip, and stale events cannot raise level", event_id=event_id)
        dimensions = event.get("dimensions", [])
        if not isinstance(dimensions, list) or any(not isinstance(item, str) for item in dimensions):
            raise FocusError("INVALID_EVIDENCE", "dimensions must be a list of strings", event_id=event_id)
        if level >= 3 and verdict in POSITIVE_VERDICTS and "mechanism" not in dimensions:
            raise FocusError("LEVEL_GATE_FAILED", "Level 3+ evidence requires a mechanism dimension", event_id=event_id)
        if level == 4 and verdict != "transfer":
            raise FocusError("LEVEL_GATE_FAILED", "Level 4 evidence requires a transfer verdict", event_id=event_id)
        confidence = event.get("confidence")
        if confidence not in CONFIDENCE_ORDER:
            raise FocusError("INVALID_EVIDENCE", "confidence must be low, medium, or high", event_id=event_id)
        source = event.get("source_artifact")
        if not isinstance(source, str) or not _reference_exists(workspace, source, pending_sources):
            raise FocusError("EVIDENCE_SOURCE_MISSING", "Evidence source reference cannot be resolved", event_id=event_id, source=source)
        node_state_after = event.get("node_state_after")
        if node_state_after is not None and node_state_after not in NODE_STATES:
            raise FocusError("INVALID_EVIDENCE", "node_state_after is not a supported learner-node state", event_id=event_id, node_state_after=node_state_after)
        if not isinstance(event.get("rubric"), str) or not event["rubric"].strip():
            raise FocusError("INVALID_EVIDENCE", "Evidence rubric must be non-empty", event_id=event_id)
        if not isinstance(event.get("recorded_at"), str) or not event["recorded_at"]:
            raise FocusError("INVALID_EVIDENCE", "Evidence recorded_at must be non-empty", event_id=event_id)
        supersedes = event.get("supersedes")
        if supersedes is not None:
            if supersedes not in by_id:
                raise FocusError("INVALID_SUPERSESSION", "Evidence may supersede only an earlier event", event_id=event_id, supersedes=supersedes)
            if by_id[supersedes].get("concept_id") != event.get("concept_id"):
                raise FocusError("INVALID_SUPERSESSION", "Supersession must remain within one concept", event_id=event_id)
        by_id[event_id] = event


def build_profile(workspace: Path, events: list[dict[str, Any]], *, pending_sources: set[str] | None = None) -> dict[str, Any]:
    validate_evidence_events(workspace, events, pending_sources=pending_sources)
    superseded = {str(event["supersedes"]) for event in events if event.get("supersedes")}
    active = [(index, event) for index, event in enumerate(events) if event["event_id"] not in superseded]
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, event in active:
        grouped.setdefault(str(event["concept_id"]), []).append((index, event))

    domains: dict[str, Any] = {}
    for concept_id in sorted(grouped):
        records = grouped[concept_id]
        positives = [(index, event) for index, event in records if event["verdict"] in POSITIVE_VERDICTS]
        negatives = [(index, event) for index, event in records if event["verdict"] in NEGATIVE_VERDICTS]
        self_reports = [(index, event) for index, event in records if event["verdict"] == "self-reported"]
        skips = [(index, event) for index, event in records if event["verdict"] == "skipped"]
        stale = [(index, event) for index, event in records if event["verdict"] == "stale"]

        level = 0
        confidence = "low"
        basis: dict[str, Any] | None = None
        if positives:
            eligible: list[tuple[int, int, dict[str, Any]]] = []
            for index, event in positives:
                candidate = int(event["level_candidate"])
                dimensions = set(event.get("dimensions", []))
                if candidate >= 3 and "mechanism" not in dimensions:
                    candidate = 2
                if candidate >= 4 and event.get("verdict") != "transfer":
                    candidate = 3
                if candidate >= 3 and event.get("node_state_after") != "mastered":
                    candidate = 2
                eligible.append((candidate, index, event))
            level, _, basis = max(eligible, key=lambda item: (item[0], item[1]))
            confidence = str(basis["confidence"])

        latest_positive = max((index for index, _ in positives), default=-1)
        latest_negative = max((index for index, _ in negatives), default=-1)
        latest_stale = max((index for index, _ in stale), default=-1)
        if latest_negative > latest_positive:
            status = "contested"
            confidence = "low"
        elif latest_stale > latest_positive:
            status = "stale"
        elif positives:
            status = "verified"
        elif skips:
            status = "skipped"
        elif self_reports:
            status = "self-reported"
        else:
            status = "unverified"

        domain, separator, local_name = concept_id.partition(".")
        if not separator:
            domain, local_name = "general", concept_id
        domain_entry = domains.setdefault(domain, {"concepts": {}})
        domain_entry["concepts"][local_name] = {
            "level": level,
            "status": status,
            "confidence": confidence,
            "evidence_refs": [event["event_id"] for _, event in records],
            "paper_refs": sorted({str(event["paper_id"]) for _, event in records}),
            "last_observed_at": records[-1][1]["recorded_at"],
        }

    return {
        "schema_version": 1,
        "generated_from_event": events[-1]["event_id"] if events else None,
        "domains": domains,
    }


def rebuild_profile(workspace: Path, evidence_path: Path, profile_path: Path) -> dict[str, Any]:
    events = read_jsonl(evidence_path)
    profile = build_profile(workspace, deepcopy(events))
    atomic_write_yaml(profile_path, profile, sort_keys=True)
    return profile


def ensure_profile_projection(workspace: Path, evidence_path: Path, profile_path: Path, history_dir: Path) -> dict[str, Any]:
    """Recover the disposable profile from read-only evidence without user approval."""
    events = read_jsonl(evidence_path)
    expected = build_profile(workspace, deepcopy(events))
    current: dict[str, Any] | None = None
    invalid = False
    if profile_path.exists():
        try:
            import yaml

            value = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            current = value if isinstance(value, dict) else None
            invalid = current is None
        except (OSError, UnicodeError, yaml.YAMLError):
            invalid = True
    else:
        invalid = True
    if current == expected:
        return {"profile": current, "recovered": False}
    if profile_path.exists():
        history_dir.mkdir(parents=True, exist_ok=True)
        backup = history_dir / f"projection-{new_id('backup')}.yaml"
        atomic_write_text(backup, profile_path.read_text(encoding="utf-8", errors="replace"))
    atomic_write_yaml(profile_path, expected, sort_keys=True)
    return {"profile": expected, "recovered": True, "reason": "invalid" if invalid else "stale"}
