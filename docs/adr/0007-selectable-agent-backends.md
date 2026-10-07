---
status: accepted
---

# Select Agent backends without changing Focus Core authority

2026-10-06 revision: [ADR 0020](0020-portable-workspaces-with-first-run-selection.md) adds first-run Backend selection, and [ADR 0021](0021-simple-backend-setup-and-apply.md) replaces the initial installation of both Backends and save-then-manual-refresh rules below with selected-Backend preparation on demand and idle Save and Apply. Those earlier rules remain historical context; shared business authority, explicit authentication and one effective Backend continue to apply.

The browser uses ReaderHost.selectBackend; HostService owns session switching and
adapters translate runtime events. Codex uses the App Server and DeepSeek uses
the Harness SDK.

Stage 6B revision (2026-09-26): Backend choice supplies Agent capabilities to one
shared FOCUS feature set. It must not create separate business implementations or
separate discussions for Codex and DeepSeek. FOCUS owns the Source-bound Discussion;
native Runtime sessions are execution context, not the discussion identity.

An idle switch checks prerequisites and preserves the same FOCUS Discussion,
Core assets and Cursor. It isolates runtime resume keys, persists selection and
rejects stale runtime events. Switching must not archive or recreate the user
discussion, including when switching back to a previously used Backend. This
supersedes the earlier archive-chat-and-create-Host-session rule. FOCUS retains
visible discussion history and supplies recent messages, earlier summaries and
source context through a shared context policy; compression does not create Notes.

Backend and model changes are settings-only and forbidden while FOCUS tasks or
actively scheduled batches are running. Saved changes take effect only after the
user refreshes the web page; Reload performs that same refresh. Before refresh,
new tasks may still use the effective configuration. A persistent bottom-right
notice, "配置更改，需要刷新页面", reflects differences between saved and effective
configuration and disappears when the saved values are changed back. Refresh
during an active task restores the page without applying pending configuration
or cancelling work; the user refreshes again after completion. One effective
configuration belongs to the Host, and all pages synchronize after activation.
Active attempts are not hot-switched.

After explicitly stopping a batch, changing settings and refreshing, an explicit
resume or retry uses the new Backend for unfinished work through new attempts.
Completed work is preserved and never automatically replayed.

One application-user default covers all AI tasks across Knowledge Bases; credentials
and runtime configuration stay outside business assets. Backend-specific protocol
and authentication adapters are allowed; Backend-specific FOCUS features are not.
First enablement installs both Backend dependencies without initiating sign-in.
Installation failures are reported separately and do not block the other ready
Backend; each failed dependency installation can be retried.
Codex uses managed ChatGPT sign-in with a settings-page login entry; an inherited
API key must not silently replace that authentication path.
FOCUS shares the user's existing personal Codex login instead of creating a
separate login store. This does not authorize changing personal runtime settings
or importing personal chats.

Stage 6B does not pin Runtime versions or reject a Runtime by version number.
Users may upgrade externally; actual startup or protocol errors are reported
without automatic downgrade or fallback. There is no in-app Runtime upgrade
action. Recorded test versions describe evidence only, not supported-version
gates. This supersedes the earlier pinned-App-Server requirement for Stage 6B;
it does not promise compatibility with every future Runtime.
Runtime resolution prefers an explicit user selection, then an existing local
installation, and installs missing dependencies during first enablement. Settings
show the actual runtime path. Resolution does not select by version or silently
switch to another executable after failure.

These are accepted target decisions, not implementation claims. The current Host
still archives its session on switching, retains some startup-bound or Codex-only
runtime paths, and stores selection in its workspace-bound database.
Backend selection tests use a protocol double; live connectivity needs separate verification.

Provider processes receive independent environment copies; switching must not mutate
Host proxy settings. Credentials and permissions stay server-side.
