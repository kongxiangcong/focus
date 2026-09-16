"""Per-backend proxy routing.

Why this file exists: the two backends do not live on the same network. Codex
talks to OpenAI, which from a mainland-CN machine needs the user's VPN; WorkBuddy
talks to a China-region endpoint that a VPN only makes slower or unreachable.
Desktop VPN clients leave `HTTP_PROXY`/`HTTPS_PROXY` behind in the environment
even after they disconnect, so the Host rewrites those variables for the selected
backend instead of trusting whatever it inherited from the shell.

Modes for `FOCUS_<BACKEND>_PROXY`:
  inherit  keep the inherited variables (default for codex)
  bypass   drop every proxy variable and set NO_PROXY=* (default for workbuddy)
  <url>    pin an explicit proxy, e.g. http://127.0.0.1:7890

Each backend receives its own environment copy, so browser switching never
rewrites the Host environment or loses the other provider's proxy settings.
"""
import os

PROXY_KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')
NO_PROXY_KEYS = ('NO_PROXY', 'no_proxy')
INHERIT = 'inherit'
BYPASS = 'bypass'
DEFAULT_MODES = {'workbuddy': BYPASS}


def proxy_mode(backend, env=None):
    """Resolve the mode for `backend`; workbuddy bypasses, everything else inherits."""
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
    apply_proxy(backend, env)
    # SDK transports may merge env over os.environ. Empty values override inherited proxies.
    if proxy_mode(backend) == BYPASS:
        env.update({key: '' for key in PROXY_KEYS})
    return env
