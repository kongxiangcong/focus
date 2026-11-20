"""Process-local successful Source probes, keyed by the effective invocation."""
import hashlib
import json
import threading
from dataclasses import dataclass

from .backend_probe import verify_source_round_trip
from .backends.base import BackendError, safe_backend_error


@dataclass(frozen=True)
class BackendInvocation:
    backend: str
    command: tuple[str, ...]
    model: str

    @property
    def receipt_id(self):
        serialized = json.dumps([self.backend, self.command, self.model], ensure_ascii=False)
        return hashlib.sha256(serialized.encode()).hexdigest()


class BackendVerification:
    def __init__(self):
        self._lock = threading.Lock()
        self._passed = set()

    @staticmethod
    def resolve(registry, payload):
        spec = registry.get_spec(payload.get('backend'))
        command = registry.resolve_command(spec.id, payload.get('runtimePath'))
        model = payload.get('model') or spec.default_model
        if not isinstance(model, str) or not model.strip() or len(model) > 160 or '\r' in model or '\n' in model:
            raise BackendError('请为所选 Backend 输入有效模型，再重新检测。')
        return BackendInvocation(spec.id, command, model.strip())

    def passed(self, invocation):
        with self._lock:
            return invocation in self._passed

    def verify(self, payload, *, registry, reuse=True, invocation=None, cancelled=None):
        try:
            invocation = invocation or self.resolve(registry, payload)
        except BackendError as exc:
            return {'backend': payload.get('backend'), 'runtimePath': payload.get('runtimePath'),
                    'status': 'failed', 'dependencyStatus': 'unavailable', 'message': str(exc)}
        result = {'backend': invocation.backend, 'runtimePath': invocation.command[0],
                  'checkedModel': invocation.model, 'dependencyStatus': 'installed'}
        if reuse and self.passed(invocation):
            return {**result, 'status': 'success', 'message': 'Backend 已通过原文读取检测。',
                    'environmentId': invocation.receipt_id}

        def factory(workspace, **options):
            return registry.create_backend(invocation.backend, workspace, model=invocation.model,
                runtime_path=invocation.command[0], credential_file=payload.get('credentialFile'), **options)

        try:
            status, message = verify_source_round_trip(factory, cancelled=cancelled)
        except Exception as exc:
            status, message = 'failed', safe_backend_error(exc)
        result.update(status=status, message=message)
        if status == 'success':
            with self._lock:
                self._passed.add(invocation)
            result['environmentId'] = invocation.receipt_id
        return result
