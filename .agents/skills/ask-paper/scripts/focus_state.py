#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from focus_core.engine import cancel_route, inspect_workspace, verify_route  # noqa: E402
from focus_core.errors import FocusError  # noqa: E402
from focus_core.maintenance import (  # noqa: E402
    migrate_paper,
    rebuild_workspace_profile,
    repair_lock,
    status_markdown,
    validate_runtime,
)
from focus_core.router import issue_next_route  # noqa: E402
from focus_core.transitions import commit_event  # noqa: E402
from focus_core.workspace import resolve_workspace  # noqa: E402


VERSION = "0.1.0"


def _workspace(args: argparse.Namespace, *, create: bool = False) -> Path:
    explicit = Path(args.workspace) if getattr(args, "workspace", None) else None
    result = resolve_workspace(
        start=Path(getattr(args, "start", ".")),
        explicit=explicit,
        adopt=getattr(args, "adopt", False),
        create=create,
    )
    return Path(str(result["workspace"]))


def command_resolve(args: argparse.Namespace) -> Any:
    return resolve_workspace(
        start=Path(args.start),
        explicit=Path(args.workspace) if args.workspace else None,
        adopt=args.adopt,
        create=not args.no_create,
    )


def command_inspect(args: argparse.Namespace) -> Any:
    workspace = _workspace(args, create=False)
    if args.format == "markdown":
        return status_markdown(workspace, args.paper)
    return inspect_workspace(workspace, args.paper)


def command_next(args: argparse.Namespace) -> Any:
    workspace = _workspace(args, create=bool(args.input))
    return issue_next_route(
        workspace,
        selector=args.paper,
        input_path=Path(args.input) if args.input else None,
    )


def command_verify(args: argparse.Namespace) -> Any:
    workspace = _workspace(args, create=False)
    return verify_route(workspace, args.route_id, target=args.target, helper=args.helper)


def command_commit(args: argparse.Namespace) -> Any:
    workspace = _workspace(args, create=False)
    return commit_event(workspace, args.route_id, Path(args.event))


def command_cancel(args: argparse.Namespace) -> Any:
    workspace = _workspace(args, create=False)
    return cancel_route(workspace, args.route_id, args.reason)


def command_migrate(args: argparse.Namespace) -> Any:
    workspace = _workspace(args, create=False)
    return migrate_paper(workspace, args.paper)


def command_validate(args: argparse.Namespace) -> Any:
    workspace = _workspace(args, create=False)
    result = validate_runtime(workspace, args.paper)
    if not result["ok"]:
        raise FocusError("VALIDATION_FAILED", "Workspace runtime validation failed", report=result)
    return result


def command_rebuild(args: argparse.Namespace) -> Any:
    workspace = _workspace(args, create=False)
    return rebuild_workspace_profile(workspace)


def command_repair(args: argparse.Namespace) -> Any:
    workspace = _workspace(args, create=False)
    return repair_lock(workspace, args.route_id, args.reason)


def _add_workspace(parser: argparse.ArgumentParser, *, with_start: bool = True) -> None:
    parser.add_argument("--workspace", help="Explicit knowledge-base directory")
    if with_start:
        parser.add_argument("--start", default=".", help="Directory from which to discover a knowledge-base")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic state kernel for the project-local paper companion suite")
    parser.add_argument("--version", action="version", version=VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve_parser = subparsers.add_parser("resolve", help="Discover, initialize, or explicitly adopt a knowledge-base")
    _add_workspace(resolve_parser)
    resolve_parser.add_argument("--adopt", action="store_true", help="Add markers to a non-empty unmarked knowledge-base")
    resolve_parser.add_argument("--no-create", action="store_true", help="Report absence instead of creating a new knowledge-base")
    resolve_parser.set_defaults(handler=command_resolve)

    inspect_parser = subparsers.add_parser("inspect", help="Read workspace or paper state without mutation")
    _add_workspace(inspect_parser)
    inspect_parser.add_argument("--paper", help="Paper ID, exact title, directory, or unique alias")
    inspect_parser.add_argument("--format", choices=("json", "markdown"), default="json")
    inspect_parser.set_defaults(handler=command_inspect)

    next_parser = subparsers.add_parser("next", help="Select one stage and issue a revision-bound route")
    _add_workspace(next_parser)
    next_parser.add_argument("--paper", help="Paper ID, exact title, directory, or unique alias")
    next_parser.add_argument("--input", help="New external PDF or parsed source to claim")
    next_parser.set_defaults(handler=command_next)

    verify_parser = subparsers.add_parser("verify-route", help="Validate an issued route without changing state")
    _add_workspace(verify_parser)
    verify_parser.add_argument("--route-id", required=True)
    verify_parser.add_argument("--target", choices=("paper-ingest", "paper-guide", "paper-reader", "paper-grill", "cognitive-profile"))
    verify_parser.add_argument("--helper", action="store_true", help="Validate target against allowed_helpers")
    verify_parser.set_defaults(handler=command_verify)

    commit_parser = subparsers.add_parser("commit", help="Validate and atomically apply one typed, route-bound event")
    _add_workspace(commit_parser)
    commit_parser.add_argument("--route-id", required=True)
    commit_parser.add_argument("--event", required=True, help="JSON or YAML event file inside the route run directory")
    commit_parser.set_defaults(handler=command_commit)

    cancel_parser = subparsers.add_parser("cancel-route", help="Cancel an uncommitted route and release its lock")
    _add_workspace(cancel_parser)
    cancel_parser.add_argument("--route-id", required=True)
    cancel_parser.add_argument("--reason", required=True)
    cancel_parser.set_defaults(handler=command_cancel)

    migrate_parser = subparsers.add_parser("migrate-paper", help="Perform the additive paper.yaml v1 to v2 migration")
    _add_workspace(migrate_parser)
    migrate_parser.add_argument("--paper", required=True)
    migrate_parser.set_defaults(handler=command_migrate)

    validate_parser = subparsers.add_parser("validate", help="Validate workspace, paper, graph, source, and ledger invariants")
    _add_workspace(validate_parser)
    validate_parser.add_argument("--paper")
    validate_parser.set_defaults(handler=command_validate)

    rebuild_parser = subparsers.add_parser("rebuild-profile", help="Rebuild profile.yaml from append-only evidence")
    _add_workspace(rebuild_parser)
    rebuild_parser.set_defaults(handler=command_rebuild)

    repair_parser = subparsers.add_parser("repair-lock", help="Recover a prepared transaction or audit-cancel its route")
    _add_workspace(repair_parser)
    repair_parser.add_argument("--route-id", required=True)
    repair_parser.add_argument("--reason", required=True)
    repair_parser.set_defaults(handler=command_repair)
    return parser


def emit(value: Any) -> None:
    if isinstance(value, str):
        print(value, end="" if value.endswith("\n") else "\n")
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
        emit(result)
        return 0
    except FocusError as exc:
        emit(exc.as_dict())
        return 2
    except KeyboardInterrupt:
        emit(FocusError("INTERRUPTED", "Operation was interrupted before completion").as_dict())
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
