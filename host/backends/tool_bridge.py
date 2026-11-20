"""Private MCP transport for the Host-owned tools.

The bridge owns transport only. Application permissions and writes remain in the
existing Host event handler. Every invocation waits for that handler's answer.
"""
import json
import queue
import secrets
import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ToolBridge:
    def __init__(self, backend, tools):
        self.backend = backend
        self.tools = {tool['name']: tool for tool in tools}
        self.pending = {}
        self.rpc_ids = {}
        self.cancelled_rpc_ids = set()
        self.lock = threading.Lock()
        self.closed = False
        self.token = secrets.token_urlsafe(32)
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.path != '/' + bridge.token or self.headers.get('Origin'):
                    self.send_error(403)
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 1024 * 1024:
                        raise ValueError()
                    value = json.loads(self.rfile.read(size))
                    if 'id' not in value:
                        if value.get('method') == 'notifications/cancelled':
                            bridge.cancel(value.get('params', {}).get('requestId'))
                        self.send_response(202)
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    result = bridge.dispatch(value.get('method'), value.get('params', {}),
                                             rpc_id=value['id'], connected=self.connected)
                    body = json.dumps({'jsonrpc': '2.0', 'id': value['id'], 'result': result}).encode()
                except (ValueError, TypeError):
                    self.send_error(400)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

            def connected(self):
                try:
                    readable, _, _ = select.select([self.connection], [], [], 0)
                    return not readable or bool(self.connection.recv(1, socket.MSG_PEEK))
                except (OSError, ValueError):
                    return False

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/{self.token}'

    def dispatch(self, method, params, *, rpc_id=None, connected=None):
        if method == 'initialize':
            return {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}},
                    'serverInfo': {'name': 'focus', 'version': '1'}}
        if method == 'tools/list':
            return {'tools': list(self.tools.values())}
        if method == 'ping':
            return {}
        if method != 'tools/call' or params.get('name') not in self.tools:
            return self.result(False, 'Tool is not allowed for this task.')
        with self.lock:
            if self.closed:
                return self.result(False, 'Task is closed.')
            if rpc_id in self.cancelled_rpc_ids:
                return self.result(False, 'Tool request cancelled.')
            request_id = self.backend.next_request_id()
            waiter = queue.Queue(maxsize=1)
            self.pending[request_id] = (waiter, connected)
            if rpc_id is not None:
                self.rpc_ids[rpc_id] = request_id
        self.backend.emit('tool/call', {'tool': params['name'], 'arguments': params.get('arguments', {})},
                          request_id=request_id)
        try:
            while self.available(request_id):
                try:
                    answer = waiter.get(timeout=.1)
                    result = answer.get('result', {})
                    return self.result(bool(result.get('success')), result.get('text') or
                                       answer.get('error', {}).get('message', 'Tool refused.'))
                except queue.Empty:
                    pass
            return self.result(False, 'Task closed.')
        finally:
            with self.lock:
                self.pending.pop(request_id, None)
                if self.rpc_ids.get(rpc_id) == request_id:
                    del self.rpc_ids[rpc_id]
            self.backend.take_request(request_id)

    @staticmethod
    def result(success, text):
        return {'content': [{'type': 'text', 'text': text}], 'isError': not success}

    def available(self, request_id):
        with self.lock:
            pending = self.pending.get(request_id)
            return bool(not self.closed and pending and (not pending[1] or pending[1]()))

    def cancel(self, rpc_id):
        if not isinstance(rpc_id, (int, str)):
            return
        with self.lock:
            self.cancelled_rpc_ids.add(rpc_id)
            self.pending.pop(self.rpc_ids.pop(rpc_id, None), None)

    def send(self, message):
        with self.lock:
            pending = self.pending.get(message.get('id'))
            if not self.closed and pending and (not pending[1] or pending[1]()):
                try:
                    pending[0].put_nowait(message)
                except queue.Full:
                    pass

    def close(self):
        with self.lock:
            self.closed = True
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
