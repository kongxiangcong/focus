---
status: accepted
---

# Parse saved web articles locally through the shared Bundle

Complete SingleFile HTML is the web-article input. Replace MinerU-HTML with Mozilla Readability for article-body selection, then local Markdown conversion and embedded-image extraction. Browser capture remains outside the parser; PDF continues to use hosted MinerU. This preserves the webpage's existing structure and image bytes without a remote HTML upload or a PDF round trip.

Readability locates the body; the matching original DOM container supplies its content so extraction heuristics cannot silently discard figures. Structural navigation, comments, recommendations, ads, dialogs and hidden interface elements are excluded. Ambiguous boundaries, missing/placeholder images and unsupported embedded media stop publication; unmarked in-body advertising remains a semantic review limitation. Canonical HTML original bytes are preserved. Origin URL is the article identity when present; otherwise original bytes identify the snapshot.

Both formats use the same Inbox confirmation, attempt, cancellation, validation and publication state machine. HTML declares a local service and no remote task reference; Core checks original binding and local media references. Article Source also enters the shared blog method; generated explanations distinguish an article's interpretation from original research evidence. This supersedes the HTML provider choice in ADR-0002 and extends ADR-0013's source scope without changing artifact ownership.
