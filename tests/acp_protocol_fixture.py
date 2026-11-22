"""ACP transport substitute for Host workflow scenarios with real ToolBridge."""
import json
import queue
import sys
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.request import ProxyHandler, Request, build_opener

from host.backends.registry import HarnessRegistry


class AcpProtocolFixture:
    def __init__(self, command, cwd, *, env=None, **options):
        self.command = command
        self.cwd = Path(cwd)
        self.env = env
        self.events = queue.Queue()
        self.closed = False
        self.process = self
        self.session = uuid.uuid4().hex
        self.pending_prompt = None
        self.calls = []
        self.tool_sequence = 0

    def poll(self):
        return 0 if self.closed else None

    def request(self, method, params, **options):
        self.calls.append((method, params))
        if method == 'initialize':
            return {'protocolVersion': 1, 'agentCapabilities': {'mcpCapabilities': {'http': True}}}
        if method == 'session/new':
            self.mcp_url = params['mcpServers'][0]['url'] if params['mcpServers'] else None
            return {'sessionId': self.session}
        if method == 'session/set_model':
            return {}
        raise AssertionError(method)

    def request_event(self, method, params, *, cancelled=None):
        assert method == 'session/prompt'
        if self.closed or (cancelled and cancelled.is_set()):
            raise RuntimeError('Fixture writer interrupted')
        self.calls.append((method, params))
        self.pending_prompt = request_id = 1
        content = params['prompt'][0]['text']

        def respond():
            try:
                if content.startswith('This is a FOCUS Source access check.'):
                    reply = self.focus('read_range', {'start': 1, 'end': 1})
                    assert not reply['isError'], reply
                    text, reason = json.loads(reply['content'][0]['text'])['source_text'], 'end_turn'
                else:
                    _, json_separator, data = content.partition('\n\n{')
                    text, reason = self.output('{' + data if json_separator and data.startswith('"task"') else content)
                if not self.closed and self.pending_prompt:
                    self.events.put({'method': 'session/update', 'params': {'sessionId': self.session, 'update': {
                        'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': text}}}})
                    self.events.put({'id': request_id, 'result': {'stopReason': reason}})
                    self.pending_prompt = None
            except Exception as exc:
                self.events.put({'id': request_id, 'error': {'message': str(exc)}})

        threading.Thread(target=respond, daemon=True).start()
        return request_id

    def output(self, content):
        raise AssertionError('Fixture received an unexpected model turn.')

    def tool(self, name, arguments):
        self.tool_sequence += 1
        request = Request(self.mcp_url, data=json.dumps({'jsonrpc': '2.0', 'id': self.tool_sequence,
            'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}).encode(),
            headers={'Content-Type': 'application/json'})
        with build_opener(ProxyHandler({})).open(request, timeout=8) as response:
            return json.load(response)['result']

    def focus(self, action, arguments):
        return self.tool('focus', {'action': action, 'arguments': json.dumps(arguments)})

    def send(self, value):
        if value.get('method') == 'session/cancel' and self.pending_prompt:
            self.events.put({'id': self.pending_prompt, 'result': {'stopReason': 'cancelled'}})
            self.pending_prompt = None

    def close(self):
        self.closed = True
        self.events.put({'method': '_transport_error', 'params': {'message': 'Fixture closed.'}})


@contextmanager
def acp_runtime(substitute):
    discover = HarnessRegistry._discover_binary

    def discover_fixture(registry, spec):
        return sys.executable if spec.id == 'deepseek' else discover(registry, spec)

    with patch('host.backends.acp.JsonRpcStdioClient', substitute), patch.object(
            HarnessRegistry, '_discover_binary', discover_fixture):
        yield
