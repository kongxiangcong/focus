"""Re-upload reveals an existing attempt; only an explicit retry invokes parsing."""
import time
import unittest
from unittest.mock import patch

import test_stage5_ingestion as single


class DuplicateIngestionRecoveryTests(unittest.TestCase):
    setUp = single.SingleIngestionTests.setUp
    tearDown = single.SingleIngestionTests.tearDown
    start_host = single.SingleIngestionTests.start_host
    stop_host = single.SingleIngestionTests.stop_host
    request = single.SingleIngestionTests.request

    def upload(self, name, content):
        return self.request('POST', '/library/inbox?name=' + name, content)

    def wait_finished(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not any(worker.is_alive() for worker in
                       [*self.host.batch_workers.values(), *self.host.ingestion_workers.values()]):
                return
            time.sleep(.01)
        self.fail('Ingestion did not finish')

    def assert_visible(self, expected):
        inbox = {item['item_id']: item for item in self.request('GET', '/library/inbox')}
        work = {item['targetId']: item for item in self.request('GET', '/reader/window')['workItems']
                if item['kind'] == 'ingestion'}
        for item_id, visible in expected.items():
            self.assertEqual(not visible, inbox[item_id]['dismissed'])
            self.assertEqual(not visible, work[item_id]['dismissed'])

    def test_single_failure_clear_reupload_restart_and_explicit_retry(self):
        first = self.upload('failed.pdf', b'%PDF first')
        other = self.upload('other.pdf', b'%PDF other')
        with patch.object(self.host.ingestion.parser, 'parse', side_effect=RuntimeError('parser offline')) as parse:
            for item in [first, other]:
                self.request('POST', '/library/inbox/' + item['item_id'] + '/confirm', {})
                self.request('POST', '/library/inbox/' + item['item_id'] + '/process', {'requestId': item['item_id']})
                self.wait_finished()
            self.assertEqual(2, parse.call_count)
            before = self.host.ingestion.get(first['item_id'])
            self.assertEqual('failed', before['status'])
            self.assertIsNone(before['source_id'])
            self.request('POST', '/reader/status/clear', {'requestId': 'clear-single'})
            self.assert_visible({first['item_id']: False, other['item_id']: False})
            repeated = self.upload('renamed.pdf', b'%PDF first')
            self.assertTrue(repeated['duplicate'])
            self.assertEqual(first['item_id'], repeated['item_id'])
            self.assertEqual(before, self.host.ingestion.get(first['item_id']))
            self.assertEqual(2, parse.call_count)
        self.assertEqual([], self.request('GET', '/library/sources'))
        self.assertEqual([], self.request('GET', '/library/batches'))
        self.assertEqual(2, len(self.request('GET', '/library/inbox')))
        self.assert_visible({first['item_id']: True, other['item_id']: False})
        self.stop_host(); self.start_host()
        self.assert_visible({first['item_id']: True, other['item_id']: False})
        # The attachment-based entry must share the HTTP upload's recovery.
        self.request('POST', '/reader/status/clear', {'requestId': 'clear-again'})
        attachment = self.host.workspace / 'uploads' / 'attachment.pdf'
        attachment.parent.mkdir(exist_ok=True)
        attachment.write_bytes(b'%PDF first')
        self.host.store.put('upload:attachment', {'path': 'uploads/attachment.pdf'})
        restored = self.host.inbox_stage('attachment')
        self.assertTrue(restored['duplicate'])
        self.assertEqual(first['item_id'], restored['item_id'])
        self.assert_visible({first['item_id']: True, other['item_id']: False})
        self.request('POST', '/library/inbox/' + first['item_id'] + '/continue', {'requestId': 'explicit-retry'})
        self.wait_finished()
        self.assertEqual('completed', self.host.ingestion.get(first['item_id'])['status'])
        self.assertEqual(1, len(self.request('GET', '/library/sources')))

    def test_batch_reupload_restores_parent_and_only_the_matching_child(self):
        first = self.upload('failed.pdf', b'%PDF batch-first')
        sibling = self.upload('sibling.pdf', b'%PDF sibling')
        other = self.upload('other.pdf', b'%PDF separate')
        with patch.object(self.host.ingestion.parser, 'parse', side_effect=RuntimeError('parser offline')) as parse:
            parent = self.request('POST', '/library/batches', {
                'itemIds': [first['item_id'], sibling['item_id']], 'requestId': 'batch-1', 'generateBlog': False})
            self.wait_finished()
            unrelated = self.request('POST', '/library/batches', {
                'itemIds': [other['item_id']], 'requestId': 'batch-2', 'generateBlog': False})
            self.wait_finished()
            self.assertEqual(3, parse.call_count)
            before = [self.host.ingestion.get(item['item_id']) for item in [first, sibling, other]]
            batch_bytes = (self.host.workspace / 'ingestion/batches.json').read_bytes()
            self.request('POST', '/reader/status/clear', {'requestId': 'clear-batches'})
            self.assertTrue(all(batch['dismissed'] for batch in self.request('GET', '/library/batches')))
            self.assert_visible({first['item_id']: False, sibling['item_id']: False, other['item_id']: False})
            repeated = self.upload('renamed.pdf', b'%PDF batch-first')
            self.assertTrue(repeated['duplicate'])
            self.assertEqual(first['item_id'], repeated['item_id'])
            self.assertEqual(3, parse.call_count)
            self.assertEqual(before, [self.host.ingestion.get(item['item_id']) for item in [first, sibling, other]])
            self.assertEqual(batch_bytes, (self.host.workspace / 'ingestion/batches.json').read_bytes())
        for restart in [False, True]:
            if restart:
                self.stop_host(); self.start_host()
            self.assert_visible({first['item_id']: True, sibling['item_id']: False, other['item_id']: False})
            batches = {batch['batchId']: batch for batch in self.request('GET', '/library/batches')}
            self.assertEqual(2, len(batches))
            self.assertFalse(batches[parent['batchId']]['dismissed'])
            self.assertEqual([False, True], [item['dismissed'] for item in batches[parent['batchId']]['items']])
            self.assertTrue(batches[unrelated['batchId']]['dismissed'])
        self.assertEqual([], self.request('GET', '/library/sources'))
        self.request('POST', '/library/batches/' + parent['batchId'] + '/retry-item', {
            'itemId': first['item_id'], 'requestId': 'explicit-batch-retry'})
        self.wait_finished()
        self.assertEqual('completed', self.host.ingestion.get(first['item_id'])['status'])
        self.assertEqual('failed', self.host.ingestion.get(sibling['item_id'])['status'])
        self.assertEqual(1, len(self.request('GET', '/library/sources')))
