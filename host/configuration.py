"""User settings, separate from Knowledge Base and Host business history."""
import json
import os
import tempfile
import uuid
from pathlib import Path

from .backends import DEFAULT_REGISTRY, BackendError, HarnessRegistry

DEFAULT_MODELS = {spec.id: spec.default_model for spec in DEFAULT_REGISTRY.list_specs()}


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
        self.registry = registry or HarnessRegistry(backends_dir if backends_dir is not None else self.path.parent / 'backends')

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
        backend = value.get('backend')
        if not backend:
            return None
        config = {k: value[k] for k in ('backend', 'model', 'runtimePath', 'credentialFile') if k in value}
        return self.normalize(self._migrated_paths(backend, config, value), allow_missing=True)

    def _migrated_paths(self, backend, config, document):
        try:
            spec = self.registry.get_spec(backend)
        except BackendError:
            return config
        versions = document.get('runtimePathVersions')
        stored = versions.get(backend, 1) if isinstance(versions, dict) else 1
        if stored != spec.runtime_path_version:
            return {**config, 'runtimePath': None}
        return config

    def normalize(self, value, *, allow_missing=False):
        return normalize(value, self.registry, allow_missing=allow_missing)

    def preferences(self):
        value = self.document()
        preferences = value.get('preferences', {})
        # Existing explicit machine selections remain explicit.
        if not preferences and value.get('backend'):
            preferences = {value['backend']: {k: value.get(k) for k in ('model', 'runtimePath', 'credentialFile')}}
        return {backend: self._migrated_paths(backend, preference, value) if isinstance(preference, dict) else preference
                for backend, preference in preferences.items()}

    def projection(self, effective=None, busy=False):
        saved = self.read()
        preferences = self.preferences()
        runtime_paths = {backend: preference.get('runtimePath') for backend, preference in preferences.items()
                         if isinstance(preference, dict)}
        if effective and effective.get('runtimePath'):
            runtime_paths[effective['backend']] = effective['runtimePath']
        return {'saved': saved, 'effective': effective or saved, 'preferences': preferences,
                'backends': self.registry.describe_all(runtime_paths), 'backendErrors': self.registry.errors,
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
        versions = document.get('runtimePathVersions')
        versions = dict(versions) if isinstance(versions, dict) else {}
        updated = {*drafts, normalized['backend']}
        versions.update({spec.id: spec.runtime_path_version
                         for spec in self.registry.list_specs() if spec.id in updated})
        document.update(normalized, preferences=preferences, runtimePathVersions=versions,
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
