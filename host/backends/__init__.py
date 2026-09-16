"""Selectable Agent backends for the FOCUS web Host.

`create_backend(name, workspace, **options)` is the only entry point the Host
uses. Adding a runtime means writing one adapter against `base.Backend` and
registering it here; no change lands in `service.py`, `server.py` or the UI.
"""
from .base import Backend, BackendError
from .codex import CodexBackend
from .workbuddy import WorkBuddyBackend

BACKENDS = {'codex': CodexBackend, 'workbuddy': WorkBuddyBackend}
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
        return '需要 openai-codex==0.154.0（host/requirements.txt）与可用 Codex 登录或 OPENAI_API_KEY。'
    if adapter is WorkBuddyBackend:
        return WorkBuddyBackend.unavailable_reason
    return ''


def check_backend(name, codex_bin=None):
    """Fail fast at startup with the prerequisites of one backend. Returns a status line."""
    adapter = BACKENDS.get(name)
    if adapter is None:
        raise BackendError(describe_missing(name))
    hint = describe_missing(name)
    if adapter is WorkBuddyBackend:
        raise BackendError(hint)
    if adapter is CodexBackend:
        try:
            from ..runtime import RUNTIME_VERSION, codex_command
            # An explicit binary must win: it is how a host reuses an installed
            # 0.154.0 without the pinned packaging helper.
            command = codex_command(codex_bin)
        except Exception as exc:  # missing pinned package / binary
            raise BackendError(f'{hint}（{exc}）') from exc
        import subprocess
        try:
            version = subprocess.run([*command, '--version'], check=True, capture_output=True,
                                     text=True, timeout=15).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise BackendError(f'Codex 运行时不可用：{exc}') from exc
        if version != f'codex-cli {RUNTIME_VERSION}':
            raise BackendError(f'Expected codex-cli {RUNTIME_VERSION}, got {version}; install host/requirements.txt')
        return f'codex-cli {RUNTIME_VERSION}: {command[0]}'
    raise BackendError(hint)


__all__ = ['BACKENDS', 'Backend', 'BackendError', 'DEFAULT_BACKEND', 'check_backend', 'create_backend',
           'describe_missing', 'backend_names']
