"""CodeBuddy Agent SDK backend: official Python SDK translated to Host vocabulary.

Why this file exists: see `research/agent-backend-integration-options.md`. The SDK
gives the Host in-process tools (`create_sdk_mcp_server`) and a single approval
callback (`can_use_tool`), which map cleanly onto the FOCUS `focus` Core tool and
the browser approval flow. It has no 1:1 equivalent of Codex `workspace-write`;
tool requests requiring confirmation are routed through `can_use_tool`.
Deploy this runtime in an isolated environment when OS-level confinement is required.

`codebuddy_agent_sdk` is imported lazily and stays an optional dependency: the
Codex backend and every test run without it installed.
"""
import asyncio
import json
import threading
from ..proxy import backend_environment

from .base import (ACTIVITY, Backend, BackendError, COMMAND_APPROVAL, FILE_APPROVAL, MESSAGE_COMPLETED,
                   MESSAGE_DELTA, SESSION_OPENED, TOOL_CALL, TURN_COMPLETED, USER_INPUT, new_item_id)

FOCUS_TOOL = 'focus'
ASK_USER_QUESTION = 'AskUserQuestion'
EDIT_TOOLS = frozenset({'Write', 'Edit', 'MultiEdit', 'NotebookEdit'})
NETWORK_TOOLS = ('WebFetch', 'WebSearch')

INSTALL_HINT = ('未安装 codebuddy_agent_sdk。选择 workbuddy 后端时先执行 '
                'pip install codebuddy-agent-sdk，并配置 CODEBUDDY_API_KEY。')

FOCUS_TOOL_DESCRIPTION = ('FOCUS Core 是阅读资产的唯一权威。arguments 是编码为 JSON 字符串的 object；'
                          '传入 action 与对应字段，不要直接编辑 state.json、Reading Plan 或 Reading Record。')


