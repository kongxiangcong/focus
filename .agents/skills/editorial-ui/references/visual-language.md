# Visual language: semantic roles before colors

## Decisions

Identify the primary content and its natural reading rhythm. Default to a quiet canvas, high-contrast text, one action accent, and restrained elevation. A beautiful but indistinguishable disabled/error state is a failure.

Use four surface roles only when useful: canvas, subtle section, raised control, overlay. Adjacent regions may share a fill when typography and spacing already separate them. Do not add a border to every nested element. This is not a ban on borders: a visible input boundary or focus indicator is functional.

Resolve values using [design authority](design-authority.md#numeric-ownership).

## Typography and density

Use system sans for UI and CJK body text, optional system serif for short editorial titles, and monospace only for code/identifiers. Never package fonts. Do not synthesize dark-mode variable-font weight changes on an unknown system font.

Start reading text at 16–18 CSS px with 1.65–1.85 line height; controls at 14–15 px; secondary metadata at 12–13 px only when nonessential. These are defaults, not universal measurements. Keep Chinese paragraphs compact enough to follow and let language determine the final measure; a Latin `ch` width is not a Chinese character count.

Use bounded reading width and full available width for graphs/tables when necessary. Long words use `overflow-wrap:anywhere`; code uses a deliberate local scroll region, never a page-wide overflow. Use tabular numerals and retain units for comparable data. Do not truncate the value needed for a decision.

## Geometry

Default rhythm comes from the space scale. Use smaller radii for compact controls, moderate radii for panels, and larger radii only for truly larger containers. Do not independently randomize every radius. Concentric nesting is a useful visual approximation, not a physical law or exact requirement in every layout.

Use a stable transparent border or outline/box-shadow when an active state would otherwise change box size. Do not assert that ordinary CSS borders inherently cause jitter. Elevation must represent actual layering, not decorate every section.

## Color and accessibility

Keep low contrast in ornamental surfaces, not in functional text. Check actual foreground/background composites, hover/selected/disabled states, both themes, and focus rings. WCAG normal-text minimum is generally 4.5:1; large text generally 3:1 [S1]. The bundled checks test specified token pairs, not every possible composition.

Essential component boundaries and states need their own contrast evaluation; color alone must not carry status. Add text or a shape/label. For touch input use comfortable targets, preferably 44×44 CSS px; WCAG 2.2 target-size minimum is 24×24 subject to exceptions [S2]. Do not confuse the preferred 44px target with the AA minimum.

Make dark mode an explicit role mapping. Do not invert a screenshot or assume all pure white/black values are forbidden. Do not impose warm orange on a product whose established accent is different.

## Avoid

Huge empty hero areas above a working tool; generic dashboard card grids; oversized KPI numbers without evidence; gratuitous gradients; giant glass panels; perpetual glow; placeholder Latin copy; arbitrary emoji as icons; tiny low-contrast action text; text clipped for symmetry.

## Sources

[S1] https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
[S2] https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
Source mapping is in the maintenance-only provenance ledger.
