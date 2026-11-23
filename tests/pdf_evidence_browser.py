"""Serve a temporary copy of the Batch B real-PDF workspace in the production Host.

Build the standalone UI, then run this file with the imported workspace path
from .scratch/evidence-backannotation-unified-ir/batch-b-acceptance.md.
Set FOCUS_BROWSER_URL to the printed origin for current_discussion_evidence_browser.mjs.
"""
from argparse import ArgumentParser
from contextlib import closing
from functools import partial
import json
from pathlib import Path
import re
from shutil import copytree
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / '.agents')]

from core.reading_application import _reference_heading
from core.reading_workspace import _source_heading_paths
from host.server import Server
from host.workbench import Workbench
from test_source_reading_http import LineCitationRuntime
from test_stage4_reading import ReadingRuntimeDouble, with_structure

SOURCE = 'Evaluating Emerging CXL-enabled Memory Pooling for HPC Systems-paper'
SCENARIO = {
    'boundaries': [96, 185, 241],
    'requests': {
        '归档回答 A': [
            {'lines': [266, 266], 'quote': 'a scalable high-bandwidth system'},
        ],
        '当前回答 B': [
            {'lines': [236, 236], 'quote': 'The performance of seven scientific applications'},
            {'lines': [318, 318], 'quote': 'On the memory underutilization'},
            {'lines': [266, 266], 'quote': 'a scalable high-bandwidth system'},
            {'lines': [266, 266], 'quote': 'a scalable high-bandwidth'},
        ],
        '当前回答 C': [
            {'lines': [266, 266], 'quote': 'high-bandwidth system'},
            {'lines': [236, 236], 'quote': 'The performance of seven scientific applications'},
        ],
    },
}


class CitationRuntime(LineCitationRuntime):
    def __init__(self, *args, requests, **kwargs):
        super().__init__(*args, answer_id=uuid4().hex, **kwargs)
        self.requests = requests

    def start_turn(self, **kwargs):
        self.label = kwargs['prompt'].splitlines()[0]
        self.answer_id = uuid4().hex
        self.markers = []
        self.citations = iter(self.requests.get(self.label, []))
        if self.label.startswith('{') and json.loads(self.label).get('task') == 'summarize_discussion':
            self.finish(json.dumps({'summary': '阅读工作区 PDF 验收'}))
        else:
            self.cite_next()

    def cite_next(self):
        request = next(self.citations, None)
        if request is None:
            self.finish(f'{self.label}。' + ' '.join(self.markers))
            return
        start, end = request['lines']
        self.call(len(self.markers) + 1, 'cite', {'start': start, 'end': end, 'quote': request['quote']})

    def send(self, reply):
        result = reply['result']
        if not result['success']:
            self.events.put({'method': 'turn/completed', 'params': {'status': 'failed', 'error': result['text']}})
            return
        self.markers.append(json.loads(result['text'])['marker'])
        self.cite_next()

    def finish(self, text):
        self.events.put({'method': 'message/completed', 'params': {'itemId': self.answer_id, 'text': text}})
        self.events.put({'method': 'turn/completed', 'params': {'status': 'completed'}})

    def interrupt(self):
        self.events.put({'method': 'turn/completed', 'params': {'status': 'interrupted'}})


class TranslationRuntime(ReadingRuntimeDouble):
    def __init__(self, lines, boundaries):
        super().__init__()
        self.lines = lines
        self.boundaries = boundaries

    def plan(self, **kwargs):
        paths = _source_heading_paths(self.lines)
        last_line = next((index - 1 for index, path in enumerate(paths, 1)
                          if path and _reference_heading(path[-1])), len(paths))
        chunks = []
        start = 1
        for end in [*(boundary for boundary in self.boundaries if boundary < last_line), last_line]:
            path = next(path for path in paths[start - 1:end] if path)
            images = re.findall(r'\((images/[^\s()]+)\)', '\n'.join(self.lines[start - 1:end]))
            chunks.append({'section_path': list(path), 'source_lines': [start, end], 'images': list(dict.fromkeys(images))})
            start = end + 1
        excluded = [[last_line + 1, len(paths)]] if last_line < len(paths) else []
        draft = with_structure({'chunks': chunks, 'glossary': [], 'excluded_ranges': excluded})
        for index, node in enumerate(draft['structure']['nodes'], 1):
            node['title'] = f'研究内容第 {index} 节'
        return draft

    def translate(self, **kwargs):
        chunk_id = kwargs['chunk']['chunk_id']
        return '\n\n'.join(f'中文验收段落 {chunk_id}，第 {index} 段。用于检查译文阅读位置。' for index in range(1, 23))

    def opening(self, **kwargs):
        return {'structure': [{'id': 'overview', 'parentId': None, 'title': '研究方法',
                               'sourceLines': [1, len(self.lines)]}], 'guide': '本文研究数据中心的内存池化。'}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    parser.add_argument('--source', default=SOURCE)
    parser.add_argument('--scenario', type=Path)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text(encoding='utf-8')) if args.scenario else SCENARIO
    with TemporaryDirectory(prefix='focus-pdf-evidence-') as scratch:
        root = Path(scratch)
        workspace = Path(copytree(args.workspace, root / 'workspace'))
        lines = (workspace / 'sources' / args.source / 'parser-bundle' / 'content.md').read_text(encoding='utf-8').splitlines()
        with closing(Workbench(workspace=workspace, settings_path=root / 'settings.json',
                               reading_runtime=TranslationRuntime(lines, scenario['boundaries']),
                               backend_factory=partial(CitationRuntime, requests=scenario['requests']))) as workbench:
            host = workbench.host
            assert host is not None, workbench.status()
            if host.source_document(args.source)['translation']['status'] != 'ready':
                host.prepare_reading(args.source, request_id=uuid4().hex)
                worker = host.reading_workers.get(args.source)
                if worker:
                    worker.join(60)
            assert host.source_document(args.source)['translation']['status'] == 'ready'
            host.select_discussion_source(args.source)
            with Server(('127.0.0.1', args.port), workbench) as server:
                print(f'http://127.0.0.1:{server.server_port}', flush=True)
                server.serve_forever()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
