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


class Backend:
    """One Agent turn inside one Host-owned workspace."""

    name = 'abstract'
    option_keys = frozenset({'network', 'approval_policy', 'model'})
    stream_supported = True

    def __init__(self, workspace, *, network=False, approval_policy='on-request', model=None):
        self.workspace = workspace
        self.network = bool(network)
        self.approval_policy = approval_policy
        self.model = model
        self.events = queue.Queue()
        self.closed = False
        self._requests = {}
        self._request_lock = threading.Lock()
        self._next_id = 0

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
