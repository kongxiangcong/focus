"""Source Discussions through Host operations and a subprocess ACP substitute."""
import ctypes
import json
import os
import sys
import unittest
from pathlib import Path

import reading_fixture
from host.backends.registry import HarnessRegistry
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

    def turn(self, number):
        selected = self.host.select_discussion_source('fixture-paper')
        self.host.start({'requestId': f'fixture-acp-turn-{number}', 'sourceId': 'fixture-paper',
                         'sessionId': selected['sessionId'], 'content': f'Explain fixture question {number}.'})
        self.host.worker.join(12)
        self.assertFalse(self.host.worker.is_alive(), 'discussion did not finish')
        snapshot = self.host.snapshot()
        self.assertEqual('completed', snapshot['agent']['run']['status'], snapshot['agent']['run'])
        return snapshot

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

        events = [json.loads(line) for line in self.log_path.read_text(encoding='utf-8').splitlines()]
        turns = [event for event in events if event['kind'] == 'discussion']
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
