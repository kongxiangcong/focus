"""Local ACP subprocess substitute. Talks wire JSON-RPC and the real MCP bridge."""
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import ExitStack
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener


def emit(**message):
    print(json.dumps({'jsonrpc': '2.0', **message}), flush=True)


class McpClient:
    def __init__(self, server, stack):
        self.transport = server.get('type', 'stdio')
        self.url = server.get('url')
        self.sequence = 0
        self.process = None
        self.http = build_opener(ProxyHandler({}))
        if self.transport == 'stdio':
            self.process = subprocess.Popen([server['command'], *server['args']],
                env={**os.environ, **{item['name']: item['value'] for item in server['env']}},
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8')
            stack.callback(self.close)
        self.rpc('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                                'clientInfo': {'name': 'fixture', 'version': '1'}})
        self.rpc('notifications/initialized', {}, notify=True)

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=3)
        self.process.stdout.close()

    def rpc(self, method, params, *, notify=False, timeout=6):
        self.sequence += 1
        request = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if not notify:
            request['id'] = self.sequence
        if self.process:
            self.process.stdin.write(json.dumps(request) + '\n')
            self.process.stdin.flush()
            return None if notify else json.loads(self.process.stdout.readline())['result']
        with self.http.open(Request(self.url, data=json.dumps(request).encode(), headers={
            'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
        }), timeout=timeout) as response:
            return None if notify else json.load(response)['result']

    def focus(self, action, arguments):
        return self.rpc('tools/call', {'name': 'focus', 'arguments': {
            'action': action, 'arguments': json.dumps(arguments)}})


def run(transport, log_path):
    session = uuid.uuid4().hex
    route = Path(log_path).with_suffix('.route')
    provider = route.read_text(encoding='utf-8') if route.exists() else 'fixture-provider'
    model = json.dumps([provider, 'default-model'], separators=(',', ':'))
    selected = json.dumps([provider, 'selected-model'], separators=(',', ':'))
    servers = []
    approval_prompt = None
    approval_id = 'fixture-native-permission'
    gate = Path(log_path).with_suffix('.release')

    def log_event(**fields):
        with open(log_path, 'a', encoding='utf-8') as log:
            log.write(json.dumps(fields) + '\n')

    def wait_for_release():
        deadline = time.monotonic() + 10
        while not gate.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('test fixture did not release the session')
            time.sleep(.02)

    def options():
        return [{'type': 'select', 'id': 'model', 'category': 'model', 'currentValue': model,
                 'options': [{'group': 'fixture', 'name': 'Fixture provider',
                              'options': [{'value': selected, 'name': 'Selected model'}]}]}]

    def update(**value):
        emit(method='session/update', params={'sessionId': session, 'update': value})

    for line in sys.stdin:
        message = json.loads(line)
        assert message['jsonrpc'] == '2.0'
        if 'method' not in message:
            assert message['id'] == approval_id
            decision = message['result']['outcome']
            log_event(kind='permission-answer', session=session, decision=decision)
            if decision.get('outcome') == 'selected' and approval_prompt:
                update(sessionUpdate='agent_message_chunk', content={'type': 'text', 'text': 'Fresh approval received.'})
                emit(id=approval_prompt, result={'stopReason': 'end_turn'})
                approval_prompt = None
            continue
        method, params = message['method'], message.get('params', {})
        if method == 'initialize':
            assert params['protocolVersion'] == 1
            assert not params.get('clientCapabilities', {}).get('fs')
            result = {'protocolVersion': 1, 'agentCapabilities': {'mcpCapabilities': {'http': transport == 'http'},
                          'sessionCapabilities': {'close': {}}}}
        elif method == 'session/new':
            assert os.path.isabs(params['cwd'])
            servers = params['mcpServers']
            cwd = params['cwd']
            result = {'sessionId': session, 'configOptions': options()}
        elif method == 'session/set_config_option':
            assert params == {'sessionId': session, 'configId': 'model', 'value': selected}
            model = params['value']
            result = {'configOptions': options()}
        elif method == 'session/prompt':
            prompt = '\n'.join(block['text'] for block in params['prompt'] if block['type'] == 'text')
            probe = 'FOCUS Source access check' in prompt
            instruction = next((flag for flag in ('expiry-disconnect', 'retry-approval', 'cancel-approval')
                                if f'\n\n{flag}\n' in prompt), None)
            if instruction and not probe:
                approval_prompt = message['id']
                update(sessionUpdate='tool_call', toolCallId='native', title='Inspect selected fixture',
                       kind='execute', status='pending')
                emit(method='session/request_permission', id=approval_id, params={
                    'sessionId': session, 'toolCall': {'toolCallId': 'native'},
                    'options': [{'optionId': 'one', 'kind': 'allow_once', 'name': 'Allow once'},
                                {'optionId': 'always', 'kind': 'allow_always', 'name': 'Allow always'},
                                {'optionId': 'deny', 'kind': 'reject_once', 'name': 'Reject'}],
                })
                child = None
                if instruction in ('expiry-disconnect', 'cancel-approval'):
                    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
                log_event(kind=instruction, session=session, pid=os.getpid(), cwd=cwd,
                          childPid=child.pid if child else None)
                if instruction == 'expiry-disconnect':
                    wait_for_release()
                    return
                continue
            if '\n\nmcp-disconnect\n' in prompt and not probe:
                with ExitStack() as stack:
                    mcp = McpClient(servers[0], stack)
                    assert mcp.transport == 'http'
                    log_event(kind='mcp-disconnect', session=session, pid=os.getpid(), cwd=cwd)
                    try:
                        mcp.rpc('tools/call', {'name': 'focus_confirm', 'arguments': {
                            'title': 'Confirm the fixture', 'detail': 'This connection expires.'
                        }}, timeout=1.5)
                        raise AssertionError('expected the MCP HTTP request to time out')
                    except (TimeoutError, URLError):
                        log_event(kind='mcp-expired', session=session)
                    wait_for_release()
                result = {'stopReason': 'end_turn'}
                emit(id=message['id'], result=result)
                continue
            with ExitStack() as stack:
                mcp = McpClient(servers[0], stack)
                assert mcp.transport == transport
                offered = mcp.rpc('tools/list', {})['tools']
                assert len(offered) == (1 if probe else 3)
                line_number = 1 if probe else 4
                update(sessionUpdate='tool_call', toolCallId='read-source', title='Read the source',
                       kind='read', status='in_progress')
                reply = mcp.focus('read_range', {'start': line_number, 'end': line_number})
                read = json.loads(reply['content'][0]['text'])['source_text']
                update(sessionUpdate='tool_call_update', toolCallId='read-source', status='completed')
                denied = True if probe else mcp.focus('source_note', {'content': 'Do not persist', 'kind': 'thought'})['isError']
            answer = read if probe else 'Evidence: ' + read
            chunks = (answer[:10], answer[10:]) if transport == 'http' else (answer,)
            for chunk in chunks:
                update(sessionUpdate='agent_message_chunk', messageId='native-answer',
                       content={'type': 'text', 'text': chunk})
            log_event(kind='probe' if probe else 'discussion', transport=transport, session=session,
                      pid=os.getpid(), cwd=cwd, model=model, read=read, deniedWrite=denied, prompt=prompt)
            result = {'stopReason': 'end_turn'}
        elif method == 'session/cancel':
            if approval_prompt:
                emit(id=approval_prompt, result={'stopReason': 'cancelled'})
            continue
        elif method == 'session/close':
            result = {}
        else:
            raise AssertionError(method)
        emit(id=message['id'], result=result)


if __name__ == '__main__':
    run(*sys.argv[1:])
