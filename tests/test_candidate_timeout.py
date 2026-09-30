"""Distinguish elapsed candidate deadlines from cancellation/closed transport."""
import unittest
from host.candidates import CandidateTurns
from host.backends.base import BackendError


class BackendDouble:
    def __init__(self, closed=False):
        self.closed = closed
        self.close_count = 0

    def open_session(self, *args, **kwargs):
        pass

    def start_turn(self, **kwargs):
        pass

    def close(self):
        self.closed = True
        self.close_count += 1


class CandidateTimeoutTests(unittest.TestCase):
    def test_elapsed_deadline_is_a_typed_timeout_and_releases_backend(self):
        backend = BackendDouble()
        turns = CandidateTurns(lambda **kwargs: backend)
        with self.assertRaisesRegex(TimeoutError, '等待超时'):
            turns.run('fixture', instructions='fixture', timeout=0)
        self.assertEqual(1, backend.close_count)
        self.assertFalse(turns.active)

    def test_closed_backend_is_not_reported_as_timeout(self):
        backend = BackendDouble(closed=True)
        turns = CandidateTurns(lambda **kwargs: backend)
        with self.assertRaisesRegex(BackendError, '连接已关闭') as raised:
            turns.run('fixture', instructions='fixture', timeout=60)
        self.assertNotIn('超时', str(raised.exception))
        self.assertFalse(turns.active)
