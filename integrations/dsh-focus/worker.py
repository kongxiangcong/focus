"""Managed FOCUS BlogApplication worker for the DSH native plugin."""
from __future__ import annotations

import argparse
import json
import sys
import threading
import traceback
import zlib
from pathlib import Path


def png_bytes() -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return len(body).to_bytes(4, "big") + kind + body + (zlib.crc32(kind + body) & 0xFFFFFFFF).to_bytes(4, "big")
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 6, 0, 0, 0]))
    return header + ihdr + chunk(b"IDAT", zlib.compress(b"focus")) + chunk(b"IEND", b"")


SOURCE = """# Fixture Paper

## 1 Introduction

The workload stalls on the interconnect.

## 2 Method

![Figure 1](images/image-001.png)

Figure 1 shows the pipeline and its buffers.

## 3 Experiments

Table 1 reports throughput for every baseline.
"""
REFERENCES = "\n\n## 参考文献\n\n1. Fixture Authors. Fixture Paper. arXiv.\n"
BLOG = "\n".join([
    "# 固件论文带读", "", "## 导语与问题背景", "", "第 1 节指出互连是瓶颈。" + "展开说明。" * 160,
    "", "## 方法与机制", "", "核心模块按输入输出展开[1]。" + "机制细节。" * 160,
    "", "## 实验与证据", "", "![Figure 1](assets/image-001.png)", "", "Table 1 对照基线。" + "证据细节。" * 160,
    "", "## 局限与边界", "", "结果只在给定配置成立。" + "边界说明。" * 120, REFERENCES,
])
VALUE = "\n".join([
    "# 论文价值分析：固件论文", "", "## 研究问题", "", "互连瓶颈与搜索成本。" + "问题说明。" * 90,
    "", "## 输入输出", "", "输入是工作负载，输出是候选设计。" + "边界说明。" * 90,
    "", "## 模块拆解", "", "搜索器生成并筛选候选。" + "模块说明。" * 90,
    "", "## 一个运行例子", "", "候选经过合法性检查与估价。" + "推演说明。" * 90,
    "", "## 贡献与边界", "", "本次未运行外部实现。" + "边界说明。" * 90,
])
EVIDENCE = "# Evidence Map\n\n| 贡献 | 原文锚点 | 证据 | 边界 |\n|---|---|---|---|\n| 互连优化 | 第 2 节 | Figure 1 | 固件配置 |\n"


class ControlledRuntime:
    def __init__(self) -> None:
        self.cancelled = threading.Event()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.hold_next = False
        self.reading_blog = BLOG
        self.value_analysis = VALUE
        self.evidence_map = EVIDENCE

    def prepare(self, hold: bool) -> None:
        self.cancelled.clear()
        self.entered.clear()
        self.release.clear()
        self.hold_next = hold

    def classify(self, **_kwargs):
        return {"applicable": True, "direction": "design_space_exploration", "reason": "主贡献是架构设计空间探索"}

    def write_artifact(self, *, artifact, **_kwargs):
        if self.hold_next:
            self.entered.set()
            self.release.wait(30)
            self.hold_next = False
        if self.cancelled.is_set():
            raise RuntimeError("controlled runtime cancelled")
        if artifact == "reading_blog":
            return {"files": {"evidence/evidence-map.md": self.evidence_map, "blog.md": self.reading_blog}, "warnings": []}
        return {"files": {"value-analysis.md": self.value_analysis}, "warnings": []}

    def search_implementation(self, **_kwargs):
        return {"notes": "受控 Runtime 未执行外部仓库，仅验证本地业务闭环。", "level": "paper_reading", "warnings": []}

    def cancel(self):
        self.cancelled.set()
        self.release.set()
        return True


