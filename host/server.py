"""Same-origin HTTP + SSE boundary. Intended for one trusted owner, one workspace."""
import hmac
import json
import mimetypes
import os
import re
import secrets
import socket
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .core_bridge import ROOT, WorkspaceError


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service, token=None, public_origin=None):
        self.service = service
        self.token = token or secrets.token_urlsafe(32)
        self.public_origin = public_origin
        self.local_access = token is None and public_origin is None and address[0] in ('127.0.0.1', 'localhost')
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, format, *args):
        # Do not log query strings, user content, paths or credentials.
        pass

    def _send(self, status, value, *, content_type='application/json; charset=utf-8', headers=None):
        data = json.dumps(value, ensure_ascii=False).encode() if content_type.startswith('application/json') else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if self.close_connection:
            self.send_header('Connection', 'close')
        for name, val in (headers or {}).items():
            self.send_header(name, val)
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        if self.server.local_access and self.client_address[0] in ('127.0.0.1', '::1'):
            return True
        cookie = dict(pair.strip().split('=', 1) for pair in self.headers.get('Cookie', '').split(';') if '=' in pair)
        credential = self.headers.get('Authorization', '').removeprefix('Bearer ') or cookie.get('focus_host', '')
        return hmac.compare_digest(credential, self.server.token)

    def _origin_ok(self):
        # Strict Host check defeats DNS rebinding; no wildcard CORS.
        host = self.headers.get('Host', '')
        port = self.server.server_port
        allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if self.server.public_origin:
            allowed.add(urlsplit(self.server.public_origin).netloc)
        if host not in allowed:
            return False
        origin = self.headers.get('Origin')
        return origin is None or origin in {f'http://127.0.0.1:{port}', f'http://localhost:{port}', self.server.public_origin}

    def _body(self, limit=1000000):
        length = int(self.headers.get('Content-Length', '0'))
        if length < 1 or length > limit:
            raise ValueError('Invalid request size')
        value = json.loads(self.rfile.read(length))
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value

    def do_GET(self):
        self._handle('GET')

    def do_DELETE(self):
        self._handle('DELETE')

    def do_POST(self):
        self._handle('POST')

    def _handle(self, method):
        try:
            self.connection.settimeout(30)
            if not self._origin_ok():
                self.close_connection = True
                self._send(403, {'ok': False, 'error': {'code': 'invalid-request', 'message': 'Origin/Host rejected', 'retryable': False}})
                return
            path = urlsplit(self.path).path
            if path.startswith(('/reader/', '/library/')):
                if method == 'POST' and path == '/reader/login':
                    payload = self._body()
                    if not hmac.compare_digest(str(payload.get('token', '')), self.server.token):
                        self._send(401, {'ok': False, 'error': {'code': 'unavailable', 'message': '访问口令不正确', 'retryable': False}})
                        return
                    secure = '; Secure' if (self.server.public_origin or '').startswith('https:') else ''
                    self._send(200, {'ok': True}, headers={'Set-Cookie': f'focus_host={self.server.token}; HttpOnly; SameSite=Strict; Path=/{secure}'})
                    return
                if not self._authorized():
                    self.close_connection = True
                    self._send(401, {'ok': False, 'error': {'code': 'unavailable', 'message': '请先输入 FOCUS 访问口令', 'retryable': False}})
                    return
                self._api(method, path)
            elif method == 'GET':
                root = ROOT / 'ui/apps/standalone/dist'
                relative = 'index.html' if path in ('/', '/library', '/reading', '/settings') else unquote(path).lstrip('/')
                target = (root / relative).resolve()
                if not target.is_relative_to(root.resolve()) or not target.is_file():
                    self._send(404, b'Build the UI with pnpm reader:build, then open /.', content_type='text/plain')
                    return
                self._send(200, target.read_bytes(), content_type=mimetypes.guess_type(target)[0] or 'application/octet-stream',
                           headers={'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"})
            else:
                self._send(404, {'ok': False})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception as exc:
            self.close_connection = True
            code = 'cursor-changed' if getattr(exc, 'error_id', None) == 'cursor_changed' else 'invalid-request' if isinstance(exc, (ValueError, WorkspaceError)) else 'unavailable'
            self._send(409 if code == 'cursor-changed' else 400 if code == 'invalid-request' else 500,
                       {'ok': False, 'error': {'code': code, 'message': str(exc), 'retryable': code == 'unavailable'}})

    def _api(self, method, path):
        service = self.server.service
        if method == 'GET' and path == '/reader/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Accel-Buffering', 'no')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            generation = -1
            while not service.shutting_down:
                with service.condition:
                    if generation == service.generation:
                        service.condition.wait(timeout=10)
                    if service.shutting_down:
                        break
                    if generation == service.generation:
                        frame = b': heartbeat\n\n'
                    else:
                        generation = service.generation
                        try:
                            value = {'ok': True, 'value': service.snapshot()}
                        except Exception as exc:
                            value = {'ok': False, 'error': {'code': 'invalid-response', 'message': str(exc), 'retryable': False}}
                        frame = ('event: snapshot\ndata: ' + json.dumps(value, ensure_ascii=False) + '\n\n').encode()
                self.wfile.write(frame)
                self.wfile.flush()
            return
        if method == 'GET' and path.startswith('/reader/assets/'):
            source, relative = unquote(path[len('/reader/assets/'):]).split('/', 1)
            target = service.core.image(source, relative)
            self._send(200, target.read_bytes(), content_type=mimetypes.guess_type(target)[0] or 'image/png')
            return
        if method == 'GET' and path == '/library/topics':
            result = service.library_topics()
        elif method == 'GET' and path == '/library/sources':
            result = service.library_sources()
        elif path.startswith('/library/sources/'):
            parts = path[len('/library/sources/'):].split('/')
            source_id = unquote(parts[0])
            if method == 'DELETE' and len(parts) == 1:
                result = service.library_delete(source_id)
            elif method == 'POST' and len(parts) == 2 and parts[1] in ('reread', 'replan', 'open'):
                self._body()
                result = service.library_read(source_id, reread=parts[1] == 'reread', replan=parts[1] == 'replan')
            else:
                raise ValueError('Unknown Library operation')
        elif method == 'GET' and path == '/reader/window':
            result = service.snapshot()
        elif method == 'POST' and path == '/reader/session':
            result = service.new_session(self._body())
        elif method == 'POST' and path == '/reader/backend':
            result = service.select_backend(self._body())
        elif method == 'POST' and path == '/reader/resume':
            result = service.resume_reading(self._body())
        elif method == 'POST' and path == '/reader/messages':
            result = service.start(self._body())
        elif method == 'POST' and path == '/reader/continue':
            result = service.start(self._body(), continuing=True)
        elif method == 'POST' and path == '/reader/stop':
            self._body()
            result = service.stop()
        elif method == 'POST' and path == '/reader/approval':
            result = service.approve(self._body())
        elif method == 'POST' and path in ('/reader/upload', '/library/sources'):
            name = parse_qs(urlsplit(self.path).query).get('name', [''])[0]
            if Path(name).name != name or '\\' in name or len(name) > 180 or Path(name).suffix.lower() not in ('.pdf', '.html', '.md', '.markdown'):
                raise ValueError('选择 PDF、单文件 HTML 或 Markdown。')
            fields = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            topic = fields.get('topic', [''])[0].strip()
            uploader = fields.get('uploader', ['孔祥聪'])[0].strip()
            if path == '/library/sources' and (not topic or len(topic) > 120 or not uploader or len(uploader) > 100):
                raise ValueError('请填写专题和上传者。')
            length = int(self.headers.get('Content-Length', '0'))
            if length < 1 or length > 200 * 1024 * 1024:
                raise ValueError('文件大小须为 1 字节到 200 MB。')
            upload_id = uuid.uuid4().hex
            base = (service.workspace / 'uploads').resolve()
            if not base.is_relative_to(service.workspace):
                raise ValueError('Upload directory is outside the Workspace')
            root = base / upload_id
            root.mkdir(parents=True)
            target = root / name
            try:
                with target.open('xb') as out:
                    remaining = length
                    while remaining:
                        data = self.rfile.read(min(remaining, 65536))
                        if not data:
                            raise ValueError('Upload interrupted')
                        out.write(data)
                        remaining -= len(data)
                if path == '/library/sources' and target.suffix.lower() == '.pdf':
                    with target.open('rb') as uploaded:
                        if uploaded.read(4) != b'%PDF':
                            raise ValueError('文件内容不是 PDF。')
                service.store.put('upload:' + upload_id, {'name': name, 'path': str(target)})
            except Exception:
                target.unlink(missing_ok=True)
                root.rmdir()
                raise
            if path == '/library/sources':
                try:
                    result = service.library_upload(upload_id, topic=topic, uploader=uploader)
                except Exception:
                    target.unlink(missing_ok=True)
                    root.rmdir()
                    service.store.put('upload:' + upload_id, None)
                    raise
                self._send(202, {'ok': True, 'value': result})
                return
            self._send(200, {'ok': True, 'value': {'attachmentId': upload_id, 'name': name}})
            return
        else:
            self._send(404, {'ok': False, 'error': {'code': 'invalid-request', 'message': 'Unknown route', 'retryable': False}})
            return
        self._send(200, {'ok': True, 'value': result})
