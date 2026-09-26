"""Offline article extraction from a complete saved HTML; no publisher adapters."""
from __future__ import annotations

import base64
import copy
import io
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .reading_workspace import WorkspaceError, _write_document


MODEL_VERSION = "local-html-v1"
MAX_HTML_BYTES = 200 * 1024 * 1024
MAX_IMAGE_BYTES = 30 * 1024 * 1024
NOISE = re.compile(r"(?:^|[-_\s])(?:comments?|replies|advertisement|advert|ads?|recommendations?|related|sidebar|share|social|toolbar|popup|modal|paywall|login|cookie|avatar)(?:$|[-_\s])", re.I)


def _clean(soup):
    # Structural UI signals only: prose mentioning comments/advertising is content.
    for node in list(soup.find_all(True)):
        if node.parent is None:
            continue
        identity = " ".join([node.get("id", ""), *node.get("class", [])])
        identity = re.sub(r"([a-z])([A-Z])", r"\1-\2", identity)
        style = re.sub(r"\s+", "", node.get("style", "")).lower()
        if (node.name in {"script", "style", "noscript", "nav", "aside", "footer", "form", "button", "input", "select", "textarea"}
            or node.get("role") in {"dialog", "navigation", "complementary", "banner"}
            or node.has_attr("hidden") or node.get("aria-hidden") == "true"
            or "sf-hidden" in node.get("class", []) or "display:none" in style
            or ("visibility:hidden" in style and "visibility:visible" not in str(node))
            or (node.name not in {"html", "body"} and NOISE.search(identity))):
            node.decompose()


def extract_article(source: Path):
    from bs4 import BeautifulSoup

    if not source.is_file() or source.stat().st_size > MAX_HTML_BYTES:
        raise WorkspaceError("source_html_invalid", "HTML is missing or exceeds 200 MB")
    raw = source.read_text(encoding="utf-8-sig")
    soup = BeautifulSoup(raw, "lxml")
    def meta(key):
        node = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        return str(node.get("content", "")).strip() if node else ""
    title = meta("og:title")
    if not title:
        heading = soup.find("h1") or soup.find("title")
        title = heading.get_text(" ", strip=True) if heading else ""
    title = re.sub(r"\s+", " ", title).strip()
    url = meta("og:url")
    if not url:
        canonical = soup.find("link", rel="canonical")
        url = canonical.get("href", "") if canonical else ""
    if not url:
        match = re.search(r"\burl:\s*(https?://[^\s<>]+)", raw[:4096])
        url = match.group(1) if match else ""
    if url and urlsplit(url).scheme not in {"http", "https"}:
        raise WorkspaceError("source_url_invalid", "Saved article URL must be HTTP or HTTPS")
    author = meta("author")
    _clean(soup)
    nodes = {}
    for index, node in enumerate(soup.find_all(True)):
        node["data-focus-node"] = str(index)
        nodes[str(index)] = node
    try:
        completed = subprocess.run(
            ["node", str(Path(__file__).with_name("extract_article.cjs"))],
            input=json.dumps({"html": str(soup), "url": url}), encoding="utf-8",
            capture_output=True, timeout=60, check=True,
        )
        extracted = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise WorkspaceError("html_extractor_unavailable", "Mozilla Readability could not run; install Node dependencies with pnpm install") from exc
    summary = BeautifulSoup(extracted.get("content", ""), "lxml")
    roots = [node for node in summary.select("[data-focus-node]")
             if not node.find_parent(attrs={"data-focus-node": True})]
    if len(roots) != 1:
        raise WorkspaceError("article_boundary_ambiguous", "Could not isolate one article body; review the saved HTML")
    selected = nodes[roots[0]["data-focus-node"]]
    extracted_length = len(roots[0].get_text(" ", strip=True))
    original_length = len(selected.get_text(" ", strip=True))
    if not title or extracted_length < 80 or original_length > max(extracted_length * 1.25, extracted_length + 100):
        raise WorkspaceError("article_boundary_ambiguous", "Article boundary or title needs review; no Bundle was published")
    body = copy.deepcopy(selected)
    _clean(body)
    return body, {"title": title, "source_url": url, "author": author}


def article_identity(source: Path) -> str:
    """Same canonical URL reuses the Source; URL-less snapshots use original bytes."""
    from .source_library import canonical_article_url
    from .ingestion import _file_fingerprint
    _, info = extract_article(source)
    return ("url:" + canonical_article_url(info["source_url"]) if info["source_url"]
            else "article-original:" + _file_fingerprint(source))


