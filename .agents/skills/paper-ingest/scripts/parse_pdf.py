#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import yaml
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ImageRefMode


BACKEND_ID = "docling-standard-formula@1"
ARTIFACT_MANIFEST = "artifacts-manifest.json"
LIGATURES = str.maketrans({"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def atomic_yaml(path: Path, value: Any) -> None:
    atomic_text(path, yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=100))


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _first_matching_file(root: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        matches = sorted(root.glob(pattern))
        if matches:
            return matches[0]
    return None


def required_artifact_paths(root: Path) -> dict[str, list[Path | None]]:
    formula_root = root / "docling-project--CodeFormulaV2"
    formula_weight = _first_matching_file(
        formula_root,
        ("model.safetensors", "model-*.safetensors", "pytorch_model.bin"),
    )
    return {
        "layout": [
            root / "docling-project--docling-layout-heron" / "config.json",
            root / "docling-project--docling-layout-heron" / "model.safetensors",
            root / "docling-project--docling-layout-heron" / "preprocessor_config.json",
        ],
        "tableformer": [
            root
            / "docling-project--docling-models"
            / "model_artifacts"
            / "tableformer"
            / "accurate"
            / "tm_config.json",
            root
            / "docling-project--docling-models"
            / "model_artifacts"
            / "tableformer"
            / "accurate"
            / "tableformer_accurate.safetensors",
        ],
        "code_formula": [formula_root / "config.json", formula_weight],
        "rapidocr": [
            root / "RapidOcr" / "onnx" / "PP-OCRv4" / "det" / "ch_PP-OCRv4_det_infer.onnx",
            root / "RapidOcr" / "onnx" / "PP-OCRv4" / "cls" / "ch_ppocr_mobile_v2.0_cls_infer.onnx",
            root / "RapidOcr" / "onnx" / "PP-OCRv4" / "rec" / "ch_PP-OCRv4_rec_infer.onnx",
            root
            / "RapidOcr"
            / "paddle"
            / "PP-OCRv4"
            / "rec"
            / "ch_PP-OCRv4_rec_infer"
            / "ppocr_keys_v1.txt",
            root / "RapidOcr" / "fonts" / "FZYTK.TTF",
        ],
    }


def artifact_inventory(root: Path, *, with_hashes: bool = False) -> dict[str, Any]:
    required = required_artifact_paths(root)
    missing: list[str] = []
    required_files: list[dict[str, Any]] = []
    for component, paths in required.items():
        for path in paths:
            if path is None:
                missing.append(f"{component}/<model weight>")
            elif not path.is_file():
                missing.append(_relative(path, root))
            else:
                entry: dict[str, Any] = {
                    "component": component,
                    "path": _relative(path, root),
                    "bytes": path.stat().st_size,
                }
                if with_hashes:
                    entry["sha256"] = sha256_file(path)
                required_files.append(entry)
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and ".cache" not in path.relative_to(root).parts
    ]
    return {
        "root": str(root.resolve()),
        "component_status": {
            component: all(path is not None and path.is_file() for path in paths)
            for component, paths in required.items()
        },
        "missing_required_files": missing,
        "file_count": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "required_files": required_files,
    }


def _license_from_readme(directory: Path) -> dict[str, Any]:
    readme = directory / "README.md"
    evidence: dict[str, Any] = {
        "readme": _relative(readme, directory) if readme.is_file() else None,
        "declared": None,
    }
    if not readme.is_file():
        return evidence
    text = readme.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?m)^license:\s*([^\r\n]+)", text[:4000])
    if match:
        evidence["declared"] = match.group(1).strip().strip("'\"")
    return evidence


def _hf_revision_evidence(directory: Path) -> dict[str, Any]:
    revisions: set[str] = set()
    etags: set[str] = set()
    metadata_root = directory / ".cache" / "huggingface" / "download"
    if metadata_root.is_dir():
        for metadata in metadata_root.rglob("*.metadata"):
            lines = metadata.read_text(encoding="utf-8", errors="replace").splitlines()
            if lines and re.fullmatch(r"[0-9a-f]{40,64}", lines[0]):
                revisions.add(lines[0])
            if len(lines) >= 2 and lines[1]:
                etags.add(lines[1])
    return {
        "resolved_revisions": sorted(revisions),
        "file_etags": sorted(etags),
        "license_evidence": _license_from_readme(directory),
    }


