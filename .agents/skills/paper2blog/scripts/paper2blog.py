#!/usr/bin/env python3
"""Prepare and validate an agent-native paper-to-blog workspace."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".jp2"}
PLACEHOLDERS = ("待补", "TODO", "TBD", "<your-", "问题 1：……", "贡献 1：")


class BlogError(RuntimeError):
    pass


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlogError(f"Invalid {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise BlogError(f"{path.name} must contain a JSON object")
    return value


def _retarget_parser_images(markdown: str) -> str:
    pattern = re.compile(r"(!\[[^\]\n]*\]\()images/([^)]+)(\))")
    return pattern.sub(r"\1assets/\2\3", markdown)


def _prepare(input_dir: Path, output: Path) -> dict:
    input_dir = input_dir.resolve()
    required = [input_dir / "paper.md", input_dir / "metadata.json", input_dir / "validation.json", input_dir / "images"]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise BlogError(f"Parser bundle is missing: {', '.join(missing)}")
    metadata = _read_json(input_dir / "metadata.json")
    validation = _read_json(input_dir / "validation.json")
    if metadata.get("parser") != "mineru-precision-api":
        raise BlogError("metadata.json is not from paper-parser")
    if validation.get("ok") is not True:
        raise BlogError("paper-parser validation did not pass")
    if output.exists() and any(output.iterdir()):
        raise BlogError(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    paper = (input_dir / "paper.md").read_text(encoding="utf-8", errors="replace")
    (output / "paper.md").write_text(_retarget_parser_images(paper), encoding="utf-8")
    shutil.copy2(input_dir / "metadata.json", output / "metadata.json")
    assets = output / "assets"
    shutil.copytree(input_dir / "images", assets, dirs_exist_ok=True)
    headings = []
    for line in (output / "paper.md").read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^#{1,4}\s+(.+?)\s*$", line)
        if match:
            headings.append(match.group(1))
        if len(headings) >= 20:
            break
    image_names = sorted(path.relative_to(assets).as_posix() for path in assets.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)
    template = [
        "# Evidence Map",
        "",
        "> Complete this map with source anchors before writing blog.md. Remove every placeholder.",
        "",
        "## Paper structure candidates",
        "",
        *(f"- {heading}" for heading in headings),
        "",
        "## Contributions and anchors",
        "",
        "| Contribution | Source anchor | Reported evidence | Assumption/boundary |",
        "|---|---|---|---|",
        "| 待补 | 待补 | 待补 | 待补 |",
        "",
        "## Method modules",
        "",
        "| Module | Input | Output | Why this design | Natural alternative | Cost/risk |",
        "|---|---|---|---|---|---|",
        "| 待补 | 待补 | 待补 | 待补 | 待补 | 待补 |",
        "",
        "## Core formulas, algorithms, or interfaces",
        "",
        "- 待补：source anchor, variables, intuition, workflow position, removal consequence.",
        "",
        "## Key figures",
        "",
        *(f"- Candidate: `assets/{name}` — 待补 figure meaning and supported claim." for name in image_names[:12]),
        "" if image_names else "- No extracted image candidate; verify whether the paper genuinely has no material figure.",
        "",
        "## Key tables and experiments",
        "",
        "- 待补：hypothesis, metric direction, baselines, decisive differences, cause, confounders.",
        "",
        "## Reproduction details and missing information",
        "",
        "- 待补：data, model/system, hyperparameters, hardware, cost, dependencies, undocumented assumptions.",
        "",
        "## Claim boundaries",
        "",
        "- 待补：what the evidence supports and what it does not support.",
    ]
    (output / "evidence-map.md").write_text("\n".join(template).rstrip() + "\n", encoding="utf-8")
    return {"ok": True, "output": str(output.resolve()), "headings": len(headings), "assets": len(image_names), "metadata_keys": sorted(metadata)}


def _find_marked() -> tuple[str, Path]:
    runtime_root = Path.home() / ".cache" / "codex-runtimes"
    node_candidates = [shutil.which("node.exe"), shutil.which("node")]
    if runtime_root.is_dir():
        node_candidates.extend(runtime_root.glob("*/dependencies/node/bin/node.exe"))
        node_candidates.extend(runtime_root.glob("*/dependencies/node/bin/node"))
    node = next((str(candidate) for candidate in node_candidates if candidate and Path(candidate).is_file()), "")
    if not node:
        raise BlogError("Node.js is required to render blog.html")
    configured = os.environ.get("MARKED_CLI", "").strip()
    candidates = [Path(configured)] if configured else []
    node_path = Path(node).resolve()
    candidates.append(node_path.parent.parent / "node_modules" / "marked" / "bin" / "marked.js")
    if runtime_root.is_dir():
        candidates.extend(runtime_root.glob("*/dependencies/node/node_modules/marked/bin/marked.js"))
    for root in (Path.cwd(), *Path(__file__).resolve().parents):
        candidates.append(root / "node_modules" / "marked" / "bin" / "marked.js")
    for candidate in candidates:
        if candidate.is_file():
            return node, candidate.resolve()
    raise BlogError("marked is required to render blog.html; configure MARKED_CLI or install marked beside Node.js")


def _render_markdown(markdown_path: Path) -> str:
    node, marked = _find_marked()
    completed = subprocess.run(
        [node, str(marked), "--gfm", "-i", str(markdown_path)],
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    if completed.returncode:
        raise BlogError(f"marked failed with exit code {completed.returncode}: {completed.stderr[:500]}")
    if not completed.stdout.strip():
        raise BlogError("marked produced empty HTML")
    return completed.stdout


def _html_document(title: str, body: str, source_hash: str) -> str:
    template = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="source-markdown-sha256" content="__SOURCE_HASH__">
  <title>__TITLE__</title>
  <style>
    :root { color-scheme: light dark; --paper:#fff; --ink:#202124; --muted:#5f6368; --line:#dadce0; --accent:#2457a7; --code:#f6f8fa; }
    @media (prefers-color-scheme: dark) { :root { --paper:#16181d; --ink:#e8eaed; --muted:#aeb4bc; --line:#3c4043; --accent:#8ab4f8; --code:#22262d; } }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--paper); color:var(--ink); font:17px/1.75 system-ui,-apple-system,"Segoe UI","Noto Sans SC",sans-serif; }
    article { width:min(920px, calc(100% - 36px)); margin:48px auto 96px; }
    h1,h2,h3,h4 { line-height:1.3; margin:1.8em 0 .65em; }
    h1 { font-size:2.2rem; border-bottom:2px solid var(--line); padding-bottom:.45em; }
    h2 { font-size:1.55rem; border-bottom:1px solid var(--line); padding-bottom:.3em; }
    a { color:var(--accent); }
    img { display:block; max-width:100%; height:auto; margin:1.5rem auto; border-radius:8px; }
    blockquote { margin:1.4rem 0; padding:.2rem 1rem; color:var(--muted); border-left:4px solid var(--accent); }
    pre,code { font-family:"Cascadia Code","SFMono-Regular",Consolas,monospace; background:var(--code); }
    code { padding:.1em .35em; border-radius:4px; }
    pre { padding:1rem; overflow:auto; border:1px solid var(--line); border-radius:8px; }
    pre code { padding:0; }
    table { display:block; width:100%; overflow:auto; border-collapse:collapse; margin:1.5rem 0; }
    th,td { border:1px solid var(--line); padding:.55rem .75rem; vertical-align:top; }
    th { background:var(--code); text-align:left; }
    hr { border:0; border-top:1px solid var(--line); margin:2rem 0; }
  </style>
</head>
<body><article>
__BODY__
</article></body>
</html>
"""
    return (
        template.replace("__SOURCE_HASH__", source_hash)
        .replace("__TITLE__", html.escape(title))
        .replace("__BODY__", body)
    )


