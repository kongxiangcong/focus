---
status: accepted
---

# Bind Inbox confirmation to the available processing scope

The v0.2 Inbox stores a selected file without authorizing external processing. Explicit confirmation identifies the services, purpose and scope: the complete product covers parsing followed by blog generation in one confirmation, while stage 1 authorizes ingestion only. Bundle publication completes ingestion independently of blog success. Questions, intensive reading and Continue Reading remain separately triggered.

This decision replaces the immediate-processing authorization of ADR 0008/0009 for the new Inbox entry point and the upload-success dependency on planning and full preparation in ADR 0010 for the new ingestion flow. ADR 0003's authorization for an explicit direct Parser invocation is unchanged. One confirmation avoids repetitive prompts for a declared workflow without granting permission for unrelated reading actions. This records the agreed target behavior, not implementation or acceptance evidence.
