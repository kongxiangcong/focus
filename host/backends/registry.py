"""Manifest registration and command resolution shared by Host operations."""
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .base import BackendError

BUILTINS = Path(__file__).parent / 'manifests'
BACKEND_ID = re.compile(r'[a-z0-9][a-z0-9_-]{0,79}\Z')
ENV_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


@dataclass(frozen=True)
class HarnessSpec:
    id: str
    label: str
    driver: str
    command: tuple[str, ...]
    default_model: str | None
    directory: Path
    env: dict = field(default_factory=dict)
    env_strip: tuple[str, ...] = ()
    credential_env: tuple[str, ...] = ()
    capabilities: dict = field(default_factory=dict)
    install_hint: str = ''
    login_hint: str = ''
    acp: dict = field(default_factory=dict)
    runtime_path_version: int = 1
    legacy_credential_file: Path | None = None

    @classmethod
    def read(cls, path, *, builtin=False):
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(value, dict):
            raise ValueError('Manifest 必须是 JSON 对象。')
        backend_id = value.get('id')
        if not isinstance(backend_id, str) or not BACKEND_ID.fullmatch(backend_id):
            raise ValueError('Backend ID 无效。')
        driver = value.get('driver')
        if driver not in ('codex-app-server', 'acp'):
            raise ValueError('driver 必须是 acp 或 codex-app-server。')
        label = value.get('label')
        command = value.get('command')
        if not isinstance(label, str) or not label.strip():
            raise ValueError('label 必须是非空名称。')
        if not isinstance(command, list) or not command or any(not isinstance(item, str) or '\0' in item for item in command) or not command[0].strip():
            raise ValueError('command 必须包含程序和有序字符串参数。')
        model = value.get('defaultModel')
        if model is not None and (not isinstance(model, str) or not model.strip() or len(model) > 160 or '\n' in model or '\r' in model):
            raise ValueError('defaultModel 无效。')
        env = value.get('env', {})
        if not isinstance(env, dict) or any(not ENV_NAME.fullmatch(key) or not isinstance(item, str) or '\0' in item for key, item in env.items()):
            raise ValueError('env 必须包含环境变量名和字符串值。')
        env_strip, credential_env = value.get('envStrip', []), value.get('credentialEnv', [])
        for names in (env_strip, credential_env):
            if not isinstance(names, list) or any(not isinstance(name, str) or not ENV_NAME.fullmatch(name) for name in names):
                raise ValueError('envStrip 与 credentialEnv 必须包含环境变量名。')
        if set(env) & set(credential_env):
            raise ValueError('凭据变量只能在 credentialEnv 中声明。')
        capabilities = value.get('capabilities', {})
        acp = value.get('acp', {})
        if not isinstance(capabilities, dict) or not isinstance(acp, dict):
            raise ValueError('capabilities 与 acp 必须是 JSON 对象。')
        for key in ('streaming', 'images'):
            if key in capabilities and not isinstance(capabilities[key], bool):
                raise ValueError(f'capabilities.{key} 必须是布尔值。')
        for key in ('mcpTransport', 'structuredOutput', 'modelDiscovery', 'authMode'):
            if key in capabilities and not isinstance(capabilities[key], str):
                raise ValueError(f'capabilities.{key} 必须是字符串。')
        install_hint, login_hint = value.get('installHint', ''), value.get('loginHint', '')
        if not isinstance(install_hint, str) or not isinstance(login_hint, str):
            raise ValueError('installHint 与 loginHint 必须是字符串。')
        runtime_path_version = value.get('runtimePathVersion', 1) if builtin else 1
        fallback = value.get('legacyCredentialFile') if builtin else None
        if type(runtime_path_version) is not int or runtime_path_version < 1:
            raise ValueError('runtimePathVersion 必须为正整数。')
        if fallback is not None and (not isinstance(fallback, str) or not fallback.strip()):
            raise ValueError('legacyCredentialFile 必须为非空路径。')
        return cls(backend_id, label.strip(), driver, tuple(command), model.strip() if model else None,
                   path.parent, env, tuple(env_strip), tuple(credential_env), capabilities,
                   install_hint, login_hint, acp, runtime_path_version, (path.parent / fallback).resolve() if fallback else None)


def _codex_bundled():
    from codex_cli_bin import bundled_codex_path
    return bundled_codex_path()


def _driver(driver):
    if driver == 'codex-app-server':
        from .codex import CodexBackend
        return CodexBackend
    from .acp import AcpBackend
    return AcpBackend


