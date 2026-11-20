"""Official Codex App Server backend: stdio JSON-RPC translated to Host vocabulary.

This keeps the deliberate choice from ADR 0006: drive the selected
app-server protocol directly instead of a high-level SDK wrapper, because dynamic
tools and the three approval round-trips are not stably wrapped there. Nothing in
this file is visible to the Host above `host.backends.base`.
"""
import queue
import threading
from urllib.parse import urlsplit
from .task_tools import discussion_tools, library_tools

from ..core_bridge import TOOL
from ..runtime import AppServer, codex_command
from ..proxy import backend_environment
from .base import (ACTIVITY, Backend, BackendConfigurationError, BackendError, COMMAND_APPROVAL, FILE_APPROVAL, MESSAGE_COMPLETED,
                   MESSAGE_DELTA, PERMISSIONS_APPROVAL, SESSION_OPENED, TOOL_CALL, TRANSPORT_ERROR,
                   TURN_COMPLETED, TURN_STARTED, USER_INPUT, UNSUPPORTED_REQUEST, safe_backend_error)

ACTIVITY_ITEM_TYPES = ('commandExecution', 'fileChange', 'dynamicToolCall', 'mcpToolCall')
APPROVAL_DECISIONS = ('accept', 'decline', 'cancel')


class CodexBackend(Backend):
    name = 'codex'
    image_input = True
    option_keys = Backend.option_keys | {'codex_bin', 'command', 'manifest', 'credential_file', 'purpose'}

    def __init__(self, workspace, *, network=False, approval_policy='on-request', model=None,
                 codex_bin=None, command=None, manifest=None, credential_file=None, purpose='business', tools=None):
        super().__init__(workspace, network=network, approval_policy=approval_policy, model=model, tools=tools)
        self.codex_bin = codex_bin
        self.command = command
        self.manifest = manifest
        self.credential_file = credential_file
        self.rpc = None
        self.thread_id = None
        self.turn_id = None
        self.purpose = purpose
        self._close_done = threading.Event()

    # --- lifecycle -------------------------------------------------

    def open_session(self, resume_key, *, instructions, skills=()):
        try:
            return self._open_session(resume_key, instructions=instructions, skills=skills)
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(safe_backend_error(exc)) from exc

    def _start_rpc(self, *options):
        command = list(self.command) if self.command else [*codex_command(self.codex_bin), 'app-server']
        env = backend_environment(self.manifest or self.name, credential_file=self.credential_file)
        for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
            env.pop(key, None)
        with self._lifecycle_lock:
            if self.closed:
                raise BackendError('任务已关闭。')
            self.rpc = rpc = AppServer([*command, '-c', 'forced_login_method="chatgpt"', *options], self.workspace, env=env)
            if self.deadline is not None:
                rpc.deadline = self.deadline
        rpc.initialize()
        rpc.send({'method': 'initialized', 'params': {}})
        return rpc

    def account(self):
        rpc = self._start_rpc()
        account = rpc.request('account/read', {'refreshToken': True}, timeout=15).get('account')
        return bool(account and account.get('type') == 'chatgpt')

    def discover_models(self):
        rpc = self._start_rpc()
        models, cursor, seen = [], None, set()
        while True:
            result = rpc.request('model/list', {'limit': 100, 'cursor': cursor, 'includeHidden': False}, timeout=20)
            models.extend(item['model'] for item in result.get('data', []) if isinstance(item.get('model'), str))
            cursor = result.get('nextCursor')
            if not cursor:
                return list(dict.fromkeys(models))
            if cursor in seen:
                raise BackendError('model list pagination repeated')
            seen.add(cursor)

    def start_login(self):
        rpc = self._start_rpc()
        result = rpc.request('account/login/start', {'type': 'chatgpt'}, timeout=15)
        url = urlsplit(result['authUrl'])
        if (url.scheme != 'https' or url.hostname not in ('auth.openai.com', 'auth0.openai.com', 'auth.chatgpt.com')
                or url.username or url.password):
            raise BackendError('Runtime returned an invalid login URL.')
        login_id = result['loginId']
        if not isinstance(login_id, str) or not login_id:
            raise BackendError('Runtime returned an invalid login ID.')
        return {'loginId': login_id, 'authUrl': result['authUrl']}

    def poll_login(self, login_id):
        while True:
            try:
                event = self.rpc.events.get_nowait()
            except queue.Empty:
                return None
            params = event.get('params', {})
            if event.get('method') == TRANSPORT_ERROR:
                return False
            if event.get('method') == 'account/login/completed' and params.get('loginId') == login_id:
                account = self.rpc.request('account/read', {'refreshToken': True}, timeout=15).get('account')
                return bool(params.get('success') and account and account.get('type') == 'chatgpt')

    def cancel_login(self, login_id):
        self.rpc.request('account/login/cancel', {'loginId': login_id}, timeout=10)

    def _open_session(self, resume_key, *, instructions, skills=()):
        options = []
        if self.purpose in ('connectivity', 'candidate', 'discussion', 'business'):
            options = ['-c', 'mcp_servers={}',
                       '-c', 'features.shell_tool=false', '-c', 'features.apply_patch_freeform=false',
                       '-c', 'web_search="live"' if self.purpose == 'discussion' else 'web_search="disabled"']
        rpc = self._start_rpc(*options)
        account = rpc.request('account/read', {'refreshToken': False}, timeout=15).get('account')
        if not account or account.get('type') != 'chatgpt':
            account = rpc.request('account/read', {'refreshToken': True}, timeout=15).get('account')
        if not account or account.get('type') != 'chatgpt':
            raise BackendError('请先使用 ChatGPT / Codex 登录。')
        params = {'cwd': str(self.workspace), 'approvalPolicy': self.approval_policy,
                  'approvalsReviewer': 'user', 'sandbox': 'workspace-write',
                  'developerInstructions': instructions}
        if self.model:
            params['model'] = self.model
        if self.purpose in ('connectivity', 'candidate', 'discussion', 'business'):
            params.update(sandbox='read-only', approvalPolicy='never', ephemeral=True)
        if resume_key:
            params['threadId'] = resume_key
            result = rpc.request('thread/resume', params)
        else:
            params['dynamicTools'] = [] if self.purpose in ('connectivity', 'candidate') else [TOOL]
            if self.purpose == 'discussion':
                params['dynamicTools'] = discussion_tools()
            elif self.purpose == 'business':
                params['dynamicTools'] = library_tools()
            if self.tools is not None:
                params['dynamicTools'] = self.tools
            params['dynamicTools'] = [dict(tool, type='function') for tool in params['dynamicTools']]
            result = rpc.request('thread/start', params)
        actual_model = result.get('model')
        if self.model and actual_model and actual_model != self.model:
            raise BackendConfigurationError('Backend 返回的实际模型与指定模型不同，请确认模型名称。')
        self.actual_model = actual_model or self.model
        with self._lifecycle_lock:
            if self.closed:
                raise BackendError('任务已关闭。')
            self.thread_id = result['thread']['id']
            self.cleanup.update(nativeSessionId=self.thread_id, persistence='ephemeral_requested')
            threading.Thread(target=self._pump, daemon=True).start()
            self.emit(SESSION_OPENED, {'key': self.thread_id})
            return self.thread_id

    def start_turn(self, *, prompt, skills=(), images=()):
        try:
            return self._start_turn(prompt=prompt, skills=skills, images=images)
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError(safe_backend_error(exc)) from exc

    def _start_turn(self, *, prompt, skills=(), images=()):
        with self._lifecycle_lock:
            rpc = self.rpc
            if self.closed or rpc is None:
                raise BackendError('任务已关闭。')
        inputs = [{'type': 'text', 'text': prompt}]
        inputs += [{'type': 'skill', 'name': name, 'path': path} for name, path in skills]
        inputs += [{'type': 'localImage', 'path': str(path)} for path in images]
        policy = {'type': 'workspaceWrite', 'writableRoots': [str(self.workspace)],
                  'networkAccess': self.network, 'excludeTmpdirEnvVar': True, 'excludeSlashTmp': True}
        if self.purpose in ('connectivity', 'candidate', 'discussion', 'business'):
            policy = {'type': 'readOnly'}
        result = rpc.request('turn/start', {'threadId': self.thread_id, 'input': inputs,
                                                'cwd': str(self.workspace),
                                                'approvalPolicy': 'never' if self.purpose in ('connectivity', 'candidate', 'discussion', 'business') else self.approval_policy,
                                                'sandboxPolicy': policy})
        with self._lifecycle_lock:
            if self.closed:
                raise BackendError('任务已关闭。')
            self.turn_id = result['turn']['id']
            self.emit(TURN_STARTED, {'turnId': self.turn_id})

    def send(self, message):
        request_id = message.get('id')
        if self.rpc is None or self.closed:
            return  # Stop/close already discarded this turn; a late answer has nowhere to go.
        if 'error' in message:
            self.rpc.send({'id': request_id, 'error': {'code': -32601,
                                                       'message': message['error'].get('message', 'Unsupported request')}})
            return
        result = message.get('result') or {}
        native = (self.take_request(request_id) or {}).get('params', {})
        if 'success' in result:
            self.rpc.send({'id': request_id, 'result': {
                'success': bool(result['success']),
                'contentItems': [{'type': 'inputText', 'text': result.get('text', '')}]}})
        elif 'decision' in result:
            self.rpc.send({'id': request_id, 'result': {'decision': result['decision']}})
        elif 'answers' in result:
            self.rpc.send({'id': request_id, 'result': {'answers': result['answers']}})
        elif 'accept' in result:
            granted = native.get('permissions', {}) if result['accept'] else {}
            self.rpc.send({'id': request_id, 'result': {'permissions': granted, 'scope': 'turn'}})
        else:
            raise BackendError('Unsupported Host reply for the Codex backend')

    def interrupt(self):
        if self.closed or not (self.rpc and self.thread_id and self.turn_id):
            return
        try:
            self.rpc.request('turn/interrupt', {'threadId': self.thread_id, 'turnId': self.turn_id}, timeout=10)
            self.cleanup['stop'] = 'interrupt_acknowledged'
        except Exception:
            self.close()

    def close(self):
        with self._lifecycle_lock:
            already_closing = self.closed
            if not already_closing:
                super().close()
                rpc, self.rpc = self.rpc, None
        if already_closing:
            self._close_done.wait()
            return
        try:
            if rpc:
                rpc.close()
                self.cleanup['release'] = 'process_closed'
                if self.cleanup['stop'] == 'not_requested':
                    self.cleanup['stop'] = 'process_closed'
        finally:
            try:
                self.report_cleanup()
            finally:
                self.fail('Codex App Server 连接已关闭。')
                self._close_done.set()

    # --- JSON-RPC translation --------------------------------------

    def _pump(self):
        while not self.closed:
            rpc = self.rpc
            if rpc is None:
                return
            try:
                event = rpc.events.get(timeout=1)
            except queue.Empty:
                continue
            except Exception as exc:
                self.fail(safe_backend_error(exc))
                return
            if self.closed:
                return
            if self._translate(event):
                return

    def _translate(self, event):
        """Returns True after a terminal transport error."""
        method, params = event.get('method'), event.get('params', {})
        request_id = event.get('id')
        if method == TRANSPORT_ERROR:
            self.fail(safe_backend_error(params.get('message')))
            return True
        if self.thread_id and params.get('threadId') and params['threadId'] != self.thread_id:
            return False
        if self.turn_id and params.get('turnId') and params['turnId'] != self.turn_id:
            return False
        if method == TURN_COMPLETED:
            turn = params.get('turn', {})
            self.emit(TURN_COMPLETED, {'status': turn.get('status'),
                                       'error': safe_backend_error(turn['error']) if turn.get('error') else None})
        elif method == MESSAGE_DELTA or method == 'item/agentMessage/delta':
            self.emit(MESSAGE_DELTA, {'itemId': params['itemId'], 'delta': params.get('delta', '')})
        elif method in ('item/started', 'item/completed'):
            self._translate_item(method, params.get('item', {}))
        elif method == 'error':
            self.emit('error', {'message': safe_backend_error(params.get('error')),
                                'willRetry': params.get('willRetry', False)})
        elif method == 'item/tool/call':
            self.emit(TOOL_CALL, {'tool': params.get('tool'), 'arguments': params.get('arguments', {})},
                      request_id=request_id)
        elif method in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
            self.emit(COMMAND_APPROVAL if 'commandExecution' in method else FILE_APPROVAL,
                      {'raw': params, 'choices': [c for c in params.get('availableDecisions', APPROVAL_DECISIONS)
                                                  if c in APPROVAL_DECISIONS]},
                      request_id=request_id)
        elif method == 'item/tool/requestUserInput':
            self.emit(USER_INPUT, {'questions': params.get('questions', [])}, request_id=request_id)
        elif method == 'item/permissions/requestApproval':
            self.emit(PERMISSIONS_APPROVAL, {'permissions': params.get('permissions', {})}, request_id=request_id)
        elif request_id is not None:
            # Unknown round-trip stays visible in the UI and is refused, never auto-granted.
            self.emit(UNSUPPORTED_REQUEST, {'method': method}, request_id=request_id)
        return False

    def _translate_item(self, method, item):
        if item.get('type') == 'agentMessage':
            if method == 'item/completed':
                self.emit(MESSAGE_COMPLETED, {'itemId': item['id'], 'text': item.get('text', '')})
        elif item.get('type') in ('reasoning', 'webSearch'):
            self.emit(ACTIVITY, {'id': item['id'], 'title': item['type'],
                                 'status': 'completed' if method == 'item/completed' else 'inProgress', 'detail': ''})
        elif item.get('type') in ACTIVITY_ITEM_TYPES:
            detail = item.get('command') or item.get('tool') or '文件更改'
            if item.get('changes'):
                detail += '\n' + '\n'.join(c.get('path', '') + '\n' + c.get('diff', '') for c in item['changes'])
            if item.get('aggregatedOutput'):
                detail += '\n' + item['aggregatedOutput']
            self.emit(ACTIVITY, {'id': item['id'], 'title': item['type'],
                                 'status': item.get('status', 'completed' if method == 'item/completed' else 'inProgress'), 'detail': detail[-16000:]})
