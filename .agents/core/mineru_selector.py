"""Server-side PDF backend selection and pinned-task continuation."""
from __future__ import annotations

import os
import json
from pathlib import Path

from .mineru import MinerUIngestionParser, ParserError, _token
from .local_mineru import LocalMinerUParser


class AutoMinerUParser:
    supports_progress_checkpoint = True
    supports_pinned_config = True
    def __init__(self, *, mode=None, local=None, remote=None, model="vlm", language="en",
                 ocr=False, timeout=1800.0, interval=5.0):
        self.mode = (mode or os.getenv("FOCUS_PDF_PARSER", "auto")).strip()
        if self.mode not in {"auto", "local-mineru", "cloud"}:
            raise ParserError("FOCUS_PDF_PARSER must be auto, local-mineru, or cloud", recoverable=False)
        self.local = local or LocalMinerUParser(os.getenv("FOCUS_MINERU_URL", "http://127.0.0.1:18765"),
                                                ocr=ocr, timeout=timeout, interval=interval)
        self.remote = remote or MinerUIngestionParser(model=model, language=language, ocr=ocr,
                                                       timeout=timeout, interval=interval)
        self.model, self.language, self.ocr = model, language, ocr
        self.local_url = self.local.base_url

    def _select(self):
        if self.mode == "cloud":
            _token()
            return "cloud", "已显式配置远端 MinerU API"
        probe = self.local.probe()
        if probe.state == "available":
            return "local-mineru", probe.reason
        if self.mode == "local-mineru" or probe.state in {"starting", "busy"}:
            raise ParserError(probe.reason + "；保持本地优先并稍后重试", error_id="local_not_ready")
        if probe.state not in {"absent", "incompatible"}:
            raise ParserError("本地 MinerU 状态未确认，稍后重试", error_id="local_not_ready")
        try:
            _token()
        except ParserError as exc:
            raise ParserError(probe.reason + "；请配置 MINERU_API_TOKEN 以使用远端精准解析 API",
                              recoverable=False, error_id="authentication_required") from exc
        return "cloud", probe.reason + "，已选择远端 MinerU API"

    def parse(self, source: Path, candidate: Path, *, checkpoint=None):
        backend, reason = self._select()
        if backend == "local-mineru":
            self.local.selection_reason = reason
            return self.local.parse(source, candidate, checkpoint=checkpoint)
        settings = {"backend": "cloud", "config": {"model": self.model, "language": self.language, "ocr": self.ocr},
                    "selection_reason": reason}
        if checkpoint:
            checkpoint({**settings, "reference_kind": "remote_submission_unknown", "reference_id": "submission"})
        def save(value):
            if checkpoint:
                checkpoint({**settings, **value})
        result = self.remote.parse(source, candidate, checkpoint=save)
        self._stamp_remote(candidate, reason)
        return result

    @staticmethod
    def _stamp_remote(candidate, reason):
        path = Path(candidate) / "metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata["selection_reason"] = reason
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def resume(self, source: Path, candidate: Path, *, checkpoint: dict, on_checkpoint=None):
        backend = checkpoint.get("backend")
        if backend is None and checkpoint.get("reference_kind", "").startswith("local_"):
            backend = "local-mineru"
        if backend is None and checkpoint.get("reference_kind") == "batch_id":
            backend = "cloud"  # historical hosted checkpoints
        if backend == "local-mineru":
            config = checkpoint
            local = LocalMinerUParser(config.get("base_url", self.local_url), language=config.get("language", "auto"),
                                      ocr=config.get("ocr", False), timeout=self.local.timeout, interval=self.local.interval)
            local.selection_reason = checkpoint.get("selection_reason", "本地优先")
            return local.resume(source, candidate, checkpoint=checkpoint, on_checkpoint=on_checkpoint)
        if backend == "cloud":
            if checkpoint.get("reference_kind") == "remote_submission_unknown":
                raise ParserError("远端任务提交结果未知，请核对原任务；不会自动重复上传", recoverable=False,
                                  error_id="submission_unknown")
            config = checkpoint.get("config") or {"model": self.model, "language": self.language, "ocr": self.ocr}
            remote = MinerUIngestionParser(hosted=self.remote.hosted, model=config["model"], language=config["language"],
                                           ocr=config["ocr"], timeout=self.remote.timeout, interval=self.remote.interval)
            callback = (lambda value: on_checkpoint({**checkpoint, **value})) if on_checkpoint else None
            result = remote.resume(source, candidate, checkpoint=checkpoint, on_checkpoint=callback)
            self._stamp_remote(candidate, checkpoint.get("selection_reason", "远端任务续接"))
            return result
        raise ParserError("未知 MinerU 后端检查点，拒绝重新提交", recoverable=False)

    def cancel(self, checkpoint: dict) -> bool:
        if checkpoint.get("backend") == "cloud" or checkpoint.get("reference_kind") == "batch_id":
            return self.remote.cancel(checkpoint)
        if checkpoint.get("reference_kind") == "local_mineru_job":
            local = LocalMinerUParser(checkpoint["base_url"], ocr=checkpoint.get("ocr", False))
            return local.cancel(checkpoint)
        return False
