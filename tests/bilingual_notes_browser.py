"""Exercise bilingual selected notes in the built Workbench and real HTTP Host."""
from contextlib import closing
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test_stage4_reading import PlanningRuntime, enter_body
from core.library_import import import_markdown
from core.workspace_lifecycle import create_workspace
from host.server import Server
from host.workbench import Workbench


class BilingualNotesRuntime(PlanningRuntime):
    def translate_document(self, *, segments, **kwargs):
        translations = {'# Shared notes': '# 双语笔记',
                        'Repeat and **repeat😀**': '重复以及**重复😀**',
                        'Then verify both layers.': '接着验证两种语言。'}
        return [{'id': segment['id'], 'text': translations[segment['source_text']]} for segment in segments]


def main():
    with TemporaryDirectory(prefix='focus-bilingual-notes-') as temporary:
        root = Path(temporary)
        workspace = root / 'workspace'
        create_workspace(workspace)
        file = root / 'notes.md'
        file.write_text('# Shared notes\n\nRepeat and **repeat😀**\nThen verify both layers.\n', encoding='utf-8')
        runtime = BilingualNotesRuntime({'chunks': [
            {'section_path': ['Shared notes'], 'source_lines': [1, 3], 'images': []},
            {'section_path': ['Shared notes'], 'source_lines': [4, 4], 'images': []}], 'glossary': []})
        with closing(Workbench(workspace=workspace, settings_path=root / 'settings.json',
                               reading_runtime=runtime)) as app:
            host = app.host
            source = import_markdown(workspace, file, short_name='bilingual-notes', language='en')['source_id']
            host.prepare_reading(source, request_id=uuid4().hex)
            host.reading_workers[source].join(12)
            ready = host.open_prepared_reading(source, request_id=uuid4().hex)
            first = ready['navigationCurrent']
            rendered_prefix = 'Shared notes\nRepeat and '
            start = len(rendered_prefix)
            host.source_highlight_create(source, {'requestId': uuid4().hex,
                'chunk': {key: first[key] for key in ('planId', 'chunkId')}, 'layer': 'source',
                'range': {'start': start, 'end': start + 8},
                'quote': {'exact': 'repeat😀', 'prefix': '', 'suffix': ''}})
            body = enter_body(host)
            host.continue_cached({'requestId': uuid4().hex,
                'receipt': {'sourceId': source, 'planId': first['planId'], 'chunkId': first['chunkId'],
                            'readingRevision': body['readingRevision']}})
            host.select_discussion_source(source)
            with Server(('127.0.0.1', 0), app) as server:
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    return subprocess.run(['node', str(Path(__file__).with_suffix('.mjs'))], timeout=100,
                        env={**os.environ, 'FOCUS_BROWSER_PORT': str(server.server_port)}).returncode
                finally:
                    server.shutdown()
                    thread.join()


if __name__ == '__main__':
    sys.exit(main())
