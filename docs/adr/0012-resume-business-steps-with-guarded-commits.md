---
status: accepted
---

# Resume business steps with guarded Core commits

The v0.2 ingestion workflow preserves recoverable business progress instead of restarting a whole document after failure. A Run identifies the business task, a Step a recoverable part, and an attempt one execution of that Step. Polling or retrieving an existing remote task does not re-execute the Step. Valid published artifacts and usable checkpoints survive downstream failures; uncertain remote acceptance must be resolved before another submission. Transient network failures permit at most two automatic continuations before manual retry; authentication and validation failures surface directly.

Core alone publishes artifacts, requiring the expected version, request ID and a valid exclusive writer identity. A version conflict retains the candidate separately and reports the conflict without overwriting the published asset. Cancellation permanently bars the cancelled attempt from committing. An explicit continuation creates a new attempt at the last valid checkpoint; late results from the cancelled attempt cannot silently publish. A second Host cannot acquire concurrent write ownership of the same workspace.

This deliberately introduces the minimal Bundle versions, durable checkpoints and commit metadata needed by ingestion, narrowly superseding ADR 0002/0003's exclusions of those mechanisms. It does not introduce a general event platform, duplicate Core authority or a second business workflow. ADR 0003's single Source Library and sole Topic membership authority remain: topic membership changes do not rewrite or copy the Bundle. Source publication and requested Topic attachment have separate outcomes, so a failed attachment resumes without reparsing a valid Source.

These are accepted target constraints from stage 0 Q7–Q12, not evidence that the new Application or its failure handling has been implemented.