class CodeBuddyBackend(Backend):
    name = 'codebuddy'
    option_keys = Backend.option_keys
    connect_timeout = 180
    answer_timeout = 3600

    def __init__(self, workspace, *, network=False, approval_policy='on-request', model=None):
        super().__init__(workspace, network=network, approval_policy=approval_policy, model=model)
        self.sdk = None
        self.client = None
        self.session_key = None
        self.instructions = ''
        self.skills = ()
        self._loop = None
        self._thread = None
        self._reader = None
        self._waiters = {}
        self._waiter_lock = threading.Lock()
        self._text_id = None

    # --- lifecycle -------------------------------------------------

    def open_session(self, resume_key, *, instructions, skills=()):
        self.sdk = self._import_sdk()
        self.instructions = instructions
        self.skills = tuple(skills)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, args=(self._loop,), daemon=True)
        self._thread.start()
        try:
            self._schedule(self._open(resume_key)).result(timeout=self.connect_timeout)
        except Exception as exc:
            self.close()
            raise BackendError(f'CodeBuddy 会话启动失败：{_message(exc)}') from exc
        return self.session_key

    def start_turn(self, *, prompt, skills=()):
        if skills:
            self.skills = tuple(skills)
        future = self._schedule(self._query(prompt))
        future.add_done_callback(self._turn_submitted)

    def send(self, message):
        """Answer a `can_use_tool` / `focus` tool round-trip from the Host thread."""
        request_id = message.get('id')
        with self._waiter_lock:
            waiter = self._waiters.get(request_id)
        if waiter is None or self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._resolve, request_id, message)
        except RuntimeError:
            self._resolve(request_id, message)

    def interrupt(self):
        if self.closed or self.client is None:
            return
        try:
            self._schedule(self._interrupt())
        except Exception:
            self.close()

    def close(self):
        if self.closed:
            return
        super().close()
        self._release(None)
        client, self.client = self.client, None
        loop, self._loop = self._loop, None
        reader, self._reader = self._reader, None
        if reader is not None and loop is not None:
            try:
                reader.cancel()
            except Exception:
                pass
        if client is not None and loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(client.disconnect(), loop).result(timeout=5)
            except Exception:
                pass
        if loop is not None:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if loop is not None:
            try:
                loop.close()
            except Exception:
                pass
        self.fail('CodeBuddy Agent SDK 连接已关闭。')

    # --- asyncio plumbing ------------------------------------------

    def _run_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _schedule(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    def _import_sdk(self):
        try:
            import codebuddy_agent_sdk
        except ImportError as exc:
            raise BackendError(INSTALL_HINT) from exc
        return codebuddy_agent_sdk

    async def _open(self, resume_key):
        self.client = self.sdk.CodeBuddySDKClient(options=self._build_options(resume_key))
        await self.client.connect()
        self._reader = asyncio.ensure_future(self._drain())

    async def _query(self, prompt):
        await self.client.query(prompt)

    async def _interrupt(self):
        try:
            await self.client.interrupt()
        except Exception:
            self.close()

    async def _drain(self):
        try:
            async for message in self.client.receive_messages():
                self._project(message)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if not self.closed:
                self.fail(f'CodeBuddy Agent SDK 连接失败：{_message(exc)}')

    def _turn_submitted(self, future):
        if future.cancelled():
            return
        error = future.exception()
        if error is not None and not self.closed:
            self.emit(TURN_COMPLETED, {'status': 'failed', 'error': _message(error)})

    # --- SDK options ------------------------------------------------

    def _build_options(self, resume_key):
        sdk = self.sdk
        options = sdk.CodeBuddyAgentOptions(
            cwd=str(self.workspace),
            system_prompt=self._system_prompt(),
            permission_mode='default',          # callback handles calls requiring permission
            env=backend_environment(self.name),
            setting_sources=[],                 # clean room: no stray project/user config
            mcp_servers={'focus': self._focus_server()},
            can_use_tool=self._can_use_tool,
            include_partial_messages=True,
            persist_session=True,
        )
        if self.model:
            options.model = self.model
        if resume_key:
            options.resume = resume_key
        if not self.network:
            options.disallowed_tools = list(NETWORK_TOOLS)
        return options

    def _system_prompt(self):
        body = self.instructions
        if self.skills:
            body += '\n\n可用 Skills（按需自行读取对应 SKILL.md，不要当作 cwd 相对路径）：\n' + \
                '\n'.join(f'- {name}: {path}' for name, path in self.skills)
        # Keep the runtime's own agent prompt when possible; only fall back to replacing it.
        append = getattr(self.sdk, 'AppendSystemPrompt', None)
        return append(append=body) if append else body

    def _focus_server(self):
        sdk = self.sdk

        @sdk.tool(FOCUS_TOOL, FOCUS_TOOL_DESCRIPTION, {'action': str, 'arguments': str})
        async def focus(args):
            answer = await self._ask_host(TOOL_CALL, {'tool': FOCUS_TOOL, 'arguments': args})
            result = (answer or {}).get('result', {}) if answer and 'result' in answer else {}
            text = result.get('text') or json.dumps({'error': 'unavailable', 'message': 'Host 未返回结果。'},
                                                    ensure_ascii=False)
            if result.get('success') is False:
                text = '[FOCUS Core 返回错误] ' + text
            return {'content': [{'type': 'text', 'text': text}]}

        return sdk.create_sdk_mcp_server(name='focus', tools=[focus])

    # --- Host round-trips -------------------------------------------

    async def _can_use_tool(self, tool_name, input_data, options):
        if tool_name in ('focus', 'mcp__focus__focus'):
            return self.sdk.PermissionResultAllow(updated_input=input_data)
        if tool_name == ASK_USER_QUESTION:
            return await self._ask_questions(input_data)
        return await self._ask_permission(tool_name, input_data)

    def _is_focus_tool(self, tool_name):
        return str(tool_name).split('__')[-1] == FOCUS_TOOL

    async def _ask_permission(self, tool_name, input_data):
        method = FILE_APPROVAL if tool_name in EDIT_TOOLS else COMMAND_APPROVAL
        answer = await self._ask_host(method, {
            'title': f'工具调用审批：{tool_name}',
            'detail': json.dumps(input_data, ensure_ascii=False, indent=2),
            'choices': ['accept', 'decline', 'cancel'], 'raw': input_data})
        decision = (answer or {}).get('result', {}).get('decision', 'cancel') if answer and 'result' in answer else 'cancel'
        if decision == 'accept':
            return self.sdk.PermissionResultAllow(updated_input=input_data)
        return self.sdk.PermissionResultDeny(message='用户拒绝了该工具调用。')

    async def _ask_questions(self, input_data):
        raw_questions = input_data.get('questions', [])
        questions = []
        for index, raw in enumerate(raw_questions):
            questions.append({
                'id': _question_id(raw, index),
                'question': raw.get('question', ''),
                'options': [{'label': o.get('label', ''), 'description': o.get('description', '')}
                            for o in raw.get('options', [])],
            })
        answer = await self._ask_host(USER_INPUT, {'questions': questions, 'raw': raw_questions})
        payload = (answer or {}).get('result', {}) if answer and 'result' in answer else {}
        answers = payload.get('answers') or {}
        resolved = {}
        for raw, projected in zip(raw_questions, questions):
            selected = answers.get(projected['id'], {}).get('answers', [])
            if selected:
                resolved[raw.get('question', projected['question'])] = list(selected)
        if resolved:
            return self.sdk.PermissionResultAllow(updated_input={**input_data, 'answers': resolved})
        return self.sdk.PermissionResultDeny(message='用户未回答该提问。')

    async def _ask_host(self, method, params):
        """Emit a normalized request and wait for the Host answer on this loop."""
        request_id = self.next_request_id()
        waiter = asyncio.get_running_loop().create_future()
        with self._waiter_lock:
            self._waiters[request_id] = waiter
        self.emit(method, params, request_id=request_id)
        try:
            return await asyncio.wait_for(waiter, timeout=self.answer_timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            with self._waiter_lock:
                self._waiters.pop(request_id, None)

    def _resolve(self, request_id, message):
        with self._waiter_lock:
            waiter = self._waiters.pop(request_id, None)
        if waiter is not None and not waiter.done():
            waiter.set_result(message)

    def _release(self, message):
        """Unblock every pending round-trip, e.g. after Stop or transport loss."""
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._release_now, message)
        except RuntimeError:
            self._release_now(message)

    def _release_now(self, message):
        with self._waiter_lock:
            waiters = list(self._waiters.values())
            self._waiters.clear()
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(message)

    # --- message projection -----------------------------------------

    def _project(self, message):
        sdk = self.sdk
        if isinstance(message, sdk.ResultMessage):
            self._finish(message)
        elif isinstance(message, sdk.AssistantMessage):
            self._project_assistant(message)
        elif isinstance(message, sdk.StreamEvent):
            self._project_partial(message)
        elif isinstance(message, sdk.SystemMessage):
            self._remember_session((message.data or {}).get('session_id'))

    def _project_assistant(self, message):
        sdk = self.sdk
        texts = []
        for block in message.content:
            if isinstance(block, sdk.TextBlock):
                texts.append(block.text)
            elif isinstance(block, sdk.ToolUseBlock):
                self.emit(ACTIVITY, {'id': block.id, 'title': block.name, 'status': 'inProgress',
                                     'detail': _dump(block.input)[-16000:]})
            elif isinstance(block, sdk.ToolResultBlock):
                self.emit(ACTIVITY, {'id': block.tool_use_id, 'title': '工具结果',
                                     'status': 'failed' if block.is_error else 'completed',
                                     'detail': _result_text(block.content)[-16000:]})
        if texts:
            item_id = self._text_item()
            self.emit(MESSAGE_COMPLETED, {'itemId': item_id, 'text': ''.join(texts)})

    def _project_partial(self, message):
        text = _stream_text(message.event)
        if not text:
            return
        if self._text_id is None:
            self._text_id = new_item_id()
        self.emit(MESSAGE_DELTA, {'itemId': self._text_id, 'delta': text})

    def _text_item(self):
        item_id = self._text_id or new_item_id()
        self._text_id = None
        return item_id

    def _finish(self, message):
        self._remember_session(message.session_id)
        self.emit(TURN_COMPLETED, {'status': 'failed' if message.is_error else 'completed',
                                   'error': '; '.join(e for e in (message.errors or []) if e) or None})

    def _remember_session(self, key):
        if key and key != self.session_key:
            self.session_key = key
            self.emit(SESSION_OPENED, {'key': key})


def _question_id(raw, index):
    return raw.get('header') or raw.get('question') or f'question-{index}'


def _message(exc):
    return str(exc) or type(exc).__name__


def _dump(value):
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(value)


def _result_text(content):
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    texts = []
    for item in content:
        if isinstance(item, dict):
            texts.append(item.get('text') or str(item))
        else:
            texts.append(str(item))
    return '\n'.join(texts)


def _stream_text(event):
    """Best-effort text delta; unknown shapes are ignored rather than duplicated."""
    if isinstance(event, str):
        return event
    if not isinstance(event, dict):
        return ''
    if event.get('type') == 'content_block_delta':
        delta = event.get('delta') or {}
        if isinstance(delta, str):
            return delta
        if isinstance(delta, dict) and delta.get('type', 'text_delta') == 'text_delta':
            return delta.get('text') or ''
        return ''
    delta = event.get('delta')
    if isinstance(delta, str) and event.get('type', 'content_delta') == 'content_delta':
        return delta
    return ''
