"""Backend registry and proxy routing contracts for Codex and WorkBuddy."""
import tempfile
import unittest
from pathlib import Path

from host.backends import BACKENDS, BackendError, create_backend, check_backend
from host.backends.codex import CodexBackend
from host.backends.workbuddy import WorkBuddyBackend
from host.proxy import apply_proxy, proxy_mode, backend_environment


class BackendRegistryTests(unittest.TestCase):
    def test_registry_exposes_both_runtimes_and_rejects_unknown(self):
        self.assertEqual(['codex', 'workbuddy'], sorted(BACKENDS))
        with self.assertRaisesRegex(BackendError, '未知 Agent 后端'):
            create_backend('gemini', Path(tempfile.gettempdir()))

    def test_options_are_filtered_per_adapter(self):
        workspace = Path(tempfile.gettempdir())
        backend = create_backend('workbuddy', workspace, codex_bin='must-not-be-passed', model='m')
        self.assertIsInstance(backend, WorkBuddyBackend)
        self.assertEqual('m', backend.model)
        self.assertFalse(hasattr(backend, 'codex_bin'))
        backend.close()

    def test_codex_declares_codex_bin_option(self):
        self.assertIn('codex_bin', CodexBackend.option_keys)

    def test_domestic_workbuddy_never_substitutes_codebuddy_sdk(self):
        with self.assertRaisesRegex(BackendError, '开放平台'):
            check_backend('workbuddy')
        backend = create_backend('workbuddy', Path(tempfile.gettempdir()))
        with self.assertRaisesRegex(BackendError, 'CodeBuddy CLI 登录不能替代'):
            backend.open_session(None, instructions='test')


class ProxyRoutingTests(unittest.TestCase):
    """Codex keeps the user's VPN proxy; WorkBuddy must not be routed through it."""

    def env(self, **extra):
        base = {'HTTP_PROXY': 'http://127.0.0.1:59588', 'HTTPS_PROXY': 'http://127.0.0.1:59588',
                'http_proxy': 'http://127.0.0.1:59588', 'https_proxy': 'http://127.0.0.1:59588'}
        base.update(extra)
        return base

    def test_switching_does_not_destroy_inherited_proxy(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, self.env(), clear=True):
            workbuddy = backend_environment('workbuddy')
            self.assertEqual('', workbuddy['HTTPS_PROXY'])
            self.assertEqual('*', workbuddy['NO_PROXY'])
            codex = backend_environment('codex')
            self.assertEqual('http://127.0.0.1:59588', codex['HTTPS_PROXY'])
            self.assertEqual('http://127.0.0.1:59588', os.environ['HTTPS_PROXY'])

    def test_defaults_are_bypass_for_workbuddy_and_inherit_for_codex(self):
        self.assertEqual('bypass', proxy_mode('workbuddy', {}))
        self.assertEqual('inherit', proxy_mode('codex', {}))

    def test_workbuddy_drops_every_inherited_proxy_variable(self):
        env = self.env()
        note = apply_proxy('workbuddy', env)
        self.assertNotIn('HTTP_PROXY', env)
        self.assertNotIn('https_proxy', env)
        self.assertEqual('*', env['NO_PROXY'])
        self.assertEqual('*', env['no_proxy'])
        self.assertIn('绕过代理', note)
        self.assertIn('http://127.0.0.1:59588', note)

    def test_codex_inherits_by_default(self):
        env = self.env()
        self.assertEqual('', apply_proxy('codex', env))
        self.assertEqual('http://127.0.0.1:59588', env['HTTP_PROXY'])

    def test_codex_can_pin_an_explicit_proxy(self):
        env = self.env(FOCUS_CODEX_PROXY='http://127.0.0.1:7890')
        note = apply_proxy('codex', env)
        self.assertEqual('http://127.0.0.1:7890', env['HTTP_PROXY'])
        self.assertEqual('http://127.0.0.1:7890', env['https_proxy'])
        self.assertNotIn('no_proxy', env)
        self.assertIn('http://127.0.0.1:7890', note)

    def test_workbuddy_can_opt_back_in_when_the_account_needs_it(self):
        env = self.env(FOCUS_WORKBUDDY_PROXY='inherit')
        self.assertEqual('', apply_proxy('workbuddy', env))
        self.assertEqual('http://127.0.0.1:59588', env['HTTPS_PROXY'])
