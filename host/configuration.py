"""User settings, separate from Knowledge Base and Host business history."""
import json
import os
import tempfile
from pathlib import Path

DEFAULT_MODELS = {'codex': 'gpt-6-astra', 'deepseek': 'deepseek-v4-flash'}


def normalize(value):
    if not isinstance(value, dict) or set(value) - {'backend', 'model', 'runtimePath', 'credentialFile'}:
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

    def read(self):
        if not self.path.is_file():
            return None
        try:
            return normalize(json.loads(self.path.read_text(encoding='utf-8')))
        except (ValueError, TypeError) as exc:
            raise ValueError('已保存的后端配置无效，请修正用户设置文件。') from exc

    def save(self, value):
        value = normalize(value)
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
