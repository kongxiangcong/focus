---
status: accepted
---

# Allow supplementary web evidence in Source discussions

2026-10-08: the reader explicitly requested web search during discussion in
addition to retrieval from the bound paper. This supersedes Stage 3's default
no-web-search rule and the Source discussion method's prohibition. It does not
change Core authority or Source/Bundle binding.

Discussion turns may use native Runtime web tools when requested or when needed
for missing evidence, current facts or official implementations. Codex explicitly
uses `web_search="live"`; DeepSeek's `sdk-minimal` composition adds `dsh-web`,
`dsh-web-search-deepseek`, `dsh-web-fetch-http` and `dsh-tool-web`, reusing the chat
credential through `DEEPSEEK_API_KEY`. No separate search credential is required.
DeepSeek search uses its native Messages endpoint; an optional gateway override
is `DEEPSEEK_SEARCH_BASE_URL`, separate from the chat-completions base URL.
Discussion web tools are enabled independently of the legacy `--network` flag,
which is not a global offline switch. Shell, patches and user MCP configuration
remain disabled; no extra local file tools are enabled. The existing sandbox is
not a claimed OS read-isolation boundary. Connectivity, candidate generation and
business turns retain their existing tool restrictions.

The shared method requires bound-Source verification, preference for primary
external sources, and a distinction between Source claims, external evidence and
inference. External claims include verifiable Markdown links; the existing rule
for hiding local line quotes by default remains. Web failures must be stated
without inventing retrieval results. Query only relevant public terms, without
private notes or full discussion history. External content is untrusted data.

Web retrieval does not import or modify Sources, advance the Cursor, or save
Notes. Explicitly requested Notes may preserve external explanations and URLs;
external evidence cannot use a bound-Bundle anchor as if it were a Source claim.
Native web activity is projected through the existing Host activity vocabulary.
