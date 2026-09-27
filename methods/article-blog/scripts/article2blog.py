#!/usr/bin/env python3
"""article-blog method pack: prepare a Blog Output candidate, render index.html, and check it.

This is the single runtime copy of the article-blog scripts. It writes only into
an explicit candidate directory; publishing `sources/<source-id>/blog/` is Core's
job. The renderer is self-contained on purpose: no Node.js, npm package or
network fetch may be required to produce a viewable HTML artifact.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / ".agents"))

from core import WorkspaceError, validate_source_id  # noqa: E402
from core.article_blog import (  # noqa: E402
    ARTICLE_BLOG_METHOD_VERSION,
    ARTIFACT_FILES,
    IMAGE_SUFFIXES,
    VALUE_ANALYSIS_DIRECTIONS,
    VERIFICATION_LEVELS,
    new_blog_metadata,
    _roman_section_number,
    validate_blog_candidate,
)

IMAGE_SUFFIXES = set(IMAGE_SUFFIXES)
MAX_HEADINGS = 20
MAX_FIGURE_CANDIDATES = 12

#: Offline formula rendering: the method pack vendors KaTeX, so no CDN is needed.
KATEX_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "katex"
_KATEX_CACHE: dict[str, tuple[str, str]] = {}

DIRECTION_LABELS = {
    "hardware_architecture": "硬件架构",
    "design_space_exploration": "设计空间探索（DSE）",
    "compiler": "编译器",
    "simulator": "仿真器",
    "performance_modeling": "性能建模",
}

VERIFICATION_LABELS = {
    "paper_reading": "仅论文阅读",
    "static_review": "静态核查",
    "executed": "实际运行",
}


class BlogError(RuntimeError):
    def __init__(self, error_id: str, message: str | None = None):
        if message is None:
            message = error_id
            error_id = "blog_output_invalid"
        super().__init__(message)
        self.error_id = error_id


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlogError(f"Invalid {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise BlogError(f"{path.name} must contain a JSON object")
    return value


# --------------------------------------------------------------------------- prepare


def _headings(markdown: str) -> list[str]:
    found: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^#{1,4}\s+(.+?)\s*$", line)
        if match:
            found.append(match.group(1))
        if len(found) >= MAX_HEADINGS:
            break
    return found


def _image_names(images: Path) -> list[str]:
    if not images.is_dir():
        return []
    return sorted(
        path.relative_to(images).as_posix()
        for path in images.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


EVIDENCE_MAP_TEMPLATE = """# Evidence Map（共享写作证据笔记）

> 写正文之前先把这张表填完并删除所有占位符。每一项都要能回到 Parser Bundle 的章节、图表或公式。

## 论文结构候选

{headings}

## 贡献与原文锚点

| 贡献 | 原文锚点 | 报告的证据 | 假设与边界 |
|---|---|---|---|
| 待补 | 待补 | 待补 | 待补 |

## 方法模块

| 模块 | 输入 | 输出 | 为什么这样设计 | 自然替代方案 | 代价与风险 |
|---|---|---|---|---|---|
| 待补 | 待补 | 待补 | 待补 | 待补 | 待补 |

## 核心公式、算法或接口

- 待补：原文锚点、变量含义、直觉、在流程中的位置、去掉它会失去什么。

## 关键图表

{figures}

## 关键表格与实验

- 待补：验证什么假设、指标方向、基线、决定性差异、成因、混淆因素。

## 复现设置与缺失信息

- 待补：数据、模型或系统、超参数、硬件、成本、依赖、未交代的假设。

## 主张边界

- 待补：证据支持什么、不支持什么；哪些是作者结论，哪些是本文推论。
"""

IMPLEMENTATION_NOTES_TEMPLATE = """# Implementation Notes（实现检索与核查层级）

> 先检查论文内部的代码、项目页和 artifact 链接，再查作者或机构发布的官方仓库。
> 访问不了就记录检索范围与缺口，不写"未开源"这类无法支持的断言。

## 检索范围

