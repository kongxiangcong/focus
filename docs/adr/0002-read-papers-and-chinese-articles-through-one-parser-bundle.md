---
status: accepted
---

# Read papers and Chinese articles through one Parser Bundle

FOCUS registers both PDF Paper Sources and Chinese Article Sources as Reading Sources. `paper-parser` uses MinerU VLM, while the peer `article-parser` uses the precision API with MinerU-HTML; both install the same minimal Parser Bundle interface consumed by `focus-map` and `focus-read`. Parser invocation authorizes the requested URL fetch or selected local-file upload in that turn. When MinerU cannot read an Article URL, the parser returns that direct error and permits only a user-saved single `.html` file on a later explicit invocation. It does not vary by publishing platform or bypass access controls, and Chinese chunks display their source text without storing a duplicate translation.

The parsers keep only the remote task reference needed for resume and the installed Bundle metadata. FOCUS adds no capture adapters, parser receipts, source revision history, event ledger, compatibility model, or derived knowledge index for this extension.

ADR-0003 supersedes this ADR's second-authorization requirement and permits explicit, source-anchored Topic Synthesis without introducing a derived knowledge index.
