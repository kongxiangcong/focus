"""Stdio JSON-RPC transport and the Codex App Server handshake."""
import json
import os
import queue
import subprocess
import threading
import time
import shutil

from .process_lifecycle import WindowsJob, stop_process

def codex_command(explicit=None):
    if explicit:
        return [explicit]
    installed = shutil.which('codex')
    if installed:
        return [installed]
    from codex_cli_bin import bundled_codex_path
    return [str(bundled_codex_path())]


class JsonRpcStdioClient:
    def __init__(self, command, cwd, *, env=None, jsonrpc=False, isolated_process=False):
        self.pending = {}
        self.event_requests = set()
        self.jsonrpc = jsonrpc
        self.events = queue.Queue()
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.process_lock = threading.Lock()
        self.next_id = 0
        self.closed = False
        self.deadline = None
        self.isolated_process = isolated_process
        self.process = subprocess.Popen(command, cwd=cwd, env=env,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1,
                                        start_new_session=isolated_process and os.name != 'nt')
        self.job = WindowsJob(self.process) if isolated_process and os.name == 'nt' else None
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        if isolated_process:
            threading.Thread(target=self._watch_exit, name='focus-runtime-exit', daemon=True).start()

    def _watch_exit(self):
        self.process.wait()
        # Drain complete messages already in the pipe before reacting to process exit.
        self.reader.join(timeout=.15)
        if self.reader.is_alive():
            with self.process_lock:
                stop_process(self.process, isolated=True, job=self.job)
            self.reader.join(timeout=.15)
        if self.reader.is_alive():
            self._disconnected()

    def _disconnected(self):
        message = 'Backend process exited; check installation, authentication and runtime version.'
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for waiter in self.pending.values():
                waiter.put({'error': {'message': message}})
        self.events.put({'method': '_transport_error', 'params': {'message': message}})

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
            self._disconnected()
            self.process.stdout.close()

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
        with self.process_lock:
            stop_process(self.process, isolated=self.isolated_process, job=self.job)
        self.reader.join(timeout=2)
        if not self.reader.is_alive():
            self.process.stdin.close()


class AppServer(JsonRpcStdioClient):
    def initialize(self):
        return self.request('initialize', {'clientInfo': {'name': 'focus_web', 'version': '0.1.0'},
                                          'capabilities': {'experimentalApi': True}}, timeout=15)
