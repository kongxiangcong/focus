from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .contracts import load_guide_contracts, validate_manifest, validate_source_map
from .engine import _require_ingest_artifacts, cancel_route, inspect_workspace, load_route
from .errors import FocusError
from .profile import rebuild_profile
from .storage import (
    PAPER_SCHEMA,
    acquire_lock,
    append_jsonl_rows,
    atomic_write_json,
    atomic_write_yaml,
    load_yaml,
    new_id,
    now_iso,
    read_jsonl,
    release_lock,
    sha256_file,
    workspace_paths,
)
from .transaction import event_ledger_path, finish_transaction, generate_source_map, transaction_path
from .workspace import load_paper, load_registry, paper_directory, resolve_paper, validate_source_identity, validate_workspace


def migrate_paper(workspace: Path, selector: str) -> dict[str, Any]:
    validate_workspace(workspace)
    paper_id, paper_dir, old = resolve_paper(workspace, selector, include_complete=True)
    if old.get("schema_version") == PAPER_SCHEMA:
        validate_manifest(old)
        return {"ok": True, "paper_id": paper_id, "migrated": False, "schema_version": PAPER_SCHEMA}
    if old.get("schema_version") != 1:
        raise FocusError("UNSUPPORTED_PAPER_SCHEMA", "Only additive v1 to v2 migration is supported", schema_version=old.get("schema_version"))
    owner = new_id("migration-route")
    acquire_lock(workspace, paper_id, owner)
    try:
        old = load_yaml(paper_dir / "paper.yaml", code="INVALID_PAPER")
        if old.get("schema_version") != 1:
            raise FocusError("REVISION_CONFLICT", "paper.yaml changed before migration")
        source_relative = old.get("artifacts", {}).get("source_pdf", "source.pdf") if isinstance(old.get("artifacts", {}), dict) else "source.pdf"
        source = paper_dir / str(source_relative)
        source_hash = sha256_file(source)
        markdown = paper_dir / "paper.md"
        metadata = paper_dir / "metadata.json"
        ingest_valid = markdown.is_file() and markdown.stat().st_size > 0 and metadata.is_file()
        if metadata.is_file():
            try:
                if not isinstance(json.loads(metadata.read_text(encoding="utf-8")), dict):
                    ingest_valid = False
            except (OSError, UnicodeError, json.JSONDecodeError):
                ingest_valid = False
        for relative in ("ingest", "guide", "reading/units", "reading/sessions", "assessment", "notes"):
            (paper_dir / relative).mkdir(parents=True, exist_ok=True)
        if ingest_valid:
            source_map_path = paper_dir / "ingest" / "source-map.yaml"
            if not source_map_path.exists():
                source_map = generate_source_map(markdown.read_text(encoding="utf-8"), source_hash)
                atomic_write_yaml(source_map_path, source_map)
            validate_source_map(load_yaml(source_map_path), source_hash)
            validation_path = paper_dir / "ingest" / "validation.json"
            if not validation_path.exists():
                atomic_write_json(validation_path, {"schema_version": 1, "blocking_errors": [], "warnings": ["Migrated existing parser output without re-extraction"]})
        timestamp = now_iso()
        migrated = deepcopy(old)
        migrated.update(
            {
                "schema_version": PAPER_SCHEMA,
                "paper_id": old.get("paper_id", paper_id),
                "title": old.get("title") or load_registry(workspace)["papers"][paper_id].get("title") or paper_id,
                "aliases": old.get("aliases", []),
                "identifiers": old.get("identifiers", {}),
                "provenance": {
                    **(old.get("provenance", {}) if isinstance(old.get("provenance"), dict) else {}),
                    "source_sha256": source_hash,
                },
                "related_versions": old.get("related_versions", []),
                "artifacts": {
                    **(old.get("artifacts", {}) if isinstance(old.get("artifacts"), dict) else {}),
                    "source_pdf": str(source_relative).replace("\\", "/"),
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
                    **(old.get("ingest", {}) if isinstance(old.get("ingest"), dict) else {}),
                    "status": "validated" if ingest_valid else "blocked",
                    "source_sha256": source_hash,
                    "validated_at": timestamp if ingest_valid else None,
                    "warnings": ["Additively migrated from paper.yaml v1"],
                },
                "reading_mode": "mastery",
                "learning_goal": old.get("learning_goal", {"mode": "mastery", "statement": None}),
                "reading": {
                    "phase": "guide" if ingest_valid else "ingest",
                    "status": "ready" if ingest_valid else "blocked",
                    "outcome": None,
                    "revision": 1,
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
                    "blocked_reason": None if ingest_valid else "INGEST_ARTIFACT_MISSING",
                    "next_route": {"target": "paper-guide", "mode": "normal", "reason": "migrated paper needs a guide"} if ingest_valid else {"blocked": "INGEST_ARTIFACT_MISSING"},
                    "updated_at": timestamp,
                },
                "legacy_schema_version": 1,
            }
        )
        validate_manifest(migrated)
        migration_id = new_id("migration")
        migration_dir = workspace_paths(workspace)["migrations"] / migration_id
        migration_dir.mkdir(parents=True, exist_ok=False)
        atomic_write_yaml(migration_dir / "paper-v1-backup.yaml", old)
        atomic_write_yaml(
            migration_dir / "record.yaml",
            {
                "schema_version": 1,
                "migration_id": migration_id,
                "kind": "paper-v1-to-v2",
                "paper_id": paper_id,
                "performed_at": timestamp,
                "additive_only": True,
            },
        )
        atomic_write_yaml(paper_dir / "paper.yaml", migrated)
        append_jsonl_rows(
            event_ledger_path(paper_dir),
            [{"schema_version": 1, "event_id": migration_id, "event_type": "paper-migrated", "paper_id": paper_id, "recorded_at": timestamp}],
            id_field="event_id",
        )
        return {"ok": True, "paper_id": paper_id, "migrated": True, "migration_id": migration_id, "schema_version": PAPER_SCHEMA}
    finally:
        release_lock(workspace, paper_id, owner)


