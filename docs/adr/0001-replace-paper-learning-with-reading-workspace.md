---
status: accepted
---

# Replace Paper Learning with a Reading Workspace

FOCUS will replace the active Paper Companion learning product with a topic-driven Reading Workspace. The new product owns papers, reading plans, reading position, translation caches, reader notes, and independent explanation sessions, but it does not model understanding, assessment, mastery, retention, or a cognitive profile. This deliberately trades automated learning evaluation for a smaller and clearer reading experience in which only Continue Reading can move the Reading Cursor.

The old `ask-paper` / Scout / Study / Mastery implementation will be recoverable through the `paper-companion-v0.2` Git tag and removed from the active mainline during implementation rather than retained in a `legacy/` directory. Phase 1 is an intentionally disposable prototype: its file formats may be replaced before DSH integration, while the domain boundaries in [CONTEXT.md](../../CONTEXT.md) remain authoritative.
