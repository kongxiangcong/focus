---
status: accepted
---

# Read papers and Chinese articles through one Parser Bundle

FOCUS registers both PDF Paper Sources and Chinese Article Sources as Reading Sources. `paper-parser` uses MinerU VLM, while the peer `article-parser` uses the precision API with MinerU-HTML; both install the same minimal Parser Bundle interface consumed by `focus-map` and `focus-read`. Article Parser accepts an authorized URL fetch or, when MinerU cannot read that URL, an explicitly authorized upload of one user-saved `.html` file. It does not vary by publishing platform or bypass access controls, and Chinese chunks display their source text without storing a duplicate translation.

The parsers keep only the remote task reference needed for resume and the installed Bundle metadata. FOCUS adds no capture adapters, parser receipts, source revision history, event ledger, compatibility model, or derived knowledge index for this extension.
