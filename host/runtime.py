"""Versioned stdio JSON-RPC adapter for the official Codex App Server."""
import json
import os
import queue
import subprocess
import threading

RUNTIME_VERSION = '0.154.0'


def codex_command(explicit=None):
    if explicit:
        return [explicit]
    from codex_cli_bin import bundled_codex_path
    return [str(bundled_codex_path())]


class AppServer:
    def __init__(self, command, cwd, *, env=None):
        self.pending = {}
        self.events = queue.Queue()
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.next_id = 0
        self.closed = False
        self.process = subprocess.Popen([*command, 'app-server'], cwd=cwd, env=env,
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
                        waiter = self.pending.get(value['id'])
                    if waiter:
                        waiter.put(value)
                else:
                    self.events.put(value)
        except Exception as exc:
            self.events.put({'method': '_transport_error', 'params': {'message': str(exc)}})
        finally:
            error = {'error': {'message': 'Codex App Server exited; check installation, authentication and runtime version.'}}
            with self.lock:
                self.closed = True
                for waiter in self.pending.values():
                    waiter.put(error)
            self.events.put({'method': '_transport_error', 'params': {'message': error['error']['message']}})

    def send(self, value):
        with self.write_lock:
            if self.closed:
                raise RuntimeError('Codex App Server is not running')
            self.process.stdin.write(json.dumps(value, ensure_ascii=False) + '\n')
            self.process.stdin.flush()

    def request(self, method, params, timeout=60):
        with self.lock:
            if self.closed:
                raise RuntimeError('Codex App Server is not running')
            self.next_id += 1
            request_id = self.next_id
            waiter = queue.Queue()
            self.pending[request_id] = waiter
        try:
            self.send({'id': request_id, 'method': method, 'params': params})
            try:
                value = waiter.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError(f'Codex {method} timed out') from exc
            if 'error' in value:
                raise RuntimeError(value['error'].get('message', str(value['error'])))
            return value['result']
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def initialize(self):
        return self.request('initialize', {'clientInfo': {'name': 'focus_web', 'version': '0.1.0'},
                                          'capabilities': {'experimentalApi': True}})

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()
