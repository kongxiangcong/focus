---
status: accepted
---

# Select the PDF parser on the FOCUS backend server

PDF ingestion in both the web Inbox and `article-parser` CLI defaults to `FOCUS_PDF_PARSER=auto`. Probe the running local MinerU HTTP V1 server with a bounded timeout, check its 4.0.8 version, file upload and ZIP capabilities, and Standard tier. Use it whenever available without cloud credentials or upload. Only a confirmed absent or incompatible local service permits mineru.net precision v4, and then `MINERU_API_TOKEN` is mandatory. A starting, busy or temporarily unreachable service is retried without cloud fallback. `FOCUS_PDF_PARSER=local-mineru|cloud` remains a diagnostic override. The browser's operating system is irrelevant.

Pin backend, nonsecret backend settings and task reference in the task checkpoint before continuing. A queued local job remains local; failures, timeout, cancellation and restart must resume its original reference, with no automatic cross-backend submission. An ambiguous POST response is reported as unresolved instead of silently submitting again. Local Standard `tier` and `ocr_mode` map to V1, while remote `model_version`, language and OCR map only to mineru.net v4. Both normalize Markdown, original bytes, figures, provenance and available structured model evidence into the Core-validated Parser Bundle. Already registered originals reuse their Source; HTML stays on local Readability.

The local V1 service may lose its in-memory job index on service restart. Persisting a reference in FOCUS does not reconstruct a missing server-side job; report the missing task for operator reconciliation rather than switching providers.
