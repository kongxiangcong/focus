from __future__ import annotations

from pathlib import Path
from typing import Any

from .engine import ROUTE_MODES, TARGETS, compute_route_spec as base_compute_route_spec
from .errors import FocusError
from .storage import (
    ROUTE_SCHEMA,
    acquire_lock,
    atomic_write_yaml,
    new_id,
    now_iso,
    portable_relative,
    release_lock,
    route_path,
    sha256_file,
    workspace_paths,
)
from .workspace import (
    find_paper_by_hash,
    load_paper,
    load_registry,
    resolve_paper,
    save_registry,
    validate_source_identity,
    validate_workspace,
)


def compute_route_spec(paper_dir: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    spec = base_compute_route_spec(paper_dir, manifest)
    if (
        spec
        and spec.get("target") == "paper-grill"
        and spec.get("operation") == "diagnose"
        and manifest.get("reading", {}).get("assessment_mode") == "targeted"
    ):
        spec = {**spec, "mode": "targeted"}
    return spec


def _persist_route(
    workspace: Path,
    *,
    route_id: str,
    lock_key: str,
    spec: dict[str, Any],
    paper_id: str | None,
    manifest: dict[str, Any] | None,
    input_path: Path | None,
    input_hash: str | None,
) -> dict[str, Any]:
    marker = validate_workspace(workspace)
    target = spec.get("target")
    mode = spec.get("mode", "normal")
    if target not in TARGETS or mode not in ROUTE_MODES:
        raise FocusError("INVALID_ROUTE", "Router produced an unsupported target or mode", target=target, mode=mode)
    run_dir = workspace_paths(workspace)["runs"] / route_id
    run_dir.mkdir(parents=True, exist_ok=False)
    route = {
        "schema_version": ROUTE_SCHEMA,
        "route_id": route_id,
        "workspace_id": marker["workspace_id"],
        "target_skill": target,
        "allowed_helpers": ["cognitive-profile"] if target in {"paper-reader", "paper-grill"} else [],
        "mode": mode,
        "paper_id": paper_id,
        "input_path": str(input_path.resolve()) if input_path else None,
        "input_sha256": input_hash or (manifest.get("provenance", {}).get("source_sha256") if manifest else None),
        "expected_revision": manifest.get("reading", {}).get("revision") if manifest else None,
        "status": "issued",
        "issued_at": now_iso(),
        "context": {key: value for key, value in spec.items() if key not in {"target", "mode"}},
        "lock_key": lock_key,
        "run_dir": portable_relative(run_dir, workspace),
    }
    atomic_write_yaml(route_path(workspace, route_id), route)
    return route


def issue_next_route(workspace: Path, *, selector: str | None = None, input_path: Path | None = None) -> dict[str, Any]:
    validate_workspace(workspace)
    if input_path is not None:
        source = input_path.resolve()
        initial_hash = sha256_file(source)
        duplicate = find_paper_by_hash(workspace, initial_hash)
        if duplicate is None:
            route_id = new_id("route")
            lock_key = f"input-{initial_hash[:16]}"
            acquire_lock(workspace, lock_key, route_id)
            try:
                confirmed_hash = sha256_file(source)
                if confirmed_hash != initial_hash:
                    raise FocusError("SOURCE_HASH_MISMATCH", "Input changed while the ingest route was being issued")
                duplicate = find_paper_by_hash(workspace, confirmed_hash)
                if duplicate is not None:
                    raise FocusError("DUPLICATE_SOURCE", "Another execution registered this source", paper_id=duplicate)
                return _persist_route(
                    workspace,
                    route_id=route_id,
                    lock_key=lock_key,
                    spec={"target": "paper-ingest", "mode": "normal", "reason": "a new source needs immutable claim and extraction validation"},
                    paper_id=None,
                    manifest=None,
                    input_path=source,
                    input_hash=confirmed_hash,
                )
            except Exception:
                release_lock(workspace, lock_key, route_id)
                raise
        selector = duplicate

    paper_id, _, prelock_manifest = resolve_paper(workspace, selector)
    if prelock_manifest.get("schema_version") != 2:
        raise FocusError("MIGRATION_REQUIRED", "This paper needs an additive v1 to v2 migration", paper_id=paper_id)
    route_id = new_id("route")
    acquire_lock(workspace, paper_id, route_id)
    try:
        paper_dir, manifest = load_paper(workspace, paper_id)
        validate_source_identity(paper_dir, manifest)
        spec = compute_route_spec(paper_dir, manifest)
        if spec is None:
            release_lock(workspace, paper_id, route_id)
            return {
                "ok": True,
                "complete": True,
                "paper_id": paper_id,
                "outcome": manifest["reading"].get("outcome", "complete"),
                "message": "The paper learning workflow is complete; no new route was issued.",
            }
        route = _persist_route(
            workspace,
            route_id=route_id,
            lock_key=paper_id,
            spec=spec,
            paper_id=paper_id,
            manifest=manifest,
            input_path=None,
            input_hash=None,
        )
        registry = load_registry(workspace)
        registry["last_used_paper"] = paper_id
        save_registry(workspace, registry)
        return route
    except Exception:
        release_lock(workspace, paper_id, route_id)
        raise
