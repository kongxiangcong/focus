"""Blog Output: product layout, metadata bindings and the shared article-blog validator.

Core is the only writer of `sources/<source-id>/blog/`. The versioned method
pack `methods/article-blog/` owns the method content; this module owns the
product contract that every Blog Output must satisfy, including the metadata
bindings (Source ID, Bundle fingerprint and article-blog method version) and
the shared validator used before any candidate is published.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import uuid
import xml.etree.ElementTree as ElementTree
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .reading_workspace import (
    WorkspaceError,
    _read_document,
    _write_document,
    validate_source_id,
)


ARTICLE_BLOG_METHOD_VERSION = "article-blog-v1"
ARTICLE_BLOG_METHOD = "article-blog"
BLOG_DIRECTORY_NAME = "blog"

READING_BLOG = "reading_blog"
VALUE_ANALYSIS = "value_analysis"
HTML = "html"
EVIDENCE = "evidence"

#: The three sub-statuses the Workbench shows, in display order.
DISPLAY_ARTIFACTS = (VALUE_ANALYSIS, READING_BLOG, HTML)

ARTIFACT_FILES = {
    READING_BLOG: "blog.md",
    VALUE_ANALYSIS: "value-analysis.md",
    HTML: "index.html",
    EVIDENCE: "evidence",
}

EVIDENCE_FILES = ("evidence-map.md", "implementation-notes.md")

STATUS_PENDING = "pending"
STATUS_GENERATING = "generating"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_NOT_APPLICABLE = "not_applicable"
BLOG_STATUSES = frozenset(
    {STATUS_PENDING, STATUS_GENERATING, STATUS_COMPLETED, STATUS_FAILED, STATUS_NOT_APPLICABLE}
)

#: Value Analysis applies when the paper's main contribution falls in one of these.
VALUE_ANALYSIS_DIRECTIONS = (
    "hardware_architecture",
    "design_space_exploration",
    "compiler",
    "simulator",
    "performance_modeling",
)

VERIFICATION_LEVELS = ("paper_reading", "static_review", "executed")

PLACEHOLDERS = ("待补", "TODO", "TBD", "<your-", "问题 1：……", "贡献 1：")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".jp2"}

#: Minimum Reading Blog length; below this the article cannot be a 细读长文.
MIN_READING_BLOG_CHARACTERS = 2000

READING_BLOG_SIGNALS = {
    "导语": ("导语", "问题", "背景"),
    "方法": ("方法", "机制", "设计", "模块"),
    "实验": ("实验", "证据", "消融", "基线", "结果"),
    "参考文献": ("参考文献", "References", "引用"),
}

#: Value Analysis must follow the fixed five-part main line of the method.
VALUE_ANALYSIS_SKELETON = {
    "研究问题": ("研究问题", "问题定义", "研究对象", "要解决"),
    "输入输出": ("输入输出", "输入与输出", "系统边界", "输入"),
    "模块拆解": ("模块拆解", "模块划分", "模块"),
    "一个运行例子": ("运行例子", "运行示例", "一个例子", "推演"),
    "贡献与边界": ("贡献与边界", "贡献", "边界"),
}

MIN_VALUE_ANALYSIS_CHARACTERS = 1500
MAX_REFERENCE_INDEX = 200

#: Validator item ④ reads the rendered document: tabs, panels, embedded resources.
HTML_TAG = re.compile(r"<(section|button)\b[^>]*>", re.IGNORECASE)
HTML_ATTRIBUTE = re.compile(r"([a-zA-Z-]+)\s*=\s*\"([^\"]*)\"")
#: External *resources* (styles, scripts, images, fonts), not ordinary hyperlinks:
#: a link to the paper is how a reader checks a claim, and needs no network to render.
HTML_EXTERNAL_RESOURCE = re.compile(
    r"""\bsrc\s*=\s*["']\s*(?:https?:)?//"""
    r"""|url\(\s*["']?(?:https?:)?//"""
    r"""|<link\b[^>]*\bhref\s*=|<script\b[^>]*\bsrc\s*=""",
    re.IGNORECASE,
)
HTML_IMAGE_SOURCE = re.compile(r"<img\b[^>]*\bsrc\s*=\s*[\"']([^\"']*)", re.IGNORECASE)
HTML_PANEL_BODY = re.compile(r'<section\b[^>]*id="([^"]+)"[^>]*>(.*?)</section>', re.IGNORECASE | re.DOTALL)
#: Embedded script sources are code, not markup; their strings are not elements.
HTML_SCRIPT_BLOCK = re.compile(r"(<script\b[^>]*>).*?</script>", re.IGNORECASE | re.DOTALL)

