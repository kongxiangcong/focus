from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import validate_manifest
from .errors import FocusError
from .storage import (
    WORKSPACE_SCHEMA,
    atomic_write_text,
    atomic_write_yaml,
    load_yaml,
    new_id,
    now_iso,
    portable_relative,
    sha256_file,
    workspace_paths,
)


def _directory_nonempty(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def initialize_workspace(workspace: Path, *, adopt: bool = False) -> dict[str, Any]:
    workspace = workspace.resolve()
    paths = workspace_paths(workspace)
    if paths["marker"].exists():
        marker = validate_workspace(workspace)
        return {"workspace": str(workspace), "created": False, "adopted": False, "marker": marker}
    if _directory_nonempty(workspace) and not adopt:
        entries = sorted(item.name for item in workspace.iterdir())[:25]
        raise FocusError(
            "WORKSPACE_ADOPTION_REQUIRED",
            "A non-empty knowledge-base has no workspace marker; inspect it and explicitly adopt it",
            workspace=str(workspace),
            entries=entries,
        )
    existed_nonempty = _directory_nonempty(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    for key in ("locks", "routes", "runs", "migrations", "transactions", "profile_history", "corpus"):
        paths[key].mkdir(parents=True, exist_ok=True)
    marker = {
        "schema_version": WORKSPACE_SCHEMA,
        "workspace_id": new_id("kb"),
        "created_at": now_iso(),
        "defaults": {
            "explanation_language": "zh-CN",
            "quote_language": "original",
        },
        "paths": {
            "registry": "reading-registry.yaml",
            "corpus": "research-corpus",
            "profile": "cognitive-profile",
            "control": ".paper-companion",
        },
    }
    atomic_write_yaml(paths["marker"], marker)
    if not paths["registry"].exists():
        atomic_write_yaml(paths["registry"], {"schema_version": 1, "last_used_paper": None, "papers": {}})
    if not paths["profile_evidence"].exists():
        atomic_write_text(paths["profile_evidence"], "")
    if not paths["profile"].exists():
        atomic_write_yaml(paths["profile"], {"schema_version": 1, "generated_from_event": None, "domains": {}}, sort_keys=True)
    if existed_nonempty:
        migration = {
            "schema_version": 1,
            "migration_id": new_id("migration"),
            "kind": "workspace-adoption",
            "performed_at": now_iso(),
            "additive_only": True,
        }
        atomic_write_yaml(paths["migrations"] / f"{migration['migration_id']}.yaml", migration)
    return {"workspace": str(workspace), "created": True, "adopted": existed_nonempty, "marker": marker}


def validate_workspace(workspace: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    paths = workspace_paths(workspace)
    marker = load_yaml(paths["marker"], code="INVALID_WORKSPACE")
    version = marker.get("schema_version")
    if version != WORKSPACE_SCHEMA:
        code = "WORKSPACE_SCHEMA_TOO_NEW" if isinstance(version, int) and version > WORKSPACE_SCHEMA else "UNSUPPORTED_WORKSPACE_SCHEMA"
        raise FocusError(code, "Workspace schema is not supported", workspace=str(workspace), schema_version=version)
    if not isinstance(marker.get("workspace_id"), str) or not marker["workspace_id"]:
        raise FocusError("INVALID_WORKSPACE", "workspace.yaml lacks workspace_id", workspace=str(workspace))
    registry = load_yaml(paths["registry"], code="INVALID_REGISTRY")
    if registry.get("schema_version") != 1 or not isinstance(registry.get("papers"), dict):
        raise FocusError("INVALID_REGISTRY", "reading-registry.yaml must contain schema_version 1 and papers mapping")
    return marker


def resolve_workspace(
    *,
    start: Path,
    explicit: Path | None = None,
    adopt: bool = False,
    create: bool = False,
) -> dict[str, Any]:
    if explicit is not None:
        target = explicit.resolve()
        if (target / "workspace.yaml").is_file():
            marker = validate_workspace(target)
            return {"workspace": str(target), "source": "explicit", "created": False, "marker": marker}
        result = initialize_workspace(target, adopt=adopt)
        result["source"] = "explicit"
        return result

    current = start.resolve()
    if current.is_file():
        current = current.parent
    ancestors = [current, *current.parents]
    for ancestor in ancestors:
        candidates = [ancestor] if ancestor.name.lower() == "knowledge-base" else []
        candidates.append(ancestor / "knowledge-base")
        for candidate in candidates:
            if (candidate / "workspace.yaml").is_file():
                marker = validate_workspace(candidate)
                return {"workspace": str(candidate.resolve()), "source": "ancestor", "created": False, "marker": marker}

    for ancestor in ancestors:
        candidates = [ancestor] if ancestor.name.lower() == "knowledge-base" else []
        candidates.append(ancestor / "knowledge-base")
        for candidate in candidates:
            if _directory_nonempty(candidate):
                if adopt:
                    result = initialize_workspace(candidate, adopt=True)
                    result["source"] = "adopted-candidate"
                    return result
                entries = sorted(item.name for item in candidate.iterdir())[:25]
                raise FocusError(
                    "WORKSPACE_ADOPTION_REQUIRED",
                    "Found a non-empty unmarked knowledge-base; explicit adoption is required",
                    workspace=str(candidate.resolve()),
                    entries=entries,
                )
    if not create:
        raise FocusError("WORKSPACE_NOT_FOUND", "No marked knowledge-base was found", start=str(current))
    result = initialize_workspace(current / "knowledge-base", adopt=False)
    result["source"] = "created-at-start"
    return result


def load_registry(workspace: Path) -> dict[str, Any]:
    validate_workspace(workspace)
    return load_yaml(workspace_paths(workspace)["registry"], code="INVALID_REGISTRY")


def save_registry(workspace: Path, registry: dict[str, Any]) -> None:
    if registry.get("schema_version") != 1 or not isinstance(registry.get("papers"), dict):
        raise FocusError("INVALID_REGISTRY", "Registry write rejected")
    forbidden = {"phase", "status", "revision", "next_route"}
    for paper_id, entry in registry["papers"].items():
        if not isinstance(entry, dict):
            raise FocusError("INVALID_REGISTRY", "Registry paper entry must be an object", paper_id=paper_id)
        leaked = sorted(forbidden & set(entry))
        if leaked:
            raise FocusError("REGISTRY_STATE_LEAK", "Registry cannot duplicate paper routing state", paper_id=paper_id, fields=leaked)
    atomic_write_yaml(workspace_paths(workspace)["registry"], registry)


def paper_directory(workspace: Path, paper_id: str, registry: dict[str, Any] | None = None) -> Path:
    registry = registry or load_registry(workspace)
    entry = registry.get("papers", {}).get(paper_id)
    if not isinstance(entry, dict) or not isinstance(entry.get("directory"), str):
        raise FocusError("PAPER_NOT_FOUND", "Paper is not registered", paper_id=paper_id)
    candidate = (workspace_paths(workspace)["corpus"] / entry["directory"]).resolve()
    return candidate


def load_paper(workspace: Path, paper_id: str, *, allow_v1: bool = False) -> tuple[Path, dict[str, Any]]:
    directory = paper_directory(workspace, paper_id)
    manifest = load_yaml(directory / "paper.yaml", code="INVALID_PAPER")
    if manifest.get("schema_version") == 1 and allow_v1:
        return directory, manifest
    validate_manifest(manifest)
    if manifest.get("paper_id") != paper_id:
        raise FocusError("PAPER_ID_MISMATCH", "Registry and paper.yaml disagree", registry_id=paper_id, manifest_id=manifest.get("paper_id"))
    return directory, manifest


def resolve_paper(workspace: Path, selector: str | None, *, include_complete: bool = False) -> tuple[str, Path, dict[str, Any]]:
    registry = load_registry(workspace)
    papers = registry["papers"]
    matches: list[str] = []
    if selector:
        folded = selector.casefold()
        for paper_id, entry in papers.items():
            aliases = [paper_id, str(entry.get("title", "")), str(entry.get("directory", "")), *map(str, entry.get("aliases", []))]
            if any(value.casefold() == folded for value in aliases):
                matches.append(paper_id)
        if not matches:
            raise FocusError("PAPER_NOT_FOUND", "No paper matches the requested ID or alias", selector=selector)
        if len(matches) > 1:
            raise FocusError("PAPER_AMBIGUOUS", "Paper selector matches multiple records", selector=selector, candidates=sorted(matches))
    else:
        for paper_id in papers:
            try:
                _, manifest = load_paper(workspace, paper_id, allow_v1=True)
            except FocusError:
                matches.append(paper_id)
                continue
            reading = manifest.get("reading", {})
            if include_complete or reading.get("phase") != "complete":
                matches.append(paper_id)
        if len(matches) > 1:
            last = registry.get("last_used_paper")
            ordered = sorted(matches, key=lambda item: (item != last, item))
            raise FocusError(
                "PAPER_SELECTION_REQUIRED",
                "Multiple papers can continue; choose one explicitly",
                candidates=ordered,
                last_used_hint=last,
            )
        if not matches:
            raise FocusError("PAPER_SELECTION_REQUIRED", "No unfinished paper is available; choose a completed paper explicitly", candidates=sorted(papers))
    paper_id = matches[0]
    directory, manifest = load_paper(workspace, paper_id, allow_v1=True)
    return paper_id, directory, manifest


def find_paper_by_hash(workspace: Path, source_hash: str) -> str | None:
    registry = load_registry(workspace)
    for paper_id in registry["papers"]:
        try:
            _, manifest = load_paper(workspace, paper_id, allow_v1=True)
        except FocusError:
            continue
        known = manifest.get("provenance", {}).get("source_sha256") or manifest.get("source_sha256")
        if known == source_hash:
            return paper_id
    return None


def validate_source_identity(paper_dir: Path, manifest: dict[str, Any]) -> None:
    relative = manifest.get("artifacts", {}).get("source_pdf", "source.pdf")
    source = paper_dir / relative
    actual = sha256_file(source)
    expected = manifest.get("provenance", {}).get("source_sha256")
    if actual != expected:
        raise FocusError(
            "SOURCE_HASH_MISMATCH",
            "The claimed source changed; generated learning evidence is blocked",
            paper_id=manifest.get("paper_id"),
            expected=expected,
            actual=actual,
        )


def list_papers(workspace: Path) -> list[dict[str, Any]]:
    registry = load_registry(workspace)
    result: list[dict[str, Any]] = []
    for paper_id, entry in registry["papers"].items():
        item = {"paper_id": paper_id, "title": entry.get("title"), "aliases": entry.get("aliases", [])}
        try:
            _, manifest = load_paper(workspace, paper_id, allow_v1=True)
            reading = manifest.get("reading", {})
            item.update({"phase": reading.get("phase"), "status": reading.get("status"), "outcome": reading.get("outcome")})
        except FocusError as exc:
            item.update({"phase": "unknown", "status": "blocked", "problem": exc.code})
        result.append(item)
    return result

