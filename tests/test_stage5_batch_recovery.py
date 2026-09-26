"""Persisted batch controls exercised through the public HTTP boundary."""
import time
import threading
import unittest

import test_stage5_batch as batch_tests
from test_html_ingestion import saved_html
from test_blog_host import ParserDouble
from core.ingestion import IngestionExternalError


class RecoveryTests(unittest.TestCase):
    setUp = batch_tests.BatchTests.setUp
    tearDown = batch_tests.BatchTests.tearDown
    start_host = batch_tests.BatchTests.start_host
    stop_host = batch_tests.BatchTests.stop_host
    request = batch_tests.BatchTests.request
    stage = batch_tests.BatchTests.stage
    wait_batch = batch_tests.BatchTests.wait_batch

    def start_blocked(self):
        self.runtime.reading_body = self.runtime.reading_body.replace('第 1 节指出', '文章指出').replace('Table 1', '表格')
        self.runtime.release.clear()
        self.ids = [self.stage('one.pdf', b'%PDF controls'), self.stage('article.html', saved_html().encode())]
        self.batch = self.request('POST', '/library/batches', {'itemIds': self.ids, 'requestId': 'controls'})
        self.assertTrue(self.runtime.entered.wait(10))

    def control(self, action, request_id, item=None):
        return self.request('POST', '/library/batches/' + self.batch['batchId'] + '/' + action,
                            {'requestId': request_id, 'itemId': item})

    def join_batch(self):
        for worker in list(self.host.batch_workers.values()):
            worker.join(15)
            self.assertFalse(worker.is_alive())

    def test_stop_restart_continue_keeps_original_and_replays_once(self):
        self.start_blocked()
        source = self.request('GET', '/library/sources')[0]['sourceId']
        original = (self.root / 'knowledge-base/sources' / source / 'parser-bundle/source.pdf').read_bytes()
        self.control('stop', 'stop-1')
        self.runtime.release.set()
        self.join_batch()
        self.assertEqual('paused', self.request('GET', '/library/batches')[0]['status'])
        self.assertEqual(1, len(self.request('GET', '/library/sources')))
        self.stop_host()
        self.start_host()
        calls = list(self.runtime.calls)
        self.assertEqual('paused', self.request('GET', '/library/batches')[0]['status'])
        self.assertEqual(calls, self.runtime.calls)
        self.control('continue', 'continue-1')
        self.control('continue', 'continue-1')
        result = self.wait_batch('completed')
        self.assertEqual(['completed', 'completed'], [i['status'] for i in result['items']])
        self.assertEqual(original, (self.root / 'knowledge-base/sources' / source / 'parser-bundle/source.pdf').read_bytes())
        calls = list(self.runtime.calls)
        self.control('continue', 'continue-1')
        self.assertEqual(calls, self.runtime.calls)

    def test_cancel_one_does_not_cancel_next_and_retry_only_that_item(self):
        self.start_blocked()
        self.control('cancel-item', 'cancel-1', self.ids[0])
        self.runtime.release.set()
        result = self.wait_batch('partial')
        self.assertEqual(['cancelled', 'completed'], [i['status'] for i in result['items']])
        self.join_batch()
        completed_id = result['items'][1]['sourceId']
        blog = self.root / 'knowledge-base/sources' / completed_id / 'blog'
        before = {str(p.relative_to(blog)): p.read_bytes() for p in blog.rglob('*') if p.is_file()}
        self.control('retry-item', 'retry-1', self.ids[0])
        self.wait_batch('completed')
        self.assertEqual(before, {str(p.relative_to(blog)): p.read_bytes() for p in blog.rglob('*') if p.is_file()})

    def test_remove_queued_item_preserves_sources_and_never_starts_it(self):
        self.start_blocked()
        self.control('remove-item', 'remove-1', self.ids[1])
        self.runtime.release.set()
        result = self.wait_batch('partial')
        self.assertEqual(['completed', 'cancelled'], [i['status'] for i in result['items']])
        self.assertEqual(1, len(self.request('GET', '/library/sources')))

    def test_late_classification_after_stop_cannot_publish_or_start_writing(self):
        classify = self.runtime.classify
        def late(**kwargs):
            self.runtime.entered.set()
            self.runtime.release.wait(10)
            return classify(**kwargs)
        self.runtime.classify = late
        self.runtime.cancel = lambda: False
        self.start_blocked()
        self.control('stop', 'stop-classification')
        self.runtime.release.set()
        self.join_batch()
        result = self.request('GET', '/library/batches')[0]
        self.assertEqual('cancelled', result['items'][0]['blog']['runStatus'])
        self.assertNotIn('reading_blog', self.runtime.calls)
        self.assertEqual('queued', result['items'][1]['status'])

    def test_remote_checkpoint_queries_and_unknown_requires_explicit_risk(self):
        for checkpointed in (True, False):
            with self.subTest(checkpointed=checkpointed):
                class RemoteParser(ParserDouble):
                    def __init__(self):
                        self.starts = self.queries = 0
                    def parse(self, source, candidate, *, checkpoint=None):
                        self.starts += 1
                        if self.starts == 1:
                            if checkpointed:
                                checkpoint({'reference_kind': 'batch_id', 'reference_id': 'remote'})
                            raise IngestionExternalError('acceptance_unknown', 'Unknown remote acceptance', acceptance_unknown=True)
                        return super().parse(source, candidate, checkpoint=checkpoint)
                    def resume(self, source, candidate, *, checkpoint):
                        self.queries += 1
                        return super().parse(source, candidate)
                parser = RemoteParser()
                self.host.ingestion.parser = parser
                item_id = self.stage('remote.pdf', b'%PDF remote ' + str(checkpointed).encode())
                self.batch = self.request('POST', '/library/batches', {'itemIds': [item_id], 'requestId': 'remote-' + str(checkpointed)})
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    result = next(b for b in self.request('GET', '/library/batches') if b['batchId'] == self.batch['batchId'])
                    if result['status'] == 'partial':
                        break
                    time.sleep(.05)
                self.join_batch()
                self.stop_host()
                self.start_host()
                self.host.ingestion.parser = parser
                self.assertEqual(1, parser.starts)
                self.control('continue', 'query-' + str(checkpointed))
                self.join_batch()
                self.assertEqual(1, parser.starts)
                if checkpointed:
                    self.assertEqual(1, parser.queries)
                else:
                    item = next(i for i in self.request('GET', '/library/inbox') if i['item_id'] == item_id)
                    self.request('POST', '/library/batches/' + self.batch['batchId'] + '/resubmit-item', {
                        'requestId': 'risk', 'itemId': item_id, 'riskChoiceId': item['resubmit_risk']['choice_id']})
                    self.join_batch()
                    self.assertEqual(2, parser.starts)
                    self.request('POST', '/library/batches/' + self.batch['batchId'] + '/resubmit-item', {
                        'requestId': 'risk', 'itemId': item_id, 'riskChoiceId': item['resubmit_risk']['choice_id']})
                    self.assertEqual(2, parser.starts)

    def test_cancelled_late_unknown_acceptance_still_requires_risk(self):
        entered, release = threading.Event(), threading.Event()
        class LateParser(ParserDouble):
            starts = 0
            def parse(self, source, candidate, *, checkpoint=None):
                self.starts += 1
                entered.set()
                release.wait(10)
                raise IngestionExternalError('acceptance_unknown', 'Late unknown', acceptance_unknown=True)
        parser = LateParser()
        self.host.ingestion.parser = parser
        item_id = self.stage('late.pdf', b'%PDF late remote')
        self.batch = self.request('POST', '/library/batches', {'itemIds': [item_id], 'requestId': 'late'})
        self.assertTrue(entered.wait(10))
        self.control('stop', 'late-stop')
        release.set()
        self.join_batch()
        item = self.request('GET', '/library/inbox')[0]
        self.assertEqual('cancelled', item['status'])
        self.assertIsNotNone(item['resubmit_risk'])
        self.control('continue', 'late-continue')
        self.join_batch()
        self.assertEqual(1, parser.starts)