CITATION_MARKER = re.compile(r"(?<![!\]#])\[(\d{1,3})\](?!\s*\()")
SECTION_ANCHOR = re.compile(r"第\s*(\d+)\s*节|Section\s*(\d+)|Sec\.\s*(\d+)", re.IGNORECASE)
EVIDENCE_ANCHOR = re.compile(
    r"(?:Figure|Fig\.|Table|Equation)\s*(\d+)|(?:图|表)\s*(\d+)|公式\s*[（(]\s*(\d+)\s*[)）]",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def blog_root(workspace: Path, source_id: str) -> Path:
    return Path(workspace).resolve() / "sources" / validate_source_id(source_id) / BLOG_DIRECTORY_NAME


def bundle_fingerprint(bundle: Path) -> str:
    """Fingerprint the published Bundle a Blog Output was derived from."""
    bundle = Path(bundle).resolve()
    digest = hashlib.sha256()
    content = bundle / "content.md"
    if content.is_file():
        digest.update(content.read_bytes())
    images = bundle / "images"
    if images.is_dir():
        for path in sorted(images.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(images).as_posix().encode("utf-8"))
                digest.update(path.read_bytes())
    return digest.hexdigest()


def new_blog_metadata(
    *,
    source_id: str,
    source_kind: str,
    bundle: Path,
    bundle_version: int = 1,
) -> dict[str, Any]:
    return {
        "source_id": validate_source_id(source_id),
        "source_kind": source_kind,
        "bundle_version": bundle_version,
        "bundle_fingerprint": bundle_fingerprint(bundle),
        "method": ARTICLE_BLOG_METHOD,
        "method_version": ARTICLE_BLOG_METHOD_VERSION,
        "artifacts": {
            name: {"status": STATUS_PENDING, "updated_at": None} for name in DISPLAY_ARTIFACTS
        },
        "evidence": {"status": STATUS_PENDING, "updated_at": None},
        "value_analysis_applicability": {"applicable": None, "direction": None, "reason": None},
        "verification_level": None,
        "warnings": [],
        "updated_at": _now(),
    }


def _require(condition: bool, error_id: str, message: str) -> None:
    if not condition:
        raise WorkspaceError(error_id, message)


def validate_applicability(value: Any) -> dict[str, Any]:
    """Normalize a Value Analysis applicability judgement.

    A paper is in scope when its main contribution falls in hardware
    architecture, DSE, compiler, simulator or performance modeling.
    """
    _require(isinstance(value, dict), "blog_applicability_invalid", "Value Analysis applicability is invalid")
    applicable = value.get("applicable")
    _require(isinstance(applicable, bool), "blog_applicability_invalid", "Value Analysis applicability must be decided")
    direction = value.get("direction")
    reason = value.get("reason")
    if applicable:
        _require(
            isinstance(direction, str) and direction in VALUE_ANALYSIS_DIRECTIONS,
            "blog_applicability_invalid",
            "An applicable Value Analysis must name one of the defined directions",
        )
    else:
        direction = None
    _require(isinstance(reason, str) and reason.strip(), "blog_applicability_invalid", "The applicability judgement needs a reason")
    return {"applicable": applicable, "direction": direction, "reason": reason.strip()}


def validate_blog_metadata(metadata: dict[str, Any], *, source_id: str, bundle: Path | None = None) -> dict[str, Any]:
    """Validate the Blog Output bindings: Source ID, Bundle and article-blog method version."""
    expected_source_id = validate_source_id(source_id)
    _require(isinstance(metadata, dict), "blog_metadata_invalid", "Blog metadata is invalid")
    _require(
        metadata.get("source_id") == expected_source_id,
        "blog_metadata_invalid",
        f"Blog metadata does not belong to this Reading Source: {expected_source_id}",
    )
    _require(
        metadata.get("method") == ARTICLE_BLOG_METHOD,
        "blog_metadata_invalid",
        "Blog metadata does not name the article-blog method",
    )
    _require(
        metadata.get("method_version") == ARTICLE_BLOG_METHOD_VERSION,
        "blog_method_version_invalid",
        "Blog metadata method version does not match the running article-blog method",
    )
    _require(
        isinstance(metadata.get("bundle_version"), int) and metadata["bundle_version"] >= 1,
        "blog_metadata_invalid",
        "Blog metadata must bind a positive Bundle version",
    )
    _require(
        isinstance(metadata.get("bundle_fingerprint"), str) and len(metadata["bundle_fingerprint"]) == 64,
        "blog_metadata_invalid",
        "Blog metadata must bind the Bundle fingerprint",
    )
    if bundle is not None:
        _require(
            metadata["bundle_fingerprint"] == bundle_fingerprint(bundle),
            "blog_bundle_mismatch",
            "Blog Output was generated from a different Parser Bundle",
        )
    artifacts = metadata.get("artifacts")
    _require(isinstance(artifacts, dict), "blog_metadata_invalid", "Blog metadata artifact states are invalid")
    for name in DISPLAY_ARTIFACTS:
        entry = artifacts.get(name)
        _require(isinstance(entry, dict), "blog_metadata_invalid", f"Blog metadata is missing artifact state: {name}")
        _require(entry.get("status") in BLOG_STATUSES, "blog_metadata_invalid", f"Blog artifact status is invalid: {name}")
    warnings = metadata.get("warnings", [])
    _require(
        isinstance(warnings, list) and all(isinstance(item, str) for item in warnings),
        "blog_metadata_invalid",
        "Blog metadata warnings are invalid",
    )
    return metadata


def read_blog_metadata(blog_dir: Path) -> dict[str, Any] | None:
    path = Path(blog_dir) / "metadata.json"
    return _read_document(path) if path.is_file() else None


def blog_status(workspace: Path, source_id: str) -> dict[str, Any]:
    """Sub-statuses of a Source's Blog Output for display, without touching reading assets."""
    source_id = validate_source_id(source_id)
    root = blog_root(workspace, source_id)
    metadata = read_blog_metadata(root)
    if metadata is None:
        return {
            "sourceId": source_id,
            "generated": False,
            "artifacts": {name: {"status": STATUS_PENDING, "updatedAt": None} for name in DISPLAY_ARTIFACTS},
            "valueAnalysis": {"applicable": None, "direction": None, "reason": None},
            "verificationLevel": None,
            "warnings": [],
            "methodVersion": None,
        }
    artifacts = metadata.get("artifacts", {})
    return {
        "sourceId": source_id,
        "generated": True,
        "artifacts": {
            name: {
                "status": artifacts.get(name, {}).get("status", STATUS_PENDING),
                "updatedAt": artifacts.get(name, {}).get("updated_at"),
            }
            for name in DISPLAY_ARTIFACTS
        },
        "valueAnalysis": dict(metadata.get("value_analysis_applicability", {})),
        "verificationLevel": metadata.get("verification_level"),
        "warnings": list(metadata.get("warnings", [])),
        "methodVersion": metadata.get("method_version"),
    }


def artifact_path(workspace: Path, source_id: str, artifact: str) -> Path | None:
    """Path of a published artifact, or None when it does not exist."""
    name = ARTIFACT_FILES.get(artifact)
    if name is None:
        raise WorkspaceError("blog_artifact_invalid", f"Unknown Blog Output artifact: {artifact}")
    path = blog_root(workspace, source_id) / name
    return path if path.is_file() else None


def _markdown_image_links(text: str) -> list[str]:
    return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _decode_png(data: bytes) -> tuple[bool, str]:
    offset = 8
    seen_header = False
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        if offset + 12 + length > len(data):
            return False, "PNG chunk is truncated"
        checksum = int.from_bytes(data[offset + 8 + length : offset + 12 + length], "big")
        if zlib.crc32(kind + body) & 0xFFFFFFFF != checksum:
            return False, f"PNG chunk {kind.decode('ascii', 'replace')} fails its checksum"
        if kind == b"IHDR":
            seen_header = len(body) >= 13
        if kind == b"IEND":
            break
        offset += 12 + length
    return seen_header, "PNG without IHDR" if not seen_header else "png"


def _decode_jpeg(data: bytes) -> tuple[bool, str]:
    if not data.endswith(b"\xff\xd9"):
        return False, "JPEG without end-of-image marker"
    offset = 2
    while offset < len(data) - 1:
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return True, "jpeg"
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        if offset + 4 > len(data):
            return False, "JPEG segment is truncated"
        offset += 2 + int.from_bytes(data[offset + 2 : offset + 4], "big")
    return False, "JPEG without a frame header"


def _decode_svg(data: bytes) -> tuple[bool, str]:
    try:
        root = ElementTree.fromstring(data.decode("utf-8", errors="replace"))
    except (ElementTree.ParseError, ValueError):
        return False, "SVG is not well-formed XML"
    return root.tag.rsplit("}", 1)[-1] == "svg", "root element is not <svg>" if root.tag.rsplit("}", 1)[-1] != "svg" else "svg"


def decode_image(path: Path) -> tuple[bool, str]:
    """Verify an image container really decodes: no dependency, no filename trust."""
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return _decode_png(data)
    if data[:3] == b"\xff\xd8\xff":
        return _decode_jpeg(data)
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return len(data) >= 13, "GIF is shorter than its header"
    if data[:2] == b"BM":
        return len(data) >= 54, "BMP is shorter than its header"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return len(data) > 16, "WEBP is shorter than its header"
    if data[:12] == b"\x00\x00\x00\x0cjP  ":
        return True, "jp2"
    stripped = data[:512].lstrip().lower()
    if stripped.startswith(b"<svg") or stripped.startswith(b"<?xml"):
        return _decode_svg(data)
    return False, "unrecognized image container"


def _bundle_image_digests(bundle: Path | None) -> set[str]:
    if bundle is None:
        return set()
    images = Path(bundle).resolve() / "images"
    if not images.is_dir():
        return set()
    return {_sha256(path) for path in images.rglob("*") if path.is_file()}


def check_images(blog_dir: Path, blog_text: str, value_text: str, bundle: Path | None) -> tuple[list[str], list[str]]:
    """Validator item ②: every referenced image decodes and comes from the Bundle."""
    errors: list[str] = []
    warnings: list[str] = []
    digests = _bundle_image_digests(bundle)
    links = [link for link in _markdown_image_links(blog_text) + _markdown_image_links(value_text) if "://" not in link]
    for link in sorted(set(links)):
        path = (blog_dir / link).resolve()
        if not path.is_file():
            errors.append(f"Broken local image link: {link}")
            continue
        decodes, detail = decode_image(path)
        if not decodes:
            errors.append(f"Referenced image does not decode: {link} ({detail})")
            continue
        if digests and _sha256(path) not in digests:
            errors.append(f"Referenced image does not come from the Parser Bundle: {link}")
    assets = blog_dir / "assets"
    asset_count = sum(1 for path in assets.rglob("*") if path.is_file()) if assets.is_dir() else 0
    if asset_count and not any(link.startswith("assets/") for link in links):
        warnings.append("已抽取图片，但正文没有引用任何一张")
    return errors, warnings


def _bibliography_entries(text: str) -> set[int]:
    """Collect the numbered entries of the reference list at the end of an article."""
    match = re.search(r"^#{1,6}\s*(?:参考文献|References)\s*$", text, flags=re.MULTILINE | re.IGNORECASE)
    section = text[match.end() :] if match else ""
    entries: set[int] = set()
    for line in section.splitlines():
        numbered = re.match(r"^\s*(?:[-*]\s*)?\[?(\d{1,3})\]?[.、:：]?\s+\S", line)
        if numbered:
            entries.add(int(numbered.group(1)))
        listed = re.match(r"^\s*(\d{1,3})[.、]\s+\S", line)
        if listed:
            entries.add(int(listed.group(1)))
    return entries


def check_references(blog_text: str, value_text: str, bundle_text: str) -> tuple[list[str], list[str]]:
    """Validator item ③: in-text citations and anchors resolve; figure anchors warn."""
    errors: list[str] = []
    warnings: list[str] = []
    for label, text in (("blog.md", blog_text), ("value-analysis.md", value_text)):
        if not text.strip():
            continue
        entries = _bibliography_entries(text)
        cited = {int(value) for value in CITATION_MARKER.findall(text)}
        missing = sorted(number for number in cited if number not in entries and number <= MAX_REFERENCE_INDEX)
        if missing:
            errors.append(f"{label} cites {', '.join(f'[{number}]' for number in missing)} with no matching reference entry")
        for match in SECTION_ANCHOR.finditer(text):
            number = next(group for group in match.groups() if group)
            pattern = rf"(?:^#+\s*{number}\b|^#+\s*{number}[.\s]|Section\s*{number}\b|第\s*{number}\s*节)"
            if bundle_text and not re.search(pattern, bundle_text, flags=re.MULTILINE | re.IGNORECASE):
                errors.append(f"{label} references section {number} but the Bundle has no such anchor")
        if bundle_text:
            for match in EVIDENCE_ANCHOR.finditer(text):
                number = next(group for group in match.groups() if group)
                if not re.search(rf"(?:Figure|Fig\.|Table|Equation|图|表)\s*{number}\b|公式\s*[（(]\s*{number}\s*[)）]", bundle_text, flags=re.IGNORECASE):
                    warnings.append(
                        f"{label} 中的 {match.group(0)} 无法在 Bundle 文本中解析，请回原文核对"
                    )
    return errors, warnings


def check_structure(blog_text: str, value_text: str, *, require_value_analysis: bool | None) -> list[str]:
    """Validator item ①: each article follows its own guide skeleton."""
    errors: list[str] = []
    if not blog_text.strip():
        return ["blog.md is missing or empty"]
    for label, signals in READING_BLOG_SIGNALS.items():
        if not any(signal in blog_text for signal in signals):
            errors.append(f"blog.md lacks an observable {label} section")
    if require_value_analysis is True:
        if not value_text.strip():
            return errors + ["value-analysis.md is missing although Value Analysis applies"]
        for label, signals in VALUE_ANALYSIS_SKELETON.items():
            if not any(signal in value_text for signal in signals):
                errors.append(f"value-analysis.md lacks the {label} part of the five-part main line")
        if len(value_text.strip()) < MIN_VALUE_ANALYSIS_CHARACTERS:
            errors.append(f"value-analysis.md is shorter than {MIN_VALUE_ANALYSIS_CHARACTERS} characters")
    return errors


def check_depth(
    *,
    blog_text: str,
    value_text: str,
    evidence_text: str,
    notes_text: str,
    bundle_text: str,
    require_value_analysis: bool | None,
) -> list[str]:
    """Validator item ⑤: depth and evidence gaps that cannot be decided mechanically.

    These are warnings on purpose; the validator never claims a quality pass.
    """
    warnings: list[str] = []
    if bundle_text and blog_text and len(blog_text) < len(bundle_text) * 0.05:
        warnings.append("带读博客正文不足解析正文长度的 5%，请检查深度")
    if evidence_text and len(evidence_text.strip()) < 400:
        warnings.append("共享写作证据笔记过薄，关键主张可能缺少原文锚点")
    if require_value_analysis is True and value_text and "实际运行" not in value_text and "未运行" not in notes_text:
        warnings.append("价值分析未说明实现是否实际运行")
    unverified = ("未运行", "未找到", "没有访问权限", "未公开", "未验证")
    found = [marker for marker in unverified if marker in notes_text]
    if found:
        warnings.append(
            "实现检索笔记记录了未核查范围（" + "、".join(found) + "）；实现相关结论只按静态阅读对待"
        )
    return warnings


def check_html(
    html_text: str,
    *,
    require_value_analysis: bool | None = None,
    not_applicable_reason: str | None = None,
) -> tuple[list[str], list[str]]:
    """Validator item ④: the artifact renders as two self-contained pages.

    "Renders" is checked as form, not as a browser: the document must be a whole
    HTML file, open on the Reading Blog page, offer one tab per page and carry
    every resource inline. No quality claim is made here.
    """
    errors: list[str] = []
    warnings: list[str] = []
    text = html_text.strip()
    if not text:
        return ["index.html is empty"], []
    lowered = text.lower()
    if not lowered.startswith("<!doctype html"):
        errors.append("index.html is not a complete HTML document")
    if not lowered.endswith("</html>"):
        errors.append("index.html does not close its document element")
    markup = HTML_SCRIPT_BLOCK.sub(lambda match: match.group(1) + "</script>", text)

    panels: list[dict[str, str]] = []
    tabs: list[dict[str, str]] = []
    for tag in HTML_TAG.finditer(markup):
        attributes = dict(HTML_ATTRIBUTE.findall(tag.group(0)))
        (panels if tag.group(1).lower() == "section" else tabs).append(attributes)
    if len(panels) < 2:
        errors.append(
            "index.html does not render two pages; the Reading Blog page and the Value Analysis page must both exist"
        )
    if len(tabs) != len(panels):
        errors.append(f"index.html has {len(tabs)} tab buttons for {len(panels)} pages")
    if [index for index, panel in enumerate(panels) if panel.get("data-active") == "true"] != [0]:
        errors.append("index.html must open on the Reading Blog page")
    if tabs and [tab for tab in tabs if tab.get("aria-selected") == "true"] != [tabs[0]]:
        errors.append("index.html must select exactly one tab by default")
    panel_ids = {panel.get("id") for panel in panels}
    if any(tab.get("aria-controls") not in panel_ids for tab in tabs):
        errors.append("index.html has a tab that points at no page")

    external = HTML_EXTERNAL_RESOURCE.search(markup)
    if external:
        errors.append("index.html is not self-contained; it references an external resource: " + external.group(0)[:48])
    for source in HTML_IMAGE_SOURCE.findall(markup):
        if not source.startswith("data:"):
            errors.append(f"index.html image is not embedded: {source[:48]}")
            break
    if "data-tex" in text and "katex.render" not in text:
        errors.append("index.html contains formulas but embeds no formula renderer")

    bodies = dict(HTML_PANEL_BODY.findall(markup))
    second = bodies.get(panels[1].get("id", ""), "") if len(panels) > 1 else ""
    if require_value_analysis is False:
        if "not-applicable" not in second:
            errors.append("index.html must explain on its second page why the Value Analysis does not apply")
        elif isinstance(not_applicable_reason, str) and not_applicable_reason.strip():
            shown = not_applicable_reason.strip()
            if shown not in second and html.escape(shown, quote=False) not in second:
                errors.append("index.html does not show the recorded reason for skipping the Value Analysis")
    elif require_value_analysis is True and "not-applicable" in second:
        errors.append("index.html shows the Value Analysis as not applicable although it applies")

    return errors, warnings


def validate_blog_candidate(
    blog_dir: Path,
    *,
    bundle: Path | None = None,
    require_html: bool = False,
    require_value_analysis: bool | None = None,
) -> dict[str, Any]:
    """Run the shared validator on a Blog Output candidate.

    The validator only proves form: skeleton, images that really decode and come
    from the Bundle, resolvable references and (when enabled) renderability.
    Depth and evidence gaps are reported as warnings, never as a quality pass.
    """
    blog_dir = Path(blog_dir).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    for original in ("source.pdf", "source.html", "source.md"):
        if (blog_dir / original).exists():
            errors.append(f"{original} must not be copied into the Blog Output")

    evidence_map = blog_dir / "evidence" / "evidence-map.md"
    if not evidence_map.is_file() or not evidence_map.read_text(encoding="utf-8", errors="replace").strip():
        errors.append("evidence/evidence-map.md is missing or empty")

    evidence_text = _read_text(evidence_map)
    notes_text = _read_text(blog_dir / "evidence" / "implementation-notes.md")
    blog_text = _read_text(blog_dir / "blog.md")
    value_text = _read_text(blog_dir / "value-analysis.md")

    if require_value_analysis is False and (blog_dir / "value-analysis.md").exists():
        errors.append("value-analysis.md exists although Value Analysis was judged not applicable")

    placeholders = sorted(
        {item for item in PLACEHOLDERS if item in evidence_text or item in blog_text or item in value_text}
    )
    if placeholders:
        errors.append("Unresolved placeholders: " + ", ".join(placeholders))
    if blog_text and len(blog_text.strip()) < MIN_READING_BLOG_CHARACTERS:
        errors.append(f"blog.md is shorter than {MIN_READING_BLOG_CHARACTERS} characters")

    errors.extend(check_structure(blog_text, value_text, require_value_analysis=require_value_analysis))
    image_errors, image_warnings = check_images(blog_dir, blog_text, value_text, bundle)
    errors.extend(image_errors)
    warnings.extend(image_warnings)

    bundle_text = _read_text(Path(bundle).resolve() / "content.md") if bundle is not None else ""
    reference_errors, reference_warnings = check_references(blog_text, value_text, bundle_text)
    errors.extend(reference_errors)
    warnings.extend(reference_warnings)

    warnings.extend(
        check_depth(
            blog_text=blog_text,
            value_text=value_text,
            evidence_text=evidence_text,
            notes_text=notes_text,
            bundle_text=bundle_text,
            require_value_analysis=require_value_analysis,
        )
    )

    html_chars = 0
    html_panels = 0
    html_images = 0
    if require_html:
        html_path = blog_dir / "index.html"
        if not html_path.is_file():
            errors.append("index.html is missing; run the render command")
        else:
            rendered = _read_text(html_path)
            html_chars = len(rendered)
            if len(rendered.strip()) < 1000:
                errors.append("index.html is incomplete")
            applicability = read_blog_metadata(blog_dir) or {}
            judgement = applicability.get("value_analysis_applicability")
            judgement = judgement if isinstance(judgement, dict) else {}
            html_errors, html_warnings = check_html(
                rendered,
                require_value_analysis=require_value_analysis,
                not_applicable_reason=judgement.get("reason") if isinstance(judgement.get("reason"), str) else None,
            )
            errors.extend(html_errors)
            warnings.extend(html_warnings)
            stripped = HTML_SCRIPT_BLOCK.sub(lambda match: match.group(1) + "</script>", rendered)
            html_panels = len(HTML_PANEL_BODY.findall(stripped))
            html_images = len([item for item in HTML_IMAGE_SOURCE.findall(stripped) if item.startswith("data:")])

    assets = blog_dir / "assets"
    asset_count = sum(1 for path in assets.rglob("*") if path.is_file()) if assets.is_dir() else 0
    seen: set[str] = set()
    errors = [item for item in errors if not (item in seen or seen.add(item))]
    warnings = [item for item in warnings if not (item in seen or seen.add(item))]
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "blog_characters": len(blog_text),
            "value_analysis_characters": len(value_text),
            "evidence_characters": len(evidence_text),
            "html_characters": html_chars,
            "html_panels": html_panels,
            "html_embedded_images": html_images,
            "source_characters": len(bundle_text),
            "asset_count": asset_count,
            "referenced_images": len(
                [link for link in _markdown_image_links(blog_text) + _markdown_image_links(value_text) if "://" not in link]
            ),
        },
    }


