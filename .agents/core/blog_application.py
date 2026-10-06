"""Shared blog generation Application.

The Application is the only business orchestration for Blog Output. Hosts and
the Workbench only assemble and forward user actions; every artifact is written
by `BlogCore`, and generated content comes from a Runtime adapter that can be
controlled in tests. Failure, cancellation and late results follow ADR-0012:
only committed attempts may publish, and a blog failure never touches the
Parser Bundle or the reader's private reading assets.
"""

from __future__ import annotations

import importlib.util
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Protocol

from .article_blog import (
    ARTIFACT_FILES,
    DISPLAY_ARTIFACTS,
    EVIDENCE,
    HTML,
    READING_BLOG,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_NOT_APPLICABLE,
    STATUS_PENDING,
    VALUE_ANALYSIS,
    VERIFICATION_LEVELS,
    BlogCore,
    blog_root,
    blog_status,
    read_blog_metadata,
    validate_applicability,
    validate_blog_candidate,
)
from .reading_workspace import WorkspaceError, _read_document, _write_document, validate_source_id
from .source_library import SourceLibrary


BLOG_METHOD_DIRECTORY = "methods/article-blog"
BLOG_AUTHORIZATIONS = ("manual_trigger", "ingestion_confirmation")

RUN_IDLE = "idle"
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"

STEP_PENDING = "pending"
STEP_RUNNING = "running"
STEP_COMPLETED = "completed"
STEP_FAILED = "failed"
STEP_SKIPPED = "skipped"
STEP_REJECTED = "rejected"

#: Steps in execution order. `html` is wired by ticket 04.
BLOG_STEPS = ("prepare", "classify", READING_BLOG, VALUE_ANALYSIS, HTML)

DEGRADED_NOTES_TEMPLATE = "\n".join(
    [
        "# Implementation Notes（实现检索与核查层级）",
        "",
        "> 本次未执行外部实现检索。以下如实记录检索范围与缺口，不把「仅论文阅读」写成「已核查实现」。",
        "",
        "## 检索范围",
        "",
        "- 网络可用性：{network}",
        "- 论文内链接与 artifact：{links}",
        "- 作者／机构官方仓库：{repo}",
        "",
        "## 核查层级",
        "",
        "- 本次核查层级：仅论文阅读（paper_reading）",
        "- 版本信息：未获得",
        "",
        "## 缺口与影响",
        "",
        "- 缺口：{reason}",
        "- 影响：实现相关结论只来自论文陈述，未经源码静态核查或实际运行；"
        "不得把论文概念名当作真实函数或文件名，也不得据此断言未开源。",
    ]
)


class BlogExternalError(RuntimeError):
    def __init__(self, error_id: str, message: str, *, transient: bool = False):
        super().__init__(message)
        self.error_id = error_id
        self.transient = transient


class BlogRuntime(Protocol):
    """Runtime adapter that produces one Blog Output artifact.

    It writes into a candidate directory only; Core decides what is published.
    """

    def write_artifact(
        self,
        *,
        artifact: str,
        bundle: Path,
        candidate: Path,
        method_dir: Path,
        network: bool,
    ) -> dict[str, Any]: ...

    def classify(self, *, bundle: Path, evidence: Path, method_dir: Path) -> dict[str, Any]: ...


