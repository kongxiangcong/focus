"""Unified preparation through the production upload and reading HTTP routes."""
import threading
import time
import unittest

from test_stage4_reading import ReadingRuntimeDouble, with_structure
import test_stage5_ingestion as ingestion
from test_html_ingestion import saved_html
from core.source_markdown import MARKDOWN_IMAGE_RE


class PausedReading(ReadingRuntimeDouble):
    def __init__(self, *, fail_once=False):
        super().__init__()
        self.context_started = threading.Event()
        self.continue_context = threading.Event()
        self.check_started = threading.Event()
        self.continue_check = threading.Event()
        self.fail_once = fail_once

    def context(self, **kwargs):
        self.context_started.set()
        if not self.continue_context.wait(10):
            raise TimeoutError('Context was not released')
        return super().context(**kwargs)

    def plan(self, *, ranges, **kwargs):
        start, end = ranges[0]['source_lines']
        path = ranges[0]['heading_paths'][0]['path']
        images = list(dict.fromkeys(MARKDOWN_IMAGE_RE.findall(ranges[0]['source_text'])))
        return with_structure({'chunks': [
            {'section_path': path, 'source_lines': [start, end], 'images': images}], 'glossary': []})

    def translate_document(self, *, segments, **kwargs):
        self.calls.append('document')
        if self.fail_once:
            self.fail_once = False
            raise TimeoutError('Translation interrupted')
        dictionary = {'# Demonstration': '# 演示', 'An independent translation.': '独立译文。'}
        return [{'id': segment['id'], 'text': dictionary.get(segment['source_text'],
                  segment['source_text'].replace('Scheduling article', '调度文章').replace('Stored Paper', '论文'))}
                for segment in segments]

    def check(self, **kwargs):
        self.check_started.set()
        if not self.continue_check.wait(10):
            raise TimeoutError('Check was not released')
        return super().check(**kwargs)


