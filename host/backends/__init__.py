"""Selectable Agent backends for the FOCUS web Host.

`create_backend(name, workspace, **options)` is the only entry point the Host
uses. Adding a runtime means writing one adapter against `base.Backend` and
registering it here; no change lands in `service.py`, `server.py` or the UI.
"""
from .base import Backend, BackendError
from .codex import CodexBackend
from .deepseek import DeepSeekBackend

BACKENDS = {'codex': CodexBackend, 'deepseek': DeepSeekBackend}
DEFAULT_BACKEND = 'codex'


def backend_names():
    return sorted(BACKENDS)


def create_backend(name, workspace, **options):
    """Build a backend by name, passing only the options that adapter declares."""
    try:
        adapter = BACKENDS[name]
    except KeyError:
        raise BackendError(f'未知 Agent 后端 {name!r}；可选：{", ".join(backend_names())}') from None
    accepted = {key: value for key, value in options.items() if key in adapter.option_keys}
    return adapter(workspace, **accepted)


def describe_missing(name):
    """Human-readable prerequisite hint for `--check-backend`."""
    adapter = BACKENDS.get(name)
    if adapter is None:
        return f'未知 Agent 后端 {name!r}；可选：{", ".join(backend_names())}'
    if adapter is CodexBackend:
        return '需要可用 Codex Runtime 与 ChatGPT / Codex 登录。'
    if adapter is DeepSeekBackend:
        return '需要可用 DeepSeek Harness SDK、Runtime 与 Host 凭据。'
    return ''


def check_backend(name, codex_bin=None):
    """Fail fast at startup with the prerequisites of one backend. Returns a status line."""
    adapter = BACKENDS.get(name)
    if adapter is None:
        raise BackendError(describe_missing(name))
    hint = describe_missing(name)
    if adapter is DeepSeekBackend:
        from pathlib import Path
        from ..backend_setup import runtime_path
        try:
            import deepseek_harness
            path = runtime_path('deepseek')
            if not path or not Path(path).is_file():
                raise BackendError(hint)
            return f'DeepSeek Harness SDK: {path}'
        except ImportError as exc:
            raise BackendError(hint) from exc
    if adapter is CodexBackend:
        try:
            from ..runtime import codex_command
            command = codex_command(codex_bin)
        except Exception as exc:  # missing pinned package / binary
            raise BackendError(f'{hint}（{exc}）') from exc
        import subprocess
        try:
            version = subprocess.run([*command, '--version'], check=True, capture_output=True,
                                     text=True, timeout=15).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise BackendError(f'Codex 运行时不可用：{exc}') from exc
        return f'{version}: {command[0]}'
    raise BackendError(hint)


__all__ = ['BACKENDS', 'Backend', 'BackendError', 'DEFAULT_BACKEND', 'check_backend', 'create_backend',
           'describe_missing', 'backend_names']
