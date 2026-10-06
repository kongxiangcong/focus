import unittest
from host.status_notifications import StatusNotifications


class MemoryStore:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value):
        self.values[key] = value


class StatusNotificationTests(unittest.TestCase):
    def test_expiring_diagnostics_does_not_restore_a_dismissed_chat_attempt(self):
        notices = StatusNotifications(MemoryStore())
        failure = {'status': 'failed', 'notificationId': 'run-1', 'label': 'chat', 'error': 'old log'}
        notices.clear([('work', 'chat:run-1', failure)], 'clear-chat')
        self.assertTrue(notices.project('work', 'chat:run-1', {**failure, 'error': None})['dismissed'])
        self.assertFalse(notices.project('work', 'chat:run-1', {**failure, 'notificationId': 'run-2'})['dismissed'])

    def test_clear_keeps_active_work_and_new_attempts_visible(self):
        store = MemoryStore()
        notices = StatusNotifications(store)
        failed = {'status': 'failed', 'notificationId': 'attempt-1', 'error': 'failure'}
        running = {'status': 'running', 'notificationId': 'attempt-2'}
        queued = {'status': 'queued'}
        notices.clear([('work', 'failed', failed), ('work', 'active', running), ('work', 'queued', queued)], 'clear-1')
        self.assertTrue(notices.project('work', 'failed', failed)['dismissed'])
        self.assertFalse(notices.project('work', 'active', running)['dismissed'])
        self.assertFalse(notices.project('work', 'queued', queued)['dismissed'])
        self.assertFalse(notices.project('work', 'failed', {**failed, 'notificationId': 'attempt-3'})['dismissed'])
        # A retry of a lost clear response must not dismiss a newly finished attempt.
        notices.clear([('work', 'failed', {**failed, 'notificationId': 'attempt-3'})], 'clear-1')
        self.assertFalse(notices.project('work', 'failed', {**failed, 'notificationId': 'attempt-3'})['dismissed'])
        self.assertTrue(StatusNotifications(store).project('work', 'failed', failed)['dismissed'])

    def test_clear_preserves_recovery_data_and_retains_active_batch_children(self):
        notices = StatusNotifications(MemoryStore())
        completed = {'status': 'completed', 'sourceId': 'paper', 'requestId': 'request'}
        batch = {'status': 'partial', 'items': [completed, {'status': 'queued'}]}
        notices.clear([('batch', 'batch', batch), ('item', 'item', completed)], 'clear-2')
        self.assertFalse(notices.project('batch', 'batch', batch)['dismissed'])
        self.assertTrue(notices.project('item', 'item', completed)['dismissed'])
        self.assertEqual({'status': 'completed', 'sourceId': 'paper', 'requestId': 'request'}, completed)
