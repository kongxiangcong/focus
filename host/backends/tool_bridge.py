"""Private MCP transport for the official Harness SDK's Host-owned tools.

The bridge owns transport only. Application permissions and writes remain in the
existing Host event handler. Every invocation waits for that handler's answer.
"""
import json
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ToolBridge:
    def __init__(self, backend, tools):
        self.backend = backend
        self.tools = {tool['name']: tool for tool in tools}
        self.pending = {}
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
                        self.send_response(202)
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    result = bridge.dispatch(value.get('method'), value.get('params', {}))
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

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/{self.token}'

    def dispatch(self, method, params):
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
            request_id = self.backend.next_request_id()
            waiter = queue.Queue(maxsize=1)
            self.pending[request_id] = waiter
        self.backend.emit('tool/call', {'tool': params['name'], 'arguments': params.get('arguments', {})},
                          request_id=request_id)
        try:
            # Host owns approval lifetime. Candidate deadlines and Stop close
            # this bridge; a displayed user question cannot expire invisibly.
            while not self.closed:
                try:
                    answer = waiter.get(timeout=.25)
                    result = answer.get('result', {})
                    return self.result(bool(result.get('success')), result.get('text') or
                                       answer.get('error', {}).get('message', 'Tool refused.'))
                except queue.Empty:
                    pass
            return self.result(False, 'Task closed.')
        finally:
            with self.lock:
                self.pending.pop(request_id, None)
            self.backend.take_request(request_id)

    @staticmethod
    def result(success, text):
        return {'content': [{'type': 'text', 'text': text}], 'isError': not success}

    def send(self, message):
        with self.lock:
            waiter = self.pending.get(message.get('id'))
            if waiter:
                try:
                    waiter.put_nowait(message)
                except queue.Full:
                    pass

    def close(self):
        self.closed = True
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