def _render(workspace: Path) -> dict:
    workspace = workspace.resolve()
    preflight = _check(workspace, require_html=False)
    if not preflight["ok"]:
        raise BlogError("Cannot render invalid blog workspace: " + "; ".join(preflight["errors"]))
    blog_path = workspace / "blog.md"
    blog = blog_path.read_text(encoding="utf-8", errors="replace")
    heading = re.search(r"^#\s+(.+?)\s*$", blog, flags=re.MULTILINE)
    title = heading.group(1) if heading else "Paper Blog"
    source_hash = hashlib.sha256(blog_path.read_bytes()).hexdigest()
    document = _html_document(title, _render_markdown(blog_path), source_hash)
    html_path = workspace / "blog.html"
    html_path.write_text(document, encoding="utf-8")
    result = _check(workspace, require_html=True)
    result["output"] = str(html_path)
    return result


def _check(workspace: Path, *, require_html: bool = True) -> dict:
    workspace = workspace.resolve()
    evidence_path = workspace / "evidence-map.md"
    blog_path = workspace / "blog.md"
    html_path = workspace / "blog.html"
    errors: list[str] = []
    warnings: list[str] = []
    if not evidence_path.is_file():
        errors.append("evidence-map.md is missing")
        evidence = ""
    else:
        evidence = evidence_path.read_text(encoding="utf-8", errors="replace")
    if not blog_path.is_file():
        errors.append("blog.md is missing")
        blog = ""
    else:
        blog = blog_path.read_text(encoding="utf-8", errors="replace")
    if (workspace / "source.pdf").exists():
        errors.append("source.pdf must not be copied into the paper2blog workspace")
    found = sorted({placeholder for placeholder in PLACEHOLDERS if placeholder in evidence or placeholder in blog})
    if found:
        errors.append("Unresolved placeholders: " + ", ".join(found))
    if blog and len(blog.strip()) < 2000:
        errors.append("blog.md is shorter than 2,000 characters")
    required_signals = {
        "method mechanics": ("方法", "机制", "设计"),
        "evidence analysis": ("实验", "证据", "消融", "基线"),
        "limitations": ("局限", "边界", "失败模式"),
        "references": ("References", "参考文献", "引用"),
    }
    for label, signals in required_signals.items():
        if blog and not any(signal in blog for signal in signals):
            errors.append(f"blog.md lacks an observable {label} section")
    local_links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", blog)
    for link in local_links:
        if "://" not in link and not (workspace / link).resolve().is_file():
            errors.append(f"Broken local image link: {link}")
    asset_count = sum(1 for path in (workspace / "assets").rglob("*") if path.is_file()) if (workspace / "assets").exists() else 0
    if asset_count and not any(link.startswith("assets/") for link in local_links):
        warnings.append("Extracted figures exist but blog.md references none of them")
    paper_chars = len((workspace / "paper.md").read_text(encoding="utf-8", errors="replace")) if (workspace / "paper.md").is_file() else 0
    if blog and paper_chars and len(blog) < paper_chars * 0.05:
        warnings.append("The blog is under 5% of parsed paper length; check depth")
    html_chars = 0
    if require_html:
        if not html_path.is_file():
            errors.append("blog.html is missing; run the render command")
        else:
            rendered = html_path.read_text(encoding="utf-8", errors="replace")
            html_chars = len(rendered)
            expected_hash = hashlib.sha256(blog_path.read_bytes()).hexdigest() if blog_path.is_file() else ""
            match = re.search(r'<meta name="source-markdown-sha256" content="([0-9a-f]{64})">', rendered)
            if not match or match.group(1) != expected_hash:
                errors.append("blog.html is stale or not rendered from the current blog.md")
            for link in re.findall(r'<img[^>]+src="([^"]+)"', rendered):
                if "://" not in link and not (workspace / link).resolve().is_file():
                    errors.append(f"Broken HTML image link: {link}")
            if len(rendered.strip()) < 1000 or "<article>" not in rendered:
                errors.append("blog.html is incomplete")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "blog_characters": len(blog),
            "html_characters": html_chars,
            "paper_characters": paper_chars,
            "asset_count": asset_count,
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("input_dir", type=Path)
    prepare.add_argument("--output", type=Path, required=True)
    check = subparsers.add_parser("check")
    check.add_argument("workspace", type=Path)
    render = subparsers.add_parser("render")
    render.add_argument("workspace", type=Path)
    return parser


def main() -> int:
    try:
        args = _build_parser().parse_args()
        if args.command == "prepare":
            result = _prepare(args.input_dir, args.output)
        elif args.command == "render":
            result = _render(args.workspace)
        else:
            result = _check(args.workspace)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except (BlogError, OSError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
