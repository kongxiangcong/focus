"""Read-only snapshot of the two local release acceptance hosts and artifacts."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect():
    reports = {}
    for backend, port in [('codex', 8875), ('deepseek', 8876)]:
        values = {}
        for key, route in [('window', '/reader/window'), ('batches', '/library/batches')]:
            with urlopen(f'http://127.0.0.1:{port}{route}', timeout=10) as response:
                values[key] = json.load(response)['value']
        (ROOT / backend / 'final-snapshot.json').write_text(
            json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
        window = values['window']
        sources = {}
        for source in sorted((ROOT / backend / 'kb/sources').iterdir()):
            if not source.is_dir():
                continue
            files = {p.relative_to(source).as_posix(): digest(p)
                     for p in sorted(source.rglob('*')) if p.is_file()}
            sources[source.name] = {'files': files,
                'preparation': window.get('preparations', {}).get(source.name)}
        reports[backend] = {
            'batches': [{'status': batch['status'], 'items': [
                {key: item.get(key) for key in ['itemId', 'fileName', 'status', 'sourceId', 'error', 'blog']}
                for item in batch['items']]} for batch in values['batches']],
            'sources': sources,
            'selected': {key: (window.get('current') or {}).get(key)
                         for key in ['sourceId', 'planId', 'chunkId', 'index', 'total']},
            'selectedNotes': len(window.get('sourceNotes', [])),
            'selectedProgress': [{key: entry.get(key) for key in
                ['progress_id', 'source_id', 'plan_id', 'chunk_id', 'operation', 'status']}
                for entry in window.get('readingProgress', [])],
            'agentStatus': (window.get('agent', {}).get('run') or {}).get('status')}
    baseline = json.loads((ROOT.parent / '05-release/baseline.json').read_text(encoding='utf-8'))
    reports['originalDirtyPreserved'] = all(
        digest(Path(item['path'])) == item['sha256'] for item in baseline['dirty'])
    (ROOT / 'final-summary.json').write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({name: {'batches': data['batches'],
        'preparations': {s: d['preparation'] for s, d in data['sources'].items()},
        'selected': data['selected'], 'selectedNotes': data['selectedNotes'],
        'selectedProgressCount': len(data['selectedProgress']), 'agentStatus': data['agentStatus']}
        if isinstance(data, dict) else data for name, data in reports.items()}, ensure_ascii=False))


if __name__ == '__main__':
    collect()
