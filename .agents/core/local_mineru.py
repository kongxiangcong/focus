"""FOCUS PDF candidates from the local MinerU 4.0.8 Standard V1 API."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .ingestion import IngestionExternalError, persist_candidate_result
from .mineru import MAX_RESPONSE_BYTES, MAX_SOURCE_BYTES, MAX_ZIP_BYTES, ParserError, _normalize


@dataclass(frozen=True)
class LocalProbe:
    state: str
    reason: str
    version: str = ""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ParserError("Local MinerU must not redirect requests", recoverable=False)


class LocalMinerUParser:
    """Submit once, checkpoint the task, and publish only model-backed results.

    This adapter supports the qualified 4.0.8 Standard / V1 jobs contract.
    The service stays on loopback; it does not consume cloud credentials.
    """

    version = "4.0.8"
    model = "standard"
    ocr = False

    def __init__(self, base_url="http://127.0.0.1:18765", *, language="auto", ocr=False, timeout=1800.0, interval=2.0, probe_timeout=3.0):
        parts = urllib.parse.urlsplit(base_url)
        if (parts.scheme != "http" or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parts.username or parts.password or parts.path not in {"", "/"}
                or parts.query or parts.fragment):
            raise ParserError("Local MinerU URL must be an HTTP loopback service root", recoverable=False)
        self.base_url = base_url.rstrip("/")
        self.language = language
        self.ocr = ocr
        self.timeout = timeout
        self.interval = interval
        self.probe_timeout = probe_timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _request(self, path, *, data=None, content_type=None, destination=None, method=None, json_body=None, timeout=60):
        if json_body is not None:
            data = json.dumps(json_body).encode()
            content_type = "application/json"
        headers = {"Accept": "application/zip" if destination else "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if data is not None and hasattr(data, "fileno"):
            headers["Content-Length"] = str(os.fstat(data.fileno()).st_size)
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                if destination:
                    if response.status != 200:
                        raise ParserError("Local MinerU result is not ready")
                    size = 0
                    with destination.open("wb") as output:
                        while block := response.read(1024 * 1024):
                            size += len(block)
                            if size > MAX_ZIP_BYTES:
                                raise ParserError("Local MinerU result exceeds the ZIP limit", recoverable=False)
                            output.write(block)
                    return None
                if response.status == 204:
                    return {}
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ParserError("Local MinerU response exceeds the JSON limit", recoverable=False)
                if method == "PUT" and not raw:
                    return {}
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("Expected object")
                return value
        except urllib.error.HTTPError as exc:
            raise ParserError(
                f"Local MinerU HTTP {exc.code}", recoverable=exc.code >= 500 or exc.code == 429,
                error_id="local_mineru_task_missing" if exc.code == 404 else
                         "local_mineru_busy" if exc.code in {429, 500} else
                         "local_mineru_starting" if exc.code in {502, 503, 504} else "local_mineru_http_error",
            ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise ParserError("Local MinerU is unavailable", error_id="service_unavailable") from exc
        except (ValueError, UnicodeError) as exc:
            raise ParserError("Local MinerU returned invalid JSON", recoverable=False) from exc

    def _health(self):
        health = self._request("/v1/health")
        if health.get("status") != "ok" or health.get("version") != self.version:
            raise ParserError("Local MinerU requires healthy 4.0.8 Standard / V1", recoverable=False,
                              error_id="local_mineru_version_mismatch")

    def probe(self) -> LocalProbe:
        """Inspect the running API and required Standard/ZIP capability before submission."""
        try:
            health = self._request("/v1/health", timeout=self.probe_timeout)
            version = str(health.get("version") or "")
            if health.get("status") != "ok":
                return LocalProbe("starting", "本地 MinerU 正在启动", version)
            if version != self.version:
                return LocalProbe("incompatible", f"本地 MinerU 版本 {version or '未知'} 不兼容，要求 4.0.8", version)
            features = health.get("features") or {}
            if (not isinstance(features, dict) or "file_id" not in (features.get("sources") or [])
                    or "zip" not in (features.get("output_formats") or [])):
                return LocalProbe("incompatible", "本地 MinerU 缺少文件上传或 ZIP 产物能力", version)
            tiers = self._request("/v1/tiers", timeout=self.probe_timeout)
            if "standard" not in {tier.get("id") for tier in tiers.get("data", []) if isinstance(tier, dict)}:
                return LocalProbe("incompatible", "本地 MinerU 不支持 Standard 解析", version)
            return LocalProbe("available", "本地 MinerU 4.0.8 Standard V1 可用", version)
        except ParserError as exc:
            if exc.error_id == "local_mineru_busy":
                return LocalProbe("busy", "本地 MinerU 暂时繁忙")
            if exc.error_id == "local_mineru_starting":
                return LocalProbe("starting", "本地 MinerU 正在启动")
            cause = exc.__cause__
            if isinstance(cause, urllib.error.URLError) and isinstance(cause.reason, ConnectionRefusedError):
                return LocalProbe("absent", "本地 MinerU 未部署或未监听")
            if exc.error_id in {"local_mineru_http_error", "local_mineru_task_missing"} or not exc.recoverable:
                return LocalProbe("incompatible", str(exc))
            return LocalProbe("starting", "本地 MinerU 暂时不可达，稍后重试")

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        source = Path(source)
        if not source.is_file() or source.suffix.lower() != ".pdf" or not 0 < source.stat().st_size <= MAX_SOURCE_BYTES:
            raise ParserError("Source must be a PDF of at most 200 MB", recoverable=False)
        self._health()
        if checkpoint:
            checkpoint({**self._reference_settings(), "reference_kind": "local_selection",
                        "reference_id": "selection", "selection_reason": getattr(self, "selection_reason", "本地优先")})
        with source.open("rb") as pdf:
            digest = hashlib.file_digest(pdf, "sha256").hexdigest()
        upload = self._request("/v1/uploads", json_body={
            "filename": "source.pdf", "bytes": source.stat().st_size,
            "mime_type": "application/pdf", "purpose": "parse", "sha256sum": digest})
        upload_id = upload.get("id")
        self._validate_id(upload_id)
        if upload.get("status") == "completed":
            # V1 SHA-256 dedup returns a ready file without a new PUT.
            completed = upload
        elif upload.get("status") == "pending":
            # Derive the loopback endpoint; never follow a server-provided upload URL.
            with source.open("rb") as pdf:
                self._request(f"/v1/uploads/{upload_id}/content", data=pdf,
                              content_type="application/octet-stream", method="PUT")
            completed = self._request(f"/v1/uploads/{upload_id}/complete", json_body={"sha256sum": digest})
        else:
            raise ParserError("Local MinerU returned an invalid upload state", recoverable=False)
        file_id = (completed.get("file") or {}).get("id")
        self._validate_id(file_id)
        if checkpoint:
            checkpoint({**self._reference_settings(), "reference_kind": "local_submission_unknown",
                        "reference_id": file_id, "file_id": file_id,
                        "selection_reason": getattr(self, "selection_reason", "本地优先")})
        try:
            submitted = self._request("/v1/parse/jobs", json_body={
                "files": [{"source": {"type": "file_id", "file_id": file_id}}],
                "tier": self.model, "ocr_mode": "ocr" if self.ocr else "auto", "output_formats": ["zip"]})
            job_id = submitted.get("job_id")
            self._validate_id(job_id)
        except ParserError as exc:
            # A lost job response must never silently submit the same PDF again.
            raise IngestionExternalError(exc.error_id, str(exc), acceptance_unknown=True) from exc
        reference = {**self._reference_settings(), "reference_id": job_id, "file_id": file_id,
                     "selection_reason": getattr(self, "selection_reason", "本地优先")}
        if checkpoint:
            checkpoint(reference)
        return self._complete(source, candidate, job_id, file_id, checkpoint)

    def _reference_settings(self):
        return {"backend": "local-mineru", "reference_kind": "local_mineru_job", "base_url": self.base_url,
                "version": self.version, "model": self.model, "language": self.language, "ocr": self.ocr}

    @staticmethod
    def _validate_id(task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task_id):
            raise ParserError("Invalid local MinerU task ID", recoverable=False)

    def resume(self, source: Path, candidate: Path, *, checkpoint, on_checkpoint=None):
        expected = self._reference_settings()
        if any(checkpoint.get(k) != v for k, v in expected.items()):
            raise ParserError("Local MinerU checkpoint does not match this parser", recoverable=False)
        if checkpoint.get("reference_kind") == "local_selection":
            # No upload was accepted before this checkpoint.
            return self.parse(source, candidate, checkpoint=on_checkpoint)
        if checkpoint.get("reference_kind") == "local_submission_unknown":
            raise ParserError("本地任务提交结果未知，请检查服务端；不会自动重复提交", recoverable=False,
                              error_id="submission_unknown")
        task_id = checkpoint.get("reference_id")
        self._validate_id(task_id)
        file_id = checkpoint.get("file_id")
        self._validate_id(file_id)
        self._health()
        return self._complete(source, candidate, task_id, file_id, on_checkpoint)

    def _complete(self, source, candidate, task_id, source_file_id, on_checkpoint=None):
        deadline = time.monotonic() + self.timeout
        while True:
            state = self._request(f"/v1/parse/jobs/{task_id}")
            if state.get("job_id") != task_id or state.get("tier") != self.model:
                raise ParserError("Local MinerU task identity or backend mismatch", recoverable=False)
            status = state.get("status")
            if status == "completed":
                break
            if status in {"failed", "partial", "canceled"}:
                raise ParserError("Local MinerU model parsing failed; inspect the server log", recoverable=False,
                                  error_id="local_mineru_parse_failed")
            if status not in {"queued", "running"}:
                raise ParserError("Unknown local MinerU task status", recoverable=False)
            if on_checkpoint:
                on_checkpoint({**self._reference_settings(), "reference_id": task_id, "file_id": source_file_id,
                               "selection_reason": getattr(self, "selection_reason", "本地优先"),
                               "progress": {"status": status, **(state.get("progress") if isinstance(state.get("progress"), dict) else {})}})
            if time.monotonic() >= deadline:
                raise ParserError("Local MinerU is still running; resume this task", error_id="parse_timeout")
            time.sleep(self.interval)
        files = state.get("files", [])
        if (len(files) != 1 or files[0].get("status") != "completed"
                or files[0].get("file_id") != source_file_id
                or (files[0].get("parse") or {}).get("parser_version") != self.version):
            raise ParserError("Local MinerU completed job has invalid file evidence", recoverable=False)
        output_id = ((files[0].get("output_files") or {}).get("zip") or {}).get("file_id")
        self._validate_id(output_id)
        candidate = Path(candidate)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="focus-local-mineru-", dir=candidate.parent) as temp:
            archive = Path(temp) / "result.zip"
            self._request(f"/v1/files/{output_id}/content", destination=archive)
            evidence, raw_evidence = self._evidence(archive)
            _normalize(source, archive, candidate, task_id, self.model, "auto")
            evidence_root = candidate / "mineru"
            evidence_root.mkdir(exist_ok=True)
            for name, raw in raw_evidence.items():
                (evidence_root / name).write_bytes(raw)
        metadata_path = candidate / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.pop("api_version", None)
        metadata.pop("batch_id", None)
        metadata.update({"provider": "local-mineru", "mineru_version": self.version,
                         "protocol_version": "v1", "task_id": task_id, "model_evidence": evidence})
        metadata["selection_reason"] = getattr(self, "selection_reason", "本地优先")
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        content = (candidate / "content.md").read_text(encoding="utf-8")
        title = next((m.group(1).strip() for line in content.splitlines()
                      if (m := re.match(r"^#\s+(.+?)\s*$", line))), Path(source).stem)
        result = {"title": title, "short_name": title, "task_id": task_id}
        persist_candidate_result(candidate, result)
        return result

    def _evidence(self, archive):
        try:
            with zipfile.ZipFile(archive) as bundle:
                evidence, raw_evidence = {}, {}
                for name in ("model_output.json", "middle_json.json", "structured_content.json"):
                    matches = [info for info in bundle.infolist() if info.filename == name]
                    if len(matches) != 1 or matches[0].file_size > 64 * 1024 * 1024:
                        raise ValueError("Missing or oversized model evidence")
                    raw = bundle.read(matches[0])
                    value = json.loads(raw)
                    if not isinstance(value, dict) or not isinstance(value.get("pages"), list) or not value["pages"]:
                        raise ValueError("Empty model evidence")
                    producer = value.get("metadata", {}).get("producer", {})
                    mineru = value.get("extensions", {}).get("mineru", {})
                    if (producer != {"name": "mineru", "version": self.version}
                            or mineru.get("tier") != self.model or value.get("fallback")):
                        raise ValueError("Wrong producer or tier")
                    if name != "model_output.json" and value.get("is_full_document") is not True:
                        raise ValueError("Incomplete document")
                    raw_evidence[name] = raw
                    evidence["mineru/" + name] = {"pages": len(value["pages"]), "bytes": len(raw),
                                                  "sha256": hashlib.sha256(raw).hexdigest()}
                return evidence, raw_evidence
        except (zipfile.BadZipFile, ValueError, UnicodeError, AttributeError) as exc:
            raise ParserError("Local MinerU output lacks valid 4.0.8 Standard model evidence", recoverable=False,
                              error_id="local_mineru_evidence_missing") from exc

    def cancel(self, checkpoint):
        if any(checkpoint.get(k) != v for k, v in self._reference_settings().items()):
            raise ParserError("Local MinerU checkpoint does not match this parser", recoverable=False)
        job_id = checkpoint.get("reference_id")
        self._validate_id(job_id)
        result = self._request(f"/v1/parse/jobs/{job_id}", method="DELETE")
        return result.get("job_id") == job_id and result.get("status") == "canceled"


def configured_pdf_parser():
    from .mineru_selector import AutoMinerUParser
    return AutoMinerUParser()