class UnifiedPreparationTests(unittest.TestCase):
    setUp = ingestion.SingleIngestionTests.setUp
    tearDown = ingestion.SingleIngestionTests.tearDown
    start_host = ingestion.SingleIngestionTests.start_host
    stop_host = ingestion.SingleIngestionTests.stop_host
    request = ingestion.SingleIngestionTests.request

    def wait_ready(self, route):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            status = self.request('GET', route + '/preparation')
            if status and status['status'] != 'running':
                return status
            time.sleep(.01)
        self.fail(f'Reading preparation did not settle: {status}')

    def upload(self, name, original):
        item = self.request('POST', '/library/inbox?name=' + name, original)
        self.request('POST', '/library/batches', {'itemIds': [item['item_id']],
            'requestId': 'unified-' + name, 'generateBlog': False, 'prepareReading': True})
        self.assertTrue(self.reading.context_started.wait(8), 'An upload should start reading preparation')
        source, = self.request('GET', '/library/sources')
        return '/library/sources/' + source['sourceId']

    def use_runtime(self, runtime):
        self.stop_host()
        self.reading = runtime
        self.start_host(reading_runtime=runtime)
        self.addCleanup(runtime.continue_check.set)
        self.addCleanup(runtime.continue_context.set)

    def test_upload_publishes_mapped_translation_before_both_reading_modes_open(self):
        self.use_runtime(PausedReading())
        try:
            route = self.upload('demonstration.md', b'# Demonstration\n\nAn independent translation.\n')
            selecting = {'selection': {'workbenchId': 'test-workbench', 'generation': 1}}
            pending = self.request('POST', route + '/discuss', selecting)
            source_id = pending['source']['sourceId']
            self.assertTrue(pending['unifiedPreparation'])
            self.assertFalse(pending['preparations'][source_id]['ready'])
            original = self.request('GET', route + '/document')
            self.assertIn('An independent translation.', original['markdown'])
            self.assertEqual([], original['translation']['segments'])
            self.reading.continue_context.set()
            self.assertTrue(self.reading.check_started.wait(8))
            translated = self.request('GET', route + '/document')
            self.assertEqual('ready', translated['translation']['status'])
            heading, prose = translated['translation']['segments']
            self.assertEqual(('# 演示', '独立译文。'), (heading['text'], prose['text']))
            self.assertEqual([3, 3], prose['sourceLines'])
            self.assertEqual('block', prose['granularity'])
            self.assertEqual([translated['blocks'][1]['blockId']], prose['blockIds'])
            prep = self.request('GET', route + '/preparation')
            self.assertFalse(prep['ready'])
            self.reading.continue_check.set()
            self.assertTrue(self.wait_ready(route)['ready'])
            window = self.request('POST', route + '/open', {'requestId': 'open-prepared-source'})
            self.assertFalse(window['readingStarted'])
            self.assertEqual([], window['readingProgress'])
            self.assertEqual('独立译文。', self.request('GET', route + '/document')['translation']['segments'][1]['text'])
            self.assertEqual(1, self.reading.calls.count('document'))
            self.assertNotIn('translate', self.reading.calls)
        finally:
            self.reading.continue_context.set()
            self.reading.continue_check.set()

    def test_chinese_upload_waits_for_chunks_without_translating(self):
        self.use_runtime(PausedReading())
        try:
            route = self.upload('chinese.md', '# 论文示例\n\n这里说明研究方法。\n'.encode())
            document = self.request('GET', route + '/document')
            self.assertEqual('zh', document['language'])
            self.assertEqual('not_applicable', document['translation']['status'])
            self.assertFalse(self.request('GET', route + '/preparation')['ready'])
            self.reading.continue_context.set()
            self.assertTrue(self.reading.check_started.wait(8))
            self.assertFalse(self.request('GET', route + '/preparation')['ready'])
            self.reading.continue_check.set()
            self.assertTrue(self.wait_ready(route)['ready'])
            self.assertNotIn('translate', self.reading.calls)
            self.assertNotIn('document', self.reading.calls)
        finally:
            self.reading.continue_context.set()
            self.reading.continue_check.set()

    def test_failed_translation_can_retry_the_same_preparation(self):
        self.use_runtime(PausedReading(fail_once=True))
        try:
            route = self.upload('retry.md', b'# Demonstration\n\nAn independent translation.\n')
            self.reading.continue_context.set()
            failed = self.wait_ready(route)
            self.assertEqual('failed', failed['status'])
            self.assertFalse(failed['ready'])
            self.assertEqual([], self.request('GET', route + '/document')['translation']['segments'])
            self.request('POST', route + '/preparation/resume', {'requestId': 'retry-unified-reading'})
            self.assertTrue(self.reading.check_started.wait(8))
            self.reading.continue_check.set()
            ready = self.wait_ready(route)
            self.assertTrue(ready['ready'])
            self.assertEqual(failed['run_id'], ready['run_id'])
            self.assertEqual(failed['plan_id'], ready['plan_id'])
            self.assertEqual(['context', 'document', 'document', 'check'], self.reading.calls)
        finally:
            self.reading.continue_context.set()
            self.reading.continue_check.set()

    def test_pdf_upload_uses_the_same_readiness_gate(self):
        self.assert_upload_ready('article.pdf', b'%PDF test original')

    def test_html_upload_uses_the_same_readiness_gate(self):
        self.assert_upload_ready('article.html', saved_html(image=False).encode())

    def assert_upload_ready(self, name, original):
        runtime = PausedReading()
        runtime.continue_check.set()
        self.use_runtime(runtime)
        try:
            route = self.upload(name, original)
            self.assertFalse(self.request('GET', route + '/preparation')['ready'])
            runtime.continue_context.set()
            status = self.wait_ready(route)
            self.assertTrue(status['ready'], status.get('error'))
            self.assertEqual('ready', self.request('GET', route + '/document')['translation']['status'])
            self.assertIn('document', runtime.calls)
        finally:
            runtime.continue_context.set()


class HistoricalPreparationTests(unittest.TestCase):
    def test_a_legacy_translation_is_reused_as_a_source_line_group(self):
        import test_source_reading_http as reader

        host = reader.SourceReadingHTTPTests()
        host.setUp()
        self.addCleanup(host.doCleanups)
        fixture = host.fixture
        fixture.core(host.workspace).save_prepared_translation(
            source_id='fixture-paper', plan_id='plan-001', chunk_id='chunk-001',
            translation='# 论文\n\n## 方法\n\n旧的译文保留在这里。')
        runtime = PausedReading()
        runtime.continue_check.set()
        runtime.continue_context.set()
        route = '/library/sources/fixture-paper'
        with host.serve(reading_runtime=runtime) as port:
            host.value(port, route + '/discuss', {'selection': {'workbenchId': 'legacy-workbench', 'generation': 1}})
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                preparation = host.value(port, route + '/preparation')
                if preparation['status'] != 'running':
                    break
                time.sleep(.01)
            self.assertTrue(preparation['ready'], preparation)
            self.assertEqual('plan-001', preparation['plan_id'])
            document = host.value(port, route + '/document')
            first, second, *_ = document['translation']['segments']
            self.assertEqual('group', first['granularity'])
            self.assertEqual([1, 6], first['sourceLines'])
            self.assertIn('旧的译文保留在这里。', first['text'])
            self.assertEqual('block', second['granularity'])
            self.assertEqual(['context', 'document', 'check'], runtime.calls)
