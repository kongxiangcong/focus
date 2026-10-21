# Maintaining editorial-ui

Read this only when changing the skill, scripts or reusable assets. Product UI tasks start at SKILL.md.

## Sources and evaluation

- [Provenance](maintenance/provenance.md): historical upstream baseline, attribution and adoption decisions.
- [Evaluation tasks](maintenance/evaluation-tasks.md): task prompts for independent agent evaluations; record actual executions separately.
- [Changelog](maintenance/CHANGELOG.md): skill revisions.
- Keep LICENSE, THIRD_PARTY_NOTICES.md and licenses/ with copied substantive material.

## Ownership map

| Rule | Authority |
|---|---|
| Route, scope size, six workflow completion criteria | SKILL.md |
| Brief fields | references/brief-schema.md |
| Visual precedence and numerical ownership | references/design-authority.md |
| State board and real product slice sequence | references/product-redesign.md |
| Evidence basis, test statuses and limitations | references/quality-gates.md |

Other files link to these authorities. Maintain one vocabulary: **real product slice**.

## Checks

Run from the product root, substituting the skill path if installed elsewhere:

```bash
python .agents/skills/editorial-ui/scripts/build_starters.py --check
python .agents/skills/editorial-ui/scripts/validate_skill.py
python -m unittest discover -s .agents/skills/editorial-ui/tests -p 'test_*.py'
```

For asset/runtime changes, when the environment permits its browser tooling:

```bash
python .agents/skills/editorial-ui/scripts/browser_smoke.py --out .scratch/editorial-ui-maintenance/browser
```

Edit assets/src/ and JSON defaults, then run build_starters.py without --check to regenerate. For documentation-only revisions, confirm generated assets remain unchanged. Use the environment's allowed browser path; the smoke script's sample selectors cover only starters. Forward-test routing on isolated tasks after major workflow changes, keeping raw task prompts and outcomes outside execution references.

Python tools use the standard library except browser_smoke.py (Playwright). Install dependencies only within existing authorization. audit_reference.py snapshots declared regular files and Git metadata without executing upstream code; check_offline.py inspects common loading patterns; validate_skill.py checks this repository's metadata profile, local links and assets. Evidence limits are defined in references/quality-gates.md.

## Retired release packaging

This repository owns the skill in place. The downloadable-package README installation scripts, SHA256SUMS.txt and generated validation/history screenshots and logs were removed from the active tree in 1.2.0. They remain recoverable at commit `a9b1a656feb62e530e6b9f9723780c4d14c631d5` under `.agents/skills/editorial-ui/` (for example with `git show <commit>:<path>`). Existing source/license records are retained above; old screenshots are historical evidence only.

Write new reproducible logs/screenshots to ignored `.scratch/<feature>/`; retain a concise reviewed result in the relevant issue or PR. Avoid checking binary release snapshots back into the skill. Repository history and the changelog replace per-release checksum manifests. Use repository checkout for installation; separate personal-directory installer scripts are outside this repository skill's scope.