def _executable(path):
    return path.is_file() and (path.suffix.lower() in {'.exe', '.com', '.cmd', '.bat'} or os.name != 'nt') and os.access(path, os.X_OK)


class HarnessRegistry:
    def __init__(self, directory=None):
        self.directory = Path(directory).expanduser().absolute() if directory is not None else None
        specs = {spec.id: spec for spec in (HarnessSpec.read(path, builtin=True) for path in sorted(BUILTINS.glob('*.json')))}
        errors = []
        for path in sorted(self.directory.glob('*.json')) if self.directory else ():
            try:
                spec = HarnessSpec.read(path)
                if spec.id in specs:
                    raise ValueError(f'Backend ID {spec.id} 已被注册。')
                specs[spec.id] = spec
            except json.JSONDecodeError as exc:
                errors.append({'file': path.name, 'message': f'JSON 无效（第 {exc.lineno} 行）。'})
            except (ValueError, OSError) as exc:
                message = str(exc) if isinstance(exc, ValueError) else '无法读取文件。'
                errors.append({'file': path.name, 'message': message})
        self._specs = specs
        self.errors = errors
        self._discovered = {spec.id: self._discover_binary(spec) for spec in self.list_specs()}

    def list_specs(self):
        return tuple(self._specs.values())

    def get_spec(self, backend_id):
        if isinstance(backend_id, str) and backend_id in self._specs:
            return self._specs[backend_id]
        raise BackendError(f'未知 Agent 后端 {backend_id!r}；可选：{", ".join(self._specs)}')

    def probe_binary(self, spec, explicit_path=None):
        if explicit_path:
            path = Path(explicit_path).expanduser().absolute()
            return str(path.resolve()) if _executable(path) else None
        return self._discovered.get(spec.id)

    def _discover_binary(self, spec):
        command = Path(spec.command[0]).expanduser()
        if command.is_absolute() or '/' in spec.command[0] or '\\' in spec.command[0]:
            path = spec.directory / command
            return str(path.resolve()) if _executable(path) else None
        # Maintain the bundled Codex selected by FOCUS before the manifest migration.
        if spec.driver == 'codex-app-server' and spec.command[0] == 'codex':
            try:
                if _executable(Path(path := _codex_bundled())):
                    return str(Path(path).resolve())
            except (ImportError, OSError):
                pass
        discovered = shutil.which(spec.command[0])
        if discovered:
            return str(Path(discovered).resolve())
        return None

    def resolve_command(self, backend_id, explicit_path=None):
        spec = self.get_spec(backend_id)
        path = self.probe_binary(spec, explicit_path)
        if path is None:
            detail = '指定的可执行文件不可用。' if explicit_path else (spec.install_hint or '请安装 Runtime 或指定可执行文件。')
            raise BackendError(f'{spec.label}：{detail}')
        return (path, *spec.command[1:])

    def describe_all(self, runtime_paths=None):
        runtime_paths = runtime_paths or {}
        result = []
        for spec in self.list_specs():
            explicit = runtime_paths.get(spec.id)
            installed = self.probe_binary(spec, explicit)
            hint = spec.install_hint or '请安装 Runtime 或指定可执行文件。'
            result.append({'id': spec.id, 'label': spec.label, 'driver': spec.driver, 'available': bool(installed),
                           'runtimePath': installed, 'defaultModel': spec.default_model, 'installHint': hint,
                           'credentialEnv': list(spec.credential_env),
                           'loginHint': spec.login_hint, 'capabilities': dict(spec.capabilities),
                           'unavailableReason': (None if installed else '指定的可执行文件不可用。' if explicit else hint)})
        return result

    def create_backend(self, backend_id, workspace, *, runtime_path=None, credential_file=None, **options):
        spec = self.get_spec(backend_id)
        adapter = _driver(spec.driver)
        if spec.driver == 'codex-app-server' and not runtime_path:
            runtime_path = options.get('codex_bin')
        options.update(command=self.resolve_command(spec.id, runtime_path),
                       manifest=spec, credential_file=credential_file)
        if not options.get('model'):
            options['model'] = spec.default_model
        accepted = {key: value for key, value in options.items() if key in adapter.option_keys}
        backend = adapter(workspace, **accepted)
        backend.name = spec.id
        if 'images' in spec.capabilities:
            backend.image_input = spec.capabilities['images']
        return backend
