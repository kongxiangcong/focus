"""ACP v1 sessions over stdio, using the Host's shared MCP tool bridge."""
import base64
import json
import mimetypes
import queue
import sys
import tempfile
import threading
import time
from pathlib import Path

from .base import (ACTIVITY, MESSAGE_COMPLETED, MESSAGE_DELTA, SESSION_OPENED, TRANSPORT_ERROR,
                   TURN_COMPLETED, TURN_STARTED, Backend, BackendError, new_item_id, safe_backend_error)
from .task_tools import discussion_tools, library_tools
from .tool_bridge import ToolBridge
from ..proxy import backend_environment
from ..runtime import JsonRpcStdioClient


def _model_config(session):
    return next((option for option in session.get('configOptions') or []
                 if option.get('type') == 'select' and
                 (option.get('category') == 'model' or option.get('id') == 'model')), None)


def _model_values(option):
    return [item['value'] for entry in option.get('options') or []
            for item in (entry.get('options') or [entry]) if isinstance(item.get('value'), str)]


def _bare_model(value):
    # Some agents identify models by a JSON [provider, model] tuple.
    if value.startswith('['):
        try:
            parts = json.loads(value)
            if len(parts) == 2 and all(isinstance(part, str) for part in parts):
                return parts[1]
        except ValueError:
            pass
    return value


