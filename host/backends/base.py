"""Transport-agnostic vocabulary between the FOCUS web Host and an Agent backend.

`HostService` only ever speaks this vocabulary. Translating it to the Codex
app-server JSON-RPC or to the WorkBuddy Agent SDK is each adapter's job, so the
Host, the Reader contract and Core never branch on which model runtime is behind
a turn.

Events are dicts on `Backend.events`:

  notifications (no reply)
    session/opened     {'key': opaque resume key for this backend}
    turn/started       {'turnId': str}
    message/delta      {'itemId': str, 'delta': str}
    message/completed  {'itemId': str, 'text': str}
    activity           {'id','title','status','detail'}
    error              {'message': str, 'willRetry': bool}
    turn/completed     {'status': str, 'error': str|None}
    _transport_error   {'message': str}

  requests (Host must answer through `Backend.send`)
    tool/call            -> {'success': bool, 'text': str}
    command/approval     -> {'decision': 'accept'|'decline'|'cancel'}
    file/approval        -> {'decision': ...}
    permissions/approval -> {'accept': bool}
    user/input           -> {'answers': {question_id: {'answers': [str]}}}
    request/unsupported  -> always answered with an error
"""
import queue
import threading
import uuid

TRANSPORT_ERROR = '_transport_error'

TURN_COMPLETED = 'turn/completed'
SESSION_OPENED = 'session/opened'
TURN_STARTED = 'turn/started'
MESSAGE_DELTA = 'message/delta'
MESSAGE_COMPLETED = 'message/completed'
ACTIVITY = 'activity'
ERROR = 'error'

TOOL_CALL = 'tool/call'
COMMAND_APPROVAL = 'command/approval'
FILE_APPROVAL = 'file/approval'
PERMISSIONS_APPROVAL = 'permissions/approval'
USER_INPUT = 'user/input'
UNSUPPORTED_REQUEST = 'request/unsupported'

APPROVAL_TITLES = {COMMAND_APPROVAL: '命令审批', FILE_APPROVAL: '文件修改审批',
                   PERMISSIONS_APPROVAL: '额外权限申请', USER_INPUT: '需要你的输入'}


class BackendError(RuntimeError):
    """A backend cannot be selected, started or driven. Surfaced as a task failure."""


def safe_backend_error(error):
    """Classify diagnostics without returning provider-controlled text or secrets."""
    text = str(error).lower()
    if any(word in text for word in ('quota', 'insufficient', '402', '额度不足')):
        return '服务额度不足，请检查所选 Backend 的账号额度。'
    if any(word in text for word in ('credential', 'unauthorized', '401', 'api key', '登录', '凭据')):
        return '认证失败或未配置，请重新登录或检查 Host 凭据。'
    if any(word in text for word in ('timeout', 'timed out', '超时')):
        return '请求超时，请检查网络和 Runtime。'
    if any(word in text for word in ('network', 'connection', 'fetch failed', 'dns', '网络')):
        return '网络请求失败，请检查连接和代理配置。'
    if any(word in text for word in ('configuration', 'unknown variant', 'config', 'not supported', '配置')):
        return 'Runtime 或模型配置不兼容，请检查当前选择；没有自动更换路径或服务。'
    return 'Runtime 调用失败，请检查实际使用的 Runtime 后重试。'


class Backend:
    """One Agent turn inside one Host-owned workspace."""

    name = 'abstract'
    option_keys = frozenset({'network', 'approval_policy', 'model', 'tools'})
    stream_supported = True

    def __init__(self, workspace, *, network=False, approval_policy='on-request', model=None, tools=None):
        self.workspace = workspace
        self.network = bool(network)
        self.approval_policy = approval_policy
        self.model = model
        self.tools = tools
        self.events = queue.Queue()
        self.closed = False
        self._lifecycle_lock = threading.RLock()
        self._requests = {}
        self._request_lock = threading.Lock()
        self._next_id = 0
        self.cleanup = {'stop': 'not_requested', 'release': 'not_attempted',
                        'archive': 'not_requested', 'delete': 'not_verified'}
        self.cleanup_callback = None

    def report_cleanup(self):
        if self.cleanup_callback:
            try:
                self.cleanup_callback({'backend': self.name, **self.cleanup})
            except Exception:
                # Diagnostics cannot strand the lifecycle completion event.
                self.cleanup['receipt'] = 'persistence_failed'

    # --- lifecycle -------------------------------------------------

    def open_session(self, resume_key, *, instructions, skills=()):
        """Start (or resume) a conversation. Returns the resume key if already known."""
        raise NotImplementedError

    def start_turn(self, *, prompt, skills=()):
        raise NotImplementedError

    def send(self, message):
        """Deliver a Host answer. `message` is {'id':..,'result':..} or {'id':..,'error':..}."""
        raise NotImplementedError

    def interrupt(self):
        """Ask the runtime to stop the active turn. May be a no-op before the turn starts."""

    def close(self):
        self.closed = True

    # --- shared helpers --------------------------------------------

    def emit(self, method, params=None, request_id=None):
        if method == TURN_COMPLETED:
            self.cleanup['stop'] = 'terminal_event'
        event = {'method': method, 'params': params or {}}
        if request_id is not None:
            event['id'] = request_id
            with self._request_lock:
                self._requests[request_id] = event
        self.events.put(event)
        return event

    def fail(self, message):
        self.emit(TRANSPORT_ERROR, {'message': message})

    def next_request_id(self):
        self._next_id += 1
        return self._next_id

    def request(self, request_id):
        with self._request_lock:
            return self._requests.get(request_id)

    def take_request(self, request_id):
        """A round-trip is answered exactly once; drop the native payload afterwards."""
        with self._request_lock:
            return self._requests.pop(request_id, None)


def new_item_id():
    return uuid.uuid4().hex
