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
import hashlib
import hmac
import json
import secrets
from urllib.request import Request, urlopen, build_opener, ProxyHandler
from contextlib import contextmanager
from urllib.parse import urlsplit
from pathlib import Path

from .proxy import backend_environment
from .runtime import AppServer
from .backends.base import safe_backend_error
from .configuration import DEFAULT_MODELS


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
    # Prefer the already-installed SDK's matching protocol carrier.  A global
    # CLI may be older than the machine's Codex configuration.  This is local
    # discovery only; an explicit selection is never replaced.
    if backend == 'codex':
        try:
            from codex_cli_bin import bundled_codex_path
            return str(bundled_codex_path())
        except (ImportError, FileNotFoundError):
            pass
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
        self.check_lock = threading.RLock()
        self.authentication_salt = secrets.token_bytes(32)
        self.connections = {}

    def environment_id(self, payload, status):
        path = Path(status['runtimePath']) if status.get('runtimePath') else None
        runtime = (str(path.resolve()), path.stat().st_size, path.stat().st_mtime_ns) if path and path.is_file() else None
        if status['backend'] == 'deepseek':
            authentication = deepseek_key(payload.get('credentialFile'))
        else:
            home = Path(os.getenv('CODEX_HOME') or Path.home() / '.codex')
            auth = home / 'auth.json'
            authentication = auth.read_text(encoding='utf-8') if auth.is_file() else ''
        private = json.dumps([status['backend'], runtime, authentication, os.getenv('DEEPSEEK_BASE_URL') if status['backend'] == 'deepseek' else None])
        return hmac.new(self.authentication_salt, private.encode(), hashlib.sha256).hexdigest()

    def discover(self, payload, status):
        if status['backend'] == 'codex':
            values, cursor, seen = [], None, set()
            with self.codex_account_runtime(status) as rpc:
                while True:
                    result = rpc.request('model/list', {'limit': 100, 'cursor': cursor, 'includeHidden': False}, timeout=20)
                    values.extend(item['model'] for item in result.get('data', []) if isinstance(item.get('model'), str))
                    cursor = result.get('nextCursor')
                    if not cursor:
                        break
                    if cursor in seen:
                        raise ValueError('model list pagination repeated')
                    seen.add(cursor)
            return list(dict.fromkeys(values))
        base = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')
        if urlsplit(base).scheme != 'https':
            raise ValueError('model endpoint must use HTTPS')
        request = Request(base + '/models', headers={'Authorization': 'Bearer ' + deepseek_key(payload.get('credentialFile'))})
        environment = backend_environment('deepseek')
        proxy = environment.get('HTTPS_PROXY') or environment.get('https_proxy')
        proxies = {} if environment.get('NO_PROXY') == '*' else {'https': proxy} if proxy else None
        opener = build_opener(ProxyHandler(proxies))
        with opener.open(request, timeout=20) as response:
            result = json.load(response)
        # DSH's official provider uses the Anthropic Messages protocol.  Only
        # text models whose supplier metadata declares that path are offered.
        return [item['id'] for item in result['data'] if isinstance(item.get('id'), str)
                and 'text' in item.get('input_modalities', []) and 'text' in item.get('output_modalities', [])
                and isinstance(item.get('api_capabilities', {}).get('anthropic_messages'), dict)]

    def models(self, payload):
        status = self.inspect(payload)
        environment = self.environment_id(payload, status)
        if environment not in self.connections:
            return {**status, 'status': 'failed', 'catalogStatus': 'not-loaded', 'environmentId': environment,
                    'message': '先通过此环境的连接检查，再加载模型清单。'}
        try:
            models = self.discover(payload, status)
            if not models:
                raise ValueError('no supported models')
            refreshed = self.environment_id(payload, status)
            self.connections[refreshed] = self.connections[environment]
            return {**status, 'status': 'success', 'catalogStatus': 'loaded', 'models': models,
                    'environmentId': refreshed, 'message': '真实模型清单已加载；清单不代表所有模型已验证。'}
        except Exception:
            return {**status, 'status': 'success', 'catalogStatus': 'failed', 'environmentId': environment,
                    'models': [], 'message': '连接已通过，模型清单加载失败；可重试清单或使用默认模型。'}

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
        with self.check_lock:
            status = self.prepare(payload)
            if status['status'] != 'installed':
                return {**status, 'status': 'failed', 'dependencyStatus': status['status']}
            environment = self.environment_id(payload, status)
            model = (payload.get('model') or DEFAULT_MODELS[status['backend']]) if environment in self.connections else DEFAULT_MODELS[status['backend']]
            result = self.infer({**payload, 'runtimePath': status['runtimePath'], 'model': model})
            result.update(environmentId=environment, checkedModel=model, dependencyStatus='installed')
            if result['status'] == 'success':
                # Bind the receipt to the authentication state after refresh.
                environment = self.environment_id(payload, status)
                self.connections[environment] = model
                catalog = self.models({**payload, 'runtimePath': status['runtimePath']})
                result.update(environmentId=catalog.get('environmentId', environment), catalogStatus=catalog.get('catalogStatus'),
                              models=catalog.get('models', []), catalogMessage=catalog['message'])
            return result

    def infer(self, payload):
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
        if action == 'models':
            return self.models(payload)
        if action in ('login-start', 'login-status', 'login-cancel'):
            return self.login_operation(action, payload)
        raise ValueError('未知 Backend 设置操作。')

    def close(self):
        with self.login_lock:
            login, self.login = self.login, None
            if login:
                login['expiry'].cancel()
                login['context'].__exit__(None, None, None)
