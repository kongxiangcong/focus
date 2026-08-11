---
name: paper-ingest
description: Claim, deduplicate, extract, and structurally validate one paper in a Paper Companion workspace. Use only when $ask-paper issues a route targeting paper-ingest for new, stale, invalid, diagnostic, or repair ingest work; otherwise remain read-only and return control to $ask-paper.
---

# Paper Ingest

Act as a route-gated internal primitive. Complete exactly one ingest stage, preserve source fidelity, and return control to `$ask-paper`.

## Establish authority

1. Require an explicit workspace and route ID.
2. Resolve `../ask-paper/scripts/focus_state.py` relative to this skill directory. Use only its `verify-route`, `validate`, `commit --route-id --event <json-or-yaml>`, and `cancel-route` commands. Express every semantic change as a typed JSON or YAML event. Never rewrite `paper.yaml`, registry state, routes, locks, or revisions as free text.
3. Verify that the route is `issued`, targets `paper-ingest`, names the same workspace, and matches either the existing paper revision or the new input path and SHA-256. Accept only the route mode that was issued.
4. On a missing or invalid route, make no changes and direct the caller to `$ask-paper`.
5. Keep an explicitly requested diagnostic invocation read-only. For repair without a valid repair route, diagnose only and return the required repair to `$ask-paper`.

Stop when authority cannot be proven.

## Run one ingest stage

1. Read [references/parser-adapter.md](references/parser-adapter.md) before selecting a parser, reusing an extraction, or repairing ingest artifacts.
2. Confirm the input hash before creating or reusing a paper record. Treat equal hashes as one source and equal titles with different hashes as separate versions. A repair route may re-extract only the paper's canonical `source.pdf` with the same hash; it never replaces that source or changes paper identity.
3. Parse into `knowledge-base/.paper-companion/runs/<run-id>/`. Promote artifacts only after the structural gate passes.
4. Produce or validate the source copy, `paper.md`, `images/`, `metadata.json`, `ingest/extraction-report.md`, `ingest/source-map.yaml`, and `ingest/validation.json`. Record unavailable locations as `null`; never invent a page, caption, formula, table, or source anchor.
5. Classify extraction defects as blocking errors or explicit warnings. Preserve failed run diagnostics.
6. On re-ingest, replace only generated ingest artifacts. Preserve notes, responses, assessments, profile evidence, and unrelated user files.

Keep semantic interpretation out of this stage. Report document structure and extraction quality; leave contribution analysis, learning order, difficulty prediction, and mastery judgments to later skills.

## Commit the result

- On a new claim, commit one typed `ingest-completed` event. Let that transaction register the validated staged artifacts, advance to `guide/ready`, increment the revision, consume the route, and release the lock.
- On a same-source repair, use the same `ingest-completed` event under the issued `repair` route. Replace only authorized generated ingest artifacts and preserve `source.pdf`, paper identity, notes, responses, assessments, and profile evidence. Preserve the prior reading phase and node states only when the repaired source map still validates every installed guide contract; otherwise fail closed by marking affected nodes `stale`, revoking plan confirmation, and returning to `paper-guide` repair.
- On failure, retain the validation artifact and other diagnostics in the route run, then use `cancel-route`. Return the exact validation error and safe retry action to `$ask-paper`. Never invent a blocker event, claim a persisted blocked projection, or mark ingest `validated` while a blocking error remains.
- Release the stage without invoking `paper-guide`. Return a short artifact summary, warnings, and the next action to `$ask-paper`.

Completion requires a consumed or cancelled route, a released lock, and state that agrees with the artifacts on disk.
