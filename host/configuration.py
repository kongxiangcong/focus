"""User settings, separate from Knowledge Base and Host business history."""
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from .backends import DEFAULT_REGISTRY, BackendError, HarnessRegistry

DEFAULT_MODELS = {spec.id: spec.default_model for spec in DEFAULT_REGISTRY.list_specs()}
_USE_SAVED = object()


@dataclass(frozen=True)
class StartupSelection:
    configuration: dict | None
    error: str | None = None


def resolve_startup(settings, *, backend=None, backend_bin=None, model=None):
    """Resolve temporary launch flags over environment variables and stored preferences."""
    backend = backend if backend is not None else os.getenv('FOCUS_BACKEND') or None
    backend_bin = backend_bin if backend_bin is not None else os.getenv('FOCUS_BACKEND_BIN') or None
    model = model if model is not None else os.getenv('FOCUS_MODEL') or None
    if backend is None and backend_bin is None and model is None:
        return None
    saved = settings.read()
    if backend is None:
        backend = saved['backend'] if saved else None
    if not isinstance(backend, str) or not backend.strip():
        return StartupSelection(None, '请使用 --backend 或 FOCUS_BACKEND 指定启动配置。')
    preference = saved if saved and saved['backend'] == backend else settings.preferences().get(backend, {})
    value = {'backend': backend, 'model': preference.get('model'), 'runtimePath': preference.get('runtimePath'),
             'credentialFile': preference.get('credentialFile')}
    if backend_bin is not None:
        value['runtimePath'] = str(backend_bin)
        if not value['runtimePath'].strip():
            return StartupSelection(value, f'{backend}：请提供有效的 --backend-bin 路径。')
    if model is not None:
        value['model'] = model
        if not isinstance(model, str) or not model.strip():
            return StartupSelection(value, f'{backend}：请提供有效的 --model 值。')
    try:
        value = settings.normalize(value, allow_missing=True)
        path = settings.registry.resolve_command(backend, value['runtimePath'])[0]
    except BackendError as exc:
        detail = value['runtimePath']
        return StartupSelection(value, f'{exc} 路径：{detail}' if detail else str(exc))
    except ValueError as exc:
        return StartupSelection(value, f'{backend}：{exc}')
    except (OSError, RuntimeError):
        return StartupSelection(value, f'{backend}：无法解析所选可执行文件路径。')
    return StartupSelection({**value, 'runtimePath': path})


class BackendBusyError(ValueError):
    """A competing Backend operation can be retried when the Host is idle."""


def normalize(value, registry=DEFAULT_REGISTRY, *, allow_missing=False):
    if not isinstance(value, dict) or set(value) - {'backend', 'model', 'runtimePath', 'credentialFile', 'requestId', 'preferences'}:
        raise ValueError('后端配置字段无效。')
    backend = value.get('backend')
    if not isinstance(backend, str) or not backend:
        raise ValueError('请选择 Backend。')
    try:
        spec = registry.get_spec(backend)
    except BackendError as exc:
        if not allow_missing:
            raise ValueError(str(exc)) from None
        spec = None
    model = value.get('model') or (spec.default_model if spec else None)
    if model is not None and (not isinstance(model, str) or not model.strip() or len(model) > 160 or '\n' in model or '\r' in model):
        raise ValueError('模型名称无效。')
    result = {'backend': backend, 'model': model.strip() if model else None}
    for key in ('runtimePath', 'credentialFile'):
        path = value.get(key)
        if path is not None and not isinstance(path, str):
            raise ValueError('配置路径必须是字符串。')
        result[key] = str(Path(path.strip()).expanduser().absolute()) if path and path.strip() else None
    if spec and not spec.credential_env:
        result['credentialFile'] = None
    return result


class UserSettings:
    def __init__(self, path=None, *, registry=None, backends_dir=None):
        base = Path(os.getenv('LOCALAPPDATA') or Path.home() / '.config') / 'FOCUS'
        self.path = Path(path or os.getenv('FOCUS_SETTINGS_FILE') or base / 'settings.json')
        directory = backends_dir if backends_dir is not None else os.getenv('FOCUS_BACKENDS_DIR') or self.path.parent / 'backends'
        self.registry = registry or HarnessRegistry(directory)

    def document(self):
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, TypeError) as exc:
            raise ValueError('已保存的后端配置无效，请修正用户设置文件。') from exc

    def read(self):
        value = self.document()
        return self.normalize({k: value[k] for k in ('backend', 'model', 'runtimePath', 'credentialFile') if k in value},
                              allow_missing=True) if value.get('backend') else None

    def normalize(self, value, *, allow_missing=False):
        return normalize(value, self.registry, allow_missing=allow_missing)

    def preferences(self):
        value = self.document()
        preferences = value.get('preferences', {})
        # Existing explicit machine selections remain explicit.
        if not preferences and value.get('backend'):
            preferences = {value['backend']: {k: value.get(k) for k in ('model', 'runtimePath', 'credentialFile')}}
        return preferences

    def projection(self, effective=_USE_SAVED, busy=False, *, startup=None):
        saved = self.read()
        if effective is _USE_SAVED:
            effective = startup.configuration if startup is not None else saved
        preferences = self.preferences()
        runtime_paths = {backend: preference.get('runtimePath') for backend, preference in preferences.items()
                         if isinstance(preference, dict)}
        if effective and effective.get('runtimePath'):
            runtime_paths[effective['backend']] = effective['runtimePath']
        return {'saved': saved, 'effective': effective, 'preferences': preferences,
                'backends': self.registry.describe_all(runtime_paths), 'backendErrors': self.registry.errors,
                'startupOverride': startup is not None, 'startupError': startup.error if startup is not None else None,
                'pending': False, 'busy': busy, 'refreshBlocked': False,
                'operationId': self.document().get('configurationOperationId')}

    def configured_document(self, value):
        document = self.document()
        preferences = self.preferences()
        normalized = self.normalize(value)
        drafts = value.get('preferences', {})
        if not isinstance(drafts, dict):
            raise ValueError('Backend 偏好无效。')
        for backend, draft in drafts.items():
            if not isinstance(draft, dict):
                raise ValueError('模型偏好无效。')
            preference = self.normalize({**draft, 'backend': backend}, allow_missing=True)
            preferences[backend] = {**preference, 'model': draft.get('model') or None}
        preferences[normalized['backend']] = {**normalized, 'model': value.get('model') or None}
        document.update(normalized, preferences=preferences,
                        configurationOperationId=value.get('requestId') or uuid.uuid4().hex)
        return document

    def save(self, value):
        self.write(self.configured_document(value))

    def write(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as file:
                name = file.name
                json.dump(value, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
        finally:
            if name and Path(name).exists():
                Path(name).unlink()