def _load_method_script(method_dir: Path):
    script = method_dir / "scripts" / "article2blog.py"
    if not script.is_file():
        raise WorkspaceError("blog_method_missing", f"article-blog method pack is missing: {script}")
    spec = importlib.util.spec_from_file_location("focus_article2blog_runtime", script)
    if spec is None or spec.loader is None:
        raise WorkspaceError("blog_method_missing", "article-blog method pack cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BlogApplication:
    """Persistent blog generation boundary for one Reading Source at a time."""

    def __init__(
        self,
        workspace: Path,
        *,
        runtime: BlogRuntime,
        writer_id: str,
        method_dir: Path | None = None,
        network: bool = True,
    ):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise WorkspaceError("workspace_missing", "Workspace does not exist")
        if not isinstance(writer_id, str) or not writer_id.strip():
            raise WorkspaceError("writer_invalid", "Writer identity is required")
        if not hasattr(runtime, "write_artifact"):
            raise WorkspaceError("blog_runtime_invalid", "Blog Runtime cannot write artifacts")
        if not hasattr(runtime, "classify"):
            raise WorkspaceError("blog_runtime_invalid", "Blog Runtime cannot judge Value Analysis applicability")
        self.runtime = runtime
        self.writer_id = writer_id.strip()
        self.network = bool(network)
        self.method_dir = (
            Path(method_dir).resolve()
            if method_dir is not None
            else Path(__file__).resolve().parents[2] / BLOG_METHOD_DIRECTORY
        )
        self.core = BlogCore(self.workspace)
        self._lock = threading.RLock()
        self._runs_path = self.workspace / "blog" / "runs.json"
        self._candidates = self.workspace / "blog" / "candidates"
        self._recover_interrupted()

    # ------------------------------------------------------------------ state

    def _runs(self) -> dict[str, Any]:
        return _read_document(self._runs_path, {})

    def _write_runs(self, runs: dict[str, Any]) -> None:
        _write_document(self._runs_path, runs)

    def _new_run(self, source_id: str) -> dict[str, Any]:
        return {
            "run_id": uuid.uuid4().hex,
            "source_id": source_id,
            "status": RUN_IDLE,
            "steps": {name: {"status": STEP_PENDING, "attempts": []} for name in BLOG_STEPS},
            "request_id": None,
            "error": None,
        }

    def _run(self, source_id: str) -> dict[str, Any]:
        with self._lock:
            runs = self._runs()
            run = runs.get(source_id)
            if not isinstance(run, dict):
                run = self._new_run(source_id)
                runs[source_id] = run
                self._write_runs(runs)
            for name in BLOG_STEPS:
                run.setdefault("steps", {}).setdefault(name, {"status": STEP_PENDING, "attempts": []})
            return run

    def _save_run(self, run: dict[str, Any]) -> None:
        with self._lock:
            runs = self._runs()
            runs[run["source_id"]] = run
            self._write_runs(runs)

    def _recover_interrupted(self) -> None:
        runs = self._runs()
        changed = False
        for run in runs.values():
            if run.get("status") == RUN_RUNNING:
                run["status"] = RUN_FAILED
                run["error"] = {"error_id": "blog_interrupted", "message": "Blog generation was interrupted"}
                for step in run.get("steps", {}).values():
                    if step.get("status") == STEP_RUNNING:
                        step["status"] = STEP_FAILED
                    for attempt in step.get("attempts", []):
                        if attempt.get("status") == "running":
                            attempt["status"] = "interrupted"
                            attempt["commit_allowed"] = False
                changed = True
        if changed:
            self._write_runs(runs)

    # ------------------------------------------------------------- validation

    def _source_bundle(self, source_id: str) -> tuple[dict[str, Any], Path]:
        source_id = validate_source_id(source_id)
        source = SourceLibrary(self.workspace).get(source_id)
        if source.get("source_kind") not in {"paper_pdf", "article_html"}:
            raise WorkspaceError("source_kind_unsupported", "article-blog accepts PDF and HTML Reading Sources")
        bundle = self.workspace / "sources" / source_id / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {source_id}")
        return source, bundle

    @staticmethod
    def _require_authorization(authorized_by: str) -> str:
        if authorized_by not in BLOG_AUTHORIZATIONS:
            raise WorkspaceError("blog_not_authorized", "Blog generation needs an explicit user authorization")
        return authorized_by

    # ------------------------------------------------------------ public view

    def status(self, source_id: str) -> dict[str, Any]:
        """Three sub-statuses plus applicability and warnings for display."""
        source_id = validate_source_id(source_id)
        with self._lock:
            published = blog_status(self.workspace, source_id)
            run = self._runs().get(source_id)
        projection = dict(published)
        projection["artifacts"] = dict(published["artifacts"])
        if isinstance(run, dict):
            for name in DISPLAY_ARTIFACTS:
                step = run.get("steps", {}).get(name, {})
                if step.get("status") == STEP_RUNNING:
                    projection["artifacts"][name] = {"status": "generating", "updatedAt": None}
            projection["runStatus"] = run.get("status")
            projection["attemptId"] = run.get("request_id")
            projection["error"] = run.get("error")
        else:
            projection["runStatus"] = RUN_IDLE
            projection["error"] = None
        return projection

    def open_artifact(self, source_id: str, artifact: str) -> dict[str, Any]:
        """Locate a published artifact for the Workbench viewer."""
        source_id = validate_source_id(source_id)
        if artifact not in ARTIFACT_FILES:
            raise WorkspaceError("blog_artifact_invalid", f"Unknown Blog Output artifact: {artifact}")
        path = blog_root(self.workspace, source_id) / ARTIFACT_FILES[artifact]
        if not path.is_file():
            raise WorkspaceError("blog_artifact_missing", f"Blog Output artifact is not published: {artifact}")
        return {
            "sourceId": source_id,
            "artifact": artifact,
            "path": str(path),
            "mediaType": "text/html" if artifact == HTML else "text/markdown",
        }

    # --------------------------------------------------------------- pipeline

    def _prepare(self, source_id: str, request_id: str) -> None:
        with self._lock:
            run = self._run(source_id)
            step = run["steps"]["prepare"]
            if run['status'] == RUN_CANCELLED:
                raise WorkspaceError('blog_cancelled', 'Blog generation was cancelled')
            if step["status"] == STEP_COMPLETED and blog_root(self.workspace, source_id).is_dir():
                return
            method = _load_method_script(self.method_dir)
            candidate = self._candidates / f"{source_id}-{uuid.uuid4().hex}"
            attempt = {"attempt_id": uuid.uuid4().hex, "status": "running", "commit_allowed": True}
            step["attempts"].append(attempt)
            step["status"] = STEP_RUNNING
            run["status"] = RUN_RUNNING
            run["request_id"] = request_id
            self._save_run(run)
            try:
                result = method._prepare_registered(self.workspace, source_id, candidate)
                if not isinstance(result, dict) or not result.get("ok"):
                    raise WorkspaceError("blog_candidate_invalid", "Blog Output skeleton could not be prepared")
            except Exception as exc:
                error_id = getattr(exc, "error_id", "blog_prepare_failed")
                step["status"] = STEP_FAILED
                run["status"] = RUN_FAILED
                run["error"] = {"error_id": error_id, "message": str(exc)}
                self._save_run(run)
                raise
            self.core.install_prepared(
                source_id=source_id, candidate=candidate, writer_id=self.writer_id, request_id=request_id + ":prepare"
            )
            attempt["status"] = "completed"
            step["status"] = STEP_COMPLETED
            self._save_run(run)

    def _candidate_dir(self, source_id: str) -> Path:
        target = self._candidates / f"{source_id}-{uuid.uuid4().hex}"
        blog = blog_root(self.workspace, source_id)
        if blog.is_dir():
            shutil.copytree(blog, target)
        else:
            target.mkdir(parents=True)
        return target

    @staticmethod
    def _validate_candidate(
        candidate: Path, bundle: Path, *, require_html: bool = False, require_value_analysis: bool | None = None
    ) -> dict[str, Any]:
        return validate_blog_candidate(
            candidate, bundle=bundle, require_html=require_html, require_value_analysis=require_value_analysis
        )

    def _record_warnings(self, source_id: str, warnings: list[str]) -> list[str]:
        """Warnings of one generation run accumulate across its steps."""
        run = self._run(source_id)
        existing = run.get("warnings") if isinstance(run.get("warnings"), list) else []
        merged = list(existing)
        for item in warnings:
            if isinstance(item, str) and item not in merged:
                merged.append(item)
        run["warnings"] = merged
        self._save_run(run)
        return merged

    def _metadata(self, source_id: str) -> dict[str, Any]:
        metadata = read_blog_metadata(blog_root(self.workspace, source_id))
        if metadata is None:
            raise WorkspaceError("blog_output_missing", f"Blog Output does not exist: {source_id}")
        return metadata

    def _applicability(self, source_id: str) -> dict[str, Any] | None:
        value = self._metadata(source_id).get("value_analysis_applicability")
        return value if isinstance(value, dict) else None

    def _classify(self, source_id: str, request_id: str) -> dict[str, Any]:
        """Decide whether the paper's main contribution is in scope for Value Analysis."""
        _, bundle = self._source_bundle(source_id)
        with self._lock:
            run = self._run(source_id)
            step = run["steps"]["classify"]
            if run['status'] == RUN_CANCELLED:
                raise WorkspaceError('blog_cancelled', 'Blog generation was cancelled')
            decided = self._applicability(source_id)
            if isinstance(decided, dict) and isinstance(decided.get("applicable"), bool):
                step["status"] = STEP_COMPLETED
                self._save_run(run)
                return decided
            step["status"] = STEP_RUNNING
            run["status"] = RUN_RUNNING
            run["request_id"] = request_id
            self._save_run(run)
        try:
            judged = validate_applicability(
                self.runtime.classify(
                    bundle=bundle,
                    evidence=blog_root(self.workspace, source_id) / "evidence",
                    method_dir=self.method_dir,
                )
            )
        except Exception as exc:
            with self._lock:
                run = self._run(source_id)
                if run['status'] != RUN_CANCELLED:
                    run['steps']['classify']['status'] = STEP_FAILED
                    run['status'] = RUN_FAILED
                    run['error'] = {'error_id': getattr(exc, 'error_id', 'blog_classification_failed'),
                                    'message': '博客适用性判定失败；来源已保留，可重试博客。'}
                    self._save_run(run)
            raise
        with self._lock:
            run = self._run(source_id)
            if run['status'] == RUN_CANCELLED:
                raise WorkspaceError('blog_cancelled', 'Blog generation was cancelled')
            self.core.commit(
                source_id=source_id, files={},
                statuses={VALUE_ANALYSIS: STATUS_NOT_APPLICABLE if not judged['applicable'] else STATUS_PENDING},
                writer_id=self.writer_id, request_id=request_id + ':classify', applicability=judged,
            )
            run['steps']['classify']['status'] = STEP_COMPLETED
            self._save_run(run)
            return judged

    def _implementation_notes(self, source_id: str, request_id: str) -> dict[str, Any]:
        """Implementation retrieval is conditional: no network means an honest degrade, never a failure."""
        _, bundle = self._source_bundle(source_id)
        notes: str | None = None
        level = "paper_reading"
        warnings: list[str] = []
        retrieval_failure: str | None = None
        if self.network and hasattr(self.runtime, "search_implementation"):
            try:
                found = self.runtime.search_implementation(bundle=bundle, method_dir=self.method_dir, network=True)
                if isinstance(found, dict) and isinstance(found.get("notes"), str) and found["notes"].strip():
                    notes = found["notes"]
                    reported = found.get("verification_level")
                    if reported in VERIFICATION_LEVELS:
                        level = reported
                    reported_warnings = found.get("warnings")
                    if isinstance(reported_warnings, list):
                        warnings = [item for item in reported_warnings if isinstance(item, str)]
            except Exception as exc:  # a failing retrieval degrades, it does not fail the step
                retrieval_failure = str(exc)
                warnings.append(f"实现检索不可用，已降级为仅论文阅读：{retrieval_failure}")
        if notes is None:
            reason = (
                "本次运行环境无网络，未检索论文内链接与官方仓库"
                if not self.network else
                f"外部实现检索调用失败：{retrieval_failure}"
                if retrieval_failure else "宿主未提供可用的实现检索能力"
            )
            notes = DEGRADED_NOTES_TEMPLATE.format(
                network="可用" if self.network else "不可用（未请求外部检索）",
                links="未检索",
                repo="未检索",
                reason=reason,
            )
            if not warnings:
                warnings.append(reason + "；实现相关结论只来自论文陈述")
        with self._lock:
            if self._run(source_id)['status'] == RUN_CANCELLED:
                raise WorkspaceError('blog_cancelled', 'Blog generation was cancelled')
            self.core.commit(
                source_id=source_id,
                files={"evidence/implementation-notes.md": notes},
                statuses={EVIDENCE: STATUS_COMPLETED},
                writer_id=self.writer_id,
                request_id=request_id + ":implementation-notes",
                warnings=self._record_warnings(source_id, warnings),
                verification_level=level,
            )
            return {"verification_level": level, "warnings": warnings}

    def _fresh(self, source_id: str, artifact: str, attempt_id: str):
        """Re-read the attempt from disk: a concurrent cancel must be visible here."""
        run = self._run(source_id)
        step = run["steps"][artifact]
        attempt = next((entry for entry in step["attempts"] if entry["attempt_id"] == attempt_id), None)
        return run, step, attempt

    def _close_attempt(
        self,
        *,
        run: dict[str, Any],
        step: dict[str, Any],
        attempt: dict[str, Any],
        step_status: str,
        attempt_status: str,
        run_status: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        attempt["status"] = attempt_status
        step["status"] = step_status
        if run_status is not None:
            run["status"] = run_status
        if error is not None:
            run["error"] = error
        self._save_run(run)

    def _complete_run_after_render(self, source_id: str, outcome: dict[str, Any]) -> None:
        """Finish a run without allowing a late renderer to overwrite cancellation."""
        with self._lock:
            run = self._run(source_id)
            if run.get("status") == RUN_CANCELLED:
                return
            run["status"] = RUN_COMPLETED if outcome.get("status") == "completed" else RUN_FAILED
            if run["status"] == RUN_COMPLETED:
                run["error"] = None
            self._save_run(run)

    def _generate_article(
        self, source_id: str, artifact: str, request_id: str, *, require_value_analysis: bool | None = None
    ) -> dict[str, Any]:
        """Run one Runtime-backed article step and commit it through Core."""
        _, bundle = self._source_bundle(source_id)
        with self._lock:
            run = self._run(source_id)
            if run.get("status") == RUN_CANCELLED:
                return {"status": "rejected", "error_id": "blog_rejected"}
            step = run["steps"][artifact]
            attempt_id = uuid.uuid4().hex
            attempt = {"attempt_id": attempt_id, "status": "running", "commit_allowed": True}
            step["attempts"].append(attempt)
            step["status"] = STEP_RUNNING
            run["status"] = RUN_RUNNING
            run["request_id"] = request_id
            self._save_run(run)

        candidate = self._candidate_dir(source_id)
        produced: dict[str, str] = {}
        warnings: list[str] = []
        failure: dict[str, Any] | None = None
        try:
            try:
                result = self.runtime.write_artifact(
                    artifact=artifact,
                    bundle=bundle,
                    candidate=candidate,
                    method_dir=self.method_dir,
                    network=self.network,
                )
            except BlogExternalError as exc:
                raise WorkspaceError(exc.error_id, str(exc)) from exc
            if not isinstance(result, dict):
                raise WorkspaceError("runtime_result_invalid", "Runtime result is invalid")
            files = result.get("files")
            if not isinstance(files, dict) or not files:
                raise WorkspaceError("runtime_result_invalid", "Runtime produced no artifact")
            for name, content in files.items():
                if not isinstance(name, str) or not isinstance(content, str):
                    raise WorkspaceError("runtime_result_invalid", "Runtime produced an invalid artifact")
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise WorkspaceError("runtime_path_invalid", "Runtime wrote outside the candidate directory")
                target = candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                produced[relative.as_posix()] = content
            reported = result.get("warnings")
            if isinstance(reported, list) and all(isinstance(item, str) for item in reported):
                warnings = list(reported)
        except WorkspaceError as exc:
            failure = {"error_id": exc.error_id, "message": str(exc)}
        except RuntimeError as exc:
            failure = {"error_id": getattr(exc, "error_id", "blog_runtime_failed"), "message": str(exc)}

        if failure is None:
            checked = self._validate_candidate(candidate, bundle, require_value_analysis=require_value_analysis)
            if not checked["ok"]:
                failure = {"error_id": "blog_candidate_invalid", "errors": checked["errors"], "message": "; ".join(checked["errors"])}
                warnings = list(checked["warnings"])

        with self._lock:
            run, step, attempt = self._fresh(source_id, artifact, attempt_id)
            if attempt is None or attempt.get("commit_allowed") is False:
                shutil.rmtree(candidate, ignore_errors=True)
                if attempt is not None:
                    self._close_attempt(
                        run=run, step=step, attempt=attempt, step_status=STEP_REJECTED, attempt_status="cancelled"
                    )
                return {"status": "rejected", "error_id": "blog_rejected"}

            if failure is not None:
                shutil.rmtree(candidate, ignore_errors=True)
                self._close_attempt(
                    run=run,
                    step=step,
                    attempt=attempt,
                    step_status=STEP_FAILED,
                    attempt_status="failed",
                    run_status=RUN_FAILED,
                    error={"error_id": failure["error_id"], "message": failure["message"]},
                )
                self.core.commit(
                    source_id=source_id,
                    files={},
                    statuses={artifact: STATUS_FAILED},
                    writer_id=self.writer_id,
                    request_id=request_id + ":fail:" + attempt_id,
                    warnings=self._record_warnings(source_id, warnings) or None,
                )
                return {"status": "failed", **failure}

            merged = self._record_warnings(
                source_id, list(checked["warnings"]) + [item for item in warnings if item not in checked["warnings"]]
            )
            self.core.commit(
                source_id=source_id,
                files=produced,
                statuses={artifact: STATUS_COMPLETED},
                writer_id=self.writer_id,
                request_id=request_id + ":" + artifact + ":" + attempt_id,
                warnings=merged,
            )
            shutil.rmtree(candidate, ignore_errors=True)
            self._close_attempt(
                run=run, step=step, attempt=attempt, step_status=STEP_COMPLETED, attempt_status="completed"
            )
            run["error"] = None
            self._save_run(run)
            return {"status": "completed", "artifact": artifact, "files": sorted(produced), "warnings": merged}

    def _render_html(self, source_id: str, request_id: str) -> dict[str, Any]:
        """Render index.html from the published Markdown.

        Rendering is derivation, not generation: it never rewrites either
        Markdown file, and the published HTML is only replaced once the new
        candidate has passed the shared validator.
        """
        _, bundle = self._source_bundle(source_id)
        with self._lock:
            run = self._run(source_id)
            if run.get("status") == RUN_CANCELLED:
                return {"status": "rejected", "error_id": "blog_rejected"}
            step = run["steps"][HTML]
            attempt_id = uuid.uuid4().hex
            attempt = {"attempt_id": attempt_id, "status": "running", "commit_allowed": True}
            step["attempts"].append(attempt)
            step["status"] = STEP_RUNNING
            run["status"] = RUN_RUNNING
            run["request_id"] = request_id
            self._save_run(run)

        candidate = self._candidate_dir(source_id)
        document: str | None = None
        failure: dict[str, Any] | None = None
        try:
            method = _load_method_script(self.method_dir)
            result = method._render(candidate, embed_images=True, bundle=bundle)
            if not isinstance(result, dict) or not result.get("ok"):
                raise WorkspaceError("blog_render_failed", "index.html could not be rendered")
            document = (candidate / ARTIFACT_FILES[HTML]).read_text(encoding="utf-8")
        except WorkspaceError as exc:
            failure = {"error_id": exc.error_id, "message": str(exc)}
        except Exception as exc:  # a renderer crash must not corrupt published assets
            failure = {"error_id": "blog_render_failed", "message": str(exc)}

        checked: dict[str, Any] | None = None
        if failure is None:
            judged = self._applicability(source_id)
            require_value_analysis = None
            if isinstance(judged, dict):
                if (candidate / ARTIFACT_FILES[VALUE_ANALYSIS]).is_file():
                    require_value_analysis = True
                elif judged.get("applicable") is False:
                    require_value_analysis = False
            checked = self._validate_candidate(
                candidate, bundle, require_html=True, require_value_analysis=require_value_analysis
            )
            if not checked["ok"]:
                failure = {
                    "error_id": "blog_candidate_invalid",
                    "errors": checked["errors"],
                    "message": "; ".join(checked["errors"]),
                }

        with self._lock:
            run, step, attempt = self._fresh(source_id, HTML, attempt_id)
            if attempt is None or attempt.get("commit_allowed") is False:
                shutil.rmtree(candidate, ignore_errors=True)
                if attempt is not None:
                    self._close_attempt(
                        run=run, step=step, attempt=attempt, step_status=STEP_REJECTED, attempt_status="cancelled"
                    )
                return {"status": "rejected", "error_id": "blog_rejected"}

            if failure is not None:
                shutil.rmtree(candidate, ignore_errors=True)
                self._close_attempt(
                    run=run,
                    step=step,
                    attempt=attempt,
                    step_status=STEP_FAILED,
                    attempt_status="failed",
                    run_status=RUN_FAILED,
                    error={"error_id": failure["error_id"], "message": failure["message"]},
                )
                self.core.commit(
                    source_id=source_id,
                    files={},
                    statuses={HTML: STATUS_FAILED},
                    writer_id=self.writer_id,
                    request_id=request_id + ":fail:" + attempt_id,
                )
                return {"status": "failed", **failure}

            merged = self._record_warnings(source_id, list(checked["warnings"]))
            self.core.commit(
                source_id=source_id,
                files={ARTIFACT_FILES[HTML]: document},
                statuses={HTML: STATUS_COMPLETED},
                writer_id=self.writer_id,
                request_id=request_id + ":html:" + attempt_id,
                warnings=merged,
            )
            shutil.rmtree(candidate, ignore_errors=True)
            self._close_attempt(
                run=run, step=step, attempt=attempt, step_status=STEP_COMPLETED, attempt_status="completed"
            )
            run["error"] = None
            self._save_run(run)
            return {"status": "completed", "artifact": HTML, "files": [ARTIFACT_FILES[HTML]], "warnings": merged}

    # ----------------------------------------------------------- user actions

    def generate(self, source_id: str, *, request_id: str, authorized_by: str, start_allowed=None) -> dict[str, Any]:
        """Generate the Blog Output for a Source, retrying only uncommitted steps."""
        source_id = validate_source_id(source_id)
        self._require_authorization(authorized_by)
        self.core.require_writer(self.writer_id)
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise WorkspaceError("request_id_invalid", "Request id is invalid")
        with self._lock:
            if start_allowed is not None and not start_allowed():
                return {**self.status(source_id), 'outcome': {'status': 'rejected'}}
            run = self._run(source_id)
            if run.get("request_id") == request_id and run.get("status") in {RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED}:
                return {**self.status(source_id), "replayed": True}
            published = blog_status(self.workspace, source_id)
            if published["generated"] and all(
                published["artifacts"][name]["status"] in {STATUS_COMPLETED, STATUS_NOT_APPLICABLE}
                for name in DISPLAY_ARTIFACTS
            ):
                return {**self.status(source_id), "replayed": True}
            self._source_bundle(source_id)
            started = self._run(source_id)
            started["warnings"] = []
            started["status"] = RUN_RUNNING
            started["request_id"] = request_id
            started["error"] = None
            self._save_run(started)
        return self._finish_missing(source_id, request_id)

    def _finish_missing(self, source_id: str, request_id: str) -> dict[str, Any]:
        """Continue the same authorized run without resetting cancellation or its request."""
        if self._run(source_id)['status'] == RUN_CANCELLED:
            return {**self.status(source_id), 'outcome': {'status': 'rejected'}}
        self._prepare(source_id, request_id)
        judged = self._classify(source_id, request_id)
        published = blog_status(self.workspace, source_id)
        outcome = {"status": "completed"}
        if published["artifacts"][READING_BLOG]["status"] != STATUS_COMPLETED:
            outcome = self._generate_article(source_id, READING_BLOG, request_id)
        if outcome.get("status") != "completed":
            status = self.status(source_id)
            return {**status, "outcome": outcome, "applicability": judged}
        if judged["applicable"] and published["artifacts"][VALUE_ANALYSIS]["status"] != STATUS_COMPLETED:
            self._implementation_notes(source_id, request_id)
            outcome = self._generate_article(
                source_id, VALUE_ANALYSIS, request_id, require_value_analysis=True
            )
        html_outcome = self._render_html(source_id, request_id)
        self._complete_run_after_render(source_id, html_outcome)
        status = self.status(source_id)
        return {**status, "outcome": outcome, "applicability": judged, "html": html_outcome}

    def regenerate(
        self, source_id: str, *, artifact: str, request_id: str, authorized_by: str
    ) -> dict[str, Any]:
        """Re-run one artifact by name, leaving every other artifact untouched."""
        source_id = validate_source_id(source_id)
        self._require_authorization(authorized_by)
        self.core.require_writer(self.writer_id)
        if artifact not in DISPLAY_ARTIFACTS:
            raise WorkspaceError("blog_artifact_invalid", f"Blog Output artifact is invalid: {artifact}")
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise WorkspaceError("request_id_invalid", "Request id is invalid")
        if not blog_root(self.workspace, source_id).is_dir():
            raise WorkspaceError("blog_output_missing", f"Blog Output does not exist: {source_id}")
        with self._lock:
            run = self._run(source_id)
            if run.get("request_id") == request_id and run.get("status") in {RUN_COMPLETED, RUN_FAILED, RUN_CANCELLED}:
                return {**self.status(source_id), "replayed": True}
            run["status"] = RUN_RUNNING
            run["request_id"] = request_id
            run["error"] = None
            self._save_run(run)
        if artifact == HTML:
            outcome = self._render_html(source_id, request_id)
            self._complete_run_after_render(source_id, outcome)
            return {**self.status(source_id), "outcome": outcome}
        require_value_analysis = None
        if artifact == VALUE_ANALYSIS:
            judged = self._applicability(source_id)
            if not isinstance(judged, dict) or judged.get("applicable") is not True:
                raise WorkspaceError(
                    "blog_artifact_not_applicable",
                    "Value Analysis does not apply to this Reading Source",
                )
            require_value_analysis = True
            self._implementation_notes(source_id, request_id)
        outcome = self._generate_article(source_id, artifact, request_id, require_value_analysis=require_value_analysis)
        if outcome.get("status") != "completed":
            return {**self.status(source_id), "outcome": outcome}
        # index.html is derived from both articles, so it follows a successful rewrite.
        published = blog_status(self.workspace, source_id)
        if any(published['artifacts'][name]['status'] == STATUS_PENDING for name in (READING_BLOG, VALUE_ANALYSIS)):
            return self._finish_missing(source_id, request_id)
        html = self._render_html(source_id, request_id)
        self._complete_run_after_render(source_id, html)
        return {**self.status(source_id), 'outcome': outcome, 'html': html}

    def regenerate_all(self, source_id: str, *, request_id: str, authorized_by: str) -> dict[str, Any]:
        """Rewrite both applicable articles, then replace HTML once they are valid."""
        source_id = validate_source_id(source_id)
        self._require_authorization(authorized_by)
        self.core.require_writer(self.writer_id)
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise WorkspaceError("request_id_invalid", "Request id is invalid")
        if not blog_root(self.workspace, source_id).is_dir():
            raise WorkspaceError("blog_output_missing", f"Blog Output does not exist: {source_id}")
        self._source_bundle(source_id)
        run = self._run(source_id)
        if run.get("full_regeneration_request_id") == request_id and run.get("status") in {RUN_COMPLETED, RUN_FAILED}:
            return {**self.status(source_id), "replayed": True}
        run["full_regeneration_request_id"] = request_id
        run["status"] = RUN_RUNNING
        run["error"] = None
        run["warnings"] = []
        self._save_run(run)
        judged = self._applicability(source_id) or self._classify(source_id, request_id)
        reading = self._generate_article(source_id, READING_BLOG, request_id)
        if reading.get("status") != "completed":
            return {**self.status(source_id), "outcome": reading}
        value = None
        if judged["applicable"]:
            self._implementation_notes(source_id, request_id)
            value = self._generate_article(
                source_id, VALUE_ANALYSIS, request_id, require_value_analysis=True
            )
            if value.get("status") != "completed":
                return {**self.status(source_id), "outcome": value}
        html = self._render_html(source_id, request_id)
        self._complete_run_after_render(source_id, html)
        return {**self.status(source_id), "reading": reading, "value": value, "html": html}

    def cancel(self, source_id: str) -> dict[str, Any]:
        """Stop the running step; its late result can no longer be published."""
        source_id = validate_source_id(source_id)
        with self._lock:
            run = self._run(source_id)
            if run.get("status") != RUN_RUNNING:
                raise WorkspaceError("blog_not_running", "Blog generation is not running")
            closed = False
            for step in run.get("steps", {}).values():
                for attempt in step.get("attempts", []):
                    if attempt.get("status") == "running":
                        attempt["commit_allowed"] = False
                        attempt["status"] = "cancelled"
                        closed = True
                if step.get("status") == STEP_RUNNING:
                    step["status"] = STEP_REJECTED
            run["status"] = RUN_CANCELLED
            run["error"] = {"error_id": "blog_cancelled", "message": "Blog generation was cancelled"}
            self._save_run(run)
        return {**self.status(source_id), "cancelledAttempts": closed}


from .workspace_lifecycle import guard_workspace_class
BlogApplication = guard_workspace_class(BlogApplication)