def prepare_local_artifacts(root: Path, *, force: bool, progress: bool) -> dict[str, Any]:
    """Materialize Docling models as normal files without Windows symlinks."""
    from docling.datamodel.pipeline_options import LayoutOptions
    from docling.models.stages.code_formula.code_formula_model import CodeFormulaModel
    from docling.models.stages.layout.layout_model import LayoutModel
    from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel
    from docling.models.stages.table_structure.table_structure_model import TableStructureModel

    root.mkdir(parents=True, exist_ok=True)
    layout_spec = LayoutOptions().model_spec
    downloads = (
        (
            "layout",
            layout_spec.repo_id,
            layout_spec.revision,
            root / layout_spec.model_repo_folder,
            lambda target: LayoutModel.download_models(
                local_dir=target,
                force=force,
                progress=progress,
                layout_model_config=layout_spec,
            ),
        ),
        (
            "tableformer",
            "docling-project/docling-models",
            "v2.3.0",
            root / TableStructureModel._model_repo_folder,
            lambda target: TableStructureModel.download_models(
                local_dir=target, force=force, progress=progress
            ),
        ),
        (
            "code_formula",
            "docling-project/CodeFormulaV2",
            "main",
            root / CodeFormulaModel._model_repo_folder,
            lambda target: CodeFormulaModel.download_models(
                local_dir=target, force=force, progress=progress
            ),
        ),
    )
    resolved: list[dict[str, Any]] = []
    for component, repo_id, revision, target, downloader in downloads:
        downloaded = Path(downloader(target)).resolve()
        resolved.append(
            {
                "component": component,
                "repo_id": repo_id,
                "requested_revision": revision,
                "local_dir": str(downloaded),
                **_hf_revision_evidence(downloaded),
            }
        )

    rapid_root = root / RapidOcrModel._model_repo_folder
    RapidOcrModel.download_models(
        backend="onnxruntime", local_dir=rapid_root, force=force, progress=progress
    )
    resolved.append(
        {
            "component": "rapidocr",
            "repo_id": "RapidAI/RapidOCR",
            "requested_revision": "v3.4.0 models plus v2.0.7 character keys",
            "local_dir": str(rapid_root.resolve()),
            "resolved_revisions": ["v3.4.0", "v2.0.7"],
            "source_urls": [
                details["url"]
                for details in RapidOcrModel._default_models["onnxruntime"].values()
            ],
            "license_evidence": {
                "declared": None,
                "note": "No model license file is embedded by Docling's direct RapidOCR downloader; review upstream before redistribution.",
            },
        }
    )

    inventory = artifact_inventory(root, with_hashes=True)
    if inventory["missing_required_files"]:
        raise FileNotFoundError(
            "Local Docling artifact preparation is incomplete: "
            + ", ".join(inventory["missing_required_files"])
        )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "ordinary-local-directories-no-symlinks",
        "docling_version": importlib.metadata.version("docling"),
        "components": resolved,
        "inventory": inventory,
    }
    atomic_json(root / ARTIFACT_MANIFEST, manifest)
    return manifest


def load_artifact_manifest(root: Path) -> dict[str, Any] | None:
    path = root / ARTIFACT_MANIFEST
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Artifact manifest must be an object: {path}")
    return value


def native_text_preflight(source: Path) -> dict[str, Any]:
    document = pdfium.PdfDocument(source)
    page_chars: list[int] = []
    samples: list[str] = []
    try:
        for page in document:
            text_page = page.get_textpage()
            text = text_page.get_text_range()
            page_chars.append(len(text.strip()))
            samples.append(text[:2000])
            text_page.close()
            page.close()
    finally:
        document.close()
    total = sum(page_chars)
    populated = sum(count >= 40 for count in page_chars)
    printable = sum(
        character.isprintable() or character in "\r\n\t"
        for sample in samples
        for character in sample
    )
    sampled = sum(len(sample) for sample in samples)
    printable_ratio = printable / sampled if sampled else 0.0
    healthy = bool(page_chars) and populated / len(page_chars) >= 0.9 and printable_ratio >= 0.97
    return {
        "page_count": len(page_chars),
        "page_text_characters": page_chars,
        "total_text_characters": total,
        "populated_pages": populated,
        "sample_printable_ratio": round(printable_ratio, 6),
        "healthy_native_text": healthy,
    }


def normalized_markdown(raw: str) -> tuple[str, dict[str, int]]:
    ligatures = sum(raw.count(chr(codepoint)) for codepoint in LIGATURES)
    normalized = raw.translate(LIGATURES)
    removed = 0
    result: list[str] = []
    for character in normalized:
        if character in "\n\t" or ord(character) >= 32:
            result.append(character)
        else:
            removed += 1
    text = "".join(result).replace("\r\n", "\n").replace("\r", "\n")
    return text, {"ligatures_expanded": ligatures, "control_characters_removed": removed}


