"""Verify single-column originals through the built workbench and formal Host."""
import base64
from contextlib import closing
from functools import partial
import json
import os
from pathlib import Path
from shutil import copytree
import subprocess
import sys
import threading

from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reading_fixture import ReadingFixture
from pdf_evidence_browser import CitationRuntime, TranslationRuntime
from workspace_fixture import publish_workspace
from core.article_blog import bundle_fingerprint
from core.source_ir import build_source_ir, publish_source_ir
from host.server import Server
from host.workbench import Workbench

PAGE_8 = 'The eighth page contains the verified result.'
PAGE_12 = 'The twelfth page follows the wider examples.'
UNKNOWN = 'This appendix passage has no verified page placement.'
SOURCE_NAMES = {'pdf': 'fixture-paper', 'html': 'fixture-html-article',
                'markdown': 'fixture-markdown-article'}
PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jQk0AAAAASUVORK5CYII='


def configure(fixture):
    workspace, source, _ = fixture._workspace()
    bundle = source / 'parser-bundle'
    columns = '| ' + ' | '.join(['Wide heading'] * 9) + ' |'
    separator = '| ' + ' | '.join(['---'] * 9) + ' |'
    values = '| ' + ' | '.join(['Detailed table value'] * 9) + ' |'
    filler = '\n\n'.join(f'Context paragraph {i}. ' + 'This paragraph provides reading context on both screen sizes. ' * 3
                          for i in range(1, 24))
    markdown = (
        '# Single-column fixture\n\n'
        f'## Results\n\n{PAGE_8}\n\n'
        f'![Fixture figure](images/image-001.png)\n\n{columns}\n{separator}\n{values}\n\n'
        f'\x60\x60\x60text\n{"wide_code_example_" * 18}\n\x60\x60\x60\n\n'
        f'$$\n{"x_{12345}+y_{67890}+" * 22}z=1\n$$\n\n'
        f'{filler}\n\n{PAGE_12}\n\n{filler}\n\n'
        f'## Appendix\n\n{UNKNOWN}\n\n{filler}\n\n'
        '## References\n\nCanonical bibliography entry.\n'
    )
    lines = markdown.splitlines()
    (bundle / 'content.md').write_text(markdown, encoding='utf-8')
    (bundle / 'images/image-001.png').write_bytes(base64.b64decode(PNG))
    pdf = PdfWriter()
    for _ in range(12):
        pdf.add_blank_page(612, 792)
    pdf.write(bundle / 'source.pdf')
    pages = [{'page_idx': i, 'blocks': [{'index': 0, 'type': 'text', 'content': text, 'bbox': [.1, .2, .9, .3]}]}
             for i, text in [(7, PAGE_8), (11, PAGE_12)]]
    (bundle / 'mineru').mkdir()
    (bundle / 'mineru/middle_json.json').write_text(json.dumps({'pages': pages}), encoding='utf-8')
    for format, source_id in SOURCE_NAMES.items():
        kind, original = {
            'pdf': ('paper_pdf', 'source.pdf'),
            'html': ('article_html', 'source.html'),
            'markdown': ('article_markdown', 'source.md'),
        }[format]
        target = workspace / 'sources' / source_id
        if target != source:
            copytree(source, target, ignore=lambda _directory, names: set(names) & {'source.pdf', 'mineru', 'source-ir.json'})
        target_bundle = target / 'parser-bundle'
        if format == 'html':
            (target_bundle / original).write_text('<h1>Saved HTML original</h1>', encoding='utf-8')
        if format == 'markdown':
            (target_bundle / original).write_text(markdown, encoding='utf-8')
        title = f'Single column {format}'
        (target / 'source.yaml').write_text(json.dumps({'source_kind': kind, 'source_id': source_id,
            'title': title, 'short_name': title, 'identity': f'fixture:single-column:{format}'}), encoding='utf-8')
        metadata = target_bundle / 'metadata.json'
        metadata.write_text(json.dumps({**json.loads(metadata.read_text()), 'source_kind': kind, 'language': 'zh',
                                          'parser': 'markdown-import' if format == 'markdown' else 'article-parser'}), encoding='utf-8')
        publish_source_ir(target_bundle, build_source_ir(target_bundle, markdown, source_kind=kind))
        plan = target / 'reading/plans/plan-001'
        (plan / 'chunks.jsonl').write_text(json.dumps({'chunk_id': 'chunk-001', 'index': 1,
            'section_path': ['Single-column fixture'], 'source_lines': [1, len(lines)], 'images': ['images/image-001.png']}) + '\n',
            encoding='utf-8')
        (plan / 'records/chunk-001.json').write_text(json.dumps({'chunk_id': 'chunk-001', 'translation': None, 'notes': []}),
                                                    encoding='utf-8')
        provenance = plan / 'provenance.json'
        provenance.write_text(json.dumps({**json.loads(provenance.read_text()), 'source_id': source_id,
                                          'bundle': bundle_fingerprint(target_bundle)}), encoding='utf-8')
        fixture.seal_preparation(workspace, source_id=source_id)
    state_path = workspace / 'state.json'
    state = json.loads(state_path.read_text())
    state['sources'] = {source_id: {'current_plan_id': 'plan-001', 'current_chunk_id': 'chunk-001'}
                        for source_id in SOURCE_NAMES.values()}
    state_path.write_text(json.dumps(state), encoding='utf-8')
    publish_workspace(workspace)
    line = lines.index(PAGE_8) + 1
    return workspace, lines, {'核对第八页': [{'lines': [line, line], 'quote': PAGE_8}]}


def main():
    fixture = ReadingFixture()
    fixture.setUp()
    try:
        workspace, lines, citations = configure(fixture)
        with closing(Workbench(workspace=workspace, settings_path=fixture.root / 'settings.json',
                               reading_runtime=TranslationRuntime(lines, []),
                               backend_factory=partial(CitationRuntime, requests=citations))) as workbench:
            host = workbench.host
            assert host is not None, workbench.status()
            pdf = host.source_document(SOURCE_NAMES['pdf'])['pdf']
            assert {block['page'] for block in pdf['blocks']} == {8, 12}, pdf
            host.select_discussion_source(SOURCE_NAMES['pdf'])
            with Server(('127.0.0.1', 0), workbench) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    return subprocess.run(['node', str(Path(__file__).with_suffix('.mjs'))],
                                          env={**os.environ, 'FOCUS_BROWSER_PORT': str(server.server_port)}).returncode
                finally:
                    server.shutdown()
                    worker.join()
    finally:
        fixture.tearDown()


if __name__ == '__main__':
    sys.exit(main())
