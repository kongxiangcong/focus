from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .contracts import validate_claim_map, validate_knowledge_map, validate_manifest, validate_reading_plan, validate_source_map
from .engine import load_route
from .errors import FocusError
from .profile import build_profile
from .router import compute_route_spec
from .storage import (
    PAPER_SCHEMA,
    acquire_lock,
    append_jsonl_rows,
    atomic_write_json,
    atomic_write_text,
    atomic_write_yaml,
    ensure_list,
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
    sha256_value,
    validate_identifier,
    workspace_paths,
)
from .workspace import find_paper_by_hash, load_paper, load_registry, save_registry, validate_source_identity, validate_workspace


def stage_path(workspace: Path, route: dict[str, Any], relative: object, field: str, *, directory: bool = False) -> Path:
    if not isinstance(relative, str) or not relative:
        raise FocusError("INVALID_EVENT", f"{field} must be a run-relative path")
    run_dir = resolve_relative(workspace, str(route["run_dir"]))
    candidate = require_within(run_dir / relative, run_dir, code="ARTIFACT_PATH_ESCAPE")
    if directory and not candidate.is_dir():
        raise FocusError("ARTIFACT_NOT_FOUND", f"Staged directory is missing: {field}", path=str(candidate))
    if not directory and not candidate.is_file():
        raise FocusError("ARTIFACT_NOT_FOUND", f"Staged file is missing: {field}", path=str(candidate))
    return candidate


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.is_file() and sha256_file(destination) == sha256_file(source):
            return
        raise FocusError("ARTIFACT_CONFLICT", "Destination artifact exists with different content", path=str(destination))
    shutil.copy2(source, destination)


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        source_files = sorted(path.relative_to(source) for path in source.rglob("*") if path.is_file())
        destination_files = sorted(path.relative_to(destination) for path in destination.rglob("*") if path.is_file())
        if source_files != destination_files:
            raise FocusError("ARTIFACT_CONFLICT", "Destination directory differs from staged artifact", path=str(destination))
        for relative in source_files:
            if sha256_file(source / relative) != sha256_file(destination / relative):
                raise FocusError("ARTIFACT_CONFLICT", "Destination file differs from staged artifact", path=str(destination / relative))
        return
    shutil.copytree(source, destination)


