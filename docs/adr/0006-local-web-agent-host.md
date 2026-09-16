---
status: accepted
---

# Run the FOCUS web conversation through a local App Server host

The standalone application now defaults to a real Python Host. Fixture mode is explicit
(`VITE_FOCUS_READER_BASE_URL=fixture`); HTTP failures never fall back to fixtures.
This chooses a FOCUS-owned Host for the first usable web workflow rather than the
future DSH integration described in Phase 2. ADR 0004's host-independent seam remains.

The Host manages a pinned Codex App Server over stdio, passing the existing four
reading/parser skills explicitly. It exposes one `focus` dynamic tool for Core
operations. Normal shell/patch capabilities remain available for user-requested
file tasks. Parser registration still uses the existing parser scripts. Reading Plan,
Cursor, translations and Notes stay under Core authority. No second planning engine,
parser, knowledge index or reading database is introduced.

`ReadingWindow` gains an empty state and optional host task projection. `ReaderHost`
gains optional subscription, upload, approval and stop capabilities, all expressed as
FOCUS types. Raw Codex protocol is confined to `host/`. The Host stores conversation,
request IDs and the Codex thread ID in a separate host-data SQLite database, outside
Reading Workspace. SQLite is host persistence, not a change to ADR 0003's domain assets.

One trusted owner and one host process own a Workspace. Host mutations are serialized;
an OS lock rejects a second Host process. Do not concurrently use the old CLI skills
against that same Workspace. Refresh/reconnect consumes a full authoritative snapshot;
missing SSE events do not require replay. The UI never persists a second Cursor.
Explicit Continue uses a captured Source/Plan/Chunk receipt and advances once; ordinary
questions cannot invoke the Core Continue tool without an additional explicit user
confirmation. A bare “继续” does not advance automatically.

Workspace writes use the runtime's `workspace-write` sandbox, with explicit writable
root and temporary-directory exceptions disabled. The pinned version does not expose
the newer documentation's restricted-read policy fields; those fields are not sent.
Shell read isolation and multi-tenant isolation are not claimed. The skill/Core-only
rule for reading assets is an agent contract, not an OS separation within Workspace.
Use a dedicated OS identity/container if a stronger execution boundary is required.
Native command/file/permission approvals and tool questions return to the existing
runtime request, without restarting a turn. Unsupported MCP elicitation is explicitly
declined. The Host never offers persistent execution-policy amendments.

Stop interrupts the real turn, then terminates an unresponsive runtime. It is not a
rollback. A restarted Host marks unfinished work interrupted and resumes the saved
Codex thread only on the next user request. Missing or invalid thread state fails
visibly instead of silently starting a context-free conversation.

Runtime/API compatibility is pinned to 0.154.0 and based on generated experimental
JSON schema, not only on website examples. Dynamic tools are an experimental App
Server interface; upgrades require protocol and local acceptance checks.

## Session revision, 2026-09-16

The Host now archives and resets its current conversation independently of Core.
Session IDs, ordered message/paragraph references and fresh-session state are Host
persistence. Reset stops and joins the active worker before replacing state. Resume
Reading is a read-only projection of the preserved Cursor. Ordinary question receipts
may reference historical paragraphs; only Continue requires the current Cursor receipt.

Default loopback-only service access opens directly without a token screen. Explicit
FOCUS_HOST_TOKEN and non-loopback/public-origin deployments retain authentication.
Host/Origin checking still applies to all routes; remote exposure is not enabled by
this change.

## Web reading output contract

The attachment start action requests reading only. For ordinary start/open/next/
continue operations, the Agent prepares or reuses the source and plan, selects the
current paragraph and saves any required translation through Core. The reading
card owns source/translation presentation and its toggle; the Agent then waits
instead of duplicating that content or adding an unsolicited explanation in chat.
The Host supplies this contract on both thread creation and resume, and reinforces
it after a Host-managed advance. Earlier explanation requests do not authorize
automatic explanation on a later standalone reading action.

Explicit explanation, summary and retranslation requests remain normal Agent tasks;
they do not independently advance the Cursor. Progress, necessary questions and
errors remain visible. No response filtering or separate reading mode is involved.
Protocol tests verify instruction delivery, Core translation projection and chat
passthrough; they do not establish live model compliance with these instructions.
