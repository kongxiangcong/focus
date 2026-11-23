"""Run the PDF/translation position browser test against the formal Host."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reading_fixture import ReadingFixture
from workspace_fixture import publish_workspace
from core.article_blog import bundle_fingerprint
from core.pdf_layout import project_pdf_layout
from core.source_ir import build_source_ir, publish_source_ir
from host.server import Server
from host.workbench import Workbench


def configure_paper(fixture):
    workspace, source, plan = fixture._workspace()
    bundle = source / 'parser-bundle'
    paper = PdfWriter()
    pages = (
        ('The alias address keeps source order.', .3),
        ('The array improves throughput.', .9),
    )
    layout = []
    for index, (text, top) in enumerate(pages):
        sheet = paper.add_blank_page(600, 1200)
        drawings = f'BT /F1 16 Tf 60 {1200 * (1 - top) - 18} Td ({text}) Tj ET'
        if index == 1:
            drawings += (' 60 650 480 180 re S 60 740 m 540 740 l S 300 650 m 300 830 l S'
                         ' BT /F1 16 Tf 60 498 Td (The alias address keeps source order.) Tj ET')
        sheet[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({
            NameObject('/F1'): DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})})})
        stream = DecodedStreamObject()
        stream.set_data(drawings.encode())
        sheet.replace_contents(stream)
        layout.append({'page_idx': index, 'blocks': [{'index': 0, 'type': 'text', 'content': text,
            'bbox': [.1, top, .9, top + .04]}]})
    paper.write(bundle / 'source.pdf')
    (bundle / 'mineru').mkdir()
    (bundle / 'mineru/middle_json.json').write_text(json.dumps({'pages': layout}), encoding='utf-8')
    markdown = (bundle / 'content.md').read_text(encoding='utf-8')
    ir = build_source_ir(bundle, markdown, source_kind='paper_pdf')
    method = next(block for block in ir['blocks'] if block['markdown'] == pages[0][0])
    regions = method['anchors']['pdf']['regions']
    regions.append({**regions[0], 'page_index': 1, 'bboxes': [[.1, .57, .9, .61]], 'raw_block_ref': '1-1'})
    ir['layout_version'] = project_pdf_layout(bundle, ir, markdown)['version']
    publish_source_ir(bundle, ir)
    provenance_file = plan / 'provenance.json'
    provenance = json.loads(provenance_file.read_text(encoding='utf-8'))
    provenance['bundle'] = bundle_fingerprint(bundle)
    provenance_file.write_text(json.dumps(provenance), encoding='utf-8')
    for index, title in enumerate(('实验方法', '实现细节', '实验结果'), start=1):
        record_file = plan / f'records/chunk-{index:03}.json'
        record = json.loads(record_file.read_text(encoding='utf-8'))
        record['translation'] = '\n\n'.join(f'{title}，第 {n} 段。' for n in range(1, 23))
        record_file.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    fixture.seal_preparation(workspace)
    publish_workspace(workspace)
    return workspace


def main():
    fixture = ReadingFixture()
    fixture.setUp()
    try:
        workspace = configure_paper(fixture)
        app = Workbench(workspace=workspace, settings_path=fixture.root / 'browser-settings.json')
        try:
            opened = app.host.open_prepared_reading('fixture-paper', request_id='browser-paper-position-open')
            chunk = opened['navigationCurrent']
            position = {'source_id': chunk['sourceId'], 'plan_id': chunk['planId'], 'chunk_id': chunk['chunkId']}
            core = app.host.reading_app.core
            started = core.start_body(**position, reading_revision=opened['readingRevision'],
                                      request_id='browser-paper-position-start')
            core.continue_reading(**position, reading_revision=started['reading_revision'],
                                  request_id='browser-paper-position-continue')
            with Server(('127.0.0.1', 0), app) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    return subprocess.run(['node', str(Path(__file__).with_suffix('.mjs'))],
                                          env={**os.environ, 'FOCUS_BROWSER_PORT': str(server.server_port)}).returncode
                finally:
                    server.shutdown()
                    worker.join()
        finally:
            app.close()
    finally:
        fixture.tearDown()


if __name__ == '__main__':
    sys.exit(main())
