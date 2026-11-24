"""Exercise bilingual reading in the built workbench against the formal Host."""
from contextlib import closing
from functools import partial
import json
import os
from pathlib import Path
from shutil import copytree
import subprocess
import sys
import threading
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reading_fixture import ReadingFixture
from pdf_evidence_browser import CitationRuntime
from test_stage4_reading import ReadingRuntimeDouble, enter_body
from workspace_fixture import publish_workspace
from core.article_blog import bundle_fingerprint
from core.source_ir import build_source_ir, publish_source_ir
from host.server import Server
from host.workbench import Workbench


class BilingualRuntime(ReadingRuntimeDouble):
    def opening(self, **kwargs):
        return {'guide': '用来核对阅读位置。', 'structure': [
            {'id': 'root', 'parentId': None, 'title': '双语位置', 'sourceLines': [1, 80]}]}

    def translate_document(self, *, segments, **kwargs):
        self.calls.append('document')
        return [{'id': segment['id'], 'text': segment['source_text']
                 .replace('Bilingual Position', '双语位置')
                 .replace('Section', '小节')
                 .replace('Reading passage', '阅读段落')
                 .replace('with context to read.', '用来核对阅读位置。')}
                for segment in segments]


def configure_source(source, source_id, title, *, chinese=False):
    plan = source / 'reading/plans/plan-001'
    passages = ['# ' + title]
    chunks = []
    for number in range(1, 4):
        start = len(passages) * 2 + 1 if number > 1 else 1
        section = f'原文小节 {number}' if chinese else f'Section {number}'
        passages.append('## ' + section)
        for index in range(number * 12 - 11, number * 12 + 1):
            passages.append(f'中文原文第 {index} 段。' if chinese else f'Reading passage {index} with context to read.')
        chunks.append({'chunk_id': f'chunk-00{number}', 'index': number,
                       'section_path': [title, section],
                       'source_lines': [start, len(passages) * 2], 'images': []})
    markdown = '\n\n'.join(passages) + '\n\n'
    bundle = source / 'parser-bundle'
    (bundle / 'source.pdf').unlink()
    (bundle / 'images' / 'image-001.png').unlink()
    for name in ('content.md', 'source.md'):
        (bundle / name).write_text(markdown, encoding='utf-8')
    ledger = source / 'source.yaml'
    ledger.write_text(json.dumps({**json.loads(ledger.read_text()), 'source_kind': 'article_markdown',
        'source_id': source_id, 'identity': f'fixture:{source_id}', 'title': title}), encoding='utf-8')
    metadata = bundle / 'metadata.json'
    metadata.write_text(json.dumps({**json.loads(metadata.read_text()), 'source_kind': 'article_markdown',
        'language': 'zh' if chinese else 'en', 'parser': 'markdown-import'}), encoding='utf-8')
    publish_source_ir(bundle, build_source_ir(bundle, markdown, source_kind='article_markdown'))
    (plan / 'chunks.jsonl').write_text(''.join(json.dumps(chunk) + '\n' for chunk in chunks), encoding='utf-8')
    provenance = plan / 'provenance.json'
    provenance.write_text(json.dumps({**json.loads(provenance.read_text()), 'source_id': source_id,
        'bundle': bundle_fingerprint(bundle)}), encoding='utf-8')


def configure(fixture):
    workspace, source, _ = fixture._workspace()
    chinese = source.parent / 'fixture-chinese-article'
    copytree(source, chinese)
    configure_source(source, source.name, 'Bilingual Position')
    configure_source(chinese, chinese.name, '中文原文示例', chinese=True)
    state_path = workspace / 'state.json'
    state = json.loads(state_path.read_text())
    state['sources'][chinese.name] = dict(state['sources'][source.name])
    state_path.write_text(json.dumps(state), encoding='utf-8')
    publish_workspace(workspace)
    return workspace


def main():
    fixture = ReadingFixture()
    fixture.setUp()
    try:
        runtime = BilingualRuntime()
        with closing(Workbench(workspace=configure(fixture), settings_path=fixture.root / 'settings.json',
                               reading_runtime=runtime, backend_factory=partial(CitationRuntime, requests={
                                   '核对双语证据': [{'lines': [39, 39], 'quote': 'Reading passage 17'}],
                               }))) as workbench:
            host = workbench.host
            assert host is not None, workbench.status()
            source_id = 'fixture-paper'
            for candidate, expected in [(source_id, 'ready'), ('fixture-chinese-article', 'not_applicable')]:
                host.prepare_reading(candidate, request_id=uuid4().hex)
                worker = host.reading_workers.get(candidate)
                if worker:
                    worker.join(15)
                assert host.source_document(candidate)['translation']['status'] == expected, host.snapshot()
            translations = runtime.calls.count('document')
            assert translations > 0, runtime.calls
            host.open_prepared_reading(source_id, request_id=uuid4().hex)
            view = enter_body(host)
            host.continue_cached({'receipt': {'sourceId': source_id, 'planId': 'plan-001', 'chunkId': 'chunk-001',
                'readingRevision': view['readingRevision']}, 'requestId': uuid4().hex})
            host.select_discussion_source(source_id)
            with Server(('127.0.0.1', 0), workbench) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    result = subprocess.run(['node', str(Path(__file__).with_suffix('.mjs'))],
                        env={**os.environ, 'FOCUS_BROWSER_PORT': str(server.server_port)}).returncode
                    assert runtime.calls.count('document') == translations, runtime.calls
                    return result
                finally:
                    server.shutdown()
                    worker.join()
    finally:
        fixture.tearDown()


if __name__ == '__main__':
    sys.exit(main())