- 论文内链接与 artifact：待补
- 作者／机构官方仓库：待补
- 第三方复现（单独标明，不用来补全作者未公开实现）：待补

## 核查层级

- 本次核查层级：待补（仅论文阅读 / 静态核查 / 实际运行）
- 网络可用性：待补
- 版本信息（commit、Release）：待补；未获得版本信息时如实说明，不编造 commit 或行号。

## 核心路径核查

| 论文主张 | 实现位置 | 实验配置或脚本 | 支持的结果 |
|---|---|---|---|
| 待补 | 待补 | 待补 | 待补 |

## 缺口与影响

- 待补：没有访问权限 / 未找到公开材料 / 材料缺失 / 代码未覆盖 / 本次未运行，分别写明，并说明对结论的影响。
"""


def _prepare(bundle: Path, candidate: Path) -> dict:
    """Build the Blog Output skeleton from a published `paper_pdf` Parser Bundle."""
    bundle = bundle.resolve()
    required = [bundle / "content.md", bundle / "metadata.json", bundle / "validation.json"]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise BlogError("parser_bundle_invalid", f"Parser bundle is missing: {', '.join(missing)}")
    metadata = _read_json(bundle / "metadata.json")
    validation = _read_json(bundle / "validation.json")
    if metadata.get("source_kind") not in {"paper_pdf", "article_html"}:
        raise BlogError("source_kind_unsupported", "article-blog accepts PDF and HTML Reading Sources")
    if metadata.get("parser") != "article-parser":
        raise BlogError("parser_bundle_invalid", "Parser bundle is not from article-parser")
    if validation.get("ok") is not True:
        raise BlogError("parser_bundle_invalid", "Parser bundle structural validation did not pass")
    if candidate.exists() and any(candidate.iterdir()):
        raise BlogError("blog_candidate_exists", f"Blog candidate directory is not empty: {candidate}")

    content = (bundle / "content.md").read_text(encoding="utf-8", errors="replace")
    candidate.mkdir(parents=True, exist_ok=True)
    assets = candidate / "assets"
    images = bundle / "images"
    if images.is_dir():
        shutil.copytree(images, assets, dirs_exist_ok=True)
    else:
        assets.mkdir(parents=True, exist_ok=True)
    evidence = candidate / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    names = _image_names(assets)
    figures = "\n".join(
        f"- 候选：`assets/{name}` —— 待补：这张图说什么、支持哪个主张。" for name in names[:MAX_FIGURE_CANDIDATES]
    ) or "- 没有抽取到图片候选；核对论文是否确实没有关键配图。"
    headings = _headings(content)
    (evidence / "evidence-map.md").write_text(
        EVIDENCE_MAP_TEMPLATE.format(
            headings="\n".join(f"- {heading}" for heading in headings) or "- 待补",
            figures=figures,
        ),
        encoding="utf-8",
    )
    (evidence / "implementation-notes.md").write_text(IMPLEMENTATION_NOTES_TEMPLATE, encoding="utf-8")
    return {
        "ok": True,
        "candidate": str(candidate.resolve()),
        "headings": len(headings),
        "assets": len(names),
        "method_version": ARTICLE_BLOG_METHOD_VERSION,
    }


def _prepare_registered(workspace: Path, source_id: str, candidate: Path) -> dict:
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise BlogError("workspace_missing", "Workspace does not exist")
    try:
        source_id = validate_source_id(source_id)
    except WorkspaceError as exc:
        raise BlogError("source_id_invalid", "Source ID is invalid") from exc
    source_path = workspace / "sources" / source_id / "source.yaml"
    if not source_path.is_file():
        raise BlogError("source_missing", f"Reading Source does not exist: {source_id}")
    source = _read_json(source_path)
    if source.get("source_id") != source_id:
        raise BlogError("source_invalid", f"Reading Source is invalid: {source_id}")
    if source.get("source_kind") not in {"paper_pdf", "article_html"}:
        raise BlogError("source_kind_unsupported", "article-blog accepts PDF and HTML Reading Sources")
    bundle = workspace / "sources" / source_id / "parser-bundle"
    if not bundle.is_dir():
        raise BlogError("parser_bundle_missing", f"Parser Bundle does not exist: {source_id}")
    try:
        result = _prepare(bundle, candidate)
        result["metadata"] = new_blog_metadata(
            source_id=source_id, source_kind=source["source_kind"], bundle=bundle
        )
        (candidate / "metadata.json").write_text(
            json.dumps(result["metadata"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except BlogError:
        shutil.rmtree(candidate, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(candidate, ignore_errors=True)
        raise
    result["source_id"] = source_id
    result["assets_dir"] = str((candidate / "assets").resolve())
    return result


# --------------------------------------------------------------------------- markdown


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _math_span(tex: str, *, display: bool) -> str:
    """Keep the TeX source visible, and let the embedded renderer replace it.

    The file must stay readable without JavaScript, so the raw TeX is the
    fallback content of the span rather than an empty placeholder.
    """
    kind = "math-display" if display else "math-inline"
    return f'<span class="{kind}" data-tex="{html.escape(tex, quote=True)}">{_escape(tex)}</span>'


def _math_inline(tex: str) -> str:
    return _math_span(html.unescape(tex), display=False)


def _math_block(tex: str) -> str:
    return _math_span(html.unescape(tex), display=True)


def _inline(text: str, image_src) -> str:
    text = _escape(text)
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: _math_block(m.group(1)), text, flags=re.DOTALL)
    text = re.sub(r"(?<!\\)\$([^$\n]+?)\$", lambda m: _math_inline(m.group(1)), text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\)",
        lambda m: f'<figure><img src="{image_src(m.group(2))}" alt="{m.group(1)}">'
        + (f"<figcaption>{m.group(1)}</figcaption>" if m.group(1) else "")
        + "</figure>",
        text,
    )
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def _table_rows(block: list[str]) -> str:
    cells = [ [cell.strip() for cell in line.strip().strip("|").split("|")] for line in block if line.strip().startswith("|") ]
    rows = [row for index, row in enumerate(cells) if index != 1]
    body = []
    for index, row in enumerate(rows):
        tag = "th" if index == 0 else "td"
        body.append("<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in row) + "</tr>")
    return "<table>" + "".join(body) + "</table>"


def _list_block(lines: list[str], image_src) -> str:
    ordered = bool(re.match(r"^\s*\d+[.)]\s+", lines[0]))
    tag = "ol" if ordered else "ul"
    items: list[str] = []
    for line in lines:
        content = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)
        if re.match(r"^\s{2,}(?:[-*+]|\d+[.)])\s+", line) and items:
            items[-1] = items[-1][:-len("</li>")] + _list_block([line], image_src) + "</li>"
            continue
        items.append(f"<li>{_inline(content, image_src)}</li>")
    return f"<{tag}>" + "".join(items) + f"</{tag}>"


def _markdown_to_html(markdown: str, image_src) -> str:
    """Render the Markdown subset the method produces into HTML fragments."""
    text = markdown.replace("\r\n", "\n")
    fences: list[str] = []

    def stash_fence(match: re.Match) -> str:
        language = match.group(1) or ""
        fences.append(
            f'<pre class="language-{_escape(language)}"><code>{_escape(match.group(2))}</code></pre>'
        )
        return f"\n\u0000FENCE{len(fences) - 1}\u0000\n"

    text = re.sub(r"```(\w*)\n(.*?)```", stash_fence, text, flags=re.DOTALL)

    blocks: list[str] = []
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        fence = re.fullmatch(r"\u0000FENCE(\d+)\u0000", stripped)
        if fence:
            blocks.append(fences[int(fence.group(1))])
            index += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2), image_src)}</h{level}>")
            index += 1
            continue
        if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
            blocks.append("<hr>")
            index += 1
            continue
        if stripped.startswith("|"):
            table: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table.append(lines[index])
                index += 1
            blocks.append(_table_rows(table))
            continue
        if stripped.startswith(">"):
            quoted: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quoted.append(re.sub(r"^\s*>\s?", "", lines[index]))
                index += 1
            blocks.append(f"<blockquote>{_markdown_to_html('\n'.join(quoted), image_src)}</blockquote>")
            continue
        if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line):
            group: list[str] = []
            while index < len(lines) and (
                re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", lines[index]) or lines[index].startswith("  ")
            ):
                group.append(lines[index])
                index += 1
            blocks.append(_list_block(group, image_src))
            continue
        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() and not re.match(
            r"^(?:#{1,6}\s|>|[-*+]\s|\d+[.)]\s|\||```)", lines[index].strip()
        ):
            paragraph.append(lines[index])
            index += 1
        if paragraph:
            blocks.append(f"<p>{_inline(' '.join(paragraph), image_src)}</p>")
        else:
            blocks.append(f"<p>{_inline(stripped, image_src)}</p>")
            index += 1
    return "\n".join(blocks)


# --------------------------------------------------------------------------- render


PAGE_CSS = """
:root { color-scheme: light; --paper:#ffffff; --ink:#1f2328; --muted:#5b6570; --line:#d8dee4; --accent:#2457a7; --code:#f5f7fa; --warn:#8a5a00; --warn-bg:#fff8e6; }
span.math-inline, span.math-display { font-family:"Cascadia Code","SFMono-Regular",Consolas,monospace; background:var(--code); border-radius:4px; padding:.1em .35em; }
span.math-display { display:block; padding:.9rem; margin:1.3rem 0; overflow:auto; border:1px solid var(--line); border-radius:8px; }
.katex-display { display:block; margin:1.3rem 0; text-align:center; overflow:auto; }
.katex { font-size:1.05em; }
* { box-sizing: border-box; }
body { margin:0; background:var(--paper); color:var(--ink); font:17px/1.78 system-ui,-apple-system,"Segoe UI","Noto Sans SC",sans-serif; }
header { border-bottom:1px solid var(--line); padding:20px 0 0; background:var(--paper); position:sticky; top:0; }
.wrap { width:min(920px, calc(100% - 36px)); margin:0 auto; }
.tabs { display:flex; gap:4px; }
.tab { appearance:none; border:1px solid var(--line); border-bottom:none; background:var(--code); color:var(--muted);
       padding:10px 18px; border-radius:8px 8px 0 0; cursor:pointer; font-size:15px; }
.tab[aria-selected="true"] { background:var(--paper); color:var(--ink); font-weight:600; }
.panel { display:none; padding:8px 0 64px; }
.panel[data-active="true"] { display:block; }
h1,h2,h3,h4 { line-height:1.35; margin:1.7em 0 .6em; }
h1 { font-size:2rem; border-bottom:2px solid var(--line); padding-bottom:.4em; }
h2 { font-size:1.5rem; border-bottom:1px solid var(--line); padding-bottom:.3em; }
a { color:var(--accent); }
img { display:block; max-width:100%; height:auto; margin:1.4rem auto; border-radius:8px; }
figure { margin:1.6rem 0; }
figcaption { text-align:center; color:var(--muted); font-size:14px; margin-top:.5rem; }
blockquote { margin:1.3rem 0; padding:.2rem 1rem; color:var(--muted); border-left:4px solid var(--accent); }
pre,code { font-family:"Cascadia Code","SFMono-Regular",Consolas,monospace; background:var(--code); }
code { padding:.1em .35em; border-radius:4px; }
pre { padding:1rem; overflow:auto; border:1px solid var(--line); border-radius:8px; }
pre code { padding:0; }
pre.math-display { text-align:center; }
table { display:block; width:100%; overflow:auto; border-collapse:collapse; margin:1.4rem 0; }
th,td { border:1px solid var(--line); padding:.5rem .7rem; vertical-align:top; }
th { background:var(--code); text-align:left; }
hr { border:0; border-top:1px solid var(--line); margin:2rem 0; }
footer { border-top:1px solid var(--line); color:var(--muted); font-size:14px; padding:20px 0 48px; }
footer .warn { background:var(--warn-bg); color:var(--warn); border:1px solid #f0dca8; border-radius:8px; padding:12px 16px; margin-bottom:16px; }
.source-evidence { border-top:1px solid var(--line); padding:18px 0 30px; }
.source-evidence details { margin:.5rem 0; }
.source-evidence pre { white-space:pre-wrap; overflow-wrap:anywhere; font-size:13px; }
.not-applicable { border:1px dashed var(--line); border-radius:8px; padding:20px; color:var(--muted); }
"""

PAGE_JS = """
document.addEventListener('click', function (event) {
  var source = event.target.closest('a.source-anchor');
  if (source) {
    var excerpt = document.getElementById(source.getAttribute('href').slice(1));
    if (excerpt && excerpt.tagName === 'DETAILS') { excerpt.open = true; }
    return;
  }
  var tab = event.target.closest('.tab');
  if (!tab) { return; }
  document.querySelectorAll('.tab').forEach(function (item) {
    var selected = item === tab;
    item.setAttribute('aria-selected', selected ? 'true' : 'false');
    var panel = document.getElementById(item.getAttribute('aria-controls'));
    if (panel) { panel.setAttribute('data-active', selected ? 'true' : 'false'); }
  });
});
"""

#: KaTeX is embedded, so the page renders formulas with no network at all. The
#: TeX source stays in the DOM as the fallback when scripting is unavailable.
KATEX_INIT_JS = """
(function () {
  if (typeof katex === 'undefined') { return; }
  var nodes = document.querySelectorAll('[data-tex]');
  for (var index = 0; index < nodes.length; index += 1) {
    var node = nodes[index];
    try {
      katex.render(node.getAttribute('data-tex') || '', node, {
        displayMode: node.classList.contains('math-display'),
        throwOnError: false,
        strict: 'ignore'
      });
    } catch (error) {
      node.setAttribute('title', '公式渲染失败，页面显示原始 TeX');
    }
  }
})();
"""


def _katex_runtime() -> tuple[str, str]:
    """Load the vendored KaTeX CSS and script, with fonts inlined as data URIs."""
    cached = _KATEX_CACHE.get("css")
    if cached is not None:
        return cached
    css_path = KATEX_DIRECTORY / "katex.min.css"
    script_path = KATEX_DIRECTORY / "katex.min.js"
    css = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
    script = script_path.read_text(encoding="utf-8") if script_path.is_file() else ""
    if css:
        css = _inline_katex_fonts(css, KATEX_DIRECTORY / "fonts")
    value = (css, script)
    _KATEX_CACHE["css"] = value
    return value


def _inline_katex_fonts(css: str, fonts: Path) -> str:
    """Replace font URLs with data URIs so the page needs no directory beside it."""

    def embed(match: re.Match) -> str:
        path = fonts / match.group(1)
        if not path.is_file():
            return "none"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return 'url("data:font/woff2;base64,' + encoded + '")'

    css = re.sub(r"url\((?:fonts/)?([\w\-]+\.woff2)\)", embed, css)
    # Browsers pick woff2; keeping woff/ttf beside it would only inflate the file.
    css = re.sub(
        r",\s*url\((?:fonts/)?[\w\-]+\.(?:woff|ttf)\)\s*format\(\s*[\"']?(?:woff|truetype)[\"']?\s*\)",
        "",
        css,
    )
    return css


def _image_source(blog_dir: Path, embed: bool):
    def resolve(link: str) -> str:
        if "://" in link:
            return link
        path = (blog_dir / link).resolve()
        if embed and path.is_file():
            suffix = path.suffix.lower()
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".svg": "image/svg+xml",
            }.get(suffix)
            if mime is None:
                return _escape(link)
            return "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        return _escape(link)

    return resolve


def _html_document(
    title: str,
    panels: list[tuple[str, str, str]],
    footer: str,
    *,
    embed_katex: bool = False,
    source_evidence: str = "",
) -> str:
    tabs = "\n".join(
        f'<button class="tab" role="tab" id="tab-{index}" aria-controls="panel-{index}" '
        f'aria-selected="{"true" if index == 0 else "false"}">{_escape(label)}</button>'
        for index, (label, _, _) in enumerate(panels)
    )
    bodies = "\n".join(
        f'<section class="panel" id="panel-{index}" role="tabpanel" aria-labelledby="tab-{index}" '
        f'data-kind="{_escape(kind)}" data-active="{"true" if index == 0 else "false"}">{body}</section>'
        for index, (_, body, kind) in enumerate(panels)
    )
    styles = f"<style>{PAGE_CSS}</style>"
    scripts = f"<script>{PAGE_JS}</script>"
    if embed_katex:
        katex_css, katex_script = _katex_runtime()
        if katex_css:
            styles += f"\n<style>{katex_css}</style>"
        if katex_script:
            scripts = f"<script>{katex_script}</script>\n{scripts}\n<script>{KATEX_INIT_JS}</script>"
    return (
        "<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<meta name=\"generator\" content=\"article-blog {ARTICLE_BLOG_METHOD_VERSION}\">\n"
        f"<title>{_escape(title)}</title>\n{styles}\n</head>\n<body>\n"
        "<header><div class=\"wrap\"><div class=\"tabs\" role=\"tablist\">" + tabs + "</div></div></header>\n"
        "<main class=\"wrap\">" + bodies + source_evidence + "</main>\n"
        + ("<footer><div class=\"wrap\">" + footer + "</div></footer>\n" if footer else "") +
        f"{scripts}\n</body>\n</html>\n"
    )


NOT_APPLICABLE_PAGE = (
    '<div class="not-applicable">'
    "<h2>架构价值分析不适用</h2>"
    "<p><strong>判定：</strong>不适用</p>"
    "<p><strong>判定理由：</strong>{reason}</p>"
    "<p>{direction}</p>"
    "<p>带读博客仍然完整生成；本页不补写价值分析，也不把「不适用」写成失败。</p>"
    "<h3>适用方向</h3><ul>{directions}</ul>"
    "<p>只有论文主要贡献落在硬件架构、设计空间探索、编译器、仿真器或性能建模之一时，"
    "价值分析才会生成。</p>"
    "</div>"
)

VALUE_PENDING_PAGE = (
    '<div class="not-applicable">'
    "<h2>架构价值分析本次未生成</h2>"
    "<p>带读博客已生成；价值分析尚未写入本目录（生成失败或尚未完成）。</p>"
    "<p>可用「重新生成价值分析」单独重跑，带读博客与已有 HTML 不受影响。</p>"
    "</div>"
)

VALUE_UNDECIDED_PAGE = (
    '<div class="not-applicable">'
    "<h2>架构价值分析尚未判定</h2>"
    "<p>本次运行还没有判定论文主要贡献是否落在价值分析的适用方向内。</p>"
    "</div>"
)


def _value_page(metadata: dict) -> str:
    """What the second page shows when there is no value-analysis.md to render."""
    judgement = metadata.get("value_analysis_applicability")
    judgement = judgement if isinstance(judgement, dict) else {}
    applicable = judgement.get("applicable")
    if applicable is False:
        reason = judgement.get("reason")
        reason = reason.strip() if isinstance(reason, str) and reason.strip() else "未提供判定理由"
        direction = judgement.get("direction")
        direction_text = (
            f"本次未把论文归入任何适用方向（记录值：{_escape(str(direction))}）。"
            if direction
            else "本次未把论文归入任何适用方向。"
        )
        return NOT_APPLICABLE_PAGE.format(
            reason=_escape(reason),
            direction=direction_text,
            directions="".join(
                f"<li>{_escape(DIRECTION_LABELS.get(name, name))}（{_escape(name)}）</li>"
                for name in VALUE_ANALYSIS_DIRECTIONS
            ),
        )
    if applicable is True:
        return VALUE_PENDING_PAGE
    return VALUE_UNDECIDED_PAGE


def _footer(metadata: dict) -> str:
    """Diagnostics remain in metadata; the reading page has no audit footer."""
    return ""


SOURCE_MENTION = re.compile(
    r"第\s*(\d+(?:\.\d+)*)\s*节|\b(Figure|Fig\.|Table)\s*(\d+)\b|公式\s*[（(]\s*(\d+)\s*[)）]",
    flags=re.IGNORECASE,
)


def _bundle_anchors(bundle: Path | None) -> dict[str, tuple[str, str]]:
    """Keep traceable source excerpts inside the self-contained HTML."""
    if bundle is None or not (bundle / "content.md").is_file():
        return {}
    lines = (bundle / "content.md").read_text(encoding="utf-8", errors="replace").splitlines()
    anchors: dict[str, tuple[str, str]] = {}
    for index, line in enumerate(lines):
        section = re.match(r"^\s*#{0,6}\s*(\d+(?:\.\d+){0,3})\s+\S", line)
        number = section.group(1) if section else None
        roman = re.match(r"^#{1,6}\s+([IVXLCDM]+)(?:[.)]\s+|\s+)\S", line, re.IGNORECASE)
        if roman:
            token = roman.group(1).upper()
            values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
            value = sum(-values[c] if i + 1 < len(token) and values[c] < values[token[i + 1]]
                        else values[c] for i, c in enumerate(token))
            if _roman_section_number(value) == token:
                number = str(value)
        if number:
            key = "section-" + number.replace(".", "-")
            anchors.setdefault(key, (f"原文第 {number} 节", "\n".join(lines[index:index + 8])[:1000]))
        figure = re.match(r"^\s*(Figure|Fig\.|Table)\s*(\d+)\s*(?:[:.]|\s+)", line, flags=re.IGNORECASE)
        if not figure:
            figure = re.match(r"^\s*!\[(Figure|Fig\.|Table)\s*(\d+)\]", line, flags=re.IGNORECASE)
        if figure:
            kind = "table" if figure.group(1).lower() == "table" else "figure"
            number = figure.group(2)
            anchors.setdefault(f"{kind}-{number}", (f"原文 {figure.group(1)} {number}", line[:1000]))
        formula = re.search(r"\\tag\{(\d+)\}", line)
        if formula:
            number = formula.group(1)
            anchors.setdefault(f"formula-{number}", (f"原文公式（{number}）", line[:1000]))
    return anchors


def _link_bundle_mentions(body: str, anchors: dict[str, tuple[str, str]], used: list[str]) -> str:
    """Link only visible text nodes, never attributes, code or existing links."""
    parts = re.split(r"(<[^>]+>)", body)
    blocked: list[str] = []

    def link(match: re.Match) -> str:
        if match.group(1):
            key = "section-" + match.group(1).replace(".", "-")
        elif match.group(2):
            key = ("table-" if match.group(2).lower() == "table" else "figure-") + match.group(3)
        else:
            key = "formula-" + match.group(4)
        if key not in anchors:
            return match.group(0)
        if key not in used:
            used.append(key)
        return f'<a class="source-anchor" href="#bundle-{key}">{match.group(0)}</a>'

    for index, part in enumerate(parts):
        if part.startswith("<"):
            closing = re.match(r"</\s*([a-z]+)", part, flags=re.IGNORECASE)
            opening = re.match(r"<\s*([a-z]+)", part, flags=re.IGNORECASE)
            if closing and blocked and closing.group(1).lower() == blocked[-1]:
                blocked.pop()
            elif opening and opening.group(1).lower() in {"a", "code", "pre", "script", "style"}:
                blocked.append(opening.group(1).lower())
        elif not blocked:
            parts[index] = SOURCE_MENTION.sub(link, part)
    return "".join(parts)


def _source_evidence(anchors: dict[str, tuple[str, str]], used: list[str]) -> str:
    if not used:
        return ""
    items = "".join(
        f'<details id="bundle-{key}" data-source-anchor="{key}"><summary>{_escape(anchors[key][0])}</summary>'
        f'<pre>{_escape(anchors[key][1])}</pre></details>'
        for key in used
    )
    return '<aside class="source-evidence"><h2>原文锚点</h2><p>以下摘录来自本 Source 的 Parser Bundle。</p>' + items + '</aside>'


def _render(blog_dir: Path, *, embed_images: bool = True, bundle: Path | None = None) -> dict:
    """Merge both Markdown artifacts into one self-contained index.html.

    Rendering only writes index.html. A failure here leaves both Markdown files
    and any previously published HTML exactly as they were.
    """
    blog_dir = blog_dir.resolve()
    blog_path = blog_dir / ARTIFACT_FILES["reading_blog"]
    if not blog_path.is_file():
        raise BlogError("blog_md_missing", "blog.md is missing; nothing to render")
    metadata = _read_json(blog_dir / "metadata.json") if (blog_dir / "metadata.json").is_file() else {}
    blog = blog_path.read_text(encoding="utf-8", errors="replace")
    heading = re.search(r"^#\s+(.+?)\s*$", blog, flags=re.MULTILINE)
    title = heading.group(1) if heading else "Blog Output"
    image_src = _image_source(blog_dir, embed_images)
    panels: list[tuple[str, str, str]] = [
        ("带读博客", _markdown_to_html(blog, image_src), "reading_blog")
    ]
    value_path = blog_dir / ARTIFACT_FILES["value_analysis"]
    if value_path.is_file():
        panels.append(
            (
                "架构价值分析",
                _markdown_to_html(value_path.read_text(encoding="utf-8", errors="replace"), image_src),
                "value_analysis",
            )
        )
    else:
        panels.append(("架构价值分析", _value_page(metadata), "value_analysis"))
    document = _html_document(
        title, panels, _footer(metadata), embed_katex="data-tex" in "".join(body for _, body, _ in panels),
    )
    target = blog_dir / ARTIFACT_FILES["html"]
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(document, encoding="utf-8")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return {
        "ok": True,
        "output": str(target),
        "characters": len(document),
        "panels": len(panels),
        "embed_images": embed_images,
        "embed_katex": "data-tex" in document,
    }


# --------------------------------------------------------------------------- check


def _check(blog_dir: Path, *, require_html: bool = False) -> dict:
    blog_dir = blog_dir.resolve()
    bundle = blog_dir.parent / "parser-bundle"
    result = validate_blog_candidate(
        blog_dir,
        bundle=bundle if bundle.is_dir() else None,
        require_html=require_html,
    )
    if require_html:
        html_path = blog_dir / ARTIFACT_FILES["html"]
        blog_path = blog_dir / ARTIFACT_FILES["reading_blog"]
        if html_path.is_file() and blog_path.is_file():
            if html_path.stat().st_mtime_ns < blog_path.stat().st_mtime_ns:
                result["errors"].append("index.html is stale or not rendered from the current blog.md")
                result["ok"] = False
    result["output"] = str(blog_dir)
    result["method_version"] = ARTICLE_BLOG_METHOD_VERSION
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--workspace", type=Path, required=True)
    prepare.add_argument("--source-id", required=True)
    prepare.add_argument("--candidate", type=Path, required=True)
    check = subparsers.add_parser("check")
    check.add_argument("blog", type=Path)
    check.add_argument("--require-html", action="store_true")
    render = subparsers.add_parser("render")
    render.add_argument("blog", type=Path)
    render.add_argument(
        "--no-embed-images",
        dest="embed_images",
        action="store_false",
        help="keep image links instead of inlining them; the default inlines every image",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        if args.command == "prepare":
            result = _prepare_registered(args.workspace, args.source_id, args.candidate)
        elif args.command == "render":
            result = _render(args.blog, embed_images=getattr(args, "embed_images", True))
        else:
            result = _check(args.blog, require_html=args.require_html)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except BlogError as exc:
        print(json.dumps({"ok": False, "error_id": exc.error_id, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except WorkspaceError as exc:
        print(json.dumps({"ok": False, "error_id": exc.error_id, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except OSError as exc:
        print(json.dumps({"ok": False, "error_id": "blog_output_write_failed", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
