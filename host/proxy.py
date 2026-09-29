"""Per-backend proxy routing without changing the Host environment.

Modes for `FOCUS_<BACKEND>_PROXY`:
  inherit  keep the inherited variables (default for codex)
  bypass   drop every proxy variable and set NO_PROXY=*
  <url>    pin an explicit proxy, e.g. http://127.0.0.1:7890

Each backend receives its own environment copy, so browser switching never
rewrites the Host environment or loses the other provider's proxy settings.
"""
import os

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


def backend_environment(backend):
    env = dict(os.environ)
    if backend == 'codex':
        for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
            env.pop(key, None)
    apply_proxy(backend, env)
    # SDK transports may merge env over os.environ. Empty values override inherited proxies.
    if proxy_mode(backend) == BYPASS:
        env.update({key: '' for key in PROXY_KEYS})
    return env
