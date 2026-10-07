"""Clear and diagnostic expiry through public Host operations and real persistence."""
import unittest

import test_source_discussion
from host.core_bridge import WorkspaceError


class ClearRetentionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_source_discussion.DiscussionTests()
        self.fixture.setUp()
        self.host = self.fixture.host

    def tearDown(self):
        self.fixture.tearDown()

    def discuss(self, source='fixture-paper', request='request-clear-note'):
        selected = self.host.select_discussion_source(source)
        self.host.start({'requestId': request, 'sourceId': source,
                         'sessionId': selected['sessionId'], 'receipt': None, 'content': '记下来'})
        self.host.worker.join(3)
        self.assertFalse(self.host.worker.is_alive())
        return self.host.snapshot()

    def test_clear_removes_history_notes_and_undo_but_preserves_other_source(self):
        other = self.discuss('fixture-b-paper', 'request-other-note')
        before = self.discuss()
        note = before['sourceNotes'][0]
        self.host.source_note_change('fixture-paper', note['noteId'],
            {'requestId': 'edit-before-clear', 'expectedRevision': 1, 'content': 'Correction'}, 'edit')
        result = self.host.clear_source('fixture-paper', {'requestId': 'clear-source-001', 'confirmed': True})
        self.assertEqual('completed', result['clearOperation']['status'])
        self.assertEqual([], result['sourceNotes'])
        self.assertEqual([], result['conversation'])
        with self.assertRaises(WorkspaceError):
            self.host.source_note_change('fixture-paper', note['noteId'],
                {'requestId': 'undo-after-clear', 'expectedRevision': 2}, 'undo')
        self.assertEqual('cancelled', self.host.source_note_request('fixture-paper', 'edit-before-clear')['status'])
        repeated = self.host.clear_source('fixture-paper', {'requestId': 'clear-source-001', 'confirmed': True})
        self.assertEqual('completed', repeated['clearOperation']['status'])
        selected = self.host.select_discussion_source('fixture-b-paper')
        self.assertEqual(other['sourceNotes'], selected['sourceNotes'])
        self.assertEqual(other['conversation'], selected['conversation'])

    def test_cancel_and_busy_refusal_leave_contents_unchanged(self):
        before = self.discuss()
        with self.assertRaises(WorkspaceError):
            self.host.clear_source('fixture-paper', {'requestId': 'clear-no-confirm', 'confirmed': False})
        self.assertEqual(before['sourceNotes'], self.host.snapshot()['sourceNotes'])
        self.fixture.pause_runtime = True
        self.fixture.runtime_ready.clear()
        self.host.start({'requestId': 'request-paused-clear', 'sourceId': 'fixture-paper',
                         'sessionId': before['sessionId'], 'receipt': None, 'content': '记下来'})
        self.assertTrue(self.fixture.runtime_ready.wait(3))
        with self.assertRaises(WorkspaceError) as caught:
            self.host.clear_source('fixture-paper', {'requestId': 'clear-busy-001', 'confirmed': True})
        self.assertEqual('source_busy', caught.exception.error_id)
        self.fixture.runtime.release()
        self.host.worker.join(3)
        self.assertEqual(2, len(self.host.snapshot()['sourceNotes']))

    def test_clear_retry_does_not_erase_new_discussion_and_old_request_cannot_replay(self):
        before = self.discuss()
        self.host.clear_source('fixture-paper', {'requestId': 'clear-once-001', 'confirmed': True})
        after = self.discuss(request='request-new-clear')
        repeated = self.host.clear_source('fixture-paper', {'requestId': 'clear-once-001', 'confirmed': True})
        self.assertEqual(after['conversation'], repeated['conversation'])
        self.assertEqual(after['sourceNotes'], repeated['sourceNotes'])
        with self.assertRaises(WorkspaceError):
            self.host.start({'requestId': 'request-clear-note', 'sourceId': 'fixture-paper',
                             'sessionId': before['sessionId'], 'receipt': None, 'content': '记下来'})

    def test_partial_disk_failure_is_visible_and_restart_completes_clear(self):
        import sqlite3
        from contextlib import closing
        from workspace_fixture import HostService
        self.discuss()
        database = self.fixture.workspace / 'discussions' / 'host.sqlite3'
        # Storage-boundary failure after Core notes commit, before Host commit.
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("CREATE TRIGGER fail_clear BEFORE UPDATE ON state WHEN NEW.key='session' BEGIN SELECT RAISE(FAIL, 'disk failure'); END")
        with self.assertRaises(WorkspaceError) as caught:
            self.host.clear_source('fixture-paper', {'requestId': 'clear-failure-001', 'confirmed': True})
        self.assertEqual('clear_incomplete', caught.exception.error_id)
        with self.assertRaises(Exception):
            self.host.start({'requestId': 'request-during-failure', 'sourceId': 'fixture-paper',
                             'receipt': None, 'content': '记下来'})
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('DROP TRIGGER fail_clear')
        self.host.close()
        self.host = self.fixture.host = HostService(self.fixture.workspace, self.fixture.fixture.root / 'host',
            backend_factory=lambda workspace, **kwargs: test_source_discussion.CandidateRuntime(workspace, **kwargs))
        restored = self.host.select_discussion_source('fixture-paper')
        self.assertEqual([], restored['sourceNotes'])
        self.assertEqual([], restored['conversation'])

    def test_detailed_activity_expires_seven_days_after_terminal_not_start(self):
        from workspace_fixture import HostService
        now = [1000000.0]
        self.host.close()
        class ActivityRuntime(test_source_discussion.CandidateRuntime):
            def start_turn(runtime, **kwargs):
                runtime.events.put({'method': 'activity', 'params': {
                    'id': 'activity-1', 'title': '工具', 'detail': 'detailed output'}})
                now[0] += 600
                super().start_turn(**kwargs)
        self.host = self.fixture.host = HostService(self.fixture.workspace, self.fixture.fixture.root / 'host',
            backend_factory=lambda workspace, **kwargs: ActivityRuntime(workspace, **kwargs), clock=lambda: now[0])
        before = self.discuss()
        self.assertTrue(before['agent']['run']['activity'])
        terminal = now[0]
        old_run = before['agent']['run']['runId']
        self.discuss(request='request-next-log')
        self.assertTrue(self.host.execution_log(old_run)['activity'])
        now[0] = terminal + 7 * 86400 - 1
        self.assertTrue(self.host.execution_log(old_run)['activity'])
        self.assertTrue(self.host.snapshot()['agent']['run']['activity'])
        now[0] += 1
        self.assertEqual([], self.host.execution_log(old_run)['activity'])
        self.assertTrue(self.host.snapshot()['agent']['run']['activity'])
        before = self.host.snapshot()
        now[0] += 600
        after = self.host.snapshot()
        self.assertEqual([], after['agent']['run']['activity'])
        self.assertEqual('completed', after['agent']['run']['status'])
        self.assertEqual(before['sourceNotes'], after['sourceNotes'])
        self.assertEqual(before['conversation'], after['conversation'])

    def test_concurrent_start_and_clear_have_one_serial_admission_order(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        before = self.discuss()
        self.fixture.pause_runtime = True
        self.fixture.runtime_ready.clear()
        barrier = threading.Barrier(2)
        def start():
            barrier.wait()
            return self.host.start({'requestId': 'request-concurrent', 'sourceId': 'fixture-paper',
                'sessionId': before['sessionId'], 'receipt': None, 'content': '记下来'})
        def clear():
            barrier.wait()
            try:
                return self.host.clear_source('fixture-paper', {'requestId': 'clear-concurrent', 'confirmed': True})['clearOperation']['status']
            except WorkspaceError as exc:
                return exc.error_id
        with ThreadPoolExecutor(2) as pool:
            started, cleared = pool.submit(start), pool.submit(clear)
            started.result(timeout=5)
            outcome = cleared.result(timeout=5)
        self.assertIn(outcome, ('completed', 'source_busy'))
        self.assertTrue(self.fixture.runtime_ready.wait(3))
        self.fixture.runtime.release()
        self.host.worker.join(3)
        self.assertEqual(1 if outcome == 'completed' else 2, len(self.host.snapshot()['sourceNotes']))

    def test_crashed_run_logs_survive_restart_and_next_task(self):
        import subprocess
        import sys
        from pathlib import Path
        from workspace_fixture import HostService
        self.host.close()
        script = r'''
import os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'tests'))
import test_source_discussion
from workspace_fixture import HostService
class Paused(test_source_discussion.CandidateRuntime):
    def start_turn(self, **kwargs):
        self.events.put({'method': 'activity', 'params': {'id': 'crash', 'title': 'Test', 'detail': 'Before crash'}})
h = HostService(Path(sys.argv[1]), Path(sys.argv[2]), backend_factory=lambda workspace, **kwargs: Paused(workspace, **kwargs))
h.select_discussion_source('fixture-paper')
h.start({'requestId':'request-crash-log', 'sourceId':'fixture-paper', 'content':'Explain'})
for _ in range(100):
    view = h.snapshot()
    if view['agent']['run']['activity']:
        os._exit(0)
    time.sleep(.01)
os._exit(1)
'''
        subprocess.run([sys.executable, '-X', 'utf8', '-c', script,
            str(self.fixture.workspace), str(self.fixture.fixture.root / 'host')], check=True, timeout=10)
        now = [1000000.0]
        self.host = self.fixture.host = HostService(self.fixture.workspace, self.fixture.fixture.root / 'host',
            backend_factory=lambda workspace, **kwargs: test_source_discussion.CandidateRuntime(workspace, **kwargs), clock=lambda: now[0])
        interrupted = self.host.snapshot()['agent']['run']
        self.assertEqual('interrupted', interrupted['status'])
        self.discuss(request='request-after-crash')
        self.assertEqual('Before crash', self.host.execution_log(interrupted['runId'])['activity'][0]['detail'])
        now[0] += 7 * 86400
        self.assertEqual([], self.host.execution_log(interrupted['runId'])['activity'])


class ClearReadingPreservationTests(unittest.TestCase):
    def setUp(self):
        import test_reading_progress
        self.fixture = test_reading_progress.ReadingProgressTests()
        self.fixture.setUp()
        self.host = self.fixture.host
        self.host.backend_factory = lambda workspace, **kwargs: test_source_discussion.CandidateRuntime(workspace, **kwargs)

    def tearDown(self):
        self.fixture.tearDown()

    def test_clear_preserves_plan_cursor_and_reading_progress(self):
        self.host.continue_cached({'receipt': self.fixture.receipt(), 'requestId': 'advance-before-clear'})
        for worker in list(self.host.progress_workers.values()):
            worker.join(3)
        self.host.start({'sourceId': 'fixture-paper', 'requestId': 'note-reading-clear', 'content': '记下来'})
        self.host.worker.join(3)
        before = self.host.snapshot()
        self.assertTrue(before['sourceNotes'])
        self.assertTrue(before['readingProgress'])
        after = self.host.clear_source('fixture-paper', {'requestId': 'clear-reading-001', 'confirmed': True})
        self.assertEqual([], after['sourceNotes'])
        self.assertEqual([], after['conversation'])
        for key in ('current', 'history', 'outline', 'readingRevision', 'readingProgress', 'preparations', 'source'):
            self.assertEqual(before[key], after[key], key)


if __name__ == '__main__':
    unittest.main()
