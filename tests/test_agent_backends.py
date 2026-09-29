"""Backend registry and proxy routing contracts for the supported web backends."""
import tempfile
import unittest
from pathlib import Path

from host.backends import BACKENDS, BackendError, create_backend
from host.backends.codex import CodexBackend
from host.backends.deepseek import DeepSeekBackend
from host.proxy import apply_proxy, proxy_mode, backend_environment


class BackendRegistryTests(unittest.TestCase):
    def test_registry_exposes_supported_runtimes_and_rejects_unknown(self):
        self.assertEqual(['codex', 'deepseek'], sorted(BACKENDS))
        with self.assertRaisesRegex(BackendError, '未知 Agent 后端'):
            create_backend('workbuddy', Path(tempfile.gettempdir()))

    def test_options_are_filtered_per_adapter(self):
        backend = create_backend('deepseek', Path(tempfile.gettempdir()), codex_bin='unused', model='m')
        self.assertIsInstance(backend, DeepSeekBackend)
        self.assertEqual('m', backend.model)
        self.assertFalse(hasattr(backend, 'codex_bin'))
        backend.close()

    def test_codex_declares_codex_bin_option(self):
        self.assertIn('codex_bin', CodexBackend.option_keys)


class ProxyRoutingTests(unittest.TestCase):
    def env(self, **extra):
        base = {'HTTP_PROXY': 'http://127.0.0.1:59588', 'HTTPS_PROXY': 'http://127.0.0.1:59588',
                'http_proxy': 'http://127.0.0.1:59588', 'https_proxy': 'http://127.0.0.1:59588'}
        base.update(extra)
        return base

    def test_environment_copies_do_not_mutate_host_proxy(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, self.env(FOCUS_DEEPSEEK_PROXY='bypass'), clear=True):
            deepseek = backend_environment('deepseek')
            self.assertEqual('', deepseek['HTTPS_PROXY'])
            self.assertEqual('*', deepseek['NO_PROXY'])
            codex = backend_environment('codex')
            self.assertEqual('http://127.0.0.1:59588', codex['HTTPS_PROXY'])
            self.assertEqual('http://127.0.0.1:59588', os.environ['HTTPS_PROXY'])

    def test_both_backends_inherit_by_default(self):
        self.assertEqual('inherit', proxy_mode('codex', {}))
        self.assertEqual('inherit', proxy_mode('deepseek', {}))

    def test_explicit_bypass_drops_inherited_proxy(self):
        env = self.env(FOCUS_DEEPSEEK_PROXY='bypass')
        note = apply_proxy('deepseek', env)
        self.assertNotIn('HTTP_PROXY', env)
        self.assertNotIn('https_proxy', env)
        self.assertEqual('*', env['NO_PROXY'])
        self.assertIn('绕过代理', note)

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

    def test_explicit_inherit_keeps_proxy(self):
        env = self.env(FOCUS_DEEPSEEK_PROXY='inherit')
        self.assertEqual('', apply_proxy('deepseek', env))
        self.assertEqual('http://127.0.0.1:59588', env['HTTPS_PROXY'])


if __name__ == '__main__':
    unittest.main()