class SubmittedCandidateRuntime:
    """One-shot Runtime that returns only the candidate submitted by DSH."""

    def __init__(self, files: dict[str, str]) -> None:
        self.files = dict(files)
        self.cancelled = threading.Event()

    def write_artifact(self, *, artifact, **_kwargs):
        if self.cancelled.is_set():
            raise RuntimeError("DSH candidate was cancelled")
        if artifact != "reading_blog":
            raise RuntimeError(f"DSH live Runtime cannot write {artifact}")
        return {"files": dict(self.files), "warnings": []}

    def cancel(self):
        self.cancelled.set()
        return True


SOURCE_ID = "Fixture-paper"


def prepare_fixture(workspace: Path) -> None:
    root = workspace / "sources" / SOURCE_ID
    bundle = root / "parser-bundle"
    (bundle / "images").mkdir(parents=True, exist_ok=True)
    (root / "source.yaml").write_text(json.dumps({"source_kind": "paper_pdf", "source_id": SOURCE_ID, "title": "Fixture Paper", "short_name": "Fixture", "identity": "fixture:stage2d"}), encoding="utf-8")
    (bundle / "source.pdf").write_bytes(b"%PDF fixture")
    (bundle / "content.md").write_text(SOURCE, encoding="utf-8")
    (bundle / "metadata.json").write_text(json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "article-parser", "batch_id": "stage2d"}), encoding="utf-8")
    (bundle / "validation.json").write_text(json.dumps({"ok": True, "warnings": []}), encoding="utf-8")
    (bundle / "images" / "image-001.png").write_bytes(png_bytes())
    state = workspace / "state.json"
    if not state.exists():
        state.write_text(json.dumps({"current_source_id": SOURCE_ID, "current_topic_id": None, "sources": {SOURCE_ID: {"current_plan_id": None, "current_chunk_id": None}}}), encoding="utf-8")


