"""Streaming projection isolation and persistence, using real Core and Store."""
import copy
import threading
import unittest
from unittest.mock import patch

from reading_fixture import ReadingFixture
from workspace_fixture import HostService
from host import discussions
from host.service import HostService as Service


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ReadingFixture(); self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.host = HostService(self.workspace, self.fixture.root / 'host')
        with self.host.lock:
            self.host.state['displayReading'] = False
            self.host.state['run'] = {'runId': 'test', 'status': 'running', 'activity': [], 'approvals': []}
            self.host.active_discussion = {'sourceId': 'fixture-paper', 'discussionId': discussions.select(self.host.state, 'fixture-paper')}
            self.host.changed()

    def tearDown(self):
        self.host.active_discussion = None
        self.host.close(); self.fixture.tearDown()

    def test_text_never_projects_core_and_every_fragment_is_durable(self):
        page, initial = self.host.event_snapshot()
        with patch.object(self.host.core, 'window', side_effect=AssertionError('Token touched Core')):
            for _ in range(300): self.host._notification('message/delta', {'itemId': 'reply', 'delta': '中文🙂'})
            with self.host.lock: update = self.host.text_event(page, initial['revision'])
        self.assertEqual('中文🙂'*300, update['messages'][0]['content'])
        self.assertEqual('中文🙂'*300, self.host.store.get('session')['conversation'][-1]['content'])
        self.assertEqual(page, self.host.page_generation)
        self.host._notification('message/completed', {'itemId': 'reply', 'text': '最终答案'})
        self.assertEqual('最终答案', self.host.store.get('session')['conversation'][-1]['content'])
        _, refreshed = self.host.event_snapshot()
        self.assertEqual('最终答案', refreshed['conversation'][-1]['content'])

    def test_projection_is_off_lock_and_rejects_structural_races(self):
        entered = threading.Event(); release = threading.Event(); results = []; calls = []
        original = Service._project_snapshot
        def slow(view):
            calls.append(1)
            if len(calls) == 1:
                entered.set(); self.assertTrue(release.wait(5))
            return original(view)
        with patch.object(Service, '_project_snapshot', slow):
            worker = threading.Thread(target=lambda: results.append(self.host.event_snapshot()))
            worker.start(); self.assertTrue(entered.wait(5))
            acquired = self.host.lock.acquire(timeout=.1)
            self.assertTrue(acquired, 'Heavy projection owns the writer lock')
            try:
                self.host.state['sessionId'] = 'replacement-session'
                self.host.state['conversation'] = []
                self.host.changed()
            finally: self.host.lock.release(); release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive()); self.assertEqual(2, len(calls))
        self.assertEqual('replacement-session', results[0][1]['sessionId'])

    def test_new_baseline_reconnect_stop_and_clear_cannot_replay_old_text(self):
        page, baseline = self.host.event_snapshot()
        self.host._notification('message/delta', {'itemId': 'reply', 'delta': 'before'})
        _, reconnect = self.host.event_snapshot()
        self.assertEqual('before', reconnect['conversation'][-1]['content'])
        with self.host.lock:
            self.host.state['run']['status'] = 'cancelled'
            self.host.changed()
            self.assertIsNone(self.host.text_event(page, baseline['revision']))
        self.host._notification('message/delta', {'itemId': 'reply', 'delta': 'late'})
        self.assertEqual('before', self.host.store.get('session')['conversation'][-1]['content'])
        with self.host.lock:
            self.host.state['conversation'] = []; self.host.state['timeline'] = []
            self.host.state['sessionId'] = 'cleared'; self.host.changed()
        _, cleared = self.host.event_snapshot()
        self.assertEqual([], cleared['conversation'])
        self.assertEqual({}, self.host.stream_messages)

    def test_fixed_cadence_stream_has_bounded_backlog(self):
        from streaming_benchmark import run
        result = run()
        self.assertLess(result['max_backlog'], 30)
        self.assertLess(result['last_apply_lag_ms'], 200)
        self.assertLess(result['last_sse_lag_ms'], 250)
        self.assertLessEqual(result['full_snapshots'], 2)

    def test_projection_retains_authoritative_discussion_identity(self):
        with self.host.lock:
            self.host.state.pop('discussions', None)
            self.host.state.pop('latestDiscussion', None)
        first = self.host.snapshot()
        second = self.host.snapshot()
        self.assertEqual(first['discussionId'], second['discussionId'])
        self.assertIn(first['discussionId'], self.host.state['discussions'])
