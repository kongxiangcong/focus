"""Discussion-only native web tools, with bound Source authority preserved."""
import json
import os
import queue
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from host.backends.codex import CodexBackend
from host.backends.deepseek import DeepSeekBackend
from host.progress import activity_label


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
                        self.assertEqual(['search', 'read_range', 'source_note'], focus['inputSchema']['properties']['action']['enum'])
                    if purpose in ('candidate', 'connectivity'):
                        self.assertEqual([], tools)
                finally:
                    backend.close()

    def test_deepseek_native_web_events_are_scoped_and_do_not_copy_page_bodies(self):
        backend = DeepSeekBackend(Path(tempfile.gettempdir()), purpose='discussion')
        backend.session_id = 'owned'

        def notify(event, session='owned'):
            backend._notification(SimpleNamespace(method='session.event', payload={'sessionId': session, 'event': event}))

        try:
            notify({'type': 'tool/call', 'data': {'callId': 'foreign', 'name': 'web_search'}}, 'other')
            self.assertTrue(backend.events.empty())
            for name, title in [('web_search', 'webSearch'), ('web_fetch', 'webFetch')]:
                notify({'type': 'tool/call', 'data': {'callId': name, 'name': name}})
                event = backend.events.get_nowait()['params']
                self.assertEqual((title, 'inProgress'), (event['title'], event['status']))
                notify({'type': 'tool/result', 'data': {'message': {'content': [
                    {'type': 'tool-result', 'toolCallId': name, 'isError': name == 'web_fetch',
                     'content': [{'type': 'text', 'text': 'untrusted page body'}]}]}}})
                event = backend.events.get_nowait()['params']
                self.assertEqual('failed' if name == 'web_fetch' else 'completed', event['status'])
                self.assertEqual('', event['detail'])
                self.assertEqual('联网搜索' if name == 'web_search' else '读取网页', activity_label(event))
            backend.close()
            notify({'type': 'tool/call', 'data': {'callId': 'late', 'name': 'web_search'}})
            self.assertFalse(backend._web_calls)
        finally:
            backend.close()


@unittest.skipUnless(os.getenv('FOCUS_TEST_REAL_DEEPSEEK_RUNTIME') == '1', 'opt-in real SDK with loopback provider fixtures')
class NativeDeepSeekWebTests(unittest.TestCase):
    def test_actual_runtime_catalog_search_fetch_failure_and_non_discussion_isolation(self):
        """Real SDK/tools; only the two model HTTP endpoints are fixtures."""
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, body))
                self.send_response(200)
                if self.path.endswith('/messages'):
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'content': [{'type': 'web_search_tool_result', 'content': [
                        {'type': 'web_search_result', 'url': 'https://example.com/official', 'title': 'Official evidence'}]}]}).encode())
                    return
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                tools = [t['function']['name'] for t in body.get('tools', [])]
                messages = body.get('messages', [])
                if 'web_search' in tools and not any(m.get('role') == 'tool' for m in messages):
                    delta = {'role': 'assistant', 'tool_calls': [
                        {'index': 0, 'id': 'search-1', 'type': 'function', 'function': {
                            'name': 'web_search', 'arguments': json.dumps({'queries': ['public mechanism']})}},
                        {'index': 1, 'id': 'fetch-1', 'type': 'function', 'function': {
                            'name': 'web_fetch', 'arguments': json.dumps({'url': 'http://127.0.0.1/private'})}}]}
                    finish = 'tool_calls'
                else:
                    delta, finish = {'role': 'assistant', 'content': 'Fixture answer.'}, 'stop'
                for value in [dict(delta=delta, finish_reason=None), dict(delta={}, finish_reason=finish)]:
                    chunk = {'id': 'fixture', 'object': 'chat.completion.chunk', 'choices': [dict(index=0, **value)]}
                    self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with patch.dict(os.environ, {'DEEPSEEK_BASE_URL': base, 'DEEPSEEK_SEARCH_BASE_URL': base + '/anthropic/v1'}):
                for purpose in ('discussion', 'candidate', 'connectivity', 'business'):
                    with self.subTest(purpose=purpose), tempfile.TemporaryDirectory() as root:
                        requests.clear()
                        backend = DeepSeekBackend(Path(root), purpose=purpose, api_key='fixture-only')
                        try:
                            backend.open_session(None, instructions='Fixture instructions.')
                            backend.start_turn(prompt='Fixture prompt.')
                            events = []
                            while True:
                                event = backend.events.get(timeout=30)
                                events.append(event)
                                if event['method'] in ('turn/completed', '_transport_error'):
                                    break
                            self.assertEqual('turn/completed', events[-1]['method'], events)
                            self.assertIsNone(events[-1]['params']['error'])
                            chat = [body for path, body in requests if path.endswith('/chat/completions')]
                            names = {t['function']['name'] for t in chat[0].get('tools', [])}
                            self.assertFalse(names & {'bash', 'pwsh', 'read', 'write', 'edit', 'run_code'})
                            if purpose == 'discussion':
                                self.assertEqual({'mcp__focus__focus', 'mcp__focus__focus_confirm', 'mcp__focus__focus_user_input', 'web_search', 'web_fetch'}, names)
                                self.assertTrue(any(path.endswith('/messages') for path, _ in requests))
                                results = [m for m in chat[-1]['messages'] if m.get('role') == 'tool']
                                self.assertIn('https://example.com/official', json.dumps(results))
                                self.assertIn('non-public', json.dumps(results).lower())
                                activity = [e['params'] for e in events if e['method'] == 'activity']
                                self.assertEqual({'webSearch', 'webFetch'}, {a['title'] for a in activity})
                                self.assertEqual('completed', next(a for a in reversed(activity) if a['title'] == 'webSearch')['status'])
                                self.assertEqual('failed', next(a for a in reversed(activity) if a['title'] == 'webFetch')['status'])
                                self.assertFalse(backend._web_calls)
                            else:
                                self.assertFalse(names & {'web_search', 'web_fetch'})
                                if purpose in ('candidate', 'connectivity'):
                                    self.assertFalse(names)
                        finally:
                            backend.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
