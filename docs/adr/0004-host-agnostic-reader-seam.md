---
status: accepted
---

# Keep the Focus Reader behind one host-independent seam

FOCUS adds one browser Reader Module whose only host dependency is the `ReaderHost` Interface in `ui/packages/reader-contracts`. The Interface projects a `ReadingWindow` and exposes explicit Continue Reading and reader-message operations. It does not expose Python CLI output, HTTP routes, Workspace paths, DSH session events, or transport-specific errors.

`ui/packages/reader-ui` owns the reading presentation and its future Markdown, motion, effects, and theme implementation. `ui/apps/standalone` is a host and currently supplies two Adapters: an in-memory Fixture Adapter and an HTTP Adapter for a future browser-safe local host. A future DSH Adapter will satisfy the same Interface outside `reader-ui`, so changing hosts does not require rewriting the Reader Module.

Focus Core remains the sole authority for Reading Plan, Reading Chunk, Reading Record, and Reading Cursor. Continue Reading remains the only Cursor move. Host conversation persistence remains outside FOCUS Workspace; `ReadingWindow.conversation` is only a host projection. Fixture state is synthetic and in-memory, and the skeleton does not read private Workspace data.

The first visual prototype must run inside this skeleton and may vary only the Reader implementation. It must not create another application structure, another state authority, or a prototype-specific host contract.
