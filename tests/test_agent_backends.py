"""Backend selection and the WorkBuddy adapter, driven by an injected fake SDK.

Nothing here contacts WorkBuddy: `codebuddy_agent_sdk` is replaced by a double
that implements the documented surface (CodeBuddySDKClient, create_sdk_mcp_server,
`tool`, can_use_tool, message types). The assertions therefore pin the mapping
between the SDK and the backend-neutral vocabulary the Host already speaks.
"""
import asyncio
import json
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import test_focus_read
from host.backends import BACKENDS, BackendError, create_backend, check_backend
from host.backends.base import ACTIVITY, COMMAND_APPROVAL, TURN_COMPLETED, USER_INPUT
from host.backends.codex import CodexBackend
from host.backends.codebuddy import CodeBuddyBackend
from host.backends.workbuddy import WorkBuddyBackend
from host.proxy import apply_proxy, proxy_mode, backend_environment
from host.service import HostService


# --------------------------------------------------------------------------- fake SDK


@dataclass
class TextBlock:
    text: str


@dataclass
class ThinkingBlock:
    thinking: str
    signature: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: Any = None
    is_error: bool | None = None


@dataclass
class AssistantMessage:
    content: list
    model: str = 'fake-model'
    parent_tool_use_id: str | None = None
    error: str | None = None


@dataclass
class UserMessage:
    content: Any = None
    uuid: str | None = None
    parent_tool_use_id: str | None = None


@dataclass
class SystemMessage:
    subtype: str
    data: dict


@dataclass
class ResultMessage:
    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    total_cost_usd: float | None = None
    usage: dict | None = None
    result: str | None = None
    errors: list | None = None


@dataclass
class StreamEvent:
    uuid: str
    session_id: str
    event: dict
    parent_tool_use_id: str | None = None


@dataclass
class CodeBuddyAgentOptions:
    env: dict = field(default_factory=dict)
    allowed_tools: list = field(default_factory=list)
    disallowed_tools: list = field(default_factory=list)
    system_prompt: Any = None
    mcp_servers: dict = field(default_factory=dict)
    permission_mode: str | None = None
    resume: str | None = None
    model: str | None = None
    cwd: Any = None
    include_partial_messages: bool = False
    persist_session: bool = True
    setting_sources: list | None = None
    can_use_tool: Any = None


@dataclass
class AppendSystemPrompt:
    append: str


@dataclass
class PermissionResultAllow:
    updated_input: dict
    behavior: str = 'allow'


@dataclass
class PermissionResultDeny:
    message: str
    behavior: str = 'deny'
    interrupt: bool = False


@dataclass
class FakeTool:
    name: str
    description: str
    schema: Any
    handler: Any


@dataclass
class FakeServer:
    name: str
    tools: list


class FakeClient:
    last = None

    def __init__(self, options=None):
        self.options = options
        self.prompts = []
        self.interrupted = False
        self.disconnected = False
        self.queue = asyncio.Queue()
        self.connected = False
        FakeClient.last = self

    async def connect(self, prompt=None):
        self.connected = True
        self.prompts.append(prompt)

    async def query(self, prompt, session_id='default'):
        self.prompts.append(prompt)

    def receive_messages(self):
        return self._generate()

    async def _generate(self):
        while True:
            message = await self.queue.get()
            if message is None:
                return
            yield message

    async def interrupt(self):
        self.interrupted = True

    async def disconnect(self):
        self.disconnected = True


def fake_tool(name, description, schema):
    def decorate(handler):
        return FakeTool(name=name, description=description, schema=schema, handler=handler)
    return decorate


def fake_create_sdk_mcp_server(name, tools):
    return FakeServer(name=name, tools=list(tools))


def build_fake_sdk():
    module = ModuleType('codebuddy_agent_sdk')
    module.__version__ = '0.0.0-test'
    module.CodeBuddySDKClient = FakeClient
    module.CodeBuddyAgentOptions = CodeBuddyAgentOptions
    module.AppendSystemPrompt = AppendSystemPrompt
    module.PermissionResultAllow = PermissionResultAllow
    module.PermissionResultDeny = PermissionResultDeny
    module.create_sdk_mcp_server = fake_create_sdk_mcp_server
    module.tool = fake_tool
    for name in ('AssistantMessage', 'UserMessage', 'SystemMessage', 'ResultMessage', 'StreamEvent',
                 'TextBlock', 'ThinkingBlock', 'ToolUseBlock', 'ToolResultBlock'):
        setattr(module, name, globals()[name])
    return module


