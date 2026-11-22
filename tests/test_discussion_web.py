"""Discussion-only native web tools, with bound Source authority preserved."""
import sys
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from host.backends.codex import CodexBackend
from acp_protocol_fixture import AcpProtocolFixture
from host.backends import create_backend


class RecordingAppServer:
    def __init__(self, command, *args, **kwargs):
        self.command, self.calls, self.events = command, {}, queue.Queue()

    def initialize(self):
        pass

    def send(self, message):
        pass

    def close(self):
        pass

    def request(self, method, params, **kwargs):
        self.calls[method] = params
        return {'account': {'type': 'chatgpt'}, 'thread': {'id': 'thread'}, 'turn': {'id': 'turn'}}


class DiscussionWebTests(unittest.TestCase):
    def test_codex_enables_live_web_only_for_discussion_and_keeps_readonly(self):
        for purpose in ('discussion', 'connectivity', 'candidate', 'business'):
            with self.subTest(purpose=purpose), tempfile.TemporaryDirectory() as root, \
                    patch('host.backends.codex.AppServer', RecordingAppServer), \
                    patch('host.backends.codex.codex_command', return_value=['codex']):
                backend = CodexBackend(Path(root), purpose=purpose)
                try:
                    backend.open_session(None, instructions='scope')
                    backend.start_turn(prompt='question')
                    rpc = backend.rpc
                    self.assertIn('web_search="live"' if purpose == 'discussion' else 'web_search="disabled"', rpc.command)
                    self.assertIn('features.shell_tool=false', rpc.command)
                    self.assertIn('features.apply_patch_freeform=false', rpc.command)
                    self.assertIn('mcp_servers={}', rpc.command)
                    self.assertEqual('readOnly', rpc.calls['turn/start']['sandboxPolicy']['type'])
                    self.assertEqual('never', rpc.calls['turn/start']['approvalPolicy'])
                    tools = rpc.calls['thread/start']['dynamicTools']
                    if purpose == 'discussion':
                        focus = next(t for t in tools if t['name'] == 'focus')
                        self.assertEqual(['search', 'read_range', 'cite', 'source_note'], focus['inputSchema']['properties']['action']['enum'])
                    if purpose in ('candidate', 'connectivity'):
                        self.assertEqual([], tools)
                finally:
                    backend.close()


    def test_acp_tool_activity_is_session_scoped_and_does_not_copy_results(self):
        class WebActivityRuntime(AcpProtocolFixture):
            def output(self, prompt):
                for session in ('another-session', self.session):
                    for status in ('in_progress', 'completed'):
                        self.events.put({'method': 'session/update', 'params': {'sessionId': session, 'update': {
                            'sessionUpdate': 'tool_call_update', 'toolCallId': 'tool-' + session,
                            'kind': 'fetch', 'title': 'Runtime web tool', 'status': status,
                            'rawOutput': 'untrusted page body'}}})
                return 'Fixture answer.', 'end_turn'

        with tempfile.TemporaryDirectory() as directory, patch('host.backends.acp.JsonRpcStdioClient', WebActivityRuntime):
            backend = create_backend('deepseek', Path(directory), runtime_path=sys.executable, purpose='discussion')
            try:
                backend.open_session(None, instructions='Only use public web content.')
                backend.start_turn(prompt='Report tool activity.')
                activity = []
                while True:
                    event = backend.events.get(timeout=3)
                    if event['method'] == 'turn/completed':
                        break
                    if event['method'] == 'activity':
                        activity.append(event['params'])
                self.assertEqual(['inProgress', 'completed'], [item['status'] for item in activity])
                self.assertEqual(['', ''], [item['detail'] for item in activity])
                self.assertTrue(all(item['id'] != 'tool-another-session' for item in activity))
            finally:
                backend.close()