def validate_runtime(workspace: Path, selector: str | None = None) -> dict[str, Any]:
    validate_workspace(workspace)
    registry = load_registry(workspace)
    selected = [resolve_paper(workspace, selector, include_complete=True)[0]] if selector else list(registry["papers"])
    papers: list[dict[str, Any]] = []
    valid = True
    for paper_id in selected:
        problems: list[dict[str, Any]] = []
        try:
            paper_dir, manifest = load_paper(workspace, paper_id)
            validate_source_identity(paper_dir, manifest)
            _require_ingest_artifacts(paper_dir, manifest)
            if manifest["reading"]["plan_revision"] > 0:
                load_guide_contracts(paper_dir, manifest)
            event_ids = [row.get("event_id") for row in read_jsonl(event_ledger_path(paper_dir))]
            if len(event_ids) != len(set(event_ids)):
                raise FocusError("DUPLICATE_EVENT", "Paper event ledger contains duplicate IDs")
        except FocusError as exc:
            valid = False
            problems.append(exc.as_dict())
        papers.append({"paper_id": paper_id, "valid": not problems, "problems": problems})
    return {"ok": valid, "workspace": str(workspace.resolve()), "papers": papers}


def repair_lock(workspace: Path, route_id: str, reason: str) -> dict[str, Any]:
    route = load_route(workspace, route_id)
    if route.get("status") != "issued":
        return {"ok": True, "route_id": route_id, "status": route.get("status"), "changed": False}
    transaction_id = route.get("transaction_id")
    if transaction_id:
        transaction = load_yaml(transaction_path(workspace, str(transaction_id)), code="INVALID_TRANSACTION")
        result = finish_transaction(workspace, transaction)
        return {**result, "recovered": True}
    cancelled = cancel_route(workspace, route_id, reason)
    audit = {
        "schema_version": 1,
        "repair_id": new_id("repair"),
        "route_id": route_id,
        "paper_id": route.get("paper_id"),
        "reason": reason,
        "action": "cancelled-uncommitted-route-and-released-lock",
        "recorded_at": now_iso(),
    }
    atomic_write_yaml(workspace_paths(workspace)["migrations"] / f"{audit['repair_id']}.yaml", audit)
    return {"ok": True, "route_id": route_id, "status": cancelled["status"], "repair_id": audit["repair_id"], "phase_advanced": False}


