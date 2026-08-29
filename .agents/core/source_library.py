"""Canonical Source Library registration and Topic membership seam."""

from __future__ import annotations

import filecmp
import re
import shutil
import unicodedata
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

from .reading_workspace import (
    WorkspaceError,
    _read_document,
    _restore,
    _slug,
    _validate_parser_bundle,
    _write_document,
    validate_source_id,
    validate_topic_id,
)


WINDOWS_EQUIVALENTS = str.maketrans(
    {"<": "＜", ">": "＞", ":": "：", '"': "＂", "/": "／", "\\": "＼", "|": "｜", "?": "？", "*": "＊"}
)
GENERIC_SHORT_NAMES = {"paper", "article", "论文", "论文阅读", "文章", "ai 文章", "reading"}


def normalize_short_name(value: str) -> str:
    if not isinstance(value, str):
        raise WorkspaceError("source_short_name_invalid", "Source Short Name is invalid")
    value = unicodedata.normalize("NFC", value).translate(WINDOWS_EQUIVALENTS)
    value = "".join(character for character in value if unicodedata.category(character) != "Cc")
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value or value.casefold() in GENERIC_SHORT_NAMES:
        raise WorkspaceError("source_short_name_invalid", "Source Short Name is empty or too generic")
    if len(value) > 140:
        value = value[:140].rstrip(" .")
    if not value:
        raise WorkspaceError("source_short_name_invalid", "Source Short Name is invalid")
    return value


def canonical_article_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WorkspaceError("source_url_invalid", "Article source URL is invalid")
    host = parsed.hostname.casefold() if parsed.hostname else ""
    port = parsed.port
    netloc = host if port is None else f"{host}:{port}"
    path = urllib.parse.quote(urllib.parse.unquote(parsed.path or "/"), safe="/%:@")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, val) for key, val in query if not key.casefold().startswith(("utm_", "spm"))]
    return urllib.parse.urlunsplit((parsed.scheme.casefold(), netloc, path, urllib.parse.urlencode(query), ""))


