# Motion: state, continuity, control

## Canonical values

The **standalone bundle defaults** live in `assets/motion-presets.json`. `scripts/build_starters.py` generates CSS and embeds those values into standalone JavaScript. For Integrate, the selected product specification and one product-owned motion configuration are authoritative, whether preserved or intentionally redesigned. Do not copy both preset tables, require matching bundle durations, or claim the selected upstream generation has been audited merely because this bundle has a historical source baseline.

These presets are independently chosen conservative defaults, not “official Claude physics”. The previous audit found incompatible values between upstream `AGENTS.md` and `ClaudeMotionPresets.ts`; do not combine those tables. No default spring dependency is needed in this bundle.

## Map intent to behavior

| Intent | Default behavior | Interruption |
|---|---|---|
| Press acknowledgment | Small scale transform or fill change | Pointer/key release returns immediately |
| Disclosure | Brief opacity/translation, or deliberate grid/height transition | Reverse from the current state |
| Overlay entry | Small transform and opacity; backdrop is subordinate | Escape works immediately |
| Selection | Color/outline change; optional small position continuity | Rapid changes cancel previous animation |
| Drag | Direct pointer tracking, no transition on width/position | Cancel restores the start state |
| Background work | Text state plus optional subtle indicator | Stop changes real state, not just the icon |

For every adopted effect record trigger, element/property, values, entry/exit, interruption, reduced-motion behavior and validation. Upstream numeric details are not mandatory effects: distinguish necessary spatial/state feedback from optional decorative confirmation and advanced media motion.

A genuine running-state indicator may loop only while that state exists, stopping or pausing for background visibility and reduced motion as appropriate; no permanent decorative glow. Business state and focus availability never wait for animationend. Exit presence must have cleanup that also works when events are cancelled or reduced motion changes. Native modality must be released at the correct close point without leaving invisible focus traps.

An animation is not a loading state. Do not make requests wait for entry/exit motion. Do not mark a simulated stream as an actual assistant run. Do not schedule a new layout-changing animation for every token.

Prefer CSS opacity/transform and the Web Animations API for small optional effects. `element.animate` must have a no-animation fallback. Do not promise GPU acceleration or stable frame rate without measuring. Avoid gratuitous blur filters on reading text.

Reduced motion: use `prefers-reduced-motion` in CSS and check `matchMedia` for JavaScript-created animations. If the preference changes while a JavaScript animation is running, cancel it. Remove nonessential spatial/looping motion, not the final state or status text [S1].

Focus is part of the interaction contract, not a decorative animation. Do not smooth-scroll a user away from their reading location just because a selected highlight changes. Native `details` without animation is acceptable when it improves reliability.

For products that already use springs: name them by role, document units/semantics of the chosen library, and verify interruption/settling. A stiffness number from one engine is not a portable physical measurement. CSS ease curves are not mathematically identical to springs.

## Avoid

`transition: all` across unknown properties; elastic panel widths during direct manipulation; auto-advancing explainers; perpetual particles/glow; required audio; motion that conveys the only status signal; no-op animation “replay” controls.

## Source

[S1] https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion
