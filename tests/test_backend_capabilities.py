"""Manifest capabilities at the Workbench Backend setup boundary."""
import json
import sys
import unittest
from unittest.mock import patch

from host.workbench import Workbench
from test_backend_setup import AccountRuntime
from test_workspace_portability import test_directory as fixture_directory


class ModelRuntime(AccountRuntime):
    def request(self, method, params, timeout=60):
        if method == 'model/list':
            return {'data': [{'model': 'one'}, {'model': 'two'}]}
        return super().request(method, params, timeout)


class BackendCapabilitiesTests(unittest.TestCase):
    def test_custom_model_catalog_checks_only_declared_file_credentials_and_can_retry(self):
        with fixture_directory() as root:
            manifests = root / 'backends'
            manifests.mkdir()
            (manifests / 'private.json').write_text(json.dumps({
                'id': 'private', 'label': 'Private', 'driver': 'codex-app-server',
                'command': [sys.executable, 'app-server'],
                'envStrip': ['FOCUS_LEGACY_TOKEN'],
                'credentialEnv': ['FOCUS_CATALOG_TOKEN'],
                'capabilities': {'authMode': 'interactive-oauth', 'modelDiscovery': 'codex-model-list'},
            }), encoding='utf-8')
            credentials = root / 'selected.env'
            values = {'backend': 'private', 'credentialFile': str(credentials)}
            app = Workbench(settings_path=root / 'settings.json')
            try:
                absent = app.backend_setup('models', values)
                self.assertEqual('failed', absent['status'])
                self.assertIn('凭据文件', absent['message'])
                credentials.write_text('FOCUS_UNUSED_TOKEN=ignore-this-value\n', encoding='utf-8')
                missing = app.backend_setup('models', values)
                self.assertEqual('failed', missing['status'])
                self.assertIn('FOCUS_CATALOG_TOKEN', missing['message'])
                credentials.write_text(
                    'FOCUS_UNUSED_TOKEN=ignore-this-value\nFOCUS_CATALOG_TOKEN="fixture-only"\n', encoding='utf-8')
                with patch('host.backends.codex.AppServer', ModelRuntime), patch.dict('os.environ', {
                    'FOCUS_CATALOG_TOKEN': 'inherited', 'FOCUS_LEGACY_TOKEN': 'legacy-value',
                }):
                    result = app.backend_setup('models', values)
                    self.assertEqual('loaded', result['catalogStatus'])
                    self.assertEqual(['one', 'two'], result['models'])
                    self.assertNotIn('checkedModel', result)
                    login = app.backend_setup('login-start', values)
                    self.assertEqual('waiting', login['status'])
                    self.assertEqual('cancelled', app.backend_setup('login-cancel', {
                        **values, 'loginId': login['loginId'],
                    })['status'])
                    for runtime in ModelRuntime.instances[-2:]:
                        self.assertEqual('fixture-only', runtime.env['FOCUS_CATALOG_TOKEN'])
                        self.assertNotIn('FOCUS_UNUSED_TOKEN', runtime.env)
                        self.assertNotIn('FOCUS_LEGACY_TOKEN', runtime.env)
                        self.assertTrue(runtime.closed)
                self.assertNotIn('fixture-only', json.dumps([absent, missing, result, login, app.configuration_status()]))
                self.assertFalse(app.settings.path.is_file())
            finally:
                app.close()