class SourceLibrary:
    """Install each Parser Bundle once and own all ordered Topic references."""

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        if not self.workspace.is_dir():
            raise WorkspaceError("workspace_missing", "Workspace does not exist")

    def _sources(self) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        for source_path in sorted((self.workspace / "sources").glob("*/source.yaml")):
            source = _read_document(source_path)
            self._validate_source(source, source_path.parent.name)
            sources.append(source)
        return sources

    @staticmethod
    def _validate_source(source: dict[str, Any], expected_source_id: str) -> None:
        required = {"source_id", "source_kind", "title", "short_name", "identity"}
        optional = {"published_at", "source_url"}
        if (
            not required.issubset(source)
            or not set(source).issubset(required | optional)
            or source.get("source_id") != expected_source_id
            or source.get("source_kind") not in {"paper_pdf", "article_html"}
            or any(not isinstance(source.get(key), str) or not source[key].strip() for key in required - {"source_id", "source_kind"})
        ):
            raise WorkspaceError("source_invalid", f"Reading Source is invalid: {expected_source_id}")
        validate_source_id(expected_source_id)
        normalize_short_name(source["short_name"])
        if "published_at" in source and not re.fullmatch(r"\d{4}(?:-\d{2}-\d{2})?", source["published_at"]):
            raise WorkspaceError("source_invalid", f"Reading Source is invalid: {expected_source_id}")
        if "source_url" in source:
            canonical_article_url(source["source_url"])

    def get(self, source_id: str) -> dict[str, Any]:
        source_id = validate_source_id(source_id)
        path = self.workspace / "sources" / source_id / "source.yaml"
        if not path.is_file():
            raise WorkspaceError("source_missing", f"Reading Source does not exist: {source_id}")
        source = _read_document(path)
        self._validate_source(source, source_id)
        return source

    def find(self, identity: str) -> dict[str, Any] | None:
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 500:
            raise WorkspaceError("source_identity_invalid", "Source identity is invalid")
        matches = [source for source in self._sources() if source.get("identity") == identity]
        if len(matches) > 1:
            raise WorkspaceError("source_identity_conflict", "Source identity is registered more than once")
        return matches[0] if matches else None

    def find_original(self, source: Path, *, source_kind: str) -> dict[str, Any] | None:
        original_name = {"paper_pdf": "source.pdf", "article_html": "source.html"}.get(source_kind)
        if original_name is None or not source.is_file():
            raise WorkspaceError("source_identity_invalid", "Source identity is invalid")
        for registered in self._sources():
            if registered.get("source_kind") != source_kind:
                continue
            candidate = self.workspace / "sources" / registered["source_id"] / "parser-bundle" / original_name
            if candidate.is_file() and filecmp.cmp(source, candidate, shallow=False):
                return registered
        return None

    def _allocate_id(self, short_name: str, source_kind: str, published_at: str | None) -> str:
        suffix = "paper" if source_kind == "paper_pdf" else "article"
        used = {source["source_id"] for source in self._sources()}
        base = f"{short_name}-{suffix}"
        if base not in used:
            return validate_source_id(base)
        if published_at:
            match = re.match(r"^(\d{4})(?:-(\d{2})-(\d{2}))?", published_at)
            if not match:
                raise WorkspaceError("source_published_at_invalid", "Source publication date is invalid")
            date_part = match.group(1)
            dated = f"{short_name}-{date_part}-{suffix}"
            if dated not in used:
                return validate_source_id(dated)
        number = 2
        while f"{short_name}-{number}-{suffix}" in used:
            number += 1
        return validate_source_id(f"{short_name}-{number}-{suffix}")

    def register(
        self,
        parser_bundle: Path,
        *,
        source_kind: str,
        title: str,
        short_name: str,
        identity: str,
        published_at: str | None = None,
        topic_title: str | None = None,
        topic_id: str | None = None,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        parser_bundle = parser_bundle.resolve()
        metadata = _validate_parser_bundle(parser_bundle)
        if source_kind not in {"paper_pdf", "article_html"} or metadata.get("source_kind") != source_kind:
            raise WorkspaceError("parser_bundle_invalid", "Parser Bundle source kind does not match registration")
        if not isinstance(title, str) or not title.strip():
            raise WorkspaceError("source_title_missing", "A trustworthy Source Title is required")
        title = title.strip()
        short_name = normalize_short_name(short_name)
        if published_at is not None and (not isinstance(published_at, str) or not re.fullmatch(r"\d{4}(?:-\d{2}-\d{2})?", published_at)):
            raise WorkspaceError("source_published_at_invalid", "Source publication date is invalid")
        if source_url is not None:
            source_url = canonical_article_url(source_url)
        existing = self.find(identity)
        if existing is not None:
            shutil.rmtree(parser_bundle, ignore_errors=True)
            if topic_title is not None or topic_id is not None:
                attached = self.attach(existing["source_id"], topic_title=topic_title, topic_id=topic_id)
            else:
                attached = None
            return {"ok": True, "status": "source_reused", "source_id": existing["source_id"], "topic_id": attached, "reused": True}

        source_id = self._allocate_id(short_name, source_kind, published_at)
        sources_root = self.workspace / "sources"
        sources_root.mkdir(parents=True, exist_ok=True)
        source_root = sources_root / source_id
        if source_root.exists():
            raise WorkspaceError("source_exists", f"Reading Source already exists: {source_id}")
        state_path = self.workspace / "state.json"
        state = _read_document(state_path, {"current_source_id": None, "current_topic_id": None, "sources": {}})
        source_states = state.get("sources")
        if not isinstance(source_states, dict):
            raise WorkspaceError("workspace_state_invalid", "Workspace state is invalid")
        state.setdefault("current_topic_id", None)
        state["current_source_id"] = source_id
        source_states[source_id] = {"current_plan_id": None, "current_chunk_id": None}
        source = {
            "source_id": source_id,
            "source_kind": source_kind,
            "title": title,
            "short_name": short_name,
            "identity": identity,
        }
        if published_at is not None:
            source["published_at"] = published_at
        if source_url is not None:
            source["source_url"] = source_url

        topic_path: Path | None = None
        topic: dict[str, Any] | None = None
        resolved_topic_id: str | None = None
        if topic_title is not None or topic_id is not None:
            resolved_topic_id, topic_path, topic = self._prepare_topic(
                topic_title=topic_title,
                topic_id=topic_id if topic_title is not None else None,
                existing_topic_id=topic_id if topic_title is None else None,
            )
            if source_id not in topic["sources"]:
                topic["sources"].append(source_id)

        registration = sources_root / f".{source_id}.{uuid.uuid4().hex}.staging"
        snapshots = {state_path: state_path.read_bytes() if state_path.is_file() else None}
        if topic_path is not None:
            snapshots[topic_path] = topic_path.read_bytes() if topic_path.is_file() else None
        installed = False
        try:
            registration.mkdir()
            parser_bundle.replace(registration / "parser-bundle")
            _write_document(registration / "source.yaml", source)
            registration.replace(source_root)
            installed = True
            _write_document(state_path, state)
            if topic_path is not None and topic is not None:
                _write_document(topic_path, topic)
        except Exception:
            for path, snapshot in snapshots.items():
                _restore(path, snapshot)
            if installed:
                shutil.rmtree(source_root, ignore_errors=True)
            shutil.rmtree(registration, ignore_errors=True)
            raise
        return {"ok": True, "status": "source_registered", "source_id": source_id, "topic_id": resolved_topic_id, "reused": False}

    def _prepare_topic(
        self,
        *,
        topic_title: str | None = None,
        topic_id: str | None = None,
        existing_topic_id: str | None = None,
    ) -> tuple[str, Path, dict[str, Any]]:
        if existing_topic_id is not None:
            resolved = validate_topic_id(existing_topic_id)
            path = self.workspace / "topics" / resolved / "topic.yaml"
            if not path.is_file():
                raise WorkspaceError("topic_missing", f"Topic does not exist: {resolved}")
            topic = _read_document(path)
        else:
            if not isinstance(topic_title, str) or not topic_title.strip():
                raise WorkspaceError("topic_invalid", "Topic title is empty or invalid")
            resolved = validate_topic_id(topic_id) if topic_id else _slug(topic_title, "topic")
            path = self.workspace / "topics" / resolved / "topic.yaml"
            topic = _read_document(path, {"topic_id": resolved, "title": topic_title.strip(), "description": "", "sources": []})
        if topic.get("topic_id") != resolved or not isinstance(topic.get("sources"), list):
            raise WorkspaceError("topic_invalid", f"Topic is invalid: {resolved}")
        return resolved, path, topic

    def attach(
        self,
        source_id: str,
        *,
        topic_title: str | None = None,
        topic_id: str | None = None,
        existing_topic_id: str | None = None,
    ) -> str:
        source_id = validate_source_id(source_id)
        source_root = self.workspace / "sources" / source_id
        source = self.get(source_id)
        bundle = source_root / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {source_id}")
        _validate_parser_bundle(bundle)
        resolved, topic_path, topic = self._prepare_topic(
            topic_title=topic_title,
            topic_id=topic_id if topic_title is not None else None,
            existing_topic_id=existing_topic_id or (topic_id if topic_title is None else None),
        )
        if source_id not in topic["sources"]:
            topic["sources"].append(source_id)
            _write_document(topic_path, topic)
        return resolved