def rebase_markdown_images(
    markdown: str,
    *,
    markdown_directory: Path,
    output_directory: Path,
    images_directory: Path,
) -> tuple[str, int]:
    """Convert Docling's absolute image targets to portable output-relative paths."""
    images_root = images_directory.resolve()
    rewritten = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal rewritten
        alt, raw_target = match.group(1), match.group(2).strip()
        if raw_target.startswith(("http://", "https://", "data:")):
            return match.group(0)
        target_text = raw_target.strip("<>")
        target = Path(target_text)
        resolved = target.resolve() if target.is_absolute() else (markdown_directory / target).resolve()
        if resolved != images_root and images_root not in resolved.parents:
            raise ValueError(f"Docling image reference escapes the candidate images directory: {raw_target}")
        portable = resolved.relative_to(output_directory.resolve()).as_posix()
        rewritten += 1
        return f"![{alt}]({portable})"

    result = re.sub(r"!\[([^\]]*)\]\(([^)\r\n]+)\)", replace, markdown)
    return result, rewritten


def item_label(item: Any) -> str:
    label = getattr(item, "label", None)
    return str(getattr(label, "value", label or item.__class__.__name__)).lower().replace(" ", "_")


def provenance_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    result: dict[str, Any] = {}
    for field in ("page_no", "charspan", "bbox"):
        item = getattr(value, field, None)
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json", exclude_none=True)
        if item is not None:
            result[field] = item
    return result


def build_source_map(document: Any, source_hash: str) -> tuple[dict[str, Any], dict[str, int]]:
    anchors: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    anchored_labels = {
        "section_header",
        "title",
        "picture",
        "table",
        "formula",
        "code",
        "caption",
        "list_item",
        "text",
    }
    for item, _level in document.iterate_items():
        label = item_label(item)
        if label not in anchored_labels:
            continue
        provenance = [provenance_dict(prov) for prov in getattr(item, "prov", [])]
        if not provenance:
            continue
        counts[label] = counts.get(label, 0) + 1
        anchor: dict[str, Any] = {
            "id": f"dl-{label}-{counts[label]:04d}",
            "kind": label,
            "backend_ref": getattr(item, "self_ref", None),
            "page": provenance[0].get("page_no"),
            "provenance": provenance,
        }
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            anchor["heading" if label in {"section_header", "title"} else "text_preview"] = text.strip()[:240]
        anchors.append(anchor)
    source_map = {
        "schema_version": 1,
        "source_sha256": source_hash,
        "backend": BACKEND_ID,
        "anchors": anchors,
    }
    return source_map, counts


def markdown_image_references(markdown: str) -> list[str]:
    return [
        match.group(1).strip().split(" ", 1)[0].strip("<>")
        for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", markdown)
    ]


def cached_model_snapshots() -> list[dict[str, str]]:
    roots = []
    if os.environ.get("HF_HOME"):
        roots.append(Path(os.environ["HF_HOME"]) / "hub")
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    snapshots: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for model in root.glob("models--*"):
            for snapshot in (model / "snapshots").glob("*") if (model / "snapshots").is_dir() else []:
                key = (model.name, snapshot.name)
                if key not in seen:
                    snapshots.append({"repository_cache": model.name, "resolved_revision": snapshot.name})
                    seen.add(key)
    return sorted(snapshots, key=lambda item: (item["repository_cache"], item["resolved_revision"]))


