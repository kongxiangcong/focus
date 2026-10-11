---
status: proposed
---

# Nonblocking, lossless Source discussion summaries and latency evidence

Source discussions must not claim the main turn started before the Host has
finished session setup and historical context preparation. Show separate
connection, history compaction, waiting-for-reply and response-generation stages,
including stage elapsed time and stalled-stage guidance.

A validated summaryThrough cursor denotes a contiguous prefix of the durable
Host transcript. Context generation excludes the current user request from its
replayed history, reuses covered summaries and includes every uncovered message
exactly once. Within a conservative 48,000-character budget, the full uncovered
tail is sent without an extra model call. Only over-budget inputs trigger visible,
transactional compaction; failed/timeout batches cannot advance the durable
cursor. If it remains over budget, report a boundary failure rather than hiding
truncated history. The character threshold does not claim provider token
accounting.

After an answer completes, optional background compaction may update only a
matching discussion with the original summary and coverage cursor. A separate
candidate runner keeps foreground and speculative backend lifetimes isolated.
New questions, source selection changes, Stop, Clear, New Session and shutdown
invalidate speculative output. Cancellation of slow backend I/O is best effort;
Host locks are never held across a summary network request.

Store numeric timings for send, session setup, summary start/end, turn submit,
turn ack, first response content, completion, batch count, and input character
count. Browser first-paint evidence uses a separate event and makes no
uncalibrated cross-machine timing claim. Do not store private input text,
credentials, or model reasoning as timing evidence. Backend/model selection and
Source authority are unchanged.
