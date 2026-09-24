"""Real Runtime adapters behind the blog Application.

The Application owns orchestration; this module is only the writer that produces
one artifact. It drives the Codex CLI the same way the bounded ingestion
inspection does: one turn, an explicit sandbox, and a stable result shape.
Nothing here touches Core or decides what gets published.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from core import BlogExternalError

READING_BLOG_FILES = ("evidence/evidence-map.md", "blog.md")
VALUE_ANALYSIS_FILES = ("value-analysis.md",)

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "applicable": {"type": "boolean"},
        "direction": {
            "type": ["string", "null"],
            "enum": [
                "hardware_architecture",
                "design_space_exploration",
                "compiler",
                "simulator",
                "performance_modeling",
                None,
            ],
        },
        "reason": {"type": "string", "maxLength": 400},
    },
    "required": ["applicable", "direction", "reason"],
    "additionalProperties": False,
}

IMPLEMENTATION_SCHEMA = {
    "type": "object",
    "properties": {
        "notes": {"type": "string"},
        "verification_level": {"type": "string", "enum": ["paper_reading", "static_review", "executed"]},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["notes", "verification_level"],
    "additionalProperties": False,
}


class BlogRuntimeError(RuntimeError):
    """The Runtime could not produce the artifact; the step fails, nothing is published."""


def _excerpt(content: str, limit: int = 12000) -> str:
    return content[:limit]


class CodexBlogRuntime:
    """One Codex turn per artifact, writing into the candidate directory only."""

    def __init__(self, codex_bin: Path, *, model: str, timeout: float = 900.0):
        self.codex_bin = Path(codex_bin).resolve()
        self.model = model
        self.timeout = timeout
        if not self.codex_bin.is_file():
            raise BlogRuntimeError("Codex executable does not exist")
        self._lock = threading.Lock()
        self._process = None

    # ------------------------------------------------------------------ driver

    def _run(self, prompt: str, *, cwd: Path, schema: dict | None = None) -> dict | None:
        command = [
            str(self.codex_bin),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-C",
            str(cwd),
        ]
        if self.model:
            command += ["-m", self.model]
        with tempfile.TemporaryDirectory(prefix="focus-blog-runtime-") as temporary:
            output_path = Path(temporary) / "result.json"
            if schema is not None:
                schema_path = Path(temporary) / "schema.json"
                schema_path.write_text(json.dumps(schema), encoding="utf-8")
                command += ["--output-schema", str(schema_path), "--output-last-message", str(output_path)]
            command.append("-")
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            with self._lock:
                self._process = process
            try:
                process.communicate(prompt, timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.communicate()
                raise BlogRuntimeError("Codex blog turn timed out") from exc
            finally:
                with self._lock:
                    self._process = None
            if process.returncode != 0:
                raise BlogRuntimeError(f"Codex blog turn failed with exit code {process.returncode}")
            if schema is None:
                return None
            try:
                return json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise BlogRuntimeError("Codex blog turn returned invalid JSON") from exc

    def cancel(self) -> bool:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return False
            process.terminate()
            return True

    # ------------------------------------------------------------------ inputs

    @staticmethod
    def _stage_input(bundle: Path, candidate: Path) -> Path:
        """Give the turn a readable copy of the paper text inside its sandbox."""
        scratch = candidate / ".runtime-input"
        scratch.mkdir(parents=True, exist_ok=True)
        content = bundle / "content.md"
        if content.is_file():
            shutil.copy2(content, scratch / "content.md")
        return scratch

    @staticmethod
    def _method_doc(method_dir: Path, name: str) -> str:
        path = Path(method_dir) / "reference" / name
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    # ------------------------------------------------------------------ turns

    def classify(self, *, bundle: Path, evidence: Path, method_dir: Path) -> dict:
        content = (bundle / "content.md").read_text(encoding="utf-8", errors="replace")
        prompt = (
            "判断这篇论文的主要贡献是否落在以下任一方向：硬件架构、设计空间探索（DSE）、编译器、"
            "仿真器、性能建模。只依据下面的论文文本判断，不要联网，不要修改文件。\n"
            "落在其中任一方向时 applicable=true 并给出 direction；否则 applicable=false 且 direction=null。"
            "reason 用一句话说明依据。\n\n"
            + _excerpt(content, 8000)
        )
        result = self._run(prompt, cwd=Path(evidence).parent, schema=CLASSIFY_SCHEMA)
        if not isinstance(result, dict):
            raise BlogRuntimeError("Codex returned no applicability judgement")
        return result

    def write_artifact(
        self,
        *,
        artifact: str,
        bundle: Path,
        candidate: Path,
        method_dir: Path,
        network: bool,
    ) -> dict:
        candidate = Path(candidate).resolve()
        scratch = self._stage_input(Path(bundle), candidate)
        try:
            if artifact == "reading_blog":
                expected = list(READING_BLOG_FILES)
                prompt = self._reading_blog_prompt(method_dir, scratch)
            elif artifact == "value_analysis":
                expected = list(VALUE_ANALYSIS_FILES)
                prompt = self._value_analysis_prompt(method_dir, scratch, candidate)
            else:
                raise BlogRuntimeError(f"Unknown blog artifact: {artifact}")
            self._run(prompt, cwd=candidate)
            files = {}
            for name in expected:
                path = candidate / name
                if not path.is_file() or not path.read_text(encoding="utf-8", errors="replace").strip():
                    raise BlogRuntimeError(f"Codex did not write {name}")
                files[name] = path.read_text(encoding="utf-8")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return {"files": files, "warnings": []}

    def _reading_blog_prompt(self, method_dir: Path, scratch: Path) -> str:
        return (
            "你是 FOCUS 的带读博客写作者。论文正文在 ./.runtime-input/content.md，"
            "写作方法在 " + str(Path(method_dir) / "reference" / "reading-blog-method.md") + "。\n"
            "严格按方法写作，先读方法再动笔，然后写出两个文件：\n"
            "1) ./evidence/evidence-map.md：3-5 项贡献及原文锚点、方法模块、核心公式或算法、"
            "关键图表与实验证据、复现设置与缺失项、主张边界。填完每一项，不留占位符。\n"
            "2) ./blog.md：中文细读长文，至少 2000 字，含导语与问题背景、方法与机制、"
            "实验与证据、局限与边界、参考文献。关键主张用 [n] 引用并在文末给出条目；"
            "引用章节写成第 n 节并在正文里能对应；提到图或表时给出 Figure n / Table n 编号；"
            "需要引用的图片用 ![](/绝对路径之外) 的相对写法 assets/<文件名>，只引用确实存在的图片。\n"
            "区分作者结论、解释性推论与局限；不发明作者、机构、年份、URL、指标或结果；"
            "缺失信息写明待核实。\n"
            "只写这两个文件，不要改动其他文件。"
        )

    def _value_analysis_prompt(self, method_dir: Path, scratch: Path, candidate: Path) -> str:
        evidence_map = candidate / "evidence" / "evidence-map.md"
        return (
            "你是 FOCUS 的论文价值分析写作者。论文正文在 ./.runtime-input/content.md，"
            + ("共享写作证据笔记在 ./evidence/evidence-map.md，" if evidence_map.is_file() else "")
            + "写作方法在 " + str(Path(method_dir) / "reference" / "value-analysis-method.md") + "。\n"
            "严格按方法的固定五段主线写出 ./value-analysis.md：研究问题 → 输入输出 → "
            "模块拆解 → 一个运行例子 → 贡献与边界，至少 1500 字。\n"
            "说明实现是否实际运行；未运行时如实写明，不把论文概念名当成真实函数或文件名。\n"
            "只写这一个文件，不要改动其他文件。"
        )

    def search_implementation(self, *, bundle: Path, method_dir: Path, network: bool) -> dict:
        """Conditional implementation retrieval: no network means no claim of a check."""
        if not network:
            raise BlogExternalError("network_unavailable", "Host has no network route for implementation retrieval")
        content = (bundle / "content.md").read_text(encoding="utf-8", errors="replace")
        prompt = (
            "检索这篇论文的官方实现：先看论文内的代码、项目页与 artifact 链接，再查作者或机构"
            "发布的官方仓库；第三方复现要单独标明。源码可访问时沿核心路径静态核查，"
            "不要声称实际运行过实验。返回 JSON：notes 为 Markdown 笔记（检索范围、核查层级、"
            "核心路径核查表、缺口与影响），verification_level 取 paper_reading/static_review/executed，"
            "warnings 为字符串数组。\n\n" + _excerpt(content, 6000)
        )
        result = self._run(prompt, cwd=Path(method_dir), schema=IMPLEMENTATION_SCHEMA)
        if not isinstance(result, dict) or not isinstance(result.get("notes"), str):
            raise BlogExternalError("implementation_search_failed", "Implementation retrieval returned no notes")
        return result