def extract_markdown_image_paths(markdown: str) -> list[str]:
    return [match.group(1).strip().split(" ", 1)[0].strip("<>") for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", markdown)]


def generate_source_map(markdown: str, source_hash: str) -> dict[str, Any]:
    anchors: list[dict[str, Any]] = []
    occurrences: dict[str, int] = {}
    for heading_match in re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", markdown):
        heading = heading_match.group(2).strip()
        base = safe_slug(heading, fallback="section", limit=48)
        occurrences[base] = occurrences.get(base, 0) + 1
        anchors.append(
            {
                "id": f"sec-{base}-{occurrences[base]}",
                "kind": "section",
                "heading": heading,
                "markdown_heading": heading_match.group(0).strip(),
                "occurrence": occurrences[base],
                "page": None,
            }
        )
    for index, asset in enumerate(extract_markdown_image_paths(markdown), 1):
        if asset.startswith(("http://", "https://", "data:")):
            continue
        anchors.append({"id": f"fig-{index}", "kind": "figure", "asset": asset, "occurrence": index, "page": None})
    if not anchors:
        anchors.append({"id": "body-1", "kind": "body", "occurrence": 1, "page": None})
    return {"schema_version": 1, "source_sha256": source_hash, "anchors": anchors}


def validate_staged_ingest(workspace: Path, route: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    markdown_path = stage_path(workspace, route, event.get("parsed_markdown"), "parsed_markdown")
    metadata_path = stage_path(workspace, route, event.get("metadata"), "metadata")
    try:
        markdown = markdown_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FocusError("INGEST_QUALITY_BLOCKED", "Parsed Markdown is unreadable", cause=str(exc)) from exc
    if not markdown.strip() or not (re.search(r"(?m)^#{1,6}\s+\S", markdown) or len(markdown.strip()) >= 80):
        raise FocusError("INGEST_QUALITY_BLOCKED", "Parsed Markdown has no usable heading or body block")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FocusError("INGEST_QUALITY_BLOCKED", "metadata must be a valid JSON object", cause=str(exc)) from exc
    if not isinstance(metadata, dict):
        raise FocusError("INGEST_QUALITY_BLOCKED", "metadata root must be an object")

    blocking_errors: list[dict[str, Any]] = []
    for reference in extract_markdown_image_paths(markdown):
        if reference.startswith(("http://", "https://", "data:")):
            continue
        candidate = require_within(markdown_path.parent / reference, markdown_path.parent, code="INGEST_IMAGE_PATH_ESCAPE")
        if not candidate.is_file():
            blocking_errors.append({"code": "BROKEN_IMAGE_REFERENCE", "path": reference})

    if event.get("validation"):
        validation_path = stage_path(workspace, route, event["validation"], "validation")
        try:
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FocusError("INGEST_QUALITY_BLOCKED", "Staged validation report is invalid JSON", cause=str(exc)) from exc
        blocking_errors.extend(ensure_list(validation.get("blocking_errors", []), "validation.blocking_errors"))
        warnings = ensure_list(validation.get("warnings", []), "validation.warnings")
    else:
        warnings = []
        validation = {"schema_version": 1, "blocking_errors": [], "warnings": []}
    validation = {**validation, "schema_version": 1, "blocking_errors": blocking_errors, "warnings": warnings}
    if blocking_errors:
        raise FocusError("INGEST_QUALITY_BLOCKED", "Extraction failed the structure quality gate", errors=blocking_errors)

    source_hash = str(route["input_sha256"])
    if event.get("source_map"):
        source_map = load_yaml(stage_path(workspace, route, event["source_map"], "source_map"))
    else:
        source_map = generate_source_map(markdown, source_hash)
    validate_source_map(source_map, source_hash)
    return {
        "markdown_path": markdown_path,
        "metadata_path": metadata_path,
        "markdown": markdown,
        "metadata": metadata,
        "validation": validation,
        "source_map": source_map,
        "warnings": warnings,
    }


def new_paper_identity(workspace: Path, title: str, source_hash: str) -> tuple[str, str, list[str]]:
    registry = load_registry(workspace)
    base_id = f"{safe_slug(title)}-{source_hash[:8]}"
    paper_id = base_id
    suffix = 8
    while paper_id in registry["papers"]:
        suffix += 4
        paper_id = f"{safe_slug(title)}-{source_hash[:suffix]}"
    base_directory = safe_directory_name(title)
    directory = base_directory
    if (workspace_paths(workspace)["corpus"] / directory).exists():
        directory = f"{base_directory}__{source_hash[:8]}"
    related = [paper for paper, entry in registry["papers"].items() if str(entry.get("title", "")).casefold() == title.casefold()]
    return paper_id, directory, sorted(related)


def event_ledger_path(paper_dir: Path) -> Path:
    return paper_dir / "reading" / "events.jsonl"


def response_ledger_path(paper_dir: Path) -> Path:
    return paper_dir / "reading" / "responses.jsonl"


def interview_ledger_path(paper_dir: Path) -> Path:
    return paper_dir / "assessment" / "interview.jsonl"


def transaction_path(workspace: Path, transaction_id: str) -> Path:
    validate_identifier(transaction_id, "transaction_id")
    return workspace_paths(workspace)["transactions"] / f"{transaction_id}.yaml"


def _rows(transaction: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = transaction.get(key, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise FocusError("INVALID_TRANSACTION", f"Transaction {key} must be a list of objects")
    return rows


PROFILE_LOCK_KEY = "cognitive-profile"


def _acquire_or_require_profile_lock(workspace: Path, route_id: str) -> None:
    try:
        acquire_lock(workspace, PROFILE_LOCK_KEY, route_id)
    except FocusError as exc:
        if exc.code != "LOCK_HELD":
            raise
        require_lock_owner(workspace, PROFILE_LOCK_KEY, route_id)


def _pending_evidence_sources(workspace: Path, paper_dir: Path, response_rows: list[dict[str, Any]], interview_rows: list[dict[str, Any]]) -> set[str]:
    response_prefix = portable_relative(response_ledger_path(paper_dir), workspace)
    interview_prefix = portable_relative(interview_ledger_path(paper_dir), workspace)
    return {
        *(f"{response_prefix}#{row['response_id']}" for row in response_rows if row.get("response_id")),
        *(f"{interview_prefix}#{row['answer_id']}" for row in interview_rows if row.get("answer_id")),
    }


def finish_transaction(workspace: Path, transaction: dict[str, Any]) -> dict[str, Any]:
    transaction_id = str(transaction["transaction_id"])
    if transaction.get("status") == "committed":
        route = load_route(workspace, str(transaction["route_id"]))
        release_lock(workspace, str(route["lock_key"]), str(transaction["route_id"]))
        return transaction.get("result", {"ok": True, "idempotent": True})
    if transaction.get("status") != "prepared":
        raise FocusError("INVALID_TRANSACTION", "Transaction is neither prepared nor committed", transaction_id=transaction_id)
    route_id = str(transaction["route_id"])
    route = load_route(workspace, route_id)
    require_lock_owner(workspace, str(route["lock_key"]), route_id)
    paper_dir = resolve_relative(workspace, str(transaction["paper_directory"]))

    append_jsonl_rows(event_ledger_path(paper_dir), _rows(transaction, "event_rows"), id_field="event_id")
    append_jsonl_rows(response_ledger_path(paper_dir), _rows(transaction, "response_rows"), id_field="response_id")
    append_jsonl_rows(interview_ledger_path(paper_dir), _rows(transaction, "interview_rows"), id_field="answer_id")
    evidence_rows = _rows(transaction, "evidence_rows")
    if evidence_rows:
        _acquire_or_require_profile_lock(workspace, route_id)
        try:
            evidence_path = workspace_paths(workspace)["profile_evidence"]
            existing = read_jsonl(evidence_path)
            existing_by_id = {str(row.get("event_id")): row for row in existing}
            pending: list[dict[str, Any]] = []
            for row in evidence_rows:
                identifier = str(row.get("event_id"))
                if identifier in existing_by_id:
                    if existing_by_id[identifier] != row:
                        raise FocusError("DUPLICATE_EVIDENCE", "Evidence event ID is already bound to a different payload", event_id=identifier)
                else:
                    pending.append(row)
            future = [*existing, *pending]
            profile = build_profile(workspace, future)
            append_jsonl_rows(evidence_path, pending, id_field="event_id")
            atomic_write_yaml(workspace_paths(workspace)["profile"], profile, sort_keys=True)
        finally:
            release_lock(workspace, PROFILE_LOCK_KEY, route_id)

    manifest = transaction.get("new_manifest")
    if not isinstance(manifest, dict):
        raise FocusError("INVALID_TRANSACTION", "Transaction lacks new_manifest")
    validate_manifest(manifest)
    atomic_write_yaml(paper_dir / "paper.yaml", manifest)
    registry = transaction.get("new_registry")
    if registry is not None:
        if not isinstance(registry, dict):
            raise FocusError("INVALID_TRANSACTION", "new_registry must be an object")
        save_registry(workspace, registry)

    route["status"] = "consumed"
    route["consumed_at"] = now_iso()
    route["transaction_id"] = transaction_id
    route["resulting_revision"] = manifest["reading"]["revision"]
    atomic_write_yaml(route_path(workspace, route_id), route)
    result = transaction.get("result", {"ok": True})
    transaction["status"] = "committed"
    transaction["committed_at"] = now_iso()
    atomic_write_yaml(transaction_path(workspace, transaction_id), transaction)
    release_lock(workspace, str(route["lock_key"]), route_id)
    return result


def prepare_transaction(
    workspace: Path,
    route: dict[str, Any],
    event: dict[str, Any],
    paper_dir: Path,
    manifest: dict[str, Any],
    *,
    event_rows: list[dict[str, Any]],
    response_rows: list[dict[str, Any]] | None = None,
    interview_rows: list[dict[str, Any]] | None = None,
    evidence_rows: list[dict[str, Any]] | None = None,
    registry: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transaction_id = str(event["event_id"])
    event_hash = sha256_value(event)
    path = transaction_path(workspace, transaction_id)
    if path.exists():
        existing = load_yaml(path, code="INVALID_TRANSACTION")
        if existing.get("route_id") != route.get("route_id"):
            raise FocusError("DUPLICATE_EVENT", "Event ID is already bound to another route", event_id=transaction_id)
        if existing.get("event_hash") is not None and existing.get("event_hash") != event_hash:
            raise FocusError("IDEMPOTENCY_CONFLICT", "The same event ID was replayed with a different payload", event_id=transaction_id)
        return finish_transaction(workspace, existing)

    manifest["reading"]["revision"] = int(manifest["reading"]["revision"]) + 1
    manifest["reading"]["updated_at"] = now_iso()
    try:
        manifest["reading"]["next_route"] = compute_route_spec(paper_dir, manifest)
    except FocusError as exc:
        manifest["reading"]["next_route"] = {"blocked": exc.code, "reason": exc.message}
    validate_manifest(manifest)
    evidence_rows = evidence_rows or []
    evidence_ids = [str(row.get("event_id")) for row in evidence_rows]
    duplicate_batch_ids = sorted({identifier for identifier in evidence_ids if evidence_ids.count(identifier) > 1})
    if duplicate_batch_ids:
        raise FocusError("DUPLICATE_EVIDENCE", "Evidence event IDs must be unique within one transaction", event_ids=duplicate_batch_ids)
    existing_evidence = read_jsonl(workspace_paths(workspace)["profile_evidence"])
    duplicate_ids = {row.get("event_id") for row in existing_evidence} & {row.get("event_id") for row in evidence_rows}
    if duplicate_ids:
        raise FocusError("DUPLICATE_EVIDENCE", "Evidence event ID already exists", event_ids=sorted(map(str, duplicate_ids)))
    response_rows = response_rows or []
    interview_rows = interview_rows or []
    profile_lock_held = False
    prepared = False
    if evidence_rows:
        _acquire_or_require_profile_lock(workspace, str(route["route_id"]))
        profile_lock_held = True
        try:
            pending_sources = _pending_evidence_sources(workspace, paper_dir, response_rows, interview_rows)
            build_profile(workspace, [*existing_evidence, *evidence_rows], pending_sources=pending_sources)
        except Exception:
            release_lock(workspace, PROFILE_LOCK_KEY, str(route["route_id"]))
            raise
    transaction = {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "event_hash": event_hash,
        "route_id": route["route_id"],
        "paper_id": manifest["paper_id"],
        "paper_directory": portable_relative(paper_dir, workspace),
        "expected_revision": route.get("expected_revision"),
        "status": "prepared",
        "prepared_at": now_iso(),
        "new_manifest": manifest,
        "new_registry": registry,
        "event_rows": event_rows,
        "response_rows": response_rows,
        "interview_rows": interview_rows,
        "evidence_rows": evidence_rows,
        "result": result or {"ok": True, "event_id": transaction_id, "paper_id": manifest["paper_id"], "revision": manifest["reading"]["revision"]},
    }
    try:
        atomic_write_yaml(path, transaction)
        prepared = True
        route["transaction_id"] = transaction_id
        atomic_write_yaml(route_path(workspace, str(route["route_id"])), route)
        return finish_transaction(workspace, transaction)
    except Exception:
        if profile_lock_held and not prepared:
            release_lock(workspace, PROFILE_LOCK_KEY, str(route["route_id"]))
        raise


def _paper_artifact_path(paper_dir: Path, manifest: dict[str, Any], field: str, default: str) -> Path:
    relative = manifest.get("artifacts", {}).get(field, default)
    if not isinstance(relative, str):
        raise FocusError("INVALID_ARTIFACT_PATH", f"artifacts.{field} must be a relative path")
    return require_within(paper_dir / relative, paper_dir)


def _guide_matches_anchors(paper_dir: Path, manifest: dict[str, Any], anchor_ids: set[str]) -> tuple[bool, str | None]:
    if int(manifest["reading"].get("plan_revision", 0)) == 0:
        return True, None
    artifacts = manifest.get("artifacts", {})
    paths = {
        "claim": _paper_artifact_path(paper_dir, manifest, "claim_map", "guide/claim-map.yaml"),
        "map": _paper_artifact_path(paper_dir, manifest, "knowledge_map", "guide/knowledge-map.yaml"),
        "plan": _paper_artifact_path(paper_dir, manifest, "reading_plan", "guide/reading-plan.yaml"),
    }
    if not all(path.is_file() for path in paths.values()):
        return False, "GUIDE_ARTIFACT_MISSING"
    try:
        validate_claim_map(load_yaml(paths["claim"]), anchor_ids)
        nodes = validate_knowledge_map(load_yaml(paths["map"]), anchor_ids)
        validate_reading_plan(
            load_yaml(paths["plan"]),
            manifest["paper_id"],
            set(nodes),
            anchor_ids,
            int(manifest["reading"]["plan_revision"]),
        )
    except FocusError as exc:
        return False, exc.code
    return True, None


def _overlay_generated_images(source: Path, destination: Path, event_id: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for source_file in sorted(path for path in source.rglob("*") if path.is_file()):
        relative = source_file.relative_to(source)
        target = require_within(destination / relative, destination, code="INGEST_IMAGE_PATH_ESCAPE")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{sha256_value(event_id)[:12]}.tmp")
        shutil.copy2(source_file, temporary)
        temporary.replace(target)


def repair_ingest(workspace: Path, route: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    if route.get("target_skill") != "paper-ingest" or route.get("mode") != "repair" or not route.get("paper_id"):
        raise FocusError("ROUTE_TARGET_MISMATCH", "Same-source ingest repair requires an existing-paper paper-ingest/repair route")
    paper_id = str(route["paper_id"])
    paper_dir, manifest = load_paper(workspace, paper_id)
    validate_source_identity(paper_dir, manifest)
    source_hash = str(manifest["provenance"]["source_sha256"])
    if route.get("input_sha256") != source_hash:
        raise FocusError("SOURCE_HASH_MISMATCH", "Repair route is not bound to the canonical source hash")
    title = str(event.get("title", "")).strip()
    if title != manifest["title"]:
        raise FocusError("PAPER_IDENTITY_CHANGE_REQUIRES_NEW_VERSION", "Same-source repair cannot change the paper title or identity", expected=manifest["title"], actual=title)

    parsed = validate_staged_ingest(workspace, route, event)
    anchor_ids = validate_source_map(parsed["source_map"], source_hash)
    guide_compatible, incompatibility = _guide_matches_anchors(paper_dir, manifest, anchor_ids)

    atomic_write_text(
        _paper_artifact_path(paper_dir, manifest, "parsed_markdown", "paper.md"),
        parsed["markdown_path"].read_text(encoding="utf-8"),
    )
    atomic_write_text(
        _paper_artifact_path(paper_dir, manifest, "parser_metadata", "metadata.json"),
        parsed["metadata_path"].read_text(encoding="utf-8"),
    )
    atomic_write_yaml(_paper_artifact_path(paper_dir, manifest, "source_map", "ingest/source-map.yaml"), parsed["source_map"])
    atomic_write_json(_paper_artifact_path(paper_dir, manifest, "ingest_validation", "ingest/validation.json"), parsed["validation"])
    if event.get("images"):
        _overlay_generated_images(
            stage_path(workspace, route, event["images"], "images", directory=True),
            _paper_artifact_path(paper_dir, manifest, "images", "images"),
            str(event["event_id"]),
        )

    parser = event.get("parser", {}) if isinstance(event.get("parser", {}), dict) else {}
    warnings = list(parsed["warnings"])
    if not guide_compatible:
        warnings.append(f"Existing guide invalidated by repaired source map: {incompatibility}")
    report = (
        "# Extraction report\n\n"
        f"- Source SHA-256: `{source_hash}`\n"
        f"- Parser: {parser.get('name', 'unspecified')}\n"
        f"- Parser version: {parser.get('version') or 'unknown'}\n"
        f"- Source anchors: {len(parsed['source_map']['anchors'])}\n"
        f"- Same-source repair: yes\n"
        f"- Existing guide compatible: {'yes' if guide_compatible else 'no'}\n"
    )
    atomic_write_text(_paper_artifact_path(paper_dir, manifest, "ingest_report", "ingest/extraction-report.md"), report)

    timestamp = now_iso()
    manifest["ingest"].update(
        {
            "status": "validated",
            "parser": parser.get("name", "unspecified"),
            "parser_version": parser.get("version"),
            "source_sha256": source_hash,
            "validated_at": timestamp,
            "warnings": warnings,
        }
    )
    reading = manifest["reading"]
    reading["blocked_reason"] = None
    if reading.get("status") == "blocked":
        reading["status"] = "ready"
    if not guide_compatible:
        for state in reading.get("node_states", {}).values():
            state["status"] = "stale"
            state["last_event_id"] = event["event_id"]
        reading.update(
            {
                "phase": "guide",
                "status": "ready",
                "outcome": None,
                "confirmed_plan_revision": None,
                "current_unit": None,
                "current_question": None,
                "completed_units": [],
                "assessment_mode": None,
                "assessment_file": None,
                "remediation_targets": [],
                "pending_interaction": None,
            }
        )
    row = {
        "schema_version": 1,
        "event_id": event["event_id"],
        "event_type": "ingest-completed",
        "operation": "same-source-repair",
        "paper_id": paper_id,
        "source_sha256": source_hash,
        "guide_compatible": guide_compatible,
        "recorded_at": timestamp,
    }
    return prepare_transaction(
        workspace,
        route,
        event,
        paper_dir,
        manifest,
        event_rows=[row],
        result={"ok": True, "event_id": event["event_id"], "paper_id": paper_id, "title": manifest["title"], "repaired": True, "guide_compatible": guide_compatible},
    )


def register_ingest(workspace: Path, route: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    if route.get("target_skill") != "paper-ingest" or route.get("paper_id") is not None:
        raise FocusError("ROUTE_TARGET_MISMATCH", "ingest-completed requires a new-input paper-ingest route")
    source = Path(str(route["input_path"]))
    actual_hash = sha256_file(source)
    if actual_hash != route.get("input_sha256"):
        raise FocusError("SOURCE_HASH_MISMATCH", "Input changed after the ingest route was issued")
    duplicate = find_paper_by_hash(workspace, actual_hash)
    if duplicate:
        raise FocusError("DUPLICATE_SOURCE", "This source hash is already registered", paper_id=duplicate)
    title = str(event.get("title", "")).strip()
    if not title:
        raise FocusError("INVALID_EVENT", "ingest-completed requires title")
    aliases = [str(item).strip() for item in ensure_list(event.get("aliases", []), "aliases") if str(item).strip()]
    parsed = validate_staged_ingest(workspace, route, event)
    paper_id, directory_name, related = new_paper_identity(workspace, title, actual_hash)
    paper_dir = workspace_paths(workspace)["corpus"] / directory_name
    if paper_dir.exists():
        raise FocusError("PAPER_DIRECTORY_CONFLICT", "Paper destination already exists", path=str(paper_dir))
    for relative in ("ingest", "guide", "reading/units", "reading/sessions", "assessment", "notes"):
        (paper_dir / relative).mkdir(parents=True, exist_ok=True)
    copy_file(source, paper_dir / "source.pdf")
    copy_file(parsed["markdown_path"], paper_dir / "paper.md")
    copy_file(parsed["metadata_path"], paper_dir / "metadata.json")
    if event.get("images"):
        copy_tree(stage_path(workspace, route, event["images"], "images", directory=True), paper_dir / "images")
    else:
        (paper_dir / "images").mkdir(exist_ok=True)
    atomic_write_yaml(paper_dir / "ingest" / "source-map.yaml", parsed["source_map"])
    atomic_write_json(paper_dir / "ingest" / "validation.json", parsed["validation"])
    parser = event.get("parser", {}) if isinstance(event.get("parser", {}), dict) else {}
    report = (
        "# Extraction report\n\n"
        f"- Source SHA-256: `{actual_hash}`\n"
        f"- Parser: {parser.get('name', 'unspecified')}\n"
        f"- Parser version: {parser.get('version') or 'unknown'}\n"
        f"- Source anchors: {len(parsed['source_map']['anchors'])}\n"
        f"- Warnings: {len(parsed['warnings'])}\n"
    )
    atomic_write_text(paper_dir / "ingest" / "extraction-report.md", report)
    for ledger in (event_ledger_path(paper_dir), response_ledger_path(paper_dir), interview_ledger_path(paper_dir)):
        atomic_write_text(ledger, "")
    timestamp = now_iso()
    manifest = {
        "schema_version": PAPER_SCHEMA,
        "paper_id": paper_id,
        "title": title,
        "aliases": aliases,
        "identifiers": event.get("identifiers", {}) if isinstance(event.get("identifiers", {}), dict) else {},
        "provenance": {"external_source": str(source.resolve()), "source_sha256": actual_hash},
        "related_versions": related,
        "artifacts": {
            "source_pdf": "source.pdf",
            "parsed_markdown": "paper.md",
            "parser_metadata": "metadata.json",
            "images": "images",
            "ingest_report": "ingest/extraction-report.md",
            "source_map": "ingest/source-map.yaml",
            "ingest_validation": "ingest/validation.json",
            "overview": "guide/overview.md",
            "claim_map": "guide/claim-map.yaml",
            "knowledge_map": "guide/knowledge-map.yaml",
            "reading_plan": "guide/reading-plan.yaml",
            "notes": "notes",
        },
        "ingest": {
            "status": "validated",
            "parser": parser.get("name", "unspecified"),
            "parser_version": parser.get("version"),
            "source_sha256": actual_hash,
            "validated_at": timestamp,
            "warnings": parsed["warnings"],
        },
        "learning_goal": {"mode": event.get("learning_goal", "deep_understanding"), "statement": event.get("goal_statement")},
        "reading": {
            "phase": "guide",
            "status": "ready",
            "outcome": None,
            "revision": 0,
            "plan_revision": 0,
            "map_revision": 0,
            "confirmed_plan_revision": None,
            "current_unit": None,
            "current_question": None,
            "node_states": {},
            "completed_units": [],
            "assessment_round": 0,
            "assessment_mode": None,
            "assessment_file": None,
            "remediation_targets": [],
            "pending_interaction": None,
            "blocked_reason": None,
            "next_route": None,
            "updated_at": timestamp,
        },
    }
    registry = load_registry(workspace)
    registry["papers"][paper_id] = {"directory": directory_name, "title": title, "aliases": aliases}
    registry["last_used_paper"] = paper_id
    event_row = {
        "schema_version": 1,
        "event_id": event["event_id"],
        "event_type": "ingest-completed",
        "paper_id": paper_id,
        "source_sha256": actual_hash,
        "recorded_at": timestamp,
    }
    return prepare_transaction(
        workspace,
        route,
        event,
        paper_dir,
        manifest,
        event_rows=[event_row],
        registry=registry,
        result={"ok": True, "event_id": event["event_id"], "paper_id": paper_id, "title": title, "reused": False},
    )
