"""Source discussion scope and explicit-note orchestration.

The Runtime supplies candidates. This Application fixes the user request's
Source and Bundle before a turn starts and validates every candidate against
that scope before asking Core to read or commit.
"""
from __future__ import annotations

import re
from pathlib import Path

from .reading_workspace import WorkspaceCore, WorkspaceError
from .source_notes import SourceNotes


_SAVE = re.compile(r"记下来|记下|记录(?:下来|为笔记)?|保存(?:为)?(?:一条|一份|个)?(?:简短|简明|新的|短)?笔记|存为笔记|save (?:this )?note|remember this", re.I)
_NEGATIVE = re.compile(
    r"(?:不要|无需|不必|不能|不想|先不|暂不).{0,10}(?:记|记录|保存|存)"
    r"|别(?:把.{0,12})?(?:记|记录|保存|存)"
    r"|(?:don't|do not|not yet)\s*(?:save|remember)", re.I)


class DiscussionApplication:
    def __init__(self, workspace: Path, *, writer_id: str = "local-core"):
        self.core = WorkspaceCore(Path(workspace))
        self.notes = SourceNotes(Path(workspace), writer_id=writer_id)

    @staticmethod
    def method() -> str:
        return (Path(__file__).resolve().parents[2] / "methods" / "source-discussion" / "METHOD.md").read_text(encoding="utf-8")

    def bind(self, *, source_id: str, request_id: str, content: str,
             bundle_version: str | None = None) -> dict:
        SourceNotes._check_request(request_id)
        if not isinstance(content, str) or not content.strip():
            raise WorkspaceError("source_question_invalid", "A question is required")
        current = self.notes.bundle_version(source_id)
        bundle = bundle_version or current
        if bundle != current:
            self.core.read_source_range(start=1, end=1, source_id=source_id, bundle_version=bundle)
        return {"sourceId": source_id, "bundle": bundle, "currentBundleAtBind": current,
                "generation": self.notes.generation(source_id),
                "requestId": request_id, "requestContent": content,
                "saveIntent": bool(_SAVE.search(content) and not _NEGATIVE.search(content))}

    def candidate(self, scope: dict, action: str, arguments: dict) -> dict:
        if not isinstance(arguments, dict):
            raise WorkspaceError("source_scope_invalid", "Tool arguments must be an object")
        source_id, bundle = scope["sourceId"], scope["bundle"]
        if scope.get('generation', 0) != self.notes.generation(source_id):
            raise WorkspaceError("discussion_cleared", "This discussion was cleared")
        if scope["currentBundleAtBind"] == bundle and self.notes.bundle_version(source_id) != bundle:
            raise WorkspaceError("source_bundle_changed", "Source Bundle changed during discussion")
        if action in ("search", "read_range"):
            if arguments.get("source_id", source_id) != source_id or arguments.get("bundle_version", bundle) != bundle:
                raise WorkspaceError("source_scope_invalid", "Tool requested another Source or Bundle")
            bounded = {**arguments, "source_id": source_id, "bundle_version": bundle}
            if action == "search":
                if set(bounded) - {"query", "limit", "source_id", "bundle_version"}:
                    raise WorkspaceError("source_scope_invalid", "Unexpected search fields")
                bounded["limit"] = min(max(int(bounded.get("limit", 5)), 1), 20)
                return self.core.search_source(**bounded)
            if set(bounded) - {"start", "end", "source_id", "bundle_version"}:
                raise WorkspaceError("source_scope_invalid", "Unexpected read fields")
            if bounded["end"] - bounded["start"] > 500:
                raise WorkspaceError("source_range_invalid", "Read at most 501 lines")
            return self.core.read_source_range(**bounded)
        if action == "source_note":
            if self.notes.bundle_version(source_id) != bundle:
                raise WorkspaceError("note_bundle_changed", "Historical Source cannot receive a new anchored Note")
            if not scope["saveIntent"]:
                raise WorkspaceError("note_intent_missing", "The user did not ask to save a note")
            if set(arguments) - {"content", "kind", "origin", "anchor", "evidence_role"}:
                raise WorkspaceError("note_invalid", "Unexpected note candidate fields")
            return self.notes.save(source_id, bundle=bundle, request_id=scope["requestId"],
                                   expected_generation=scope.get('generation', 0),
                                   intent_id=scope["requestId"], **arguments)
        raise WorkspaceError("source_scope_invalid", "This discussion cannot call that tool")

    def cancel(self, scope: dict) -> dict:
        return self.notes.cancel(scope["sourceId"], scope["requestId"])

    def result(self, scope: dict) -> dict | None:
        return self.notes.result(scope["sourceId"], scope["requestId"])


from .workspace_lifecycle import guard_workspace_class
DiscussionApplication = guard_workspace_class(DiscussionApplication)
