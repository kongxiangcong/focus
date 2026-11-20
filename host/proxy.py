"""Per-backend proxy routing without changing the Host environment.

Modes for `FOCUS_<BACKEND>_PROXY`:
  inherit  keep the inherited variables (default for codex)
  bypass   drop every proxy variable and set NO_PROXY=*
  <url>    pin an explicit proxy, e.g. http://127.0.0.1:7890

Each backend receives its own environment copy, so browser switching never
rewrites the Host environment or loses the other provider's proxy settings.
"""
import os
from pathlib import Path

from .backends.base import BackendConfigurationError

PROXY_KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')
NO_PROXY_KEYS = ('NO_PROXY', 'no_proxy')
INHERIT = 'inherit'
BYPASS = 'bypass'
DEFAULT_MODES = {}


def proxy_mode(backend, env=None):
    """Resolve the mode for `backend`; the default is inherit."""
    source = os.environ if env is None else env
    default = DEFAULT_MODES.get(backend, INHERIT)
    raw = source.get(f'FOCUS_{str(backend).upper()}_PROXY')
    mode = (raw or '').strip() or default
    return mode.lower() if mode.lower() in (INHERIT, BYPASS) else mode


def apply_proxy(backend, env=None):
    """Rewrite proxy variables for `backend` in place. Returns a note for the log."""
    target = os.environ if env is None else env
    mode = proxy_mode(backend, target)
    if mode == INHERIT:
        return ''
    if mode == BYPASS:
        removed = [value for value in (target.pop(key, None) for key in PROXY_KEYS) if value]
        for key in NO_PROXY_KEYS:
            target[key] = '*'
        note = f'{backend}: 绕过代理'
        if removed:
            note += f'（已忽略继承的 {", ".join(sorted(set(removed)))}）'
        return note
    for key in PROXY_KEYS:
        target[key] = mode
    for key in NO_PROXY_KEYS:
        target.pop(key, None)
    return f'{backend}: 代理固定为 {mode}'


def file_credentials(path, names):
    """Read only the declared assignment names without echoing file contents."""
    wanted = set(names)
    if not wanted:
        return {}
    try:
        lines = Path(path).expanduser().read_text(encoding='utf-8-sig').splitlines()
    except (OSError, UnicodeError, ValueError):
        raise BackendConfigurationError('无法读取凭据文件，请检查文件路径、权限和 UTF-8 编码。') from None
    values = {}
    for line in lines:
        key, separator, value = line.strip().removeprefix('export ').partition('=')
        key = key.strip()
        if not separator or key not in wanted:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]
        if value and '\0' not in value:
            values[key] = value
        else:
            values.pop(key, None)
    missing = wanted - values.keys()
    if missing:
        raise BackendConfigurationError(f'凭据文件缺少 {", ".join(sorted(missing))}，请补充后重试。')
    return values


def backend_environment(backend, *, credential_file=None):
    env = dict(os.environ)
    if isinstance(backend, str):
        from .backends import BACKENDS
        spec = BACKENDS.get(backend)
        name = backend
    else:
        spec = backend
        name = spec.id
    if spec:
        for key in spec.env_strip:
            env.pop(key, None)
        env.update(spec.env)
        if credential_file:
            env.update(file_credentials(credential_file, spec.credential_env))
    apply_proxy(name, env)
    # SDK transports may merge env over os.environ. Empty values override inherited proxies.
    if proxy_mode(name) == BYPASS:
        env.update({key: '' for key in PROXY_KEYS})
    return env