def parse(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    if not source.is_file():
        raise ValueError(f"Source PDF not found: {source}")
    output.mkdir(parents=True, exist_ok=True)
    images = output / "images"
    raw = output / "raw"
    images.mkdir(exist_ok=True)
    raw.mkdir(exist_ok=True)

    artifacts_path = Path(args.artifacts_path).resolve() if args.artifacts_path else None
    if args.prepare_artifacts and artifacts_path is None:
        raise ValueError("--prepare-artifacts requires --artifacts-path")
    if os.name == "nt" and artifacts_path is None:
        raise ValueError(
            "Windows requires --artifacts-path pointing to ordinary local model files. "
            "Add --prepare-artifacts on the first run to avoid Hugging Face cache symlink privilege errors."
        )
    if artifacts_path is not None and args.prepare_artifacts:
        prepare_local_artifacts(
            artifacts_path,
            force=args.force_model_downloads,
            progress=args.model_download_progress,
        )
    artifact_state: dict[str, Any] | None = None
    artifact_manifest: dict[str, Any] | None = None
    if artifacts_path is not None:
        artifact_state = artifact_inventory(artifacts_path)
        if artifact_state["missing_required_files"]:
            raise FileNotFoundError(
                "Local Docling artifacts are incomplete: "
                + ", ".join(artifact_state["missing_required_files"])
            )
        artifact_manifest = load_artifact_manifest(artifacts_path)
        if artifact_manifest is None:
            raise FileNotFoundError(
                f"Missing {ARTIFACT_MANIFEST} in {artifacts_path}; run once with --prepare-artifacts"
            )
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    source_hash = sha256_file(source)
    preflight = native_text_preflight(source)

    options = PdfPipelineOptions()
    options.enable_remote_services = False
    options.allow_external_plugins = False
    options.do_ocr = True
    options.ocr_options.force_full_page_ocr = not preflight["healthy_native_text"]
    options.force_backend_text = bool(preflight["healthy_native_text"])
    options.do_table_structure = True
    options.do_formula_enrichment = True
    options.generate_page_images = True
    options.generate_picture_images = True
    options.generate_table_images = True
    options.images_scale = args.image_scale
    options.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice(args.device), num_threads=args.threads
    )
    if artifacts_path is not None:
        options.artifacts_path = artifacts_path

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    started = time.perf_counter()
    result = converter.convert(source)
    elapsed = time.perf_counter() - started
    document = result.document
    document.save_as_json(
        raw / "docling.json",
        artifacts_dir=images,
        image_mode=ImageRefMode.REFERENCED,
        coord_precision=3,
        confid_precision=4,
    )
    document.save_as_markdown(
        raw / "docling.md",
        artifacts_dir=images,
        image_mode=ImageRefMode.REFERENCED,
        page_break_placeholder="\n\n<!-- page break -->\n\n",
    )
    raw_markdown = (raw / "docling.md").read_text(encoding="utf-8")
    paper_markdown, transformations = normalized_markdown(raw_markdown)
    paper_markdown, rebased_images = rebase_markdown_images(
        paper_markdown,
        markdown_directory=raw,
        output_directory=output,
        images_directory=images,
    )
    transformations["image_references_rebased"] = rebased_images
    atomic_text(output / "paper.md", paper_markdown)

    source_map, counts = build_source_map(document, source_hash)
    atomic_yaml(output / "source-map.yaml", source_map)
    page_coverage = sorted(
        {
            int(anchor["page"])
            for anchor in source_map["anchors"]
            if isinstance(anchor.get("page"), int)
        }
    )
    broken_images: list[str] = []
    escaped_images: list[str] = []
    output_root = output.resolve()
    for reference in markdown_image_references(paper_markdown):
        if reference.startswith(("http://", "https://", "data:")):
            continue
        resolved = (output / reference).resolve()
        if resolved != output_root and output_root not in resolved.parents:
            escaped_images.append(reference)
        elif not resolved.is_file():
            broken_images.append(reference)

    blocking_errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if len(getattr(document, "pages", {})) != preflight["page_count"]:
        blocking_errors.append(
            {
                "code": "PAGE_COUNT_MISMATCH",
                "input": preflight["page_count"],
                "parsed": len(getattr(document, "pages", {})),
            }
        )
    if len(paper_markdown.strip()) < args.min_markdown_chars:
        blocking_errors.append(
            {"code": "MARKDOWN_TOO_SHORT", "characters": len(paper_markdown.strip())}
        )
    if len(page_coverage) != preflight["page_count"]:
        blocking_errors.append(
            {
                "code": "PAGE_PROVENANCE_INCOMPLETE",
                "covered_pages": page_coverage,
                "input_pages": preflight["page_count"],
            }
        )
    if broken_images:
        blocking_errors.append(
            {"code": "BROKEN_IMAGE_REFERENCES", "paths": sorted(set(broken_images))}
        )
    if escaped_images:
        blocking_errors.append(
            {"code": "ESCAPING_IMAGE_REFERENCES", "paths": sorted(set(escaped_images))}
        )
    picture_count = counts.get("picture", 0)
    formula_count = counts.get("formula", 0)
    table_count = counts.get("table", 0)
    if picture_count < args.expect_min_pictures:
        blocking_errors.append(
            {
                "code": "PICTURE_COUNT_BELOW_EXPECTATION",
                "expected_minimum": args.expect_min_pictures,
                "actual": picture_count,
            }
        )
    if formula_count < args.expect_min_formulas:
        blocking_errors.append(
            {
                "code": "FORMULA_COUNT_BELOW_EXPECTATION",
                "expected_minimum": args.expect_min_formulas,
                "actual": formula_count,
            }
        )
    if preflight["healthy_native_text"]:
        warnings.append(
            {
                "code": "NATIVE_TEXT_PREFERRED",
                "message": "Healthy native text was preserved; OCR was limited to uncovered bitmap regions.",
            }
        )
    if transformations["ligatures_expanded"] or transformations["control_characters_removed"]:
        warnings.append({"code": "TEXT_NORMALIZED", **transformations})
    conversion_status = str(getattr(result, "status", "unknown"))
    if "success" not in conversion_status.lower():
        warnings.append({"code": "DOCLING_STATUS", "value": conversion_status})

    metadata = {
        "schema_version": 1,
        "source": {"filename": source.name, "sha256": source_hash, **preflight},
        "parser": {
            "backend_id": BACKEND_ID,
            "docling_version": importlib.metadata.version("docling"),
            "docling_core_version": importlib.metadata.version("docling-core"),
            "docling_parse_version": importlib.metadata.version("docling-parse"),
            "pipeline_options": options.model_dump(mode="json", exclude_none=True),
            "artifacts_path": str(artifacts_path) if artifacts_path else None,
            "artifact_inventory": artifact_state,
            "artifact_manifest": artifact_manifest,
            "ambient_cache_snapshots_not_used": cached_model_snapshots(),
            "model_loading": "local-files-only",
            "remote_services_enabled": False,
            "external_plugins_allowed": False,
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "device": args.device,
            "threads": args.threads,
            "elapsed_seconds": round(elapsed, 3),
        },
        "output": {
            "page_count": len(getattr(document, "pages", {})),
            "anchor_count": len(source_map["anchors"]),
            "label_counts": counts,
            "picture_count": picture_count,
            "formula_count": formula_count,
            "table_count": table_count,
            "markdown_characters": len(paper_markdown),
            "normalization": transformations,
        },
        "licenses": {
            "docling_code": "MIT",
            "model_evidence": [
                {
                    "component": component.get("component"),
                    "repo_id": component.get("repo_id"),
                    "license_evidence": component.get("license_evidence"),
                }
                for component in (artifact_manifest or {}).get("components", [])
            ],
            "redistribution_review_required_when_license_is_null": True,
        },
    }
    validation = {
        "schema_version": 1,
        "backend_id": BACKEND_ID,
        "source_sha256": source_hash,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
        "checks": {
            "input_pages": preflight["page_count"],
            "parsed_pages": len(getattr(document, "pages", {})),
            "page_provenance_coverage": page_coverage,
            "broken_image_references": sorted(set(broken_images)),
            "escaping_image_references": sorted(set(escaped_images)),
            "picture_count": picture_count,
            "formula_count": formula_count,
            "table_count": table_count,
            "local_artifact_components": (artifact_state or {}).get(
                "component_status", {}
            ),
        },
        "manual_spot_checks_required": [
            "section and page coverage",
            "two-column reading order",
            "key formula semantics and numbering",
            "vector figure crops and captions",
            "algorithm blocks and table structure",
            "sampled source-anchor span accuracy",
        ],
    }
    atomic_json(output / "metadata.json", metadata)
    atomic_json(output / "validation.json", validation)
    summary = {
        "ok": not blocking_errors,
        "backend_id": BACKEND_ID,
        "source_sha256": source_hash,
        "output": str(output),
        "blocking_error_count": len(blocking_errors),
        "warning_count": len(warnings),
        "counts": metadata["output"],
    }
    atomic_json(output / "summary.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse a paper PDF into a Paper Companion ingest candidate with local Docling"
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--device", choices=("auto", "cpu", "cuda", "mps", "xpu"), default="auto"
    )
    parser.add_argument("--threads", type=int, default=max(1, min(8, os.cpu_count() or 4)))
    parser.add_argument("--image-scale", type=float, default=2.0)
    parser.add_argument(
        "--artifacts-path",
        help="Directory containing ordinary local Docling model files; required on Windows",
    )
    parser.add_argument(
        "--prepare-artifacts",
        action="store_true",
        help="Download missing Docling models directly into --artifacts-path without cache symlinks",
    )
    parser.add_argument("--force-model-downloads", action="store_true")
    parser.add_argument("--model-download-progress", action="store_true")
    parser.add_argument("--min-markdown-chars", type=int, default=500)
    parser.add_argument("--expect-min-pictures", type=int, default=0)
    parser.add_argument("--expect-min-formulas", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        summary = parse(args)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if summary["ok"] else 2
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
