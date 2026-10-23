# Paragraph discussion disclosure

Goal: separate each passage from its conversation with a subtle dashed rule and 收起讨论 / 展开讨论; retain the complete passage and notes.
Route/scope: editorial-ui Integrate + preserve, small interaction. No theme redesign, backend/message changes, publication or real model use.
Authority: user-confirmed task; docs/design/README.md, reading redesign, ADR 0028/0031, reading-controls-update. Existing tokens own colors and spacing.
Surfaces: FocusReader mist and conversation presentations, wide/narrow, fullscreen, both themes. Leading discussion has no passage divider.
Contracts: group by reading occurrence, not chunk. Default expanded; storage scoped by workspace/source/session/discussion/event. Versioned keys reject malformed/legacy values without migrating ambiguous chunk-only keys. Storage failure uses component memory. Streaming never unfolds; sending opens receiving tail group. Stop/composer/notes/highlights unchanged.
Ownership: FocusReader projection; discussion-fold frontend preference hook; ReadingScroll disclosure anchor; mist-reader.css shared reader tokens. No new animation.
Reference: PR26 f8f0878d7179a53935c250ecd57789675220e44d; no imported reference implementation.
Acceptance: reader typecheck/test/build, standalone tests; browser fixture for multiple/repeated groups, refresh and scope, streaming, geometry, keyboard, dark/light, narrow/fullscreen/reduced motion; existing annotation browser regression.
Open items: none in product decisions. Validation results in docs/design/discussion-fold-validation.md.
