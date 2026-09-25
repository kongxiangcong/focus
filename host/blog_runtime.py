"""Real Runtime adapters behind the blog Application.

The Application owns orchestration; this module is only the writer that produces
one artifact. It drives the Codex CLI the same way the bounded ingestion
inspection does: one turn, an explicit sandbox, and a stable result shape.
Nothing here touches Core or decides what gets published.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from core import BlogExternalError

READING_BLOG_SCHEMA = {
    "type": "object",
    "properties": {
        "evidence_map": {"type": "string"},
        "blog": {"type": "string"},
    },
    "required": ["evidence_map", "blog"],
    "additionalProperties": False,
}
VALUE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {"value_analysis": {"type": "string"}},
    "required": ["value_analysis"],
    "additionalProperties": False,
}

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
    """One Codex turn per artifact; trusted Application code writes its response."""

    def __init__(self, codex_bin: Path, *, model: str, timeout: float = 900.0):
        self.codex_bin = Path(codex_bin).resolve()
        self.model = model
        self.timeout = timeout
        if not self.codex_bin.is_file():
            raise BlogRuntimeError("Codex executable does not exist")
        self._lock = threading.Lock()
        self._process = None

    # ------------------------------------------------------------------ driver

    def _run(self, prompt: str, *, cwd: Path, schema: dict | None = None) -> dict | str:
        command = [
            str(self.codex_bin),
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
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
                command += ["--output-schema", str(schema_path)]
            command += ["--output-last-message", str(output_path)]
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
                return output_path.read_text(encoding="utf-8", errors="replace") if output_path.is_file() else ""
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
        content = (Path(bundle) / "content.md").read_text(encoding="utf-8", errors="replace")
        if artifact == "reading_blog":
            prompt = self._reading_blog_prompt(method_dir, content, candidate)
            result = self._run(prompt, cwd=candidate, schema=READING_BLOG_SCHEMA)
            keys = {"evidence/evidence-map.md": "evidence_map", "blog.md": "blog"}
        elif artifact == "value_analysis":
            prompt = self._value_analysis_prompt(method_dir, content, candidate)
            result = self._run(prompt, cwd=candidate, schema=VALUE_ANALYSIS_SCHEMA)
            keys = {"value-analysis.md": "value_analysis"}
        else:
            raise BlogRuntimeError(f"Unknown blog artifact: {artifact}")
        files = {}
        for name, key in keys.items():
            value = result.get(key) if isinstance(result, dict) else None
            if not isinstance(value, str) or not value.strip():
                raise BlogRuntimeError(f"Codex did not return {name}")
            files[name] = value
        return {"files": files, "warnings": []}

    def _reading_blog_prompt(self, method_dir: Path, content: str, candidate: Path) -> str:
        assets = sorted(path.name for path in (candidate / "assets").iterdir() if path.is_file())
        sections = re.findall(r"^#{1,3}\s+(\d+)(?:\s|\.)", content, flags=re.MULTILINE)
        allowed_sections = ", ".join(dict.fromkeys(sections)) or "按论文目录逐项核对"
        return (
            "你是 FOCUS 的带读博客写作者。下方提供完整论文正文和写作方法。"
            "只返回符合 JSON schema 的两段 Markdown；宿主会把它们写入候选目录。\n"
            "evidence_map：3-5 项贡献及原文锚点、方法模块、核心公式或算法、"
            "关键图表与实验证据、复现设置与缺失项、主张边界。填完每一项，不留占位符。\n"
            "blog：中文细读长文，至少 2000 字，含导语与问题背景、方法与机制、"
            "实验与证据、局限与边界、参考文献。关键主张用 [n] 引用并在文末给出条目；"
            "文末必须有独立标题 `## 参考文献`，每个文内 [n] 必须对应一条格式为 `n. 作者. 题名. 来源` 的文末条目；"
            "不要把证据笔记的编号当成文献引用。引用章节写成第 n 节并在正文里能对应；"
            "仅可引用论文正文中存在的顶层章节编号：" + allowed_sections + "。提到图或表时给出 Figure n / Table n 编号；"
            "需要引用的图片用 ![](assets/<文件名>)，只引用下面列出的图片。\n"
            "区分作者结论、解释性推论与局限；不发明作者、机构、年份、URL、指标或结果；"
            "缺失信息写明待核实。不要尝试读取或修改本地文件。\n\n"
            "可用图片文件名：" + ", ".join(assets) + "\n\n"
            "# 写作方法\n" + self._method_doc(method_dir, "reading-blog-method.md") + "\n\n"
            "# 论文正文\n" + content
        )

    def _value_analysis_prompt(self, method_dir: Path, content: str, candidate: Path) -> str:
        evidence_map = candidate / "evidence" / "evidence-map.md"
        return (
            "你是 FOCUS 的论文价值分析写作者。下方提供完整论文正文、写作方法与共享证据。"
            "只返回符合 JSON schema 的 Markdown；宿主会写入候选目录。\n"
            "严格按方法的固定五段主线写出 value_analysis：研究问题 → 输入输出 → "
            "模块拆解 → 一个运行例子 → 贡献与边界，至少 1500 字。\n"
            "说明实现是否实际运行；未运行时如实写明，不把论文概念名当成真实函数或文件名。\n"
            "不要尝试读取或修改本地文件。\n\n"
            "# 写作方法\n" + self._method_doc(method_dir, "value-analysis-method.md") + "\n\n"
            "# 共享证据笔记\n" + (evidence_map.read_text(encoding="utf-8") if evidence_map.is_file() else "未获得") + "\n\n"
            "# 实现核查笔记\n" + (candidate / "evidence" / "implementation-notes.md").read_text(encoding="utf-8") + "\n\n"
            "# 论文正文\n" + content
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
