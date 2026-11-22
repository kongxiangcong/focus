"""PDF upload, shared translations and version-bound layout evidence."""
import json
import tempfile
from contextlib import closing
import unittest
import zipfile
from pathlib import Path

from pypdf import PdfWriter

from workspace_fixture import HostService
from core.ingestion import persist_candidate_result
from core.mineru import _normalize
from core.pdf_layout import align, layout
from core.source_reading import SourceReading
from test_blog_host import ControlledBlogRuntime, ParserDouble
from test_stage4_reading import PlanningRuntime


def page(number, *blocks):
    return {'page_idx': number, 'blocks': [
        {'index': index, 'type': 'text', 'content': [{'type': 'text', 'content': text}], 'bbox': bbox}
        for index, (text, bbox) in enumerate(blocks)]}


class IndexedParser(ParserDouble):
    def parse(self, source, candidate, **kwargs):
        result = super().parse(source, candidate, **kwargs)
        (candidate / 'mineru').mkdir()
        pages = [page(0, ('The workload stalls on the interconnect.', [0.1, 0.2, 0.45, 0.3])),
                 page(1, ('Table 1 reports throughput for every baseline.', [0.53, 0.2, 0.9, 0.35]))]
        (candidate / 'mineru/middle_json.json').write_text(json.dumps({'pages': pages}))
        return result


class ArchivedParser(ParserDouble):
    def __init__(self, artifact, payload, markdown):
        self.artifact, self.payload, self.markdown = artifact, payload, markdown

    def parse(self, source, candidate, **kwargs):
        archive = candidate.parent / 'fixture.zip'
        with zipfile.ZipFile(archive, 'w') as zip_file:
            zip_file.writestr('paper/full.md', self.markdown)
            zip_file.writestr('paper/' + self.artifact, json.dumps(self.payload))
        _normalize(source, archive, candidate, 'fixture', 'vlm', 'en')
        result = {'title': 'Fixture Paper', 'short_name': 'Fixture Paper'}
        persist_candidate_result(candidate, result)
        return result


def reading_runtime():
    return PlanningRuntime({'glossary': [], 'chunks': [
        {'section_path': ['Fixture Paper', section], 'source_lines': lines, 'images': images}
        for section, lines, images in [('1 Introduction', [1, 6], []), ('2 Method', [7, 12], ['images/image-001.png']),
                                      ('3 Experiments', [13, 15], [])]]})


