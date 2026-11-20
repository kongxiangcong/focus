"""Machine preferences and diagnostics through the public Host seams."""
import json
import unittest
import io
from unittest.mock import patch
from pathlib import Path
from test_workspace_portability import test_directory
from host.workbench import Workbench
from host.configuration import DEFAULT_MODELS
from host.backend_setup import BackendSetup
from test_backend_setup import AccountRuntime
from test_backend_verification import Protocol


class BackendOnboardingTests(unittest.TestCase):
    def test_catalog_intersects_supplier_models_with_text_and_current_protocol(self):
        setup = BackendSetup()
        body = {'data': [
            {'id': 'supported', 'input_modalities': ['text'], 'output_modalities': ['text'], 'api_capabilities': {'anthropic_messages': {}}},
            {'id': 'image-only', 'input_modalities': ['image'], 'output_modalities': ['text'], 'api_capabilities': {'anthropic_messages': {}}},
            {'id': 'different-protocol', 'input_modalities': ['text'], 'output_modalities': ['text'], 'api_capabilities': {'responses': {}}},
        ]}
        with test_directory() as root, patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'fixture-key'}):
            binary = root / 'runtime.exe'
            binary.touch()
            payload = {'backend': 'deepseek', 'runtimePath': str(binary)}
            with patch('host.backends.deepseek.build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(json.dumps(body).encode())
                result = setup.models(payload)
            self.assertEqual(['supported'], result['models'])

    def test_skip_default_binds_once_without_optional_actions_and_restart(self):
        with test_directory() as root, patch.object(BackendSetup, 'operate', side_effect=AssertionError('not authorized')), \
                patch.object(BackendSetup, 'prepare', side_effect=AssertionError('not authorized')):
            app = Workbench(settings_path=root / 'machine/settings.json')
            app.bind({'mode': 'create', 'path': str(root), 'configuration': {'backend': 'deepseek'}})
            self.assertEqual('deepseek', app.host.backend_name)
            self.assertEqual(DEFAULT_MODELS['deepseek'], app.host.models['deepseek'])
            self.assertIsNone(app.settings.preferences()['deepseek']['model'])
            app.close()
            app = Workbench(settings_path=root / 'machine/settings.json')
            self.assertEqual('deepseek', app.host.backend_name)
            app.close()

    def test_each_preference_and_return_to_default_removes_override(self):
        with test_directory() as root:
            app = Workbench(settings_path=root / 'machine/settings.json')
            app.bind({'mode': 'create', 'path': str(root)})
            host = app.host
            host.save_configuration({'backend': 'codex', 'model': 'custom-codex'})
            host.save_configuration({'backend': 'deepseek', 'model': 'custom-deepseek'})
            self.assertEqual('custom-codex', app.settings.preferences()['codex']['model'])
            self.assertEqual('custom-deepseek', app.settings.preferences()['deepseek']['model'])
            result = host.save_configuration({'backend': 'codex', 'requestId': 'default-again'})
            self.assertEqual(DEFAULT_MODELS['codex'], result['configuration']['effective']['model'])
            self.assertIsNone(result['configuration']['preferences']['codex']['model'])
            self.assertFalse(result['configuration']['pending'])
            self.assertEqual('default-again', result['configuration']['operationId'])
            app.bind({'mode': 'create', 'path': str(root), 'name': 'other'})
            self.assertEqual('custom-deepseek', app.settings.preferences()['deepseek']['model'])
            app.close()

    def test_apply_and_disk_failure_keep_old_saved_and_effective(self):
        with test_directory() as root:
            app = Workbench(settings_path=root / 'machine/settings.json')
            app.bind({'mode': 'create', 'path': str(root), 'configuration': {'backend': 'codex'}})
            before = app.host.configuration_status()
            for point in ('save', 'apply'):
                with self.subTest(point=point):
                    if point == 'save':
                        context = patch.object(app.host.settings, 'save', side_effect=OSError('disk'))
                    else:
                        original = app.host._apply_configuration
                        def fail(value):
                            original(value)
                            if value['backend'] == 'deepseek':
                                raise OSError('activate')
                        context = patch.object(app.host, '_apply_configuration', side_effect=fail)
                    with context, self.assertRaises(OSError):
                        app.host.save_configuration({'backend': 'deepseek'})
                    self.assertEqual(before, app.host.configuration_status())
            app.close()
            app = Workbench(settings_path=root / 'machine/settings.json')
            self.assertEqual('codex', app.host.backend_name)
            app.close()

    def test_initial_configuration_and_binding_disk_failure_are_one_commit(self):
        with test_directory() as root:
            app = Workbench(settings_path=root / 'machine/settings.json')
            with patch.object(app.binding.settings, 'write', side_effect=OSError('disk')), self.assertRaises(OSError):
                app.bind({'mode': 'create', 'path': str(root), 'configuration': {'backend': 'deepseek'}})
            self.assertFalse(app.status()['bound'])
            self.assertFalse(app.settings.path.exists())
            app.bind({'mode': 'import', 'path': str(root / 'knowledge-base'), 'configuration': {'backend': 'codex'}})
            self.assertEqual('codex', app.configuration_status()['effective']['backend'])
            app.close()

    def test_check_runs_the_selected_model_without_installing_or_discovering_models(self):
        setup = BackendSetup()
        with test_directory() as root:
            binary = root / 'runtime.exe'
            binary.touch()
            payload = {'backend': 'codex', 'runtimePath': str(binary), 'model': 'chosen'}
            with patch.object(setup, 'prepare', side_effect=AssertionError('no automatic installation')), \
                    patch.object(Protocol, 'source_read', True), patch.object(Protocol, 'instances', []), \
                    patch('host.backends.codex.AppServer', Protocol), \
                    patch.object(setup, 'models', side_effect=AssertionError('no automatic catalog')):
                first = setup.check(payload)
                self.assertEqual('success', first['status'])
                self.assertEqual('chosen', first['checkedModel'])
                changed = setup.check({**payload, 'model': None})
                self.assertEqual('success', changed['status'])
                self.assertEqual(DEFAULT_MODELS['codex'], changed['checkedModel'])
                self.assertNotEqual(first['environmentId'], changed['environmentId'])
                self.assertEqual(['chosen', DEFAULT_MODELS['codex']], [runtime.model for runtime in Protocol.instances])

    def test_catalog_retry_requires_no_inference(self):
        class CatalogRuntime(AccountRuntime):
            def request(self, method, params, timeout=60):
                if method == 'model/list':
                    return {'data': [{'model': 'selected'}]}
                return super().request(method, params, timeout)

        setup = BackendSetup()
        with test_directory() as root:
            binary = root / 'runtime.exe'; binary.touch()
            payload = {'backend': 'codex', 'runtimePath': str(binary)}
            with patch.object(setup, 'check', side_effect=AssertionError('no inference')):
                with patch('host.backends.codex.AppServer', side_effect=OSError('catalog secret-value')):
                    failed = setup.models(payload)
                    self.assertEqual('failed', failed['catalogStatus'])
                    self.assertNotIn('secret-value', str(failed))
                with patch('host.backends.codex.AppServer', CatalogRuntime):
                    result = setup.models(payload)
                self.assertEqual(['selected'], result['models'])
                self.assertNotIn('checkedModel', result)

    def test_busy_apply_refused_before_save_or_activation(self):
        with test_directory() as root:
            app = Workbench(settings_path=root / 'machine/settings.json')
            app.bind({'mode': 'create', 'path': str(root)})
            before = app.host.configuration_status()
            with patch.object(app.host, '_configuration_busy', return_value=True), self.assertRaisesRegex(ValueError, '任务运行中'):
                app.host.save_configuration({'backend': 'deepseek'})
            self.assertEqual(before, app.host.configuration_status())
            app.close()


if __name__ == '__main__':
    unittest.main()
