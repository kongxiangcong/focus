# Parser adapter contract

Load this reference when invoking a parser, deciding whether existing extraction artifacts are reusable, or classifying ingest defects.

## Stable boundary

Treat the parser as a replaceable extraction backend. Require only these stable outputs:

- a byte-identical source PDF copy;
- non-empty `paper.md`;
- parseable `metadata.json`;
- `images/`, which may be empty when the paper contains no extracted images.

Do not require page-by-page Markdown, separate formula files, separate table files, SVG, or semantic claims. Record the parser name, version, source SHA-256, run ID, completion time, warnings, resolved model revisions, and available model-license evidence.

## Local Docling setup

The qualified runtime is CPython 3.12 with the exact packages in [requirements-docling.txt](requirements-docling.txt). `onnxruntime` is intentional: it makes Docling AutoOCR select the ONNX backend whose artifacts the adapter provisions.

On Windows, do not let Hugging Face build its normal cache snapshot. Snapshot entries use symlinks and can fail with `WinError 1314` when Developer Mode or link privilege is unavailable. Use an ordinary project-local model directory instead:

```powershell
uv venv --python 3.12 .scratch/docling-qualification/.venv
uv pip install --python .scratch/docling-qualification/.venv/Scripts/python.exe `
  -r .agents/skills/paper-ingest/references/requirements-docling.txt

.scratch/docling-qualification/.venv/Scripts/python.exe `
  .agents/skills/paper-ingest/scripts/parse_pdf.py `
  --source <paper.pdf> `
  --output <route-run>/candidate `
  --artifacts-path .scratch/docling-artifacts `
  --prepare-artifacts
```

`--prepare-artifacts` downloads model files only. It passes a `local_dir` for every model repository, records a manifest, and never sends the paper anywhere. Omit it on later runs; the adapter verifies the manifest, sets Hugging Face and Transformers to offline mode, disables Docling remote services and external plugins, and loads only `--artifacts-path`.

Do not register an OCR API for this backend. A hosted parser remains disabled until the user gives explicit document-upload consent.

## FlexSA qualification record

`docling-standard-formula@1` passed a real local extraction on 2026-08-01 using `A04_FlexSA.pdf`, SHA-256 `fbf6be55d74985716c65f4132abf745d80b69db32212cd211aa3692d079ec93e`:

- 13 input and parsed pages with provenance on all 13 pages;
- 66,309 normalized Markdown characters and 259 source anchors;
- 13 portable image references, 13 picture labels, 2 table labels, and no broken or escaping references;
- 0 formula labels, correctly treated as no displayed formula objects rather than missing content;
- local-only layout, TableFormer, CodeFormula, and RapidOCR artifacts recorded in metadata;
- no structural blocking errors.

Manual review passed section order and representative figure crops. Preserve these explicit warnings: Algorithm 1 is legible in its extracted image but one assignment is split in the generated Markdown table; native PDF line boundaries join a few words; inline algebra and pseudocode exist even though there are no displayed formula objects. Exact wording and pseudocode must remain traceable to the image/source PDF.

## Staging and promotion

1. Compute SHA-256 before parsing.
2. Search the registry for that hash. Reuse a validated record rather than creating a duplicate.
3. Treat the same title with a different hash as a distinct version. Preserve the relationship without inheriting generated learning evidence.
4. Write parser output under `.paper-companion/runs/<run-id>/` inside the selected workspace.
5. Validate the staged output.
6. Promote it to `research-corpus/<paper-directory>/` only after validation succeeds.
7. Never overwrite an existing paper directory implicitly. Use the state service to select a collision-safe identity.

For re-ingest, preserve `notes/`, `reading/`, `assessment/`, and workspace cognitive evidence. Replace only generated source and ingest artifacts authorized by the repair route.

## Source map

Create `ingest/source-map.yaml` with stable anchors derived from observable extraction structure:

```yaml
schema_version: 1
source_sha256: <sha256>
anchors:
  - id: sec-3-2
    kind: section
    heading: Voxel Overview
    markdown_heading: "## 3.2 Voxel Overview"
    page: null
  - id: fig-3
    kind: figure
    asset: images/figure_003.png
    caption: null
    page: null
```

Use stable IDs for `section`, `figure`, `equation`, and `table` anchors that actually exist. Use `null` for unavailable page or caption data. Do not infer semantic importance in this file.

## Validation gate

Write machine-readable `ingest/validation.json` and a concise `ingest/extraction-report.md`. Require all of the following before promotion:

- `source.pdf` exists and its recorded hash matches;
- `paper.md` is non-empty and contains at least one recognizable heading or body block;
- `metadata.json` parses;
- normalized image references are portable, remain within the candidate directory, and resolve;
- raw backend output is preserved unchanged even when it contains absolute artifact paths;
- source-map paths resolve and anchor IDs are unique;
- `blocking_errors` is empty;
- non-blocking defects appear in `warnings` and in the extraction report.
- every backend-declared `manual_spot_checks_required` item has a recorded `passed` review before promotion; this includes section/page coverage, reading order, central formulas/tables/figures, and sampled source-anchor span accuracy.

Classify as blocking when damage would make later claims untraceable, including missing pages, unreadable core sections, broken essential figures, or severely corrupted central formulas or tables with no preserved source image. Classify cosmetic layout loss, unavailable page numbers, native word-boundary joins, or a degraded generated table with a legible source crop as warnings when source fidelity remains adequate.

Parser exit success is not gate success. Preserve the staged run and block the paper when the structural contract is unmet.
