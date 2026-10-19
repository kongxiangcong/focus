# Provenance and adoption ledger

## Baseline

Source: https://github.com/Caho1/open-claude-ui
Pinned commit: `02d021fceaf2a907f9e63a8125621bdda1b85d60`.
Evidence basis: the source-level review in the preceding conversation, dated 2026-10-16. This bundle does not claim a fresh full-repository audit or an execution of upstream components. The new native HTML implementations are authored for this bundle and separately tested.

Use these immutable paths for reproducibility:
`https://github.com/Caho1/open-claude-ui/blob/02d021fceaf2a907f9e63a8125621bdda1b85d60/<path>`.

## Adoption decisions

| Topic | Source file(s) | Evidence / limitation | Bundle decision |
|---|---|---|---|
| Semantic surface, spacing and radius roles | `code-examples/cds-theme.css`, `docs/v1/01-设计哲学与设计令牌体系.md` | Source-confirmed tokens; not proof of official Anthropic design intent | Adopt role-based approach; independently author values and contrast-safe action colors |
| Unified motion | `AGENTS.md`, `code-examples/ClaudeMotionPresets.ts` | Same names have inconsistent numeric parameters | Do not copy springs; use one JSON and conservative native transitions |
| Chinese input | `code-examples/ChatComposer.tsx` | Composition checks are present; native platform coverage unverified | Adopt behavior requirement; write native handler and synthetic tests |
| Scroll-follow intent | `code-examples/useClaudeScrollPinning.ts` | Cooldown and bottom tolerance present; full runtime robustness unverified | Write explicit follow/history state with frame-coalesced updates |
| Dialog | `code-examples/ConfirmationDialog.tsx` | Audited source lacked complete focus containment/restoration/name wiring despite broader documentation claim | Reimplement using native dialog; test focus restoration and containment |
| Splitter | `code-examples/ArtifactsSplitPaneResizer.tsx` | Comments mention dead zone/spring reset not implemented equivalently; keyboard adjustment absent | Implement real threshold, keyboard, cancellation and responsive fallback |
| Iframe drag shield | Same splitter | `pointer-events:none` shield alone cannot intercept | Reference correct requirement; no iframe in demos, no iframe test claim |
| Responsive toolbar | `code-examples/ContainerResponsiveBar.tsx` | Container adaptation demonstrated; utility framework assumptions | Adopt task-priority adaptation, not fixed class syntax |
| Offline HTML | `docs/claude-components-storybook.html` | Has CDN React/Tailwind/Babel and remote fonts | Author actual self-contained native HTML; test blocked-network file:// paths |
| Branding/assets | `LICENSE`, `assets/README.md` | Upstream MIT and asset policy, not third-party legal clearance | Retain license notice; no proprietary fonts/audio/logos; no endorsement claim |

## What is not claimed

No official Anthropic affiliation or certification. No independent verification of the upstream reverse-engineering provenance or “production-grade” claims. No copied desktop/electron/audio engine. No automatic graph-layout engine or NPU performance simulator. No measured LLM skill effectiveness, screen-reader certification, or universal browser compatibility.

## Independent additions

All three native starters; accessible native-dialog wiring; deterministic build; self-contained-file checker; scoped token contrast checks; browser regression tests; CSV safety handling; task contracts; project-style preservation; honesty in validation; agent evaluation prompts.

These are new engineering/design decisions, not claims about what exists in the upstream code. Demonstration architecture descriptions and numbers are illustrative and explicitly marked as such.

## External reference sources (checked 2026-10-16)

- Agent Skills format: https://agentskills.io/specification
- Codex skill discovery/metadata: https://developers.openai.com/codex/skills
- Claude Code: https://code.claude.com/docs/en/skills
- Cursor: https://cursor.com/docs/skills
- WAI modal dialog: https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
- WAI window splitter: https://www.w3.org/WAI/ARIA/apg/patterns/windowsplitter/ (pattern notes incomplete review)
- WAI tabs: https://www.w3.org/WAI/ARIA/apg/patterns/tabs/
- WCAG contrast: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
- WCAG target size: https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- MDN native dialog: https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog
- MDN reduced motion: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion

## Updating

Pin the new upstream commit; compare only relevant files; record discrepancies before adoption. Existing product tests and bundle behavior contracts override upstream marketing claims. Edit canonical source files, regenerate, run validation, then update this ledger. Never blindly replace the skill with upstream AGENTS.md.

## 1.1.0 workflow update — 2026-10-17

The existing standalone assets and their original upstream baseline are unchanged. This update responds to a supplied FOCUS design analysis and execution brief: explicit redesign authority, local reference snapshots, product-owned parameter precedence, scope classification, and real-path-first delivery. These are new generic workflow decisions; they are not a fresh audit of open-claude-ui v2 or the user's local external directory. FOCUS-specific tokens, ADRs, routes and scope remain in the separate product handoff.

`reference-adoption.md` and `product-redesign.md` define how the executing local agent must check its actual reference checkout and authoritative product spec. `audit_reference.py` collects declared-file hashes/Git metadata; it does not verify design claims. New unit tests cover that deterministic helper and packaging/document contracts, not empirical agent behavior. Original 1.0.0 evidence is retained under `history/1.0.0/validation/`; new release evidence is in `validation/`.

Codex local discovery/invocation and Agent Skills structure were rechecked against the official documentation on 2026-10-17. Earlier platform/accessibility references above retain their original check date unless specifically rechecked; no platform installation or agent generation run is implied.
