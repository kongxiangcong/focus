"""Switch editable Reading Versions from the built Workbench against its Host."""
from contextlib import closing
from functools import partial
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilingual_position_browser import BilingualRuntime, configure
from pdf_evidence_browser import CitationRuntime
from reading_fixture import ReadingFixture
from test_stage4_reading import enter_body, with_structure
from host.server import Server
from host.workbench import Workbench


class RoundRuntime(BilingualRuntime):
    def __init__(self, workspace):
        super().__init__()
        plan = workspace / 'sources/fixture-paper/reading/plans/plan-001/chunks.jsonl'
        chunks = [json.loads(line) for line in plan.read_text().splitlines()]
        self.draft = with_structure({'chunks': [{key: chunk[key] for key in ('section_path', 'source_lines', 'images')}
                                               for chunk in chunks], 'glossary': []})

    def plan(self, **kwargs):
        self.calls.append('plan')
        return self.draft

    def translate_document(self, **kwargs):
        segments = super().translate_document(**kwargs)
        rounds = self.calls.count('plan')
        if rounds:
            prefix = {1: '重读段落', 2: '第三轮段落'}[rounds]
            return [{**segment, 'text': segment['text'].replace('阅读段落', prefix)} for segment in segments]
        return segments


def main():
    fixture = ReadingFixture()
    fixture.setUp()
    try:
        workspace = configure(fixture)
        runtime = RoundRuntime(workspace)
        quote = 'Reading passage 17'
        markdown = workspace / 'sources/fixture-paper/parser-bundle/content.md'
        line = next(index for index, text in enumerate(markdown.read_text().splitlines(), 1) if quote in text)
        with closing(Workbench(workspace=workspace, settings_path=fixture.root / 'settings.json',
                               reading_runtime=runtime, backend_factory=partial(CitationRuntime, requests={
                                   '第二轮的问题': [{'lines': [line, line], 'quote': quote}],
                               }))) as workbench:
            host = workbench.host
            source = 'fixture-paper'
            host.prepare_reading(source, request_id='browser-first-round')
            host.reading_workers[source].join(15)
            initial_batches = runtime.calls.count('document')
            assert initial_batches > 0, runtime.calls
            host.open_prepared_reading(source, request_id='browser-open-first-round')
            view = enter_body(host)
            host.continue_cached({'receipt': {'sourceId': source, 'planId': 'plan-001', 'chunkId': 'chunk-001',
                                 'readingRevision': view['readingRevision']}, 'requestId': 'browser-advance-first-round'})
            host.source_note_create(source, {'requestId': 'browser-round-note', 'kind': 'thought',
                'origin': 'user', 'content': '待复现'})
            with Server(('127.0.0.1', 0), workbench) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    result = subprocess.run(['node', str(Path(__file__).with_suffix('.mjs'))],
                        env={**os.environ, 'FOCUS_BROWSER_PORT': str(server.server_port)}).returncode
                    if result == 0:
                        assert runtime.calls.count('plan') == 2, runtime.calls
                        assert runtime.calls.count('document') == initial_batches * 3, runtime.calls
                    return result
                finally:
                    server.shutdown()
                    worker.join()
    finally:
        fixture.tearDown()


if __name__ == '__main__':
    sys.exit(main())
