"""Host-owned settings operations for a registered Backend."""
import tempfile
import threading
from contextlib import ExitStack
from pathlib import Path

from .backends import DEFAULT_REGISTRY, BackendError
from .backend_verification import BackendVerification
from .backends.base import BackendConfigurationError, safe_backend_error


class BackendSetup:
    def __init__(self, *, registry=None, verification=None):
        self.registry = registry or DEFAULT_REGISTRY
        self.verification = verification or BackendVerification()
        self.login_lock = threading.RLock()
        self.login = None
        self.check_lock = threading.RLock()

    def _runtime(self, stack, payload, status):
        workspace = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='focus-setup-')))
        backend = self.registry.create_backend(
            status['backend'], workspace, runtime_path=status['runtimePath'],
            credential_file=payload.get('credentialFile'), model=payload.get('model'),
            purpose='candidate', tools=[],
        )
        stack.callback(backend.close)
        return backend

    def _operation_error(self, status, error):
        message = str(error) if isinstance(error, BackendConfigurationError) else safe_backend_error(error)
        return {**status, 'status': 'failed', 'message': message}

    def models(self, payload):
        status = self.inspect(payload)
        if status['status'] != 'installed':
            return {**status, 'status': 'failed', 'catalogStatus': 'failed', 'models': []}
        spec = self.registry.get_spec(status['backend'])
        if spec.capabilities.get('modelDiscovery', 'none') == 'none':
            return {**status, 'status': 'failed', 'catalogStatus': 'not-supported', 'models': [],
                    'message': '此 Backend 不提供模型清单。'}
        try:
            with ExitStack() as stack:
                models = self._runtime(stack, payload, status).discover_models()
            if not models:
                raise BackendConfigurationError('Runtime 未返回可用模型，请重试。')
        except Exception as exc:
            return {**self._operation_error(status, exc), 'catalogStatus': 'failed', 'models': []}
        return {**status, 'status': 'success', 'catalogStatus': 'loaded', 'models': models,
                'message': '已加载模型清单。选择模型后可检测原文读取能力。'}

    def prepare(self, payload):
        """Compatibility action for older readers. Only discover the executable."""
        return self.inspect(payload)

    def login_operation(self, action, payload):
        with self.login_lock:
            status = self.inspect(payload)
            if status['status'] != 'installed':
                return self._operation_error(status, BackendConfigurationError(status['message']))
            spec = self.registry.get_spec(status['backend'])
            if spec.capabilities.get('authMode') != 'interactive-oauth':
                return {**status, 'status': 'external-login',
                        'message': spec.login_hint or '请通过本机 CLI 完成登录。'}
            command = self.registry.resolve_command(spec.id, status['runtimePath'])
            identity = spec.id, command, payload.get('credentialFile')
            if action == 'login-start':
                self.close()
                stack = ExitStack()
                try:
                    backend = self._runtime(stack, payload, status)
                    result = backend.start_login()
                    login = {'stack': stack, 'backend': backend, 'identity': identity, 'id': result['loginId']}
                    expiry = threading.Timer(300, self._expire_login, args=(login,))
                    expiry.daemon = True
                    self.login = login
                    login['expiry'] = expiry
                    expiry.start()
                    return {**status, **result, 'status': 'waiting', 'message': '请在浏览器完成授权。'}
                except Exception as exc:
                    stack.close()
                    return self._operation_error(status, exc)
            login = self.login
            if not login or payload.get('loginId') != login['id'] or identity != login['identity']:
                return {**status, 'status': 'expired', 'message': '登录请求已失效，请重试。'}
            try:
                if action == 'login-cancel':
                    login['backend'].cancel_login(login['id'])
                    self.close()
                    return {**status, 'status': 'cancelled', 'message': '登录已取消，可以重试。'}
                success = login['backend'].poll_login(login['id'])
                if success is None:
                    return {**status, 'status': 'waiting', 'message': '等待浏览器授权。', 'loginId': login['id']}
                self.close()
                return {**status, 'status': 'authenticated' if success else 'failed',
                        'message': '已确认登录。' if success else '授权未完成，请重试。'}
            except Exception as exc:
                self.close()
                return self._operation_error(status, exc)

    def _expire_login(self, login):
        with self.login_lock:
            if self.login is login:
                self.close()

    def check(self, payload):
        with self.check_lock:
            return self.verification.verify(payload, registry=self.registry, reuse=False)

    def account(self, payload):
        status = self.inspect(payload)
        if status['status'] != 'installed':
            return status
        spec = self.registry.get_spec(status['backend'])
        if spec.capabilities.get('authMode') != 'interactive-oauth':
            return {**status, 'status': 'external-login',
                    'message': spec.login_hint or '请通过本机 CLI 完成登录。'}
        try:
            with ExitStack() as stack:
                authenticated = self._runtime(stack, payload, status).account()
        except Exception as exc:
            return self._operation_error(status, exc)
        return {**status, 'status': 'authenticated' if authenticated else 'not-configured',
                'message': '已确认登录。' if authenticated else (spec.login_hint or '请先登录此 Backend。')}

    def inspect(self, payload):
        backend = payload.get('backend')
        explicit = payload.get('runtimePath')
        try:
            selected, *_ = self.registry.resolve_command(backend, explicit)
        except BackendError as exc:
            return {'backend': backend, 'runtimePath': str(Path(explicit).expanduser().absolute()) if explicit else None,
                    'status': 'unavailable', 'message': str(exc)}
        return {'backend': backend, 'runtimePath': selected, 'status': 'installed',
                'message': '已找到可执行文件；尚未验证认证和连通性。'}

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
                login['stack'].close()