class Worker:
    SOURCE_ID = SOURCE_ID

    def __init__(self, focus_root: Path, workspace: Path) -> None:
        sys.path.insert(0, str(focus_root / ".agents"))
        from core import BlogApplication
        self.focus_root = focus_root
        self.workspace = workspace
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.runtime = ControlledRuntime()
        prepare_fixture(workspace)
        self.app = BlogApplication(workspace, runtime=self.runtime, writer_id="dsh-native", network=False)
        self.active: dict | None = None
        self.active_runtime = None
        self.active_done = threading.Event()
        self.lock = threading.RLock()
        if not (workspace / "sources" / self.SOURCE_ID / "blog" / "index.html").is_file():
            self.app.generate(self.SOURCE_ID, request_id="fixture-initial", authorized_by="manual_trigger")

    def list_sources(self):
        return [{"sourceId": self.SOURCE_ID, "title": "Fixture Paper", "publicFixture": True}]

    def live_context(self, source_id: str):
        if source_id != self.SOURCE_ID:
            raise ValueError("unknown public fixture")
        bundle = self.workspace / "sources" / source_id / "parser-bundle"
        method_root = self.focus_root / "methods" / "article-blog"
        return {
            "sourceId": source_id,
            "bundle": (bundle / "content.md").read_text(encoding="utf-8"),
            "images": sorted(path.name for path in (bundle / "images").iterdir() if path.is_file()),
            "method": "\n\n".join([
                (method_root / "SKILL.md").read_text(encoding="utf-8"),
                (method_root / "reference" / "reading-blog-method.md").read_text(encoding="utf-8"),
            ]),
        }

    def status(self, source_id: str):
        value = self.app.status(source_id)
        with self.lock:
            if self.active is not None:
                value["attempt"] = dict(self.active)
                value["runStatus"] = "running"
        return value

    def regenerate(self, source_id: str, request_id: str, attempt_id: str, hold: bool = False):
        with self.lock:
            if self.active is not None:
                raise RuntimeError("a controlled attempt is already active")
            self.runtime.prepare(hold)
            self.active_done.clear()
            self.active = {"attemptId": attempt_id, "requestId": request_id, "status": "running"}
            self.active_runtime = self.runtime

        def run():
            try:
                self.app.regenerate_all(source_id, request_id=request_id, authorized_by="manual_trigger")
            except Exception as exc:
                with self.lock:
                    if self.active is not None:
                        self.active.update(status="failed", error=str(exc))
            else:
                with self.lock:
                    if self.active is not None:
                        self.active["status"] = "completed"
            finally:
                with self.lock:
                    self.active = None
                    self.active_runtime = None
                    self.active_done.set()

        threading.Thread(target=run, name="focus-blog-attempt", daemon=True).start()
        if hold and not self.runtime.entered.wait(5):
            raise RuntimeError("controlled runtime did not reach the cancellation barrier")
        return {"accepted": True, "attemptId": attempt_id}

    def regenerate_live(self, source_id: str, request_id: str, attempt_id: str, files: dict[str, str]):
        required = {"blog.md", "evidence/evidence-map.md"}
        if set(files) != required or not all(isinstance(value, str) for value in files.values()):
            raise ValueError("DSH live candidate must contain blog.md and evidence/evidence-map.md")
        with self.lock:
            if self.active is not None:
                raise RuntimeError("a DSH live attempt is already active")
            runtime = SubmittedCandidateRuntime(files)
            self.active_done.clear()
            self.active = {"attemptId": attempt_id, "requestId": request_id, "status": "running", "kind": "dsh-live"}
            self.active_runtime = runtime

        def run():
            previous = self.app.runtime
            self.app.runtime = runtime
            try:
                self.app.regenerate(
                    source_id, artifact="reading_blog", request_id=request_id,
                    authorized_by="manual_trigger",
                )
            except Exception as exc:
                with self.lock:
                    if self.active is not None:
                        self.active.update(status="failed", error=str(exc))
            else:
                with self.lock:
                    if self.active is not None:
                        self.active["status"] = "completed"
            finally:
                self.app.runtime = previous
                with self.lock:
                    self.active = None
                    self.active_runtime = None
                    self.active_done.set()

        threading.Thread(target=run, name="focus-dsh-live-attempt", daemon=True).start()
        return {"accepted": True, "attemptId": attempt_id}

    def cancel(self, sourceId: str, attemptId: str):
        with self.lock:
            if self.active is None or self.active["attemptId"] != attemptId:
                raise RuntimeError("attempt is not active")
            self.app.cancel(sourceId)
            self.active_runtime.cancel()
        if not self.active_done.wait(5):
            raise RuntimeError("controlled runtime did not terminate after cancellation")
        return self.app.status(sourceId)

    def open(self, source_id: str):
        opened = self.app.open_artifact(source_id, "html")
        return {**opened, "document": Path(opened["path"]).read_text(encoding="utf-8")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--focus-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    worker = Worker(args.focus_root.resolve(), args.workspace.resolve())
    for line in sys.stdin:
        request = json.loads(line)
        try:
            method = request["method"]
            params = request.get("params", {})
            if method == "listSources": value = worker.list_sources()
            elif method == "liveContext": value = worker.live_context(params["sourceId"])
            elif method == "status": value = worker.status(params["sourceId"])
            elif method == "regenerate": value = worker.regenerate(params["sourceId"], params["requestId"], params["attemptId"], bool(params.get("hold")))
            elif method == "regenerateLive": value = worker.regenerate_live(params["sourceId"], params["requestId"], params["attemptId"], params["files"])
            elif method == "cancel": value = worker.cancel(**params)
            elif method == "open": value = worker.open(params["sourceId"])
            elif method == "shutdown":
                print(json.dumps({"id": request["id"], "ok": True, "value": {"stopped": True}}), flush=True)
                return
            else: raise ValueError(f"unknown method: {method}")
            response = {"id": request["id"], "ok": True, "value": value}
        except Exception as exc:
            response = {"id": request.get("id"), "ok": False, "error": {"message": str(exc), "trace": traceback.format_exc(limit=3)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