def rebuild_workspace_profile(workspace: Path) -> dict[str, Any]:
    validate_workspace(workspace)
    profile = rebuild_profile(workspace, workspace_paths(workspace)["profile_evidence"], workspace_paths(workspace)["profile"])
    return {"ok": True, "profile": profile, "path": str(workspace_paths(workspace)["profile"])}


STATUS_PRESENTATION = {
    "mastered": ("✓", "已掌握"),
    "provisional": ("◐", "初步掌握"),
    "learning": ("▶", "学习中"),
    "needs-remediation": ("!", "待补缺口"),
    "planned": ("○", "待开始"),
    "skipped": ("↷", "已跳过"),
    "stale": ("↺", "需重学"),
}


GOAL_FALLBACKS = {
    "scout": "判断这篇论文是否值得进一步投入，并定位其与当前研究问题的关系。",
    "study": "形成可用于研究比较、批判和综合的机制理解。",
    "mastery": "独立重构、迁移并在延迟复测中保持这篇核心论文的模型。",
    "overview": "建立这篇论文的问题、方法、证据与限制的整体认识。",
    "deep_understanding": "理解这篇论文的核心机制、证据与适用边界。",
    "reproduction": "掌握复现这篇论文所需的方法、条件与验证步骤。",
    "critique": "审查这篇论文的论证、证据与限制。",
    "research_extension": "理解论文并形成可验证的研究延伸。",
}


