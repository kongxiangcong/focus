"""Backend registry entry points for callers without a Workbench."""
from .base import Backend, BackendError
from .registry import HarnessRegistry, HarnessSpec

DEFAULT_BACKEND = 'codex'
DEFAULT_REGISTRY = HarnessRegistry()
BACKENDS = {spec.id: spec for spec in DEFAULT_REGISTRY.list_specs()}


def backend_names():
    return sorted(BACKENDS)


def create_backend(name, workspace, *, registry=None, **options):
    return (registry or DEFAULT_REGISTRY).create_backend(name, workspace, **options)


def describe_missing(name):
    try:
        return DEFAULT_REGISTRY.get_spec(name).install_hint
    except BackendError as exc:
        return str(exc)


def check_backend(name, codex_bin=None):
    command = DEFAULT_REGISTRY.resolve_command(name, codex_bin)
    return command[0]


__all__ = ['BACKENDS', 'Backend', 'BackendError', 'DEFAULT_BACKEND', 'DEFAULT_REGISTRY', 'HarnessRegistry',
           'HarnessSpec', 'check_backend', 'create_backend', 'describe_missing', 'backend_names']