def push(backend, message):
    """Hand a message to the SDK drain loop from the test thread."""
    asyncio.run_coroutine_threadsafe(FakeClient.last.queue.put(message), backend._loop).result(timeout=5)


def sdk_backend(workspace, **options):
    return CodeBuddyBackend(workspace, **{k: v for k, v in options.items() if k in CodeBuddyBackend.option_keys})


def wait_for(predicate, description, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError(f'Timed out waiting for {description}')
        time.sleep(.01)


# --------------------------------------------------------------------------- tests


class BackendRegistryTests(unittest.TestCase):
    def test_registry_exposes_both_runtimes_and_rejects_unknown(self):
        self.assertEqual(['codex', 'workbuddy'], sorted(BACKENDS))
        with self.assertRaisesRegex(BackendError, '未知 Agent 后端'):
            create_backend('gemini', Path(tempfile.gettempdir()))

    def test_options_are_filtered_per_adapter(self):
        workspace = Path(tempfile.gettempdir())
        backend = create_backend('workbuddy', workspace, codex_bin='must-not-be-passed', model='m')
        self.assertIsInstance(backend, WorkBuddyBackend)
        self.assertEqual('m', backend.model)
        self.assertFalse(hasattr(backend, 'codex_bin'))
        backend.close()

    def test_codex_declares_codex_bin_option(self):
        self.assertIn('codex_bin', CodexBackend.option_keys)

    def test_domestic_workbuddy_never_substitutes_codebuddy_sdk(self):
        with self.assertRaisesRegex(BackendError, '开放平台'):
            check_backend('workbuddy')
        backend = create_backend('workbuddy', Path(tempfile.gettempdir()))
        with self.assertRaisesRegex(BackendError, 'CodeBuddy CLI 登录不能替代'):
            backend.open_session(None, instructions='test')


class CodeBuddyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.sdk = build_fake_sdk()
        self.previous = sys.modules.get('codebuddy_agent_sdk')
        sys.modules['codebuddy_agent_sdk'] = self.sdk
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        FakeClient.last = None

    def tearDown(self):
        sys.modules.pop('codebuddy_agent_sdk', None)
        if self.previous is not None:
            sys.modules['codebuddy_agent_sdk'] = self.previous
        self.tmp.cleanup()

    def open(self, backend, resume_key=None):
        key = backend.open_session(resume_key, instructions='FOCUS reading host',
                                   skills=[('focus-read', 'C:/repo/.agents/skills/focus-read/SKILL.md')])
        return key

    def test_open_session_builds_clean_room_options_and_resumes(self):
        backend = CodeBuddyBackend(self.workspace, network=False, model='deepseek-v3.1')
        try:
            self.open(backend, resume_key='session-1')
            options = FakeClient.last.options
            self.assertEqual('session-1', options.resume)
            self.assertEqual('deepseek-v3.1', options.model)
            self.assertEqual([], options.setting_sources)          # no user/project config leakage
            self.assertEqual('default', options.permission_mode)   # asks only when runtime requires permission
            self.assertEqual(['WebFetch', 'WebSearch'], options.disallowed_tools)
            self.assertTrue(options.include_partial_messages)
            self.assertIn('focus', options.mcp_servers)
            self.assertIsInstance(options.system_prompt, AppendSystemPrompt)
            self.assertIn('focus-read', options.system_prompt.append)
            # The focus tool is exposed in-process, not as a second MCP process.
            tool = options.mcp_servers['focus'].tools[0]
            self.assertEqual('focus', tool.name)
            self.assertEqual({'action': str, 'arguments': str}, tool.schema)
        finally:
            backend.close()

    def test_network_mode_keeps_web_tools(self):
        backend = CodeBuddyBackend(self.workspace, network=True)
        try:
            self.open(backend)
            self.assertEqual([], FakeClient.last.options.disallowed_tools)
        finally:
            backend.close()

    def test_missing_sdk_fails_with_install_hint(self):
        original = sys.modules.pop('codebuddy_agent_sdk')
        self.assertIsNot(original, None)
        backend = CodeBuddyBackend(self.workspace)
        try:
            with self.assertRaisesRegex(BackendError, 'codebuddy-agent-sdk'):
                self.open(backend)
        finally:
            backend.close()

    def test_start_turn_forwards_prompt(self):
        backend = CodeBuddyBackend(self.workspace)
        try:
            self.open(backend)
            backend.start_turn(prompt='读取当前段')
            wait_for(lambda: any('读取当前段' in prompt for prompt in FakeClient.last.prompts if prompt),
                     'prompt to reach the SDK')
        finally:
            backend.close()

    def answer(self, backend, method, result, timeout=5):
        event = backend.events.get(timeout=timeout)
        self.assertEqual(method, event['method'], event)
        backend.send({'id': event['id'], 'result': result})
        return event

    def test_focus_tool_round_trip_reaches_host(self):
        backend = CodeBuddyBackend(self.workspace)
        try:
            self.open(backend)
            tool = FakeClient.last.options.mcp_servers['focus'].tools[0]
            future = asyncio.run_coroutine_threadsafe(
                tool.handler({'action': 'catalog', 'arguments': '{}'}), backend._loop)
            request = backend.events.get(timeout=5)
            self.assertEqual('tool/call', request['method'])
            self.assertEqual({'action': 'catalog', 'arguments': '{}'}, request['params']['arguments'])
            backend.send({'id': request['id'], 'result': {'success': True, 'text': '{"sources": []}'}})
            payload = future.result(timeout=5)
            self.assertEqual('{"sources": []}', payload['content'][0]['text'])
        finally:
            backend.close()

    def test_focus_tool_never_prompts_for_permission(self):
        backend = CodeBuddyBackend(self.workspace)
        try:
            self.open(backend)
            future = asyncio.run_coroutine_threadsafe(
                backend._can_use_tool('mcp__focus__focus', {'action': 'catalog'}, None), backend._loop)
            result = future.result(timeout=5)
            self.assertEqual('allow', result.behavior)
            self.assertTrue(backend.events.empty())
        finally:
            backend.close()

    def test_declined_tool_use_denies_permission(self):
        backend = CodeBuddyBackend(self.workspace)
        try:
            self.open(backend)
            future = asyncio.run_coroutine_threadsafe(
                backend._can_use_tool('Bash', {'command': 'pytest'}, None), backend._loop)
            event = self.answer(backend, COMMAND_APPROVAL, {'decision': 'decline'})
            self.assertIn('Bash', event['params']['title'])
            result = future.result(timeout=5)
            self.assertEqual('deny', result.behavior)
        finally:
            backend.close()

    def test_edit_tools_use_the_file_approval_kind(self):
        backend = CodeBuddyBackend(self.workspace)
        try:
            self.open(backend)
            future = asyncio.run_coroutine_threadsafe(
                backend._can_use_tool('Edit', {'file_path': 'a.py'}, None), backend._loop)
            self.answer(backend, 'file/approval', {'decision': 'accept'})
            self.assertEqual('allow', future.result(timeout=5).behavior)
        finally:
            backend.close()

    def test_ask_user_question_round_trip(self):
        backend = CodeBuddyBackend(self.workspace)
        try:
            self.open(backend)
            future = asyncio.run_coroutine_threadsafe(backend._can_use_tool('AskUserQuestion', {
                'questions': [{'question': '用哪个模型？', 'header': '模型',
                               'options': [{'label': 'deepseek', 'description': '快'}], 'multiSelect': False}]}, None),
                backend._loop)
            event = self.answer(backend, USER_INPUT, {'answers': {'模型': {'answers': ['deepseek']}}})
            self.assertEqual('模型', event['params']['questions'][0]['id'])
            result = future.result(timeout=5)
            self.assertEqual('allow', result.behavior)
            self.assertEqual({'用哪个模型？': ['deepseek']}, result.updated_input['answers'])
        finally:
            backend.close()

    def test_streaming_text_activity_and_result_projections(self):
        backend = CodeBuddyBackend(self.workspace)
        try:
            self.open(backend)
            push(backend, StreamEvent('u1', 'session-9',
                                      {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': '真实 Core，'}}))
            push(backend, AssistantMessage([ToolUseBlock('tool-1', 'Bash', {'command': 'ls'})]))
            push(backend, StreamEvent('u2', 'session-9',
                                      {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': 'SDK 替身。'}}))
            push(backend, AssistantMessage([TextBlock('真实 Core，SDK 替身。')]))
            push(backend, UserMessage([ToolResultBlock('tool-1', [{'type': 'text', 'text': 'ok'}])]))
            seen = [backend.events.get(timeout=5) for _ in range(4)]
            self.assertEqual(['message/delta', ACTIVITY, 'message/delta', 'message/completed'],
                             [e['method'] for e in seen])
            self.assertEqual(seen[0]['params']['itemId'], seen[3]['params']['itemId'])
            self.assertEqual('真实 Core，SDK 替身。', seen[3]['params']['text'])
            self.assertEqual('Bash', seen[1]['params']['title'])
            self.assertEqual('inProgress', seen[1]['params']['status'])

            push(backend, ResultMessage('success', 10, 10, False, 1, 'session-9', result='done'))
            opened, completed = backend.events.get(timeout=5), backend.events.get(timeout=5)
            self.assertEqual({'key': 'session-9'}, opened['params'])
            self.assertEqual(TURN_COMPLETED, completed['method'])
            self.assertEqual('completed', completed['params']['status'])
            self.assertEqual('session-9', backend.session_key)
        finally:
            backend.close()

    def test_failed_result_surfaces_errors(self):
        backend = CodeBuddyBackend(self.workspace)
        try:
            self.open(backend)
            push(backend, ResultMessage('error_during_execution', 1, 1, True, 1, 'session-9',
                                        errors=['额度不足']))
            opened, completed = backend.events.get(timeout=5), backend.events.get(timeout=5)
            self.assertEqual('session-9', opened['params']['key'])
            self.assertEqual('failed', completed['params']['status'])
            self.assertEqual('额度不足', completed['params']['error'])
        finally:
            backend.close()

    def test_close_releases_pending_round_trips(self):
        backend = CodeBuddyBackend(self.workspace)
        self.open(backend)
        future = asyncio.run_coroutine_threadsafe(
            backend._can_use_tool('Bash', {'command': 'pytest'}, None), backend._loop)
        backend.events.get(timeout=5)
        backend.close()
        self.assertEqual('deny', future.result(timeout=5).behavior)
        self.assertTrue(FakeClient.last.disconnected)


class CodeBuddyHostTests(unittest.TestCase):
    """One real HostService turn through the WorkBuddy backend and real Core."""

    def setUp(self):
        self.fixture = test_focus_read.FocusReadTests()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.data = self.fixture.root / 'host'
        self.sdk = build_fake_sdk()
        self.previous = sys.modules.get('codebuddy_agent_sdk')
        sys.modules['codebuddy_agent_sdk'] = self.sdk
        FakeClient.last = None
        self.host = HostService(self.workspace, self.data, backend='codebuddy', backend_factory=sdk_backend)
        self.receipt = {'sourceId': 'fixture-paper', 'planId': 'plan-001', 'chunkId': 'chunk-001'}

    def tearDown(self):
        self.host.close()
        sys.modules.pop('codebuddy_agent_sdk', None)
        if self.previous is not None:
            sys.modules['codebuddy_agent_sdk'] = self.previous
        self.fixture.tearDown()

    def wait(self, predicate):
        try:
            wait_for(predicate, repr(predicate))
        except AssertionError as exc:
            self.fail(str(exc) + ': ' + json.dumps(self.host.snapshot()['agent'], ensure_ascii=False))

    def test_workbuddy_turn_streams_and_writes_through_core(self):
        self.host.start({'requestId': 'workbuddy-1234', 'receipt': self.receipt, 'content': '记一条 Note'})
        self.wait(lambda: self.host.backend is not None and self.host.backend.client is not None)
        backend = self.host.backend
        client = FakeClient.last
        self.wait(lambda: any('记一条 Note' in prompt for prompt in client.prompts if prompt))

        push(backend, StreamEvent('u1', 'session-wb',
                                  {'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': '已保存。'}}))

        tool = client.options.mcp_servers['focus'].tools[0]
        arguments = json.dumps({'expected_plan_id': 'plan-001', 'expected_chunk_id': 'chunk-001',
                                'kind': 'clarification', 'origin': 'dialogue', 'content': 'WorkBuddy 后端写入。'})
        future = asyncio.run_coroutine_threadsafe(
            tool.handler({'action': 'append_note', 'arguments': arguments}), backend._loop)
        future.result(timeout=15)
        record = json.loads((self.workspace / 'sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json').read_text())
        self.assertEqual('WorkBuddy 后端写入。', record['notes'][0]['content'])
        self.assertFalse(self.host.advanced)  # a note never moves the Reading Cursor

        push(backend, ResultMessage('success', 1, 1, False, 1, 'session-wb', result='done'))
        self.host.worker.join(15)
        self.assertFalse(self.host.worker.is_alive())
        window = self.host.snapshot()
        self.assertEqual('completed', window['agent']['run']['status'])
        self.assertEqual('已保存。', window['conversation'][-1]['content'])
        self.assertEqual('session-wb', self.host.state['threadId'])
        self.assertEqual('codebuddy', self.host.state['resumeBackend'])

    def test_next_turn_resumes_only_in_the_same_backend(self):
        self.host.start({'requestId': 'workbuddy-1234', 'receipt': self.receipt, 'content': '你好'})
        self.wait(lambda: self.host.backend is not None and self.host.backend.client is not None)
        push(self.host.backend, ResultMessage('success', 1, 1, False, 1, 'session-wb', result='done'))
        self.host.worker.join(15)
        self.assertEqual('session-wb', self.host.state['threadId'])

        # A workspace previously driven by another runtime must not hand its key over.
        self.host.state['resumeBackend'] = 'codex'
        self.host.store.save()
        resumed = HostService(self.workspace, self.data, backend='codebuddy', backend_factory=sdk_backend)
        try:
            self.assertIsNone(resumed._resume_key())
        finally:
            resumed.close()


class ProxyRoutingTests(unittest.TestCase):
    """Codex keeps the user's VPN proxy; WorkBuddy must not be routed through it."""

    def env(self, **extra):
        base = {'HTTP_PROXY': 'http://127.0.0.1:59588', 'HTTPS_PROXY': 'http://127.0.0.1:59588',
                'http_proxy': 'http://127.0.0.1:59588', 'https_proxy': 'http://127.0.0.1:59588'}
        base.update(extra)
        return base

    def test_switching_does_not_destroy_inherited_proxy(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, self.env(), clear=True):
            workbuddy = backend_environment('workbuddy')
            self.assertEqual('', workbuddy['HTTPS_PROXY'])
            self.assertEqual('*', workbuddy['NO_PROXY'])
            codex = backend_environment('codex')
            self.assertEqual('http://127.0.0.1:59588', codex['HTTPS_PROXY'])
            self.assertEqual('http://127.0.0.1:59588', os.environ['HTTPS_PROXY'])

    def test_defaults_are_bypass_for_workbuddy_and_inherit_for_codex(self):
        self.assertEqual('bypass', proxy_mode('workbuddy', {}))
        self.assertEqual('inherit', proxy_mode('codex', {}))

    def test_workbuddy_drops_every_inherited_proxy_variable(self):
        env = self.env()
        note = apply_proxy('workbuddy', env)
        self.assertNotIn('HTTP_PROXY', env)
        self.assertNotIn('https_proxy', env)
        self.assertEqual('*', env['NO_PROXY'])
        self.assertEqual('*', env['no_proxy'])
        self.assertIn('绕过代理', note)
        self.assertIn('http://127.0.0.1:59588', note)

    def test_codex_inherits_by_default(self):
        env = self.env()
        self.assertEqual('', apply_proxy('codex', env))
        self.assertEqual('http://127.0.0.1:59588', env['HTTP_PROXY'])

    def test_codex_can_pin_an_explicit_proxy(self):
        env = self.env(FOCUS_CODEX_PROXY='http://127.0.0.1:7890')
        note = apply_proxy('codex', env)
        self.assertEqual('http://127.0.0.1:7890', env['HTTP_PROXY'])
        self.assertEqual('http://127.0.0.1:7890', env['https_proxy'])
        self.assertNotIn('no_proxy', env)
        self.assertIn('http://127.0.0.1:7890', note)

    def test_workbuddy_can_opt_back_in_when_the_account_needs_it(self):
        env = self.env(FOCUS_WORKBUDDY_PROXY='inherit')
        self.assertEqual('', apply_proxy('workbuddy', env))
        self.assertEqual('http://127.0.0.1:59588', env['HTTPS_PROXY'])
