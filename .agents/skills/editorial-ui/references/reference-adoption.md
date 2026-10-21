# Reference-led adoption: inspect, decide, own, verify

Use when the user supplies a local reference repository, a design analysis, or a chosen visual specification. This workflow is generic: repository names, brands, product tokens and feature scope belong in the product brief, not this skill.

## 1. Establish what is actually available

Resolve the product root and the explicitly supplied reference path. If a reference is said to be local, inspect that directory before substituting a remote main branch. Missing access is a concrete limitation: do not claim to have audited it. Do not clone/update/pull/reset or run reference installation scripts automatically.

Record the reference's own Git top-level root, HEAD, dirty/untracked status, and the files used. `git -C external/example rev-parse HEAD` alone may return the parent product's HEAD. Attribute a repository commit only when the resolved Git top-level equals the reference root. Otherwise label a plain-directory snapshot and use file hashes; do not invent a reference revision.

A commit is insufficient for a dirty working tree. Include SHA-256 and size for each adopted file; list relevant modifications. Pin a new reference only after recording its differences from the selected design baseline. A changed HEAD is not permission to change the design.

Optional metadata tool (writes JSON to stdout, not into the source tree):
```bash
python <skill-root>/scripts/audit_reference.py \
  --reference external/example \
  --files README.md LICENSE package.json docs/README.md
```
The caller may save stdout outside the read-only reference. It hashes only declared regular files and rejects escapes/binary assets; it does not execute source, install dependencies, fetch remotes, determine license validity, or certify UI correctness. Its PASS means snapshot collection succeeded, not that adoption is safe or complete.

## 2. Record authority and evidence

Use [design authority](design-authority.md) to resolve target choices and reference trust. Label each finding with the basis/status in [quality gates](quality-gates.md#evidence-levels).

## 3. Inspect only relevant layers

Read the reference's package/build declarations, docs index, selected design generation, theme, motion source, used components and their dependencies. Inspect screenshots/demos when permitted; distinguish a demo rebuilt from inline code from a runtime using the exported components. Check actual state wiring, not just styling.

Typical conflicts: docs vs CSS values; same preset name with different numbers; title “v2” with v1 inline tokens; advertised focus trap without focus behavior; utility classes without the required build/plugin; fake attachments/model menus; desktop exports in a web root; CDN-loaded “offline” previews.

Reuse the supplied analysis as a map. Verify critical claims and changed files instead of re-reading every source file. A historical audit does not guarantee the local checkout matches.

## 4. Keep one adoption/conflict ledger

Use the project's existing design record or the product-redesign brief. Suggested columns:

| Item | Selected target | Evidence / version / file | Difference from implementation | Adopt / adapt / exclude | Product owner | Test |
|---|---|---|---|---|---|---|
| Overlay | Product-approved radius and entry | Spec section + source hash | Sample lacks async failure retention | Adapt appearance, retain native modal | Product Dialog | Failure stays open; focus returns |

Resolve ledger decisions using [design authority](design-authority.md); record accessibility/capability adaptations.

## 5. Product-owned implementation

Keep the reference read-only and outside production imports, public assets, package file: dependencies, Vite/TS aliases and dynamic loading. Copy only necessary reviewed code into a clearly owned product module when permitted; retain relevant attribution/license notices. Reimplement behavior where samples are incomplete. Do not redistribute fonts, proprietary logos or audio.

Do not install an entire utility framework or motion engine merely to make reference class strings work. Translate intent into the existing stack. A new dependency requires a concrete benefit, locked version, compatibility review and required authorization.

For visual and motion values use [numeric ownership](design-authority.md#numeric-ownership).

## 6. Verify adoption in the product

When adoption accompanies a redesign, follow the [real product slice sequence](product-redesign.md#real-product-slice). For scoped preserve-mode adoption, exercise the modified route directly. Record each required scenario using the [quality-gate matrix](quality-gates.md); keep implementation coverage as a list of changed modules, not a second test-status vocabulary.
