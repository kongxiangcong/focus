"""Recheck retained Stage 5 evidence and isolate the Node dependency.

Run from the repository root with the repository Python. This reads retained
assets, restores this process's PATH, and prints JSON without modifying assets.
It is not a clean-install or real-Runtime acceptance runner.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path('.agents').resolve()))
from core.html_article import extract_article
from core.reading_workspace import WorkspaceError, _validate_parser_bundle


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    root = Path('.scratch/focus-v02-stage5/live-20260926')
    inputs = json.loads((root / 'inputs.json').read_text(encoding='utf-8'))
    input_audit = [
        {'file': item['file'], 'exists': (root / 'inputs' / item['file']).is_file(),
         'sha256Matches': sha256(root / 'inputs' / item['file']) == item['sha256']}
        for item in inputs
    ]
    source = root / 'inputs/functional-programming.html'
    body, metadata = extract_article(source)
    normal = {'status': 'passed', 'title': metadata['title'], 'bodyCharacters': len(body.get_text())}
    original_path = os.environ.get('PATH')
    try:
        os.environ['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        if shutil.which('node') is not None:
            raise RuntimeError('Node is still discoverable; dependency isolation is invalid')
        try:
            extract_article(source)
            missing = {'status': 'unexpected-success'}
        except WorkspaceError as exc:
            missing = {'status': 'failed', 'code': exc.error_id,
                       'message': str(exc), 'cause': type(exc.__cause__).__name__}
    finally:
        if original_path is None:
            os.environ.pop('PATH', None)
        else:
            os.environ['PATH'] = original_path

    snapshot = json.loads((root / 'after-final-restart.json').read_text(encoding='utf-8'))
    sources = []
    for source_id, data in snapshot['sources'].items():
        base = root / 'knowledge-base/sources' / source_id
        _validate_parser_bundle(base / 'parser-bundle')
        sources.append({'source': source_id, 'bundleValidated': True,
                        'comparedFiles': len(data['hashes']),
                        'mismatches': [name for name, expected in data['hashes'].items()
                                       if sha256(base / name) != expected]})
    state = json.loads((root / 'knowledge-base/state.json').read_text(encoding='utf-8'))
    print(json.dumps({
        'scope': 'Read-only retained evidence audit; NOT clean installation or Stage 6B Runtime execution',
        'stage5InputHashAudit': input_audit, 'normalPath': normal, 'pathWithoutNode': missing,
        'sources': sources, 'cursorMatches': state['sources'] == snapshot['state']['sources'],
        'deletedNoImageSourceAbsent': not (root / 'knowledge-base/sources/Functional Programming HOWTO-article').exists(),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
