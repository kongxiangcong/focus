"""Host-owned dependency and authentication checks, independent of business state.

Setup never activates a backend or opens a FOCUS Discussion. Runtime errors are
projected as fixed, actionable messages rather than leaking provider diagnostics.
"""
import os
import shutil
import tempfile
import queue
import threading
import time
import subprocess
import sys
import importlib.util
from contextlib import contextmanager
from urllib.parse import urlsplit
from pathlib import Path

from .proxy import backend_environment
from .runtime import AppServer
from .backends.base import safe_backend_error


def deepseek_key(credential_file=None):
    """Read only the named key. Never return .env contents in a Host projection."""
    if not credential_file and os.getenv('DEEPSEEK_API_KEY'):
        return os.environ['DEEPSEEK_API_KEY']
    path = Path(credential_file) if credential_file else Path(__file__).resolve().parents[1] / '.env'
    if not path.is_file():
        return ''
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        key, separator, value = line.strip().removeprefix('export ').partition('=')
        if separator and key.strip() == 'DEEPSEEK_API_KEY':
            return value.strip().strip('"\'')
    return ''


def runtime_path(backend, explicit=None):
    if backend not in ('codex', 'deepseek'):
        raise ValueError('请选择 Codex 或 DeepSeek。')
    if explicit:
        return str(Path(explicit).expanduser().absolute())
    installed = shutil.which('codex' if backend == 'codex' else 'dsh')
    if installed:
        return installed
    try:
        if backend == 'codex':
            from codex_cli_bin import bundled_codex_path
            return str(bundled_codex_path())
        from deepseek_harness_runtime import bundled_runtime_path
        return str(bundled_runtime_path())
    except (ImportError, FileNotFoundError):
        return None