class LocalHTMLParser:
    model = MODEL_VERSION
    language = "auto"

    def parse(self, source: Path, candidate: Path, *, checkpoint=None) -> dict:
        from PIL import Image, UnidentifiedImageError
        from markdownify import markdownify
        from .ingestion import persist_candidate_result

        body, info = extract_article(source)
        if candidate.exists() and any(candidate.iterdir()):
            raise WorkspaceError("parser_candidate_exists", "HTML candidate directory is not empty")
        candidate.mkdir(parents=True, exist_ok=True)
        images = list(body.select("img"))
        if len(images) > 300:
            raise WorkspaceError("article_media_limit", "Article has too many images")
        # Small inline SVGs are interface icons; meaningful vector media require review.
        for anchor in list(body.select("a")):
            if anchor.find("svg"):
                anchor.unwrap()
        for svg in list(body.select("svg")):
            box = svg.get("viewbox", svg.get("viewBox", "")).split()
            if len(box) == 4 and max(float(box[2]), float(box[3])) <= 32:
                svg.decompose()
            else:
                raise WorkspaceError("article_media_unsupported", "Article contains inline SVG requiring review")
        for node in body.select("iframe,video,audio,canvas,math"):
            raise WorkspaceError("article_media_unsupported", "Article contains embedded media or math requiring review")
        for index, img in enumerate(images, 1):
            src = str(img.get("src", ""))
            match = re.fullmatch(r"data:image/[a-zA-Z0-9.+-]+;base64,([A-Za-z0-9+/=\s]+)", src)
            if not match or len(match.group(1)) > MAX_IMAGE_BYTES * 4 // 3 + 1024:
                raise WorkspaceError("article_image_missing", f"Article image {index} is not a complete embedded image; save again with SingleFile")
            try:
                payload = base64.b64decode(re.sub(r"\s", "", match.group(1)), validate=True)
                with Image.open(io.BytesIO(payload)) as image:
                    width, height = image.size
                    extension = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}.get(image.format)
                    image.verify()
                if not extension or min(width, height) <= 1 or len(payload) > MAX_IMAGE_BYTES:
                    raise ValueError("unsupported or placeholder image")
            except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
                raise WorkspaceError("article_image_invalid", f"Article image {index} is invalid or a placeholder") from exc
            name = f"images/image-{index:03d}.{extension}"
            (candidate / "images").mkdir(exist_ok=True)
            (candidate / name).write_bytes(payload)
            alt = str(img.get("alt", "")).replace("[", "").replace("]", "").replace("\n", " ")
            img.attrs = {"src": name, "alt": alt}
        for anchor in body.select("a"):
            href = urljoin(info["source_url"], anchor.get("href", ""))
            if urlsplit(href).scheme in {"http", "https", "mailto"}:
                anchor.attrs = {"href": href}
            else:
                anchor.unwrap()
        for node in body.select("[style]"):
            if "url(" in node.get("style", ""):
                raise WorkspaceError("article_media_unsupported", "Article contains a CSS image requiring review")
        tables = len(body.select("table"))
        code_blocks = len(body.select("pre"))
        headings = len(body.select("h1,h2,h3,h4,h5,h6"))
        text = markdownify(str(body), heading_style="ATX", bullets="-", wrap=False,
                           keep_inline_images_in=["td", "th"], table_infer_header=True)
        title = info["title"]
        if not text.lstrip().startswith("# " + title):
            text = "# " + title + "\n\n" + text.strip()
        text = text.strip() + "\n"
        shutil.copy2(source, candidate / "source.html")
        (candidate / "content.md").write_text(text, encoding="utf-8")
        metadata = {"source_kind": "article_html", "parser": "article-parser", "model_version": self.model,
                    "extractor": "@mozilla/readability@0.6.0",
                    "language": "zh" if re.search(r"[\u4e00-\u9fff]", title) else "en",
                    "image_count": len(images), "title": title}
        metadata.update({k: v for k, v in info.items() if v})
        _write_document(candidate / "metadata.json", metadata)
        _write_document(candidate / "validation.json", {"ok": True, "checks": {
            "content_markdown_nonempty": bool(text.strip()), "source_html_preserved": True,
            "article_boundary_selected": True, "embedded_images_decoded": True},
            "statistics": {"images": len(images), "tables": tables, "code_blocks": code_blocks, "headings": headings},
            "warnings": ["Body selection is heuristic; semantic completeness requires a source spot check."]})
        result = {"title": title, "short_name": title, "source_url": info["source_url"]}
        persist_candidate_result(candidate, result)
        return result
