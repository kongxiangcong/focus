#!/usr/bin/env python3
"""Read-only snapshot of declared reference files and their own Git metadata.

Prints JSON only. Does not execute source, fetch remotes, install dependencies,
write files, or certify UI correctness. A parent repository's HEAD is not a
reference commit. Python 3.10+ standard library; Git metadata is optional.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import stat
import subprocess
from typing import Any

ALLOWED_SUFFIXES = {'.md', '.txt', '.css', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs',
                    '.json', '.yaml', '.yml', '.html', '.htm'}
ALLOWED_NAMES = {'LICENSE', 'LICENCE', 'NOTICE', 'COPYING', 'README'}
MAX_BYTES = 8 * 1024 * 1024


def _git(root: Path, *args: str) -> tuple[int, str]:
    env = dict(os.environ)
    for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        env.pop(key, None)
    env['GIT_OPTIONAL_LOCKS'] = '0'
    env['GIT_TERMINAL_PROMPT'] = '0'
    try:
        result = subprocess.run(
            ['git', '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
             '-c', 'core.quotePath=false', '-C', str(root), *args],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            env=env, check=False, timeout=10,
        )
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ''


def git_metadata(root: Path) -> dict[str, Any]:
    code, top = _git(root, 'rev-parse', '--show-toplevel')
    if code or not top:
        return {'kind': 'directory_snapshot', 'own_head': None,
                'dirty': None, 'reason': 'No readable Git root; use declared-file hashes.'}
    if Path(top).resolve() != root.resolve():
        return {'kind': 'directory_snapshot', 'enclosing_git_root': top,
                'own_head': None, 'dirty': None,
                'reason': 'Reference is not its own Git root; parent HEAD is not attributed.'}
    hcode, head = _git(root, 'rev-parse', '--verify', 'HEAD')
    scode, status = _git(root, 'status', '--porcelain=v1', '--untracked-files=normal')
    bcode, branch = _git(root, 'symbolic-ref', '--quiet', '--short', 'HEAD')
    return {'kind': 'git_repository', 'git_root': top,
            'own_head': head if hcode == 0 else None,
            'branch': branch if bcode == 0 else None,
            'dirty': bool(status) if scode == 0 else None,
            'status_porcelain': status.splitlines() if scode == 0 else [],
            'head_read': 'PASS' if hcode == 0 else 'NOT_RUN',
            'status_read': 'PASS' if scode == 0 else 'NOT_RUN'}


def inspect_file(root: Path, name: str) -> dict[str, Any]:
    base: dict[str, Any] = {'path': name}
    rel = Path(name)
    if not name or rel.is_absolute() or PureWindowsPath(name).drive or '..' in rel.parts or '\\' in name:
        return {**base, 'status': 'FAIL', 'reason': 'Expected a relative non-escaping path.'}
    if any(part == '.git' or part.startswith('.env') for part in rel.parts):
        return {**base, 'status': 'FAIL', 'reason': 'VCS internals and environment secrets are not reference files.'}
    if rel.suffix.lower() not in ALLOWED_SUFFIXES and rel.name.upper() not in ALLOWED_NAMES:
        return {**base, 'status': 'FAIL', 'reason': 'Only declared text/source files are supported; no binary assets.'}
    try:
        path = (root / rel).resolve(strict=True)
        if not path.is_relative_to(root.resolve()):
            return {**base, 'status': 'FAIL', 'reason': 'Resolved path escapes the reference root.'}
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            return {**base, 'status': 'FAIL', 'reason': 'Not a regular file.'}
        if before.st_size > MAX_BYTES:
            return {**base, 'status': 'FAIL', 'reason': f'Exceeds declared-file limit ({MAX_BYTES} bytes).'}
        with path.open('rb') as handle:
            content = handle.read(MAX_BYTES + 1)
        after = path.stat()
        if len(content) > MAX_BYTES or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            return {**base, 'status': 'FAIL', 'reason': 'File changed during snapshot or exceeded size limit.'}
        if b'\0' in content:
            return {**base, 'status': 'FAIL', 'reason': 'Binary or unsupported text encoding (NUL bytes).'}
        return {**base, 'status': 'PASS', 'bytes': len(content),
                'sha256': hashlib.sha256(content).hexdigest()}
    except (OSError, RuntimeError, ValueError) as exc:
        return {**base, 'status': 'FAIL', 'reason': f'{type(exc).__name__}: file unavailable or invalid.'}


def collect(reference: Path, files: list[str]) -> dict[str, Any]:
    root = reference.expanduser().resolve()
    record: dict[str, Any] = {
        'schema_version': '1', 'created_at': datetime.now(timezone.utc).isoformat(),
        'reference_root': str(root), 'read_only': True,
        'scope': 'Declared-file hashes and optional own-repository metadata only; not a code/visual/license audit.',
        'files': [],
    }
    if not root.is_dir():
        return {**record, 'status': 'FAIL', 'error': 'Reference directory is unavailable.',
                'vcs': {'kind': 'unavailable', 'own_head': None}}
    record['vcs'] = git_metadata(root)
    # Retain one record per declared path; never silently expand to the entire tree.
    record['files'] = [inspect_file(root, f) for f in dict.fromkeys(files)]
    record['status'] = 'PASS' if record['files'] and all(f['status'] == 'PASS' for f in record['files']) else 'FAIL'
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True, help='Local reference root; never updated.')
    parser.add_argument('--files', nargs='+', default=['README.md', 'LICENSE', 'package.json'],
                        help='Existing relative text/source paths, e.g. docs/README.md. No globs.')
    args = parser.parse_args()
    try:
        result = collect(args.reference, args.files)
    except (OSError, RuntimeError, ValueError) as exc:
        result = {'status': 'FAIL', 'read_only': True, 'error': f'{type(exc).__name__}: invalid reference.'}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