class BackendSetup:
    def __init__(self):
        self.login_lock = threading.RLock()
        self.login = None
        self.install_lock = threading.Lock()

    def prepare(self, payload):
        with self.install_lock:
            status = self.inspect(payload)
            if payload.get('runtimePath') and status['status'] == 'unavailable':
                return status  # An explicit broken path is never silently replaced.
            module = 'deepseek_harness' if status['backend'] == 'deepseek' else 'codex_cli_bin'
            needs_sdk = status['backend'] == 'deepseek' and importlib.util.find_spec(module) is None
            if status['status'] == 'installed' and not needs_sdk:
                return status
            package = 'deepseek-harness-sdk' if status['backend'] == 'deepseek' else 'openai-codex'
            try:
                # An existing external DSH must not cause a hidden bundled copy
                # to be installed merely to obtain the Python protocol client.
                options = ['--no-deps'] if needs_sdk and status['status'] == 'installed' else []
                if options:
                    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-input', 'pydantic>=2.12,<3'],
                                   capture_output=True, timeout=240, check=True)
                subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-input', *options, package],
                               capture_output=True, timeout=240, check=True)
                importlib.invalidate_caches()
            except (OSError, subprocess.SubprocessError):
                return {**status, 'status': 'failed', 'message': '依赖安装失败，请检查网络后重试此 Backend。'}
            return self.inspect(payload)

    @contextmanager
    def codex_account_runtime(self, status):
        env = backend_environment('codex')
        for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
            env.pop(key, None)
        with tempfile.TemporaryDirectory(prefix='focus-account-') as temporary:
            rpc = AppServer([status['runtimePath'], '-c', 'forced_login_method="chatgpt"'], temporary, env=env)
            try:
                rpc.initialize()
                rpc.send({'method': 'initialized', 'params': {}})
                yield rpc
            finally:
                rpc.close()

    def login_operation(self, action, payload):
        with self.login_lock:
            status = self.inspect(payload)
            if status['backend'] != 'codex' or status['status'] == 'unavailable':
                raise ValueError('请选择已安装的 Codex Runtime。')
            if action == 'login-start':
                self.close()
                context = self.codex_account_runtime(status)
                rpc = context.__enter__()
                try:
                    result = rpc.request('account/login/start', {'type': 'chatgpt'}, timeout=15)
                    url = urlsplit(result['authUrl'])
                    if url.scheme != 'https' or url.hostname not in ('auth.openai.com', 'auth0.openai.com', 'auth.chatgpt.com'):
                        raise ValueError('Runtime 返回了无效的授权地址。')
                    self.login = {'context': context, 'rpc': rpc, 'id': result['loginId'],
                                  'path': status['runtimePath'], 'deadline': time.monotonic()+300}
                    expiry = threading.Timer(300, self.close)
                    expiry.daemon = True
                    self.login['expiry'] = expiry
                    expiry.start()
                    return {**status, 'status': 'waiting', 'loginId': result['loginId'],
                            'authUrl': result['authUrl'], 'message': '请在浏览器完成授权；打开页面不代表登录成功。'}
                except Exception:
                    context.__exit__(None, None, None)
                    raise
            login = self.login
            if not login or payload.get('loginId') != login['id'] or status['runtimePath'] != login['path']:
                return {**status, 'status': 'expired', 'message': '登录请求已失效，请重试。'}
            if action == 'login-cancel' or time.monotonic() >= login['deadline']:
                try:
                    login['rpc'].request('account/login/cancel', {'loginId': login['id']}, timeout=10)
                finally:
                    self.close()
                return {**status, 'status': 'cancelled', 'message': '登录已取消，可以重试。'}
            while True:
                try:
                    event = login['rpc'].events.get_nowait()
                except queue.Empty:
                    return {**status, 'status': 'waiting', 'message': '等待浏览器授权。', 'loginId': login['id']}
                if event.get('method') == '_transport_error':
                    self.close()
                    return {**status, 'status': 'failed', 'message': '授权连接已关闭，请重试。'}
                params = event.get('params', {})
                if event.get('method') == 'account/login/completed' and params.get('loginId') == login['id']:
                    try:
                        account = login['rpc'].request('account/read', {'refreshToken': True}, timeout=15).get('account')
                        success = bool(params.get('success') and account and account.get('type') == 'chatgpt')
                        return {**status, 'status': 'authenticated' if success else 'failed',
                                'message': '已确认 ChatGPT / Codex 登录。' if success else '授权未完成，请重试。'}
                    finally:
                        self.close()

    def check(self, payload):
        from .backends import create_backend
        status = self.inspect(payload)
        if status['status'] == 'unavailable':
            return {**status, 'status': 'failed'}
        key = deepseek_key(payload.get('credentialFile')) if status['backend'] == 'deepseek' else None
        if status['backend'] == 'deepseek' and not key:
            return {**status, 'status': 'failed', 'message': '未配置 DeepSeek 凭据，请在 Host 的 .env 设置 DEEPSEEK_API_KEY。'}
        # The private workspace is never passed to a diagnostic model request.
        with tempfile.TemporaryDirectory(prefix='focus-connectivity-') as temporary:
            backend = create_backend(status['backend'], Path(temporary), model=payload.get('model'),
                codex_bin=status['runtimePath'], runtime_path=status['runtimePath'], api_key=key,
                purpose='connectivity')
            timer = threading.Timer(45, backend.close)
            timer.start()
            text = ''
            try:
                backend.open_session(None, instructions='Reply FOCUS_OK. No tools or source material are provided.')
                backend.start_turn(prompt='Reply exactly FOCUS_OK. Do not use tools.')
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    event = backend.events.get(timeout=max(.01, deadline-time.monotonic()))
                    method, params = event.get('method'), event.get('params', {})
                    if 'id' in event:
                        backend.send({'id': event['id'], 'error': {'message': 'Connectivity checks do not permit tools.'}})
                    elif method == 'message/completed':
                        text = params.get('text', '')
                    elif method == 'message/delta':
                        text += params.get('delta', '')
                    elif method == 'turn/completed':
                        if params.get('status') != 'completed' or text.strip() != 'FOCUS_OK':
                            raise RuntimeError(params.get('error') or 'request failed')
                        return {**status, 'status': 'success', 'message': '本次最小请求成功；不代表完整业务能力已通过验收。'}
                    elif method == '_transport_error':
                        raise RuntimeError(params.get('message') or 'transport failed')
                raise TimeoutError()
            except (TimeoutError, queue.Empty):
                return {**status, 'status': 'failed', 'message': '请求超时，请检查网络和 Runtime。'}
            except Exception as exc:
                return {**status, 'status': 'failed', 'message': safe_backend_error(exc)}
            finally:
                timer.cancel()
                backend.close()

    def account(self, payload):
        status = self.inspect(payload)
        if status['status'] == 'unavailable':
            return status
        if status['backend'] != 'codex':
            raise ValueError('此账号操作仅适用于 Codex。')
        with self.codex_account_runtime(status) as rpc:
            account = rpc.request('account/read', {'refreshToken': True}, timeout=15).get('account')
            authenticated = bool(account and account.get('type') == 'chatgpt')
            return {**status, 'status': 'authenticated' if authenticated else 'not-configured',
                    'message': '已登录 ChatGPT / Codex。' if authenticated else '请使用 ChatGPT / Codex 浏览器登录。'}

    def inspect(self, payload):
        backend = payload.get('backend', 'codex')
        selected = runtime_path(backend, payload.get('runtimePath'))
        available = bool(selected and Path(selected).is_file())
        return {'backend': backend, 'runtimePath': selected,
                'status': 'installed' if available else 'unavailable',
                'message': '依赖已安装；尚未验证认证和连通性。' if available else 'Runtime 不存在，请检查指定路径或准备依赖。'}

    def operate(self, action, payload):
        if action == 'inspect':
            return self.inspect(payload)
        if action == 'prepare':
            return self.prepare(payload)
        if action == 'account':
            return self.account(payload)
        if action == 'check':
            return self.check(payload)
        if action in ('login-start', 'login-status', 'login-cancel'):
            return self.login_operation(action, payload)
        raise ValueError('未知 Backend 设置操作。')

    def close(self):
        with self.login_lock:
            login, self.login = self.login, None
            if login:
                login['expiry'].cancel()
                login['context'].__exit__(None, None, None)
