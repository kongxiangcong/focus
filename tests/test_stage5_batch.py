"""Batch acceptance at the HTTP boundary; only external services are replaced."""
import time
import unittest

import test_stage5_ingestion as single
from test_html_ingestion import saved_html
from core.mineru import ParserError
from core.blog_application import BlogExternalError


class BatchTests(unittest.TestCase):
    setUp = single.SingleIngestionTests.setUp
    tearDown = single.SingleIngestionTests.tearDown
    start_host = single.SingleIngestionTests.start_host
    stop_host = single.SingleIngestionTests.stop_host
    request = single.SingleIngestionTests.request

    def stage(self, name, content):
        return self.request('POST', '/library/inbox?name=' + name + '&topic=Systems', content)['item_id']

    def wait_batch(self, status):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            batches = self.request('GET', '/library/batches')
            if batches and batches[0]['status'] == status and not batches[0].get('executing'):
                return batches[0]
            time.sleep(.05)
        self.fail(str(batches))

    def test_mixed_batch_is_serial_freezes_scope_and_keeps_partial_results(self):
        write = self.runtime.write_artifact
        def article(**kwargs):
            body = self.runtime.reading_body
            if (kwargs['bundle'] / 'source.html').exists():
                self.runtime.reading_body = body.replace('第 1 节指出', '文章指出').replace('Table 1', '表格')
            try:
                return write(**kwargs)
            finally:
                self.runtime.reading_body = body
        self.runtime.write_artifact = article
        self.runtime.release.clear()
        ids = [self.stage('one.pdf', b'%PDF first'),
               self.stage('bad.html', saved_html(missing=True).encode()),
               self.stage('good.html', saved_html().encode())]
        batch = self.request('POST', '/library/batches', {'itemIds': ids, 'requestId': 'mixed'})
        self.assertTrue(self.runtime.entered.wait(10))
        running = self.request('GET', '/library/batches')[0]
        self.assertEqual('processing', running['items'][0]['status'])
        self.assertEqual('queued', running['items'][1]['status'])
        self.assertEqual(1, len(self.request('GET', '/library/sources')))
        self.assertIsNotNone(running['items'][0]['sourceId'])
        repeated = self.request('POST', '/library/batches', {'itemIds': ids, 'requestId': 'mixed'})
        self.assertEqual(batch['batchId'], repeated['batchId'])
        self.request('POST', '/library/inbox/' + ids[0] + '/process', {'requestId': 'duplicate'}, expected_status=400)
        self.request('POST', '/library/batches', {'itemIds': ids[:1], 'requestId': 'mixed'}, expected_status=400)
        self.runtime.release.set()
        result = self.wait_batch('partial')
        self.assertEqual(['completed', 'failed', 'completed'], [i['status'] for i in result['items']], result)
        self.assertEqual(2, len(self.request('GET', '/library/sources')))
        calls = list(self.runtime.calls)
        self.stop_host()
        self.start_host()
        self.assertEqual(result, self.request('GET', '/library/batches')[0])
        self.assertEqual(calls, self.runtime.calls)

    def test_common_auth_failure_pauses_remaining_items(self):
        def fail(*args, **kwargs):
            raise ParserError('Authentication failed', recoverable=False, error_id='authentication_failed')
        self.host.ingestion.parser.parse = fail
        ids = [self.stage('one.pdf', b'%PDF auth'), self.stage('two.pdf', b'%PDF queued')]
        self.request('POST', '/library/batches', {'itemIds': ids, 'requestId': 'auth'})
        result = self.wait_batch('paused')
        self.assertEqual('authentication_failed', result['error']['error_id'])
        self.assertEqual('queued', result['items'][1]['status'])
        self.assertEqual([], self.runtime.calls)

    def test_blog_service_failure_pauses_and_preserves_source(self):
        def fail(**kwargs):
            raise BlogExternalError('service_unavailable', 'provider unavailable')
        self.runtime.classify = fail
        ids = [self.stage('one.pdf', b'%PDF blog auth'), self.stage('two.pdf', b'%PDF untouched')]
        self.request('POST', '/library/batches', {'itemIds': ids, 'requestId': 'blog-auth'})
        result = self.wait_batch('paused')
        self.assertEqual('service_unavailable', result['error']['error_id'])
        self.assertEqual(['partial', 'queued'], [i['status'] for i in result['items']])
        self.assertEqual(1, len(self.request('GET', '/library/sources')))

    def test_reject_mixed_topics_before_confirming_any_item(self):
        first = self.stage('one.pdf', b'%PDF systems')
        other = self.request('POST', '/library/inbox?name=two.pdf&topic=Other', b'%PDF other')['item_id']
        self.request('POST', '/library/batches', {'itemIds': [first, other], 'requestId': 'wrong-topic'}, expected_status=400)
        self.assertTrue(all(i['status'] == 'awaiting_confirmation' for i in self.request('GET', '/library/inbox')))
        self.assertEqual([], self.request('GET', '/library/batches'))

    def test_local_blog_output_failure_continues_to_next_item(self):
        classify = self.runtime.classify
        def fail_pdf(**kwargs):
            if (kwargs['bundle'] / 'source.pdf').exists():
                raise RuntimeError('invalid generated JSON')
            return classify(**kwargs)
        self.runtime.classify = fail_pdf
        self.runtime.reading_body = self.runtime.reading_body.replace('第 1 节指出', '文章指出').replace('Table 1', '表格')
        ids = [self.stage('one.pdf', b'%PDF local failure'), self.stage('good.html', saved_html().encode())]
        self.request('POST', '/library/batches', {'itemIds': ids, 'requestId': 'local-blog'})
        result = self.wait_batch('partial')
        self.assertEqual(['partial', 'completed'], [i['status'] for i in result['items']], result)

    def test_cannot_take_over_a_running_single_item(self):
        self.runtime.release.clear()
        first = self.stage('one.pdf', b'%PDF existing single')
        other = self.stage('other.pdf', b'%PDF other')
        self.request('POST', '/library/inbox/' + first + '/confirm', {'generateBlog': True})
        self.request('POST', '/library/inbox/' + first + '/process', {'requestId': 'legacy-single'})
        self.assertTrue(self.runtime.entered.wait(10))
        self.request('POST', '/library/batches', {'itemIds': [first, other], 'requestId': 'takeover'}, expected_status=400)
        self.assertEqual([], self.request('GET', '/library/batches'))
        self.assertEqual('awaiting_confirmation', next(i for i in self.request('GET', '/library/inbox') if i['item_id'] == other)['status'])

    def test_parser_configuration_change_is_not_silently_reauthorized(self):
        self.runtime.release.clear()
        ids = [self.stage('one.pdf', b'%PDF initial'), self.stage('next.pdf', b'%PDF later')]
        self.request('POST', '/library/batches', {'itemIds': ids, 'requestId': 'config'})
        self.assertTrue(self.runtime.entered.wait(10))
        self.host.ingestion.parser.model = 'changed-after-confirmation'
        self.runtime.release.set()
        result = self.wait_batch('partial')
        self.assertEqual('failed', result['items'][1]['status'])
        self.assertEqual(1, len(self.request('GET', '/library/sources')))

