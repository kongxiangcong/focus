#!/usr/bin/env python3
"""Prepare and validate an agent-native paper-to-blog workspace."""

from __future__ import annotations

import argparse
import json
import re
import shutil
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
        raise BlogError(f"Invalid metadata.json: {exc}") from exc
    if not isinstance(value, dict):
        raise BlogError("metadata.json must contain a JSON object")
    return value


def _prepare(input_dir: Path, output: Path) -> dict:
    input_dir = input_dir.resolve()
    required = [input_dir / "paper.md", input_dir / "metadata.json", input_dir / "images"]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise BlogError(f"Parser bundle is missing: {', '.join(missing)}")
    metadata = _read_json(input_dir / "metadata.json")
    if output.exists() and any(output.iterdir()):
        raise BlogError(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_dir / "paper.md", output / "paper.md")
    shutil.copy2(input_dir / "metadata.json", output / "metadata.json")
    assets = output / "assets"
    shutil.copytree(input_dir / "images", assets, dirs_exist_ok=True)
    source = input_dir / "source.pdf"
    if source.exists():
        shutil.copy2(source, output / "source.pdf")
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


def _check(workspace: Path) -> dict:
    workspace = workspace.resolve()
    evidence_path = workspace / "evidence-map.md"
    blog_path = workspace / "blog.md"
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
    return {"ok": not errors, "errors": errors, "warnings": warnings, "metrics": {"blog_characters": len(blog), "paper_characters": paper_chars, "asset_count": asset_count}}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("input_dir", type=Path)
    prepare.add_argument("--output", type=Path, required=True)
    check = subparsers.add_parser("check")
    check.add_argument("workspace", type=Path)
    return parser


def main() -> int:
    try:
        args = _build_parser().parse_args()
        result = _prepare(args.input_dir, args.output) if args.command == "prepare" else _check(args.workspace)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    except (BlogError, OSError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
