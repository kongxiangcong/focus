# MinerU precision API contract

Use this reference when maintaining the client or diagnosing an API response. The authoritative live documentation is <https://mineru.net/apiManage/docs>.

The project intentionally uses the token-authenticated precision API, not MinerU's lightweight Agent API.

## Local-file flow

1. `POST https://mineru.net/api/v4/file-urls/batch`
   - Header: `Authorization: Bearer <token>`.
   - Body contains one `files` item with `name` and a non-secret `data_id`, plus `model_version`, `enable_formula`, `enable_table`, and `language`.
2. `PUT` the PDF bytes to the returned signed `file_urls[0]` with system `curl`, passing its config over standard input. Do not add an Authorization header or persist the signed URL or place it in process arguments.
3. Poll `GET https://mineru.net/api/v4/extract-results/batch/{batch_id}` with the Bearer token.
4. Accept only `state=done`; treat `failed` as terminal and the other documented states as pending.
5. Download `full_zip_url` into a temporary directory, reject redirects outside HTTPS, cap the download, validate it as ZIP, and extract without path traversal.
6. Project `full.md` and its referenced images into `parser-bundle/`, rewrite image links to sequential names, then discard the ZIP and extracted raw tree.

The current documented states include `waiting-file`, `pending`, `running`, `converting`, `done`, and `failed`. The ZIP normally contains `full.md`, layout/middle JSON, model JSON, content-list JSON, and image assets. Exact internal names are backend output, not this skill's stable interface.

## Security invariants

- Token only in the `MINERU_API_TOKEN` process environment.
- Never place the token in CLI arguments, files, error messages, metadata, or test fixtures.
- Never store signed upload or download URLs.
- Require HTTPS for signed uploads, downloads, and redirects; pass signed URLs to `curl` only over standard input.
- Reject archive members that are absolute, contain `..`, or escape the extraction root.
- Cap API response, ZIP download, archive member count, and expanded bytes.
- Preserve the source SHA-256 and verify the copied source.
- Keep the transient ZIP and raw extraction outside the stable parser bundle.
