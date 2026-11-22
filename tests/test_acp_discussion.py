"""Source Discussions through Host operations and a subprocess ACP substitute."""
import ctypes
import json
import os
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import reading_fixture
from host.backends.registry import HarnessRegistry
from host.backends.base import BackendError
from acp_protocol_fixture import AcpProtocolFixture
from workspace_fixture import HostService


class AcpDiscussionTests(unittest.TestCase):
    def setUp(self):
        fixture = reading_fixture.ReadingFixture()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.workspace = fixture._workspace()[0]
        self.log_path = fixture.root / 'acp.jsonl'
        manifests = fixture.root / 'backends'
        manifests.mkdir()
        substitute = Path(__file__).with_name('acp_runtime_fixture.py')
        for transport in ('http', 'stdio'):
            (manifests / f'{transport}.json').write_text(json.dumps({
                'id': f'acp-{transport}', 'label': f'Fixture {transport}', 'driver': 'acp',
                'command': [sys.executable, str(substitute), transport, str(self.log_path)],
                'defaultModel': 'selected-model', 'capabilities': {'streaming': transport == 'http'},
            }), encoding='utf-8')
        self.host = HostService(self.workspace, fixture.root / 'host', backend='acp-http',
                                registry=HarnessRegistry(manifests))
        self.addCleanup(self.host.close)

    def start(self, request, content):
        selected = self.host.select_discussion_source('fixture-paper')
        self.host.start({'requestId': request, 'sourceId': 'fixture-paper',
                         'sessionId': selected['sessionId'], 'content': content})

    def finished(self, status):
        self.host.worker.join(12)
        self.assertFalse(self.host.worker.is_alive(), 'discussion did not finish')
        snapshot = self.host.snapshot()
        self.assertEqual(status, snapshot['agent']['run']['status'], snapshot['agent']['run'])
        return snapshot

    def turn(self, number):
        self.start(f'fixture-acp-turn-{number}', f'Explain fixture question {number}.')
        return self.finished('completed')

    def events(self):
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text(encoding='utf-8').splitlines()]

    def approval(self, *, expired=False, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.host.snapshot()['agent']['run']
            matched = [item for item in run['approvals'] if (item.get('status') == 'expired') == expired]
            if matched:
                return matched[0]
            time.sleep(.03)
        self.fail(f'Expected {"expired" if expired else "active"} approval: {run}')

    def test_fresh_sessions_use_host_history_and_both_mcp_transports(self):
        first = self.turn(1)
        self.assertEqual('Evidence: The alias address keeps source order.', first['conversation'][-1]['content'])
        second = self.turn(2)
        # Exercise loading an already-compacted prefix without another summary request.
        discussion_id = first['conversation'][0]['discussionId']
        with self.host.lock:
            self.host.state['discussions'][discussion_id].update(
                summary='Summary of the first completed question.',
                summaryThrough=first['conversation'][-1]['messageId'])
            self.host.changed()
        self.host.save_configuration({'backend': 'acp-stdio'})
        third = self.turn(3)
        self.assertEqual(discussion_id, third['conversation'][-1]['discussionId'])
        self.assertEqual(6, len(third['conversation']))
        self.assertEqual(first['conversation'][-1]['content'], third['conversation'][-1]['content'])
        self.assertEqual([], third['sourceNotes'])
        for snapshot in (first, second, third):
            run = snapshot['agent']['run']
            self.assertEqual('process_closed', run['runtimeCleanup']['release'])
            self.assertTrue(any(activity['title'] == 'mcpToolCall' and activity['status'] == 'completed'
                                for activity in run['activity']))

        turns = [event for event in self.events() if event['kind'] == 'discussion']
        self.assertEqual(['http', 'http', 'stdio'], [turn['transport'] for turn in turns])
        self.assertEqual(3, len({turn['pid'] for turn in turns}))
        self.assertEqual(3, len({turn['session'] for turn in turns}))
        self.assertIn('Explain fixture question 1.', turns[1]['prompt'])
        self.assertIn('Summary of the first completed question.', turns[2]['prompt'])
        self.assertNotIn('Explain fixture question 1.', turns[2]['prompt'])
        self.assertIn('Explain fixture question 2.', turns[2]['prompt'])
        self.assertIn('Evidence: The alias address keeps source order.', turns[2]['prompt'])
        self.assertIn('fixture-paper', turns[2]['prompt'])
        for turn in turns:
            self.assertEqual('["fixture-provider","selected-model"]', turn['model'])
            self.assertEqual('The alias address keeps source order.', turn['read'])
            self.assertTrue(turn['deniedWrite'])
            self.assertFalse(Path(turn['cwd']).exists())
            self.assertTrue(process_exited(turn['pid']))

    def test_runtime_disconnect_expires_confirmation_and_retry_requires_a_new_answer(self):
        self.start('fixture-acp-disconnect', 'expiry-disconnect')
        old = self.approval()
        self.assertEqual(['accept', 'decline'], old['choices'])
        self.assertIn('Inspect selected fixture', old['detail'])
        self.log_path.with_suffix('.release').touch()
        failed = self.finished('failed')
        self.assertEqual(old['id'], self.approval(expired=True)['id'])
        with self.assertRaisesRegex(ValueError, '本次请求已过期，请重试'):
            self.host.approve({'approvalId': old['id'], 'decision': 'accept'})
        disconnected = next(event for event in self.events() if event['kind'] == 'expiry-disconnect')
        self.assertTrue(process_exited(disconnected['pid']))
        self.assertTrue(process_exited(disconnected['childPid']))
        self.assertFalse(Path(disconnected['cwd']).exists())

        self.start('fixture-acp-retry', 'retry-approval')
        new = self.approval()
        self.assertNotEqual(old['id'], new['id'])
        with self.assertRaisesRegex(ValueError, '本次请求已过期，请重试'):
            self.host.approve({'approvalId': old['id'], 'decision': 'accept'})
        self.host.approve({'approvalId': new['id'], 'decision': 'accept'})
        retry = self.finished('completed')
        self.assertEqual(failed['conversation'][0]['discussionId'], retry['conversation'][-1]['discussionId'])
        self.assertEqual('Fresh approval received.', retry['conversation'][-1]['content'])
        answers = [event['decision'] for event in self.events() if event['kind'] == 'permission-answer']
        self.assertEqual([{'outcome': 'selected', 'optionId': 'one'}], answers)

    def test_a_verified_bare_model_cannot_route_a_followup_to_a_different_provider(self):
        self.turn(1)
        self.log_path.with_suffix('.route').write_text('other-provider', encoding='utf-8')
        # A deliberate setup check can show that the new route works. It only
        # updates the candidate receipt and may not retarget an active discussion.
        check = self.host.backend_setup('check', {'backend': 'acp-http', 'model': 'selected-model'})
        self.assertEqual('success', check['status'], check)
        self.start('fixture-model-drift', 'Follow-up must not reach the new provider.')
        failed = self.finished('failed')
        self.assertEqual('selected-model', failed['configuration']['effective']['model'])
        self.assertIn('已验证的 ACP 模型', failed['agent']['run']['error'])
        self.assertEqual(1, sum(event['kind'] == 'discussion' for event in self.events()))
        self.assertNotIn('Follow-up must not reach', json.dumps(self.events()))

    def test_stop_cancels_pending_permission_and_releases_descendant(self):
        self.start('fixture-acp-cancel', 'cancel-approval')
        approval = self.approval()
        self.host.stop()
        snapshot = self.finished('interrupted')
        self.assertEqual(approval['id'], self.approval(expired=True)['id'])
        self.assertEqual('process_closed', snapshot['agent']['run']['runtimeCleanup']['release'])
        events = self.events()
        self.assertIn({'outcome': 'cancelled'}, [event.get('decision') for event in events])
        cancelled = next(event for event in events if event['kind'] == 'cancel-approval')
        self.assertTrue(process_exited(cancelled['pid']))
        self.assertTrue(process_exited(cancelled['childPid']))
        self.assertFalse(Path(cancelled['cwd']).exists())

    def test_stop_during_prompt_submission_closes_transport_without_sending_cancel_first(self):
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        wire = []

        class GatedProtocol(AcpProtocolFixture):
            def request_event(self, method, params, **options):
                entered.set()
                release.wait(4)
                cancelled = options.get('cancelled')
                if self.closed or (cancelled and cancelled.is_set()):
                    raise RuntimeError('Fixture writer interrupted')
                wire.append(method)
                return super().request_event(method, params)

            def send(self, value):
                wire.append(value.get('method'))
                return super().send(value)

            def close(self):
                super().close()
                closed.set()

        backend = self.host.registry.create_backend('acp-http', self.workspace, purpose='candidate', tools=[])
        self.addCleanup(backend.close)
        with patch('host.backends.acp.JsonRpcStdioClient', GatedProtocol), ThreadPoolExecutor(2) as pool:
            backend.open_session(None, instructions='Fixture')
            turn = pool.submit(backend.start_turn, prompt='Do not send this content')
            try:
                self.assertTrue(entered.wait(2))
                stopped = pool.submit(backend.interrupt)
                self.assertTrue(closed.wait(1), wire)
                stopped.result(timeout=2)
            finally:
                release.set()
            with self.assertRaises((BackendError, RuntimeError)):
                turn.result(timeout=2)
        self.assertEqual([], wire)

    def test_mcp_timeout_expires_confirmation_while_the_acp_turn_is_still_alive(self):
        self.start('fixture-acp-mcp-expiry', 'mcp-disconnect')
        approval = self.approval()
        self.assertEqual(approval['id'], self.approval(expired=True)['id'])
        self.assertEqual('running', self.host.snapshot()['agent']['run']['status'])
        with self.assertRaisesRegex(ValueError, '本次请求已过期，请重试'):
            self.host.approve({'approvalId': approval['id'], 'decision': 'accept'})
        self.log_path.with_suffix('.release').touch()
        self.finished('completed')


def process_exited(pid):
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32')
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return True
        try:
            return kernel.WaitForSingleObject(handle, 0) == 0
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False
