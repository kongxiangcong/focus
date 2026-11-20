"""Stdio JSON-RPC transport and the Codex App Server handshake."""
import json
import os
import queue
import subprocess
import threading
import time
import shutil

def codex_command(explicit=None):
    if explicit:
        return [explicit]
    installed = shutil.which('codex')
    if installed:
        return [installed]
    from codex_cli_bin import bundled_codex_path
    return [str(bundled_codex_path())]


class JsonRpcStdioClient:
    def __init__(self, command, cwd, *, env=None, jsonrpc=False):
        self.pending = {}
        self.event_requests = set()
        self.jsonrpc = jsonrpc
        self.events = queue.Queue()
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.next_id = 0
        self.closed = False
        self.deadline = None
        self.process = subprocess.Popen(command, cwd=cwd, env=env,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                value = json.loads(line)
                if 'method' not in value and 'id' in value:
                    with self.lock:
                        request_id = value['id']
                        waiter = self.pending.get(request_id)
                        deliver_event = request_id in self.event_requests
                        self.event_requests.discard(request_id)
                    if waiter:
                        waiter.put(value)
                    elif deliver_event:
                        self.events.put(value)
                else:
                    self.events.put(value)
        except Exception as exc:
            self.events.put({'method': '_transport_error', 'params': {'message': str(exc)}})
        finally:
            error = {'error': {'message': 'Backend process exited; check installation, authentication and runtime version.'}}
            with self.lock:
                self.closed = True
                for waiter in self.pending.values():
                    waiter.put(error)
            self.events.put({'method': '_transport_error', 'params': {'message': error['error']['message']}})

    def send(self, value):
        with self.write_lock:
            if self.closed:
                raise RuntimeError('Backend process is not running')
            if self.jsonrpc:
                value = {'jsonrpc': '2.0', **value}
            self.process.stdin.write(json.dumps(value, ensure_ascii=False) + '\n')
            self.process.stdin.flush()

    def request_event(self, method, params):
        """Receive the reply on events in transport order with notifications."""
        if self.deadline is not None and self.deadline <= time.monotonic():
            raise TimeoutError(f'{method} timed out')
        with self.lock:
            if self.closed:
                raise RuntimeError('Backend process is not running')
            self.next_id += 1
            request_id = self.next_id
            self.event_requests.add(request_id)
        try:
            self.send({'id': request_id, 'method': method, 'params': params})
        except Exception:
            with self.lock:
                self.event_requests.discard(request_id)
            raise
        return request_id

    def request(self, method, params, timeout=60):
        if self.deadline is not None:
            timeout = min(timeout, self.deadline - time.monotonic())
            if timeout <= 0:
                raise TimeoutError(f'{method} timed out')
        with self.lock:
            if self.closed:
                raise RuntimeError('Backend process is not running')
            self.next_id += 1
            request_id = self.next_id
            waiter = queue.Queue()
            self.pending[request_id] = waiter
        try:
            self.send({'id': request_id, 'method': method, 'params': params})
            try:
                value = waiter.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError(f'{method} timed out') from exc
            if 'error' in value:
                raise RuntimeError(value['error'].get('message', str(value['error'])))
            return value['result']
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def close(self):
        if self.process.poll() is None:
            if os.name == 'nt':
                # PATH may select an npm .cmd launcher. Terminating that wrapper
                # alone leaves its Node/Codex child alive with the stdio handles.
                subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                               capture_output=True, timeout=10, check=False)
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()


class AppServer(JsonRpcStdioClient):
    def initialize(self):
        return self.request('initialize', {'clientInfo': {'name': 'focus_web', 'version': '0.1.0'},
                                          'capabilities': {'experimentalApi': True}}, timeout=15)