class PdfReadingTests(unittest.TestCase):
    def upload_archive(self, artifact, payload, text):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        host = self.enterContext(closing(HostService(
            root / 'workspace', root / 'host', ingestion_parser=ArchivedParser(artifact, payload, text),
            blog_runtime=ControlledBlogRuntime())))
        pdf = root / 'paper.pdf'
        writer = PdfWriter()
        writer.add_blank_page(600, 800).rotate(90)
        writer.write(pdf)
        item = host.inbox_stage_file(pdf)
        batch = host.batch_start([item['item_id']], request_id='fixture-upload', generate_blog=False)
        host.batch_workers[batch['batchId']].join(15)
        source_id = host.batch_list()[0]['items'][0]['sourceId']
        return host, source_id

    def test_new_pdf_publishes_reproducible_source_ir_and_signed_canonical_text(self):
        markdown = '# Paper\n\n## Results\n\n**Exact result.**\n\nNext paragraph.\n'
        payload = {'coordinate_space': 'normalized_unrotated_top_left', 'pages': [page(
            0, ('Next paragraph.', None), ('Exact result.', None),
        )]}
        payload['pages'][0]['blocks'][1]['bboxes'] = [[0.1, 0.1, 0.2, 0.2], [0.3, 0.3, 0.4, 0.4]]
        host, sid = self.upload_archive('paper_middle.json', payload, markdown.replace('\n', '\r\n'))
        bundle = host.workspace / 'sources' / sid / 'parser-bundle'
        ir = json.loads((bundle / 'source-ir.json').read_text(encoding='utf-8'))
        from core.source_ir import IRSerializer
        self.assertEqual(markdown.encode(), (bundle / 'content.md').read_bytes())
        self.assertEqual([markdown, markdown], [IRSerializer.markdown(ir), IRSerializer.markdown(ir)])
        self.assertEqual((1, 'paper_pdf'), (ir['ir_version'], ir['source_kind']))
        document = host.source_document(sid)
        self.assertEqual(document['bundleVersion'], ir['bundle_version'])
        self.assertEqual(document['pdf']['version'], ir['layout_version'])
        self.assertEqual(90, ir['pages'][0]['rotation'])
        paper, results = ir['sections']
        self.assertIsNone(paper['parent_id'])
        self.assertEqual(paper['section_id'], results['parent_id'])
        exact = next(block for block in ir['blocks'] if block['markdown'] == '**Exact result.**')
        self.assertEqual('Exact result.', exact['plain_text'])
        self.assertEqual([5, 5], exact['anchors']['markdown']['source_lines'])
        span = exact['anchors']['markdown']['char_span']
        self.assertEqual('**Exact result.**', markdown[span['start']:span['end']])
        self.assertEqual(2, len(exact['anchors']['pdf']['regions'][0]['bboxes']))
        scope = host.discussion_app.bind(source_id=sid, request_id='cite-new-ir', content='results')
        quote = '**Exact result.**\n\nNext paragraph.'
        citation = SourceReading(host.workspace).cite(scope, {'start': 5, 'end': 7, 'quote': quote,
            'block_ids': [exact['block_id'], ir['blocks'][-1]['block_id']]})
        self.assertEqual(quote, citation['quote']['exact'])
        self.assertEqual(document['pdf']['version'], citation['layoutVersion'])
        self.assertEqual(2, len(citation['pdfRegions'][0]['bboxes']))

    def test_prefixed_middle_archive_binds_all_rotated_boxes_to_the_original(self):
        payload = {'coordinate_space': 'normalized_unrotated_top_left', 'pages': [page(
            0, ('Two column result.', None),
        )]}
        block = payload['pages'][0]['blocks'][0]
        block['bboxes'] = [[0.125, 0.125, 0.375, 0.25], [0.625, 0.5, 0.875, 0.625]]
        host, sid = self.upload_archive('paper_middle.json', payload, 'Two column result.\n')
        doc = host.source_document(sid)
        self.assertEqual('Two column result.\n', doc['markdown'])
        self.assertEqual([{'page': 1, 'width': 800, 'height': 600, 'rotation': 90}], doc['pdf']['pages'])
        self.assertEqual([[0.75, 0.125, 0.875, 0.375], [0.375, 0.625, 0.5, 0.875]],
                         doc['pdf']['blocks'][0]['bboxes'])

        bundle = host.workspace / 'sources' / sid / 'parser-bundle'
        path = bundle / 'source-ir.json'
        ir = json.loads(path.read_text(encoding='utf-8'))
        ir['blocks'][0]['anchors']['pdf']['regions'][0]['bboxes'][1][0] = 0.25
        path.write_text(json.dumps(ir), encoding='utf-8')
        changed = host.source_document(sid)
        self.assertEqual(doc['bundleVersion'], changed['bundleVersion'])
        self.assertNotEqual(doc['pdf']['version'], changed['pdf']['version'])

        # Historical Bundles still derive their layout from verifiable parser assets.
        path.unlink()
        old = host.source_document(sid)
        block['bboxes'][1][3] = 0.75
        (bundle / 'mineru' / 'middle_json.json').write_text(json.dumps(payload), encoding='utf-8')
        changed_legacy = host.source_document(sid)
        self.assertNotEqual(old['pdf']['version'], changed_legacy['pdf']['version'])
        self.assertFalse(path.exists())

    def test_incompatible_middle_geometry_still_locates_the_independent_page(self):
        payload = {'pages': [page(
            0, ('Original quote.', [0.125, 0.125, 0.375, 0.25]),
            ('No declared coordinate contract.', [0.1, 0.5, 0.3, 0.6]),
            ('No reference dimensions.', [100, 150, 300, 250]),
            ('Out of bounds.', [0.1, 0.7, 1.1, 0.8]),
        )]}
        bad_page = payload['pages'][0]
        bad_page['rotation'] = 0
        bad_page['blocks'][1]['coordinate_space'] = 'unknown'
        bad_page['blocks'][2]['coordinate_space'] = 'page_unrotated_top_left'
        host, sid = self.upload_archive('middle_json.json', payload, '\n\n'.join(
            [block['content'][0]['content'] for block in bad_page['blocks']]
        ))
        document = host.source_document(sid)
        self.assertEqual([(1, None)] * 4, [(block['page'], block['bbox']) for block in document['pdf']['blocks']])

    def test_content_lists_align_in_the_display_coordinate_space(self):
        samples = (
            ('paper_content_list.json', [{'type': 'text', 'page_idx': 0, 'text': 'Quoted result.',
                                          'bbox': [250, 125, 750, 500]}]),
            ('paper_content_list_v2.json', [[{'type': 'paragraph', 'bbox': [250, 125, 750, 500],
                                             'content': {'paragraph_content': [
                                                 {'type': 'text', 'content': 'Quoted result.'},
                                             ]}}]]),
            ('paper_middle.json', {'_backend': 'vlm', 'pdf_info': [{
                'page_idx': 0, 'page_size': [800, 600], 'para_blocks': [{
                    'type': 'text', 'bbox': [200, 75, 600, 300],
                    'lines': [{'spans': [{'type': 'text', 'content': 'Quoted result.'}]}],
                }],
            }]}),
        )
        for artifact, payload in samples:
            with self.subTest(artifact=artifact):
                host, sid = self.upload_archive(artifact, payload, 'Quoted result.')
                doc = host.source_document(sid)
                self.assertEqual([(1, [0.25, 0.125, 0.75, 0.5])],
                                 [(block['page'], block['bbox']) for block in doc['pdf']['blocks']])

    def test_page_column_offsets_and_conservative_fallback(self):
        md = 'Left: shared term. Right: shared term.\n\nTable continues\non another page.'
        blocks = align(md, [page(0, ('Left: shared term.', [0, 0, .4, .2]), ('Right: shared term.', [.5, 0, 1, .2]),
                                     ('Table continues', [0, .8, 1, 1])),
                            page(1, ('on another page.', None), ('absent OCR text', [0, 0, 1, 1]))])
        self.assertEqual(['0-0', '0-1', '0-2', '1-0'], [b['blockId'] for b in blocks])
        self.assertEqual('Right: shared term.', md[slice(*blocks[1]['offsets'])])
        self.assertEqual([4, 4], blocks[-1]['sourceLines'])
        self.assertIsNone(blocks[-1]['bbox'])
        self.assertEqual([], align('same\nsame', [page(0, ('same', None))]))

    def test_one_upload_produces_shared_plan_and_versioned_evidence(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        runtime = reading_runtime()
        host = HostService(root / 'workspace', root / 'host', ingestion_parser=IndexedParser(),
                           blog_runtime=ControlledBlogRuntime(), reading_runtime=runtime)
        self.enterContext(closing(host))
        original = root / 'paper.pdf'
        original.write_bytes(b'%PDF example')
        item = host.inbox_stage_file(original)
        batch = host.batch_start([item['item_id']], request_id='one-upload', prepare_reading=True)
        host.batch_workers[batch['batchId']].join(15)
        status = host.batch_list()[0]
        sid = status['items'][0]['sourceId']
        document = host.source_document(sid)
        self.assertEqual('ready', document['translation']['status'], host.reading_app.status(sid))
        self.assertEqual('completed', status['status'])
        self.assertEqual(3, runtime.calls.count('translate'))
        self.assertTrue(all(c['text'] == '已准备的译文' for c in document['translation']['chunks']))
        self.assertEqual(['1-0'], document['translation']['chunks'][-1]['blockIds'])
        self.assertIsNone(host.reading_app.status(sid)['selected_plan_id'])
        scope = host.discussion_app.bind(source_id=sid, request_id='cite-test-pdf', content='实验')
        citation = SourceReading(host.workspace).cite(scope, {'start': 15, 'end': 15, 'quote': 'throughput'})
        self.assertEqual(['1-0'], citation['blockIds'])
        self.assertEqual(document['pdf']['version'], citation['layoutVersion'])
        host.batch_start([item['item_id']], request_id='one-upload', prepare_reading=True)
        self.assertEqual(3, runtime.calls.count('translate'))
        bundle = host.workspace / 'sources' / sid / 'parser-bundle'
        (bundle / 'source.pdf').write_bytes(b'%PDF repaginated')
        self.assertNotEqual(citation['layoutVersion'], layout(bundle)['version'])
        self.assertEqual([], host.source_document(sid)['pdf']['blocks'])
        current = SourceReading(host.workspace).cite(scope, {'start': 15, 'end': 15, 'quote': 'throughput'})
        self.assertEqual([], current['pdfRegions'])
        self.assertEqual(citation['bundleVersion'], current['bundleVersion'])

    def test_repeated_paragraphs_and_split_table_wrappers(self):
        pages = [page(0, ('Repeated paragraph', [0, 0, .4, .3]), ('Repeated paragraph', [.5, 0, 1, .3]))]
        blocks = align('Repeated paragraph\n\nRepeated paragraph', pages)
        self.assertEqual([[1, 1], [3, 3]], [b['sourceLines'] for b in blocks])
        rows = ['<tr><td>A</td></tr>', '<tr><td>B</td></tr>']
        pages = [{'page_idx': n, 'blocks': [{'type': 'table', 'index': 0, 'content': [
            {'type': 'table_body', 'content': '<table>' + row + '</table>'}]}]} for n, row in enumerate(rows)]
        blocks = align('<table>\n' + '\n'.join(rows) + '\n</table>', pages)
        self.assertEqual([(1, [2, 2]), (2, [3, 3])], [(b['page'], b['sourceLines']) for b in blocks])

    def test_translation_retry_keeps_original_and_completed_blog(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        runtime = reading_runtime()
        translate = runtime.translate
        def unavailable(**kwargs):
            raise RuntimeError('translation offline')
        runtime.translate = unavailable
        blog = ControlledBlogRuntime()
        host = self.enterContext(closing(HostService(root / 'workspace', root / 'host', ingestion_parser=IndexedParser(),
                                                     reading_runtime=runtime, blog_runtime=blog)))
        pdf = root / 'paper.pdf'
        pdf.write_bytes(b'%PDF retry')
        item = host.inbox_stage_file(pdf)
        batch = host.batch_start([item['item_id']], request_id='first-upload', prepare_reading=True)
        host.batch_workers[batch['batchId']].join(15)
        first = host.batch_list()[0]
        self.assertEqual('partial', first['status'])
        source = first['items'][0]['sourceId']
        self.assertEqual('failed', host.source_document(source)['translation']['status'])
        calls = list(blog.calls)
        runtime.translate = translate
        host.batch_control(batch['batchId'], 'retry-item', item_id=item['item_id'], request_id='retry-translation')
        host.batch_workers[batch['batchId']].join(15)
        self.assertEqual('ready', host.source_document(source)['translation']['status'])
        self.assertEqual('completed', host.batch_list()[0]['status'])
        self.assertEqual(calls, blog.calls)
