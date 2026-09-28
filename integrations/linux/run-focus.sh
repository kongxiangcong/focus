#!/bin/bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$project_root"
export FOCUS_CODEX_BIN="$(.venv/bin/python -c 'from codex_cli_bin import bundled_codex_path; print(bundled_codex_path())')"
exec .venv/bin/python -m host --workspace "$project_root/knowledge-base" \
  --host-data "$project_root/.focus-host" --bind "${FOCUS_BIND:-127.0.0.1}" --port 8765