class BlogCore:
    """Guarded Core commits for Blog Output assets.

    A single exclusive writer owns the Workspace's Blog Output; every commit is
    bound to a request id so a replayed request returns the recorded result
    instead of publishing twice.
    """

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise WorkspaceError("workspace_missing", "Workspace does not exist")
        self.path = self.workspace / "blog" / "core.json"

    def _state(self) -> dict[str, Any]:
        return _read_document(self.path, {"version": 0, "writer_id": None, "requests": {}})

    @property
    def version(self) -> int:
        return int(self._state()["version"])

    def _authorize(self, state: dict[str, Any], writer_id: str) -> None:
        if not isinstance(writer_id, str) or not writer_id.strip():
            raise WorkspaceError("writer_invalid", "Writer identity is required")
        owner = state.get("writer_id")
        if owner not in {None, writer_id}:
            raise WorkspaceError("writer_conflict", "Another writer owns this Workspace")
        state["writer_id"] = writer_id

    def require_writer(self, writer_id: str) -> None:
        """Reject a second writer before any external call is made."""
        if not isinstance(writer_id, str) or not writer_id.strip():
            raise WorkspaceError("writer_invalid", "Writer identity is required")
        owner = self._state().get("writer_id")
        if owner not in {None, writer_id}:
            raise WorkspaceError("writer_conflict", "Another writer owns this Workspace")

    @staticmethod
    def _check_request_id(request_id: str) -> str:
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
            raise WorkspaceError("request_id_invalid", "Request id is invalid")
        return request_id

    def install_prepared(
        self,
        *,
        source_id: str,
        candidate: Path,
        writer_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Publish a prepared Blog Output skeleton as the Source's blog/ directory."""
        source_id = validate_source_id(source_id)
        request_id = self._check_request_id(request_id)
        candidate = Path(candidate).resolve()
        if not candidate.is_dir():
            raise WorkspaceError("blog_candidate_missing", "Blog candidate does not exist")
        bundle = self.workspace / "sources" / source_id / "parser-bundle"
        if not bundle.is_dir():
            raise WorkspaceError("parser_bundle_missing", f"Parser Bundle does not exist: {source_id}")
        metadata = _read_document(candidate / "metadata.json")
        validate_blog_metadata(metadata, source_id=source_id, bundle=bundle)
        for relative in ("evidence/evidence-map.md", "evidence/implementation-notes.md", "metadata.json"):
            if not (candidate / relative).is_file():
                raise WorkspaceError("blog_candidate_invalid", f"Blog candidate is missing: {relative}")
        root = blog_root(self.workspace, source_id)
        state = self._state()
        self._authorize(state, writer_id)
        requests = state.setdefault("requests", {})
        if request_id in requests:
            return dict(requests[request_id])
        published = root / ARTIFACT_FILES[READING_BLOG]
        staging = root.parent / f".{BLOG_DIRECTORY_NAME}-{uuid.uuid4().hex}.staging"
        root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(candidate, staging)
        try:
            staging.replace(root)
            shutil.rmtree(candidate, ignore_errors=True)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        state["version"] = int(state.get("version", 0)) + 1
        committed = {
            "status": "installed",
            "source_id": source_id,
            "version": state["version"],
            "published_reading_blog": published.is_file(),
        }
        requests[request_id] = committed
        _write_document(self.path, state)
        return committed

    def commit(
        self,
        *,
        source_id: str,
        files: dict[str, str],
        statuses: dict[str, str],
        writer_id: str,
        request_id: str,
        warnings: list[str] | None = None,
        applicability: dict[str, Any] | None = None,
        verification_level: str | None = None,
    ) -> dict[str, Any]:
        """Write generated artifacts into an existing Blog Output directory.

        Every file is written atomically, so a previously published and still
        valid index.html stays readable while a regeneration is in flight.
        """
        source_id = validate_source_id(source_id)
        request_id = self._check_request_id(request_id)
        root = blog_root(self.workspace, source_id)
        if not root.is_dir():
            raise WorkspaceError("blog_output_missing", f"Blog Output does not exist: {source_id}")
        for name, status in statuses.items():
            if name not in DISPLAY_ARTIFACTS and name != EVIDENCE:
                raise WorkspaceError("blog_artifact_invalid", f"Unknown Blog Output artifact: {name}")
            if status not in BLOG_STATUSES:
                raise WorkspaceError("blog_status_invalid", f"Blog artifact status is invalid: {name}")
        state = self._state()
        self._authorize(state, writer_id)
        requests = state.setdefault("requests", {})
        if request_id in requests:
            return dict(requests[request_id])
        metadata = _read_document(root / "metadata.json")
        validate_blog_metadata(metadata, source_id=source_id)
        snapshots = {root / name: (root / name).read_text(encoding="utf-8") if (root / name).is_file() else None for name in files}
        snapshots[root / "metadata.json"] = (root / "metadata.json").read_text(encoding="utf-8")
        try:
            for name, content in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
                temporary.write_text(content, encoding="utf-8")
                temporary.replace(target)
            for name, status in statuses.items():
                if name == EVIDENCE:
                    metadata["evidence"] = {"status": status, "updated_at": _now()}
                else:
                    metadata.setdefault("artifacts", {})[name] = {"status": status, "updated_at": _now()}
            if warnings is not None:
                metadata["warnings"] = list(warnings)
            if applicability is not None:
                metadata["value_analysis_applicability"] = dict(applicability)
            if verification_level is not None:
                if verification_level not in VERIFICATION_LEVELS:
                    raise WorkspaceError("blog_verification_level_invalid", "Verification level is invalid")
                metadata["verification_level"] = verification_level
            metadata["updated_at"] = _now()
            validate_blog_metadata(metadata, source_id=source_id)
            _write_document(root / "metadata.json", metadata)
        except Exception:
            for path, snapshot in snapshots.items():
                if snapshot is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(snapshot, encoding="utf-8")
            raise
        state["version"] = int(state.get("version", 0)) + 1
        committed = {
            "status": "committed",
            "source_id": source_id,
            "version": state["version"],
            "artifacts": sorted(files),
        }
        requests[request_id] = committed
        _write_document(self.path, state)
        return committed

    def fail(
        self,
        *,
        source_id: str,
        statuses: dict[str, str],
        writer_id: str,
        request_id: str,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        """Record a failed artifact without deleting anything already published."""
        return self.commit(
            source_id=source_id,
            files={},
            statuses=statuses,
            writer_id=writer_id,
            request_id=request_id,
            warnings=warnings,
        )


def _dump(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
