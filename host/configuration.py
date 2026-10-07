"""User settings, separate from Knowledge Base and Host business history."""
import json
import os
import tempfile
import uuid
from pathlib import Path

DEFAULT_MODELS = {'codex': 'gpt-6-astra', 'deepseek': 'deepseek-v4-flash'}


def normalize(value):
    if not isinstance(value, dict) or set(value) - {'backend', 'model', 'runtimePath', 'credentialFile', 'requestId', 'preferences'}:
        raise ValueError('后端配置字段无效。')
    backend = value.get('backend')
    if backend not in DEFAULT_MODELS:
        raise ValueError('请选择 Codex 或 DeepSeek。')
    model = value.get('model') or DEFAULT_MODELS[backend]
    if not isinstance(model, str) or not model.strip() or len(model) > 160 or '\n' in model or '\r' in model:
        raise ValueError('模型名称无效。')
    result = {'backend': backend, 'model': model.strip()}
    for key in ('runtimePath', 'credentialFile'):
        path = value.get(key)
        if path is not None and not isinstance(path, str):
            raise ValueError('配置路径必须是字符串。')
        result[key] = str(Path(path.strip()).expanduser().absolute()) if path and path.strip() else None
    if backend == 'codex':
        result['credentialFile'] = None
    return result


class UserSettings:
    def __init__(self, path=None):
        base = Path(os.getenv('LOCALAPPDATA') or Path.home() / '.config') / 'FOCUS'
        self.path = Path(path or os.getenv('FOCUS_SETTINGS_FILE') or base / 'settings.json')

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
        return normalize({k: value[k] for k in ('backend', 'model', 'runtimePath', 'credentialFile') if k in value}) if value.get('backend') else None

    def preferences(self):
        value = self.document()
        preferences = value.get('preferences', {})
        # Existing explicit machine selections remain explicit.
        if not preferences and value.get('backend'):
            preferences = {value['backend']: {k: value.get(k) for k in ('model', 'runtimePath', 'credentialFile')}}
        return preferences

    def projection(self, effective=None, busy=False):
        saved = self.read() or effective or normalize({'backend': 'codex'})
        return {'saved': saved, 'effective': effective or saved, 'preferences': self.preferences(),
                'pending': False, 'busy': busy, 'refreshBlocked': False,
                'operationId': self.document().get('configurationOperationId')}

    def configured_document(self, value):
        document = self.document()
        preferences = self.preferences()
        normalized = normalize(value)
        drafts = value.get('preferences', {})
        if not isinstance(drafts, dict) or set(drafts) - set(DEFAULT_MODELS):
            raise ValueError('Backend 偏好无效。')
        for backend, draft in drafts.items():
            if not isinstance(draft, dict):
                raise ValueError('模型偏好无效。')
            preference = normalize({**draft, 'backend': backend})
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
