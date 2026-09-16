"""Official Codex App Server backend: stdio JSON-RPC translated to Host vocabulary.

This keeps the deliberate choice from ADR 0006: drive the pinned `0.154.0`
app-server protocol directly instead of a high-level SDK wrapper, because dynamic
tools and the three approval round-trips are not stably wrapped there. Nothing in
this file is visible to the Host above `host.backends.base`.
"""
import os
import queue
import threading

from ..core_bridge import TOOL
from ..runtime import AppServer, codex_command
from ..proxy import backend_environment
from .base import (ACTIVITY, Backend, BackendError, COMMAND_APPROVAL, FILE_APPROVAL, MESSAGE_COMPLETED,
                   MESSAGE_DELTA, PERMISSIONS_APPROVAL, SESSION_OPENED, TOOL_CALL, TRANSPORT_ERROR,
                   TURN_COMPLETED, TURN_STARTED, USER_INPUT, UNSUPPORTED_REQUEST)

ACTIVITY_ITEM_TYPES = ('commandExecution', 'fileChange', 'dynamicToolCall', 'mcpToolCall')
APPROVAL_DECISIONS = ('accept', 'decline', 'cancel')


class CodexBackend(Backend):
    name = 'codex'
    option_keys = Backend.option_keys | {'codex_bin'}

    def __init__(self, workspace, *, network=False, approval_policy='on-request', model=None, codex_bin=None):
        super().__init__(workspace, network=network, approval_policy=approval_policy, model=model)
        self.codex_bin = codex_bin
        self.rpc = None
        self.thread_id = None
        self.turn_id = None

    # --- lifecycle -------------------------------------------------

    def open_session(self, resume_key, *, instructions, skills=()):
        self.rpc = AppServer(codex_command(self.codex_bin), self.workspace, env=backend_environment(self.name))
        self.rpc.initialize()
        self.rpc.send({'method': 'initialized', 'params': {}})
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            self.rpc.request('account/login/start', {'type': 'apiKey', 'apiKey': api_key})
        params = {'cwd': str(self.workspace), 'approvalPolicy': self.approval_policy,
                  'approvalsReviewer': 'user', 'sandbox': 'workspace-write',
                  'developerInstructions': instructions}
        if self.model:
            params['model'] = self.model
        if resume_key:
            params['threadId'] = resume_key
            result = self.rpc.request('thread/resume', params)
        else:
            params['dynamicTools'] = [TOOL]
            result = self.rpc.request('thread/start', params)
        self.thread_id = result['thread']['id']
        threading.Thread(target=self._pump, daemon=True).start()
        self.emit(SESSION_OPENED, {'key': self.thread_id})
        return self.thread_id

    def start_turn(self, *, prompt, skills=()):
        inputs = [{'type': 'text', 'text': prompt}]
        inputs += [{'type': 'skill', 'name': name, 'path': path} for name, path in skills]
        policy = {'type': 'workspaceWrite', 'writableRoots': [str(self.workspace)],
                  'networkAccess': self.network, 'excludeTmpdirEnvVar': True, 'excludeSlashTmp': True}
        result = self.rpc.request('turn/start', {'threadId': self.thread_id, 'input': inputs,
                                                'cwd': str(self.workspace),
                                                'approvalPolicy': self.approval_policy,
                                                'sandboxPolicy': policy})
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
        except Exception:
            self.close()

    def close(self):
        if self.closed:
            return
        super().close()
        rpc, self.rpc = self.rpc, None
        if rpc:
            try:
                rpc.close()
            except Exception:
                pass
        self.fail('Codex App Server 连接已关闭。')

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
                self.fail(str(exc))
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
            self.fail(params.get('message', 'Codex App Server transport failed'))
            return True
        if self.thread_id and params.get('threadId') and params['threadId'] != self.thread_id:
            return False
        if self.turn_id and params.get('turnId') and params['turnId'] != self.turn_id:
            return False
        if method == TURN_COMPLETED:
            turn = params.get('turn', {})
            self.emit(TURN_COMPLETED, {'status': turn.get('status'),
                                       'error': (turn.get('error') or {}).get('message')})
        elif method == MESSAGE_DELTA or method == 'item/agentMessage/delta':
            self.emit(MESSAGE_DELTA, {'itemId': params['itemId'], 'delta': params.get('delta', '')})
        elif method in ('item/started', 'item/completed'):
            self._translate_item(method, params.get('item', {}))
        elif method == 'error':
            self.emit('error', {'message': (params.get('error') or {}).get('message', 'Unknown runtime error'),
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
        elif item.get('type') in ACTIVITY_ITEM_TYPES:
            detail = item.get('command') or item.get('tool') or '文件更改'
            if item.get('changes'):
                detail += '\n' + '\n'.join(c.get('path', '') + '\n' + c.get('diff', '') for c in item['changes'])
            if item.get('aggregatedOutput'):
                detail += '\n' + item['aggregatedOutput']
            self.emit(ACTIVITY, {'id': item['id'], 'title': item['type'],
                                 'status': item.get('status', 'inProgress'), 'detail': detail[-16000:]})
