import unittest

from host.status_notifications import StatusNotifications


class MemoryStore:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key):
        return self.values.get(key)

    def put(self, key, value):
        self.values[key] = value


class StatusNotificationTests(unittest.TestCase):
    def test_clear_replays_without_growing_request_records(self):
        store = MemoryStore({'statusNotifications': {'requests': ['legacy-request']}})
        failed = {'status': 'failed'}
        notices = StatusNotifications(store)
        notices.project('work', 'source', failed, eligible=True, attempt='first', offer=True)
        tokens = list(notices.available)
        notices.clear('clear-1', tokens)
        before = store.get('statusNotifications')
        self.assertNotIn('requests', before)

        for request_id in range(200):
            notices = StatusNotifications(store)
            current = notices.project('work', 'source', failed, eligible=True, attempt='second', offer=True)
            self.assertFalse(current['dismissed'])
            self.assertFalse(notices.clear(str(request_id), tokens))

        self.assertEqual(before, store.get('statusNotifications'))
        reloaded = StatusNotifications(store)
        self.assertTrue(reloaded.project('work', 'source', failed, eligible=True, attempt='first')['dismissed'])
