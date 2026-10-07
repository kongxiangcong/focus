import hashlib
import time
import unittest
import test_stage5_ingestion as single


class StatusClearHostTests(unittest.TestCase):
    setUp = single.SingleIngestionTests.setUp
    tearDown = single.SingleIngestionTests.tearDown
    start_host = single.SingleIngestionTests.start_host
    stop_host = single.SingleIngestionTests.stop_host
    request = single.SingleIngestionTests.request

    def test_chat_log_expiry_preserves_dismissal_but_a_new_run_is_visible(self):
        clock = [1000.0]
        self.host.store.clock = lambda: clock[0]
        with self.host.lock:
            self.host.state['run'] = {'runId': 'failed-run', 'status': 'failed', 'error': 'diagnostic',
                                      'activity': [], 'approvals': [], 'terminalAt': clock[0]}
            self.host.changed()
        self.request('POST', '/reader/status/clear', {'requestId': 'clear-chat'})
        self.assertTrue(self.request('GET', '/reader/window')['workItems'][0]['dismissed'])
        clock[0] += 8 * 24 * 60 * 60
        expired = self.request('GET', '/reader/window')
        self.assertTrue(expired['agent']['run']['logsExpired'])
        self.assertTrue(expired['workItems'][0]['dismissed'])
        with self.host.lock:
            self.host.state['run'] = {**self.host.state['run'], 'runId': 'new-failed-run', 'terminalAt': clock[0]}
            self.host.changed()
        self.assertFalse(self.request('GET', '/reader/window')['workItems'][0]['dismissed'])

    def test_unclassified_upload_then_manage_topics_and_clear_status_without_asset_loss(self):
        item = self.request('POST', '/library/inbox?name=unclassified.pdf', b'%PDF unclassified')
        self.request('POST', '/library/batches', {'itemIds': [item['item_id']], 'requestId': 'upload', 'generateBlog': False})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            batches = self.request('GET', '/library/batches')
            if batches[0]['status'] == 'completed' and not batches[0]['executing']:
                break
            time.sleep(.05)
        self.assertEqual('completed', batches[0]['status'])
        self.assertIsNone(batches[0]['topicId'])
        source = self.request('GET', '/library/sources')[0]
        self.assertEqual([], source['topicIds'])
        topic = self.request('POST', '/library/topics', {'title': 'Later'})
        self.request('POST', '/library/sources/' + source['sourceId'] + '/manage', {
            'title': source['title'], 'topicIds': [topic['topicId']], 'requestId': 'attach-later'})
        self.assertEqual([topic['topicId']], self.request('GET', '/library/sources')[0]['topicIds'])
        self.request('POST', '/library/sources/' + source['sourceId'] + '/manage', {
            'title': source['title'], 'topicIds': [], 'requestId': 'detach-later'})
        self.assertEqual([], self.request('GET', '/library/sources')[0]['topicIds'])
        def assets():
            values = {str(path.relative_to(self.host.workspace)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for folder in ['sources', 'inbox', 'ingestion'] for path in (self.host.workspace / folder).rglob('*') if path.is_file()}
            values['state.json'] = hashlib.sha256((self.host.workspace / 'state.json').read_bytes()).hexdigest()
            return values
        before = assets()
        self.request('POST', '/reader/status/clear', {'requestId': 'clear-1'})
        self.assertTrue(self.request('GET', '/library/batches')[0]['dismissed'])
        self.assertTrue(self.request('GET', '/library/inbox')[0]['dismissed'])
        self.assertEqual(before, assets())
        self.stop_host()
        self.start_host()
        self.assertTrue(self.request('GET', '/library/batches')[0]['dismissed'])
        self.assertTrue(self.request('GET', '/library/inbox')[0]['dismissed'])

    def test_running_and_awaiting_confirmation_survive_clear(self):
        staged = self.request('POST', '/library/inbox?name=pending.pdf', b'%PDF staged')
        self.request('POST', '/reader/status/clear', {'requestId': 'clear-pending'})
        pending = self.request('GET', '/library/inbox')[0]
        self.assertEqual(staged['item_id'], pending['item_id'])
        self.assertFalse(pending['dismissed'])
        self.runtime.release.clear()
        self.request('POST', '/library/batches', {'itemIds': [staged['item_id']], 'requestId': 'running-upload'})
        deadline = time.monotonic() + 15
        while not self.runtime.calls and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertTrue(self.runtime.calls)
        self.request('POST', '/reader/status/clear', {'requestId': 'clear-running'})
        batch = self.request('GET', '/library/batches')[0]
        self.assertTrue(batch['executing'])
        self.assertFalse(batch['dismissed'])
        self.assertFalse(batch['items'][0]['dismissed'])
        self.assertTrue(any(item['status'] == 'running' and not item['dismissed'] for item in self.request('GET', '/reader/window')['workItems']))