class AcpBackend(Backend):
    option_keys = Backend.option_keys | {'command', 'manifest', 'credential_file', 'purpose'}

    def __init__(self, workspace, *, command, manifest, credential_file=None, purpose='business', **options):
        super().__init__(workspace, **options)
        self.command = command
        self.manifest = manifest
        self.credential_file = credential_file
        self.purpose = purpose
        self.stream_supported = manifest.capabilities.get('streaming', True)
        self.image_input = manifest.capabilities.get('images', False)
        self.rpc = None
        self.bridge = None
        self.temporary = None
        self.session_id = None
        self.turn_id = None
        self.capabilities = {}
        self.instructions = ''
        self._pump_thread = None
        self._thinking = False
        self._prompt_finished = threading.Event()
        self._close_done = threading.Event()

    def open_session(self, resume_key, *, instructions, skills=()):
        if resume_key or skills:
            raise BackendError('ACP 仅支持 FOCUS 发起的新会话。')
        try:
            session = self._open_session(self._tools())
            self.instructions = instructions
            if self.model:
                self._select_model(session)
            self.emit(SESSION_OPENED, {'key': self.session_id})
            return self.session_id
        except (BackendError, TimeoutError):
            raise
        except Exception as exc:
            raise BackendError(safe_backend_error(exc)) from exc

    def _tools(self):
        if self.tools is not None:
            return self.tools
        if self.purpose == 'discussion':
            return discussion_tools()
        if self.purpose == 'business':
            return library_tools()
        return []

    def _open_session(self, tools):
        env = (backend_environment(self.manifest, credential_file=self.credential_file)
               if self.credential_file else backend_environment(self.manifest))
        if tools:
            inherited = env.get('NO_PROXY') or env.get('no_proxy', '')
            env['NO_PROXY'] = env['no_proxy'] = ','.join(filter(None, (inherited, '127.0.0.1', 'localhost')))
        started = time.monotonic()
        with self._lifecycle_lock:
            if self.closed or self.rpc:
                raise BackendError('ACP 会话不可用。')
            workspace = self.workspace
            if self.purpose == 'business':
                # FOCUS remains the sole holder of the business workspace path.
                self.temporary = tempfile.TemporaryDirectory(prefix='focus-acp-')
                workspace = Path(self.temporary.name)
            rpc = self.rpc = JsonRpcStdioClient(self.command, workspace, env=env, jsonrpc=True)
            rpc.deadline = self.deadline
        result = rpc.request('initialize', {'protocolVersion': 1, 'clientCapabilities': {},
            'clientInfo': {'name': 'focus', 'version': '0.1.0'}}, timeout=30)
        if result.get('protocolVersion') != 1:
            raise BackendError('ACP 协议版本不兼容，请检查所选 Runtime。')
        self.cleanup['handshakeMs'] = round((time.monotonic() - started) * 1000)
        self.capabilities = result.get('agentCapabilities') or {}
        with self._lifecycle_lock:
            if self.closed:
                raise BackendError('任务已关闭。')
            servers = []
            if tools:
                self.bridge = ToolBridge(self, tools)
                servers.append(self._mcp_server(self.bridge.url))
        session = rpc.request('session/new', {'cwd': str(workspace.absolute()), 'mcpServers': servers}, timeout=30)
        session_id = session.get('sessionId')
        if not isinstance(session_id, str) or not session_id:
            raise BackendError('ACP Runtime 未返回会话标识。')
        self.session_id = session_id
        self.cleanup.update(nativeSessionId=session_id, persistence='runtime_owned')
        return session

    def _mcp_server(self, url):
        http = (self.capabilities.get('mcpCapabilities') or {}).get('http')
        if http and self.manifest.capabilities.get('mcpTransport') != 'stdio':
            return {'type': 'http', 'name': 'focus', 'url': url, 'headers': []}
        return {'name': 'focus', 'command': sys.executable,
                'args': [str(Path(__file__).resolve().parents[1] / 'mcp_stdio_proxy.py'), url], 'env': []}

    def discover_models(self):
        try:
            return self._catalog(self._open_session([]))
        except (BackendError, TimeoutError):
            raise
        except Exception as exc:
            raise BackendError(safe_backend_error(exc)) from exc
        finally:
            self.close()

    @staticmethod
    def _catalog(session):
        option = _model_config(session)
        if option:
            return list(dict.fromkeys(_model_values(option)))
        legacy = session.get('models') or {}
        return list(dict.fromkeys(item['modelId'] for item in legacy.get('availableModels') or []
                                  if isinstance(item.get('modelId'), str)))

    def _select_model(self, session):
        option = _model_config(session)
        current = option.get('currentValue') if option else (session.get('models') or {}).get('currentModelId')
        models = self._catalog(session)
        value = self.model
        if value not in models:
            matches = [model for model in models if _bare_model(model) == value]
            if len(matches) > 1:
                raise BackendError('模型名称对应多个 ACP 选项，请在模型清单中明确选择。')
            if matches:
                value = matches[0]
        if value == current:
            return
        with self._lifecycle_lock:
            rpc = self.rpc
            if self.closed or not rpc:
                raise BackendError('任务已关闭。')
        params = {'sessionId': self.session_id}
        if option:
            reply = rpc.request('session/set_config_option', {**params, 'configId': option['id'], 'value': value}, timeout=20)
            actual = _model_config(reply)
            if not actual or actual.get('currentValue') != value:
                raise BackendError('ACP Runtime 未应用所选模型。')
        else:
            # Older ACP agents implement the pre-config-options model endpoint.
            rpc.request('session/set_model', {**params, 'modelId': value}, timeout=20)

    def start_turn(self, *, prompt, skills=(), images=()):
        if skills:
            raise BackendError('ACP 不接受本机技能。')
        if images and (not self.image_input or not (self.capabilities.get('promptCapabilities') or {}).get('image')):
            raise BackendError('当前 ACP Runtime 未启用图片输入。')
        content = [{'type': 'text', 'text': self.instructions + '\n\n' + prompt}]
        content.extend({'type': 'image', 'mimeType': mimetypes.guess_type(path.name)[0],
                        'data': base64.b64encode(path.read_bytes()).decode('ascii')} for path in images)
        with self._lifecycle_lock:
            rpc = self.rpc
            if self.closed or not rpc or not self.session_id or self.turn_id:
                raise BackendError('ACP 会话无法启动此轮。')
            self.turn_id = new_item_id()
        started = time.monotonic()
        request_id = rpc.request_event('session/prompt', {'sessionId': self.session_id, 'prompt': content})
        with self._lifecycle_lock:
            if self.closed:
                raise BackendError('ACP 会话已关闭。')
            self.emit(TURN_STARTED, {'turnId': self.turn_id})
            self._pump_thread = threading.Thread(target=self._pump, args=(rpc, request_id, started),
                                                 name='focus-acp-events', daemon=True)
            self._pump_thread.start()

    def _pump(self, rpc, request_id, started):
        deadline = min(self.deadline or float('inf'), started + 3600)
        messages = {}
        try:
            while not self.closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('ACP prompt timed out')
                event = rpc.events.get(timeout=remaining)
                method = event.get('method')
                if method == TRANSPORT_ERROR:
                    raise RuntimeError(event.get('params', {}).get('message'))
                if method is None and event.get('id') == request_id:
                    self._prompt_finished.set()
                    if 'error' in event:
                        raise RuntimeError(event['error'].get('message'))
                    self._finish_thinking()
                    for item, text in messages.values():
                        self.emit(MESSAGE_COMPLETED, {'itemId': item, 'text': text})
                    reason = event.get('result', {}).get('stopReason')
                    self._complete_prompt(reason)
                    return
                params = event.get('params') or {}
                if 'id' in event and method:
                    self._client_request(rpc, event['id'], method, params)
                elif method == 'session/update' and params.get('sessionId') == self.session_id:
                    self._session_update(params.get('update') or {}, messages, started)
        except (TimeoutError, queue.Empty):
            if not self.closed:
                self.fail(safe_backend_error('ACP prompt timeout'))
        except Exception as exc:
            if not self.closed:
                self.fail(safe_backend_error(exc))
        finally:
            self._prompt_finished.set()

    def _session_update(self, update, messages, started):
        kind = update.get('sessionUpdate')
        if kind == 'agent_message_chunk':
            content = update.get('content') or {}
            text = content.get('text')
            if content.get('type') != 'text' or not isinstance(text, str) or not text:
                return
            key = update.get('messageId')
            if not isinstance(key, str):
                key = None
            previous = messages.pop(key, None)
            item, accumulated = previous if previous else (new_item_id(), '')
            messages[key] = (item, accumulated + text)
            self._finish_thinking()
            self.cleanup.setdefault('firstOutputMs', round((time.monotonic() - started) * 1000))
            if self.stream_supported:
                self.emit(MESSAGE_DELTA, {'itemId': item, 'delta': text})
        elif kind == 'agent_thought_chunk' and not self._thinking:
            self._thinking = True
            self.emit(ACTIVITY, {'id': self.turn_id + '-thought', 'title': 'reasoning',
                                 'status': 'inProgress', 'detail': ''})
        elif kind in ('tool_call', 'tool_call_update') and update.get('toolCallId'):
            state = update.get('status')
            if state:
                self.emit(ACTIVITY, {'id': update['toolCallId'], 'title': 'mcpToolCall',
                                     'status': state if state in ('completed', 'failed') else 'inProgress',
                                     'detail': ''})

    def _finish_thinking(self):
        if self._thinking:
            self._thinking = False
            self.emit(ACTIVITY, {'id': self.turn_id + '-thought', 'title': 'reasoning',
                                 'status': 'completed', 'detail': ''})

    def _complete_prompt(self, reason):
        if reason == 'end_turn':
            result = {'status': 'completed', 'error': None}
        elif reason == 'cancelled':
            result = {'status': 'interrupted', 'error': None}
        else:
            error = {'max_tokens': safe_backend_error('max-tokens'),
                     'max_turn_requests': 'ACP Runtime 达到本轮请求上限。',
                     'refusal': 'ACP Runtime 拒绝继续本轮请求。'}.get(reason, 'ACP Runtime 返回了未知的终止状态。')
            result = {'status': 'failed', 'error': error}
        self.emit(TURN_COMPLETED, result)

    @staticmethod
    def _client_request(rpc, request_id, method, params):
        if method == 'session/request_permission':
            rpc.send({'id': request_id, 'result': {'outcome': {'outcome': 'cancelled'}}})
        else:
            rpc.send({'id': request_id, 'error': {'code': -32601, 'message': 'Client capability unavailable.'}})

    def send(self, message):
        bridge = self.bridge
        if not self.closed and bridge:
            bridge.send(message)

    def interrupt(self):
        rpc = self.rpc
        if not self.closed and rpc and self.turn_id and not self._prompt_finished.is_set():
            try:
                rpc.send({'method': 'session/cancel', 'params': {'sessionId': self.session_id}})
                self.cleanup['stop'] = 'cancel_sent'
            except (RuntimeError, OSError):
                pass

    def close(self):
        with self._lifecycle_lock:
            already_closing = self.closed
            if not already_closing:
                super().close()
                rpc, self.rpc = self.rpc, None
                bridge, self.bridge = self.bridge, None
        if already_closing:
            self._close_done.wait()
            return
        try:
            try:
                if bridge:
                    bridge.close()
            finally:
                if rpc:
                    if (self.session_id and 'close' in (self.capabilities.get('sessionCapabilities') or {})
                            and (not self.turn_id or self._prompt_finished.is_set())):
                        try:
                            rpc.request('session/close', {'sessionId': self.session_id}, timeout=1)
                        except (RuntimeError, TimeoutError, OSError):
                            pass
                    rpc.close()
                    self.cleanup['release'] = 'process_closed'
                    if self.cleanup['stop'] == 'not_requested':
                        self.cleanup['stop'] = 'process_closed'
        finally:
            try:
                if self._pump_thread:
                    self._pump_thread.join(timeout=2)
                if self.temporary:
                    self.temporary.cleanup()
            finally:
                self.report_cleanup()
                self.fail('ACP 连接已关闭。')
                self._close_done.set()