def _one_line(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    compact = " ".join(value.split())
    return compact or fallback


def _node_sort_key(nodes: dict[str, dict[str, Any]], node_id: str) -> tuple[float, str, str]:
    node = nodes[node_id]
    raw_order = node.get("order", 0)
    order = float(raw_order) if isinstance(raw_order, (int, float)) else 0.0
    return order, _one_line(node.get("title"), "未命名知识点"), node_id


def _tree_lines(nodes: dict[str, dict[str, Any]], states: dict[str, Any]) -> list[str]:
    children: dict[str | None, list[str]] = {None: []}
    for node_id, node in nodes.items():
        parent = node.get("tree_parent")
        parent_id = str(parent) if parent is not None else None
        children.setdefault(parent_id, []).append(node_id)
        children.setdefault(node_id, [])
    for node_ids in children.values():
        node_ids.sort(key=lambda identifier: _node_sort_key(nodes, identifier))

    rendered: list[str] = []

    def visit(node_id: str, prefix: str, connector: str) -> None:
        status = states.get(node_id, {}).get("status", "planned")
        icon, _ = STATUS_PRESENTATION.get(str(status), STATUS_PRESENTATION["planned"])
        title = _one_line(nodes[node_id].get("title"), "未命名知识点")
        rendered.append(f"{prefix}{connector}{icon} {title}")
        child_ids = children.get(node_id, [])
        child_prefix = prefix + ("│  " if connector == "├─ " else "   " if connector == "└─ " else "")
        for index, child_id in enumerate(child_ids):
            child_connector = "└─ " if index == len(child_ids) - 1 else "├─ "
            visit(child_id, child_prefix, child_connector)

    for root_id in children.get(None, []):
        visit(root_id, "", "")
    return rendered


def _node_title(nodes: dict[str, dict[str, Any]], node_id: object, fallback: str = "当前知识点") -> str:
    if isinstance(node_id, str) and node_id in nodes:
        return _one_line(nodes[node_id].get("title"), fallback)
    return fallback


def _target_node_title(reading: dict[str, Any], nodes: dict[str, dict[str, Any]], statuses: set[str]) -> str:
    targets = [item for item in reading.get("remediation_targets", []) if isinstance(item, dict) and item.get("status") in statuses]
    if not targets:
        return "当前薄弱点"
    targets.sort(key=lambda item: _node_sort_key(nodes, str(item.get("node_id"))) if str(item.get("node_id")) in nodes else (float("inf"), "", str(item.get("node_id"))))
    return _node_title(nodes, targets[0].get("node_id"), "当前薄弱点")


def _goal_text(paper: dict[str, Any]) -> str:
    goal = paper.get("learning_goal")
    if isinstance(goal, dict):
        statement = goal.get("statement")
        if isinstance(statement, str) and statement.strip():
            return _one_line(statement, "理解这篇论文。")
        return GOAL_FALLBACKS.get(str(goal.get("mode")), "理解这篇论文的核心内容并能够复述和应用。")
    return "理解这篇论文的核心内容并能够复述和应用。"


def _why_and_action(paper: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> tuple[str, str]:
    reading = paper.get("reading", {})
    if paper.get("problem") or reading.get("status") == "blocked" or reading.get("blocked_reason"):
        return (
            "当前材料或学习记录存在需要处理的问题，继续学习前必须先恢复到可验证状态。",
            "请让我检查并修复当前论文的学习材料。",
        )
    if reading.get("phase") == "complete":
        if reading.get("outcome") == "complete":
            why = "这篇论文的必学知识点和闭卷检验都已完成，现在适合把理解压缩成自己的整体模型。"
        else:
            why = "本轮学习已经结束，但仍保留少量未完全掌握的内容，现在适合做一次针对性总结。"
        return why, "请用三句话总结这篇论文的核心机制、证据和限制。"

    pending = reading.get("pending_interaction")
    if isinstance(pending, dict):
        kind = pending.get("kind")
        if kind == "plan-confirmation":
            count = len(nodes)
            return (
                "论文拆解和学习路线已经准备好，但还需要你确认是否按这条路线学习。",
                f"请回复：确认按这套 {count} 节点路线开始学习。" if count else "请回复：确认按当前路线开始学习。",
            )
        if kind == "unit-checkpoint":
            title = _node_title(nodes, pending.get("node_id"))
            return (
                f"“{title}”的讲解已经完成，现在需要用自己的话复述，才能判断是否真正掌握。",
                "请不看材料，回答当前检查题。",
            )
        if kind == "remediation-checkpoint":
            title = _node_title(nodes, pending.get("node_id"), "当前薄弱点")
            return (
                f"“{title}”的补缺讲解已经完成，现在需要用一次回答验证误区是否消除。",
                "请不看材料，回答当前补缺检查题。",
            )
        if kind == "grill-question":
            if pending.get("assessment_mode") == "targeted":
                why = "补缺学习已经完成，现在需要通过不看材料的复测确认理解已经稳定。"
            else:
                why = "必学知识点已经完成初步学习，现在需要通过不看材料的回答检验整体掌握。"
            return why, "请不看材料，回答当前检验问题。"

    if reading.get("phase") == "grill" and reading.get("status") == "running":
        return (
            "闭卷回答已经完成，现在需要按掌握标准逐项核对并定位仍然存在的缺口。",
            "请让我评估刚才的闭卷回答。",
        )

    remediation = [item for item in reading.get("remediation_targets", []) if isinstance(item, dict)]
    if any(item.get("status") in {"pending", "teaching"} for item in remediation):
        title = _target_node_title(reading, nodes, {"pending", "teaching"})
        return (
            f"闭卷检验发现“{title}”仍有关键缺口，先补齐这个环节才能继续。",
            f"请开始学习“{title}”的针对性补缺内容。",
        )
    if any(item.get("status") == "ready-for-regrill" for item in remediation):
        title = _target_node_title(reading, nodes, {"ready-for-regrill"})
        return (
            f"“{title}”的补缺已经完成，现在需要一次不看材料的复测来确认掌握。",
            f"请开始“{title}”的闭卷复测。",
        )

    next_step = paper.get("next") if isinstance(paper.get("next"), dict) else {}
    target = next_step.get("target")
    if target == "paper-reader":
        title = _node_title(nodes, next_step.get("node_id"))
        return (
            f"“{title}”的前置内容已经达到继续学习的条件，现在轮到这个节点。",
            f"请开始学习“{title}”。",
        )
    if target == "paper-grill":
        if next_step.get("operation") == "diagnose":
            return (
                "闭卷回答已经完成，现在需要按掌握标准逐项核对并定位仍然存在的缺口。",
                "请让我评估刚才的闭卷回答。",
            )
        return (
            "必学知识点已经完成初步学习，现在需要通过闭卷回答检验是否能够独立重建和迁移。",
            "请开始这篇论文的闭卷检验。",
        )
    if target == "paper-guide":
        return (
            "论文原文已经准备好，但知识树和学习路线仍需建立或修复。",
            "请生成这篇论文的知识树和学习路线。",
        )
    if target == "paper-ingest":
        return (
            "论文原文仍然保留，但结构化学习材料需要重新校验后才能可靠使用。",
            "请重新解析并校验这篇论文。",
        )
    return (
        "当前学习记录已经恢复，但还没有形成明确的下一步。",
        "请重新检查这篇论文的学习状态。",
    )


def status_markdown(workspace: Path, selector: str | None = None) -> str:
    snapshot = inspect_workspace(workspace, selector)
    if not selector:
        lines = ["# 论文学习状态", "", f"当前知识库有 {len(snapshot['papers'])} 篇论文。", ""]
        for paper in snapshot["papers"]:
            if paper.get("phase") == "complete":
                label = "已完成"
            elif paper.get("status") == "blocked":
                label = "需要处理"
            elif paper.get("status") == "awaiting-user":
                label = "等待你的下一步"
            else:
                label = "学习中"
            lines.append(f"- {_one_line(paper.get('title'), '未命名论文')}：{label}")
        return "\n".join(lines) + "\n"
    paper = snapshot["paper"]
    reading = paper["reading"]
    states = reading.get("node_states", {}) if isinstance(reading.get("node_states", {}), dict) else {}
    nodes: dict[str, dict[str, Any]] = {}
    try:
        paper_dir, manifest = load_paper(workspace, str(paper["paper_id"]))
        _, nodes, _ = load_guide_contracts(paper_dir, manifest)
    except FocusError:
        nodes = {}
    counts = {status: 0 for status in STATUS_PRESENTATION}
    for node_id in nodes:
        status = str(states.get(node_id, {}).get("status", "planned"))
        counts[status if status in counts else "planned"] += 1
    total = len(nodes)
    count_parts = [f"{icon} {label} {counts[status]}" for status, (icon, label) in STATUS_PRESENTATION.items() if counts[status]]
    progress = f"进度：已掌握 {counts['mastered']}/{total}；{' · '.join(count_parts)}。" if total else "进度：知识树尚未准备好。"
    legend = "图例：" + " · ".join(f"{icon} {label}" for icon, label in STATUS_PRESENTATION.values())
    tree = _tree_lines(nodes, states)
    why, action = _why_and_action(paper, nodes)
    lines = [
        f"# {_one_line(paper.get('title'), '未命名论文')}",
        "",
        "## 学习目标",
        "",
        _goal_text(paper),
        "",
        "## 学习进度",
        "",
        progress,
        "",
        legend,
        "",
    ]
    if tree:
        lines.extend(["```text", *tree, "```", ""])
    else:
        lines.extend(["知识树尚未准备好。", ""])
    lines.extend(
        [
            "## 为什么现在做这一步",
            "",
            why,
            "",
            "## 现在只做一件事",
            "",
            action,
        ]
    )
    return "\n".join(lines) + "\n"
