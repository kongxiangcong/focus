"""DeepSeek settings and declared credentials survive the ACP cutover."""
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from host.backends.registry import HarnessRegistry
from host.configuration import UserSettings, resolve_startup
from host.proxy import backend_environment


class DeepSeekCutoverTests(unittest.TestCase):
    def test_old_sdk_path_is_rediscovered_and_an_explicit_new_dsh_path_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / 'sdk-only.exe'
            detected = root / 'dsh.cmd'
            explicit = root / 'selected-dsh.cmd'
            credential = root / 'deepseek.env'
            for path in (legacy, detected, explicit):
                path.touch()
                path.chmod(0o700)
            old = {'backend': 'deepseek', 'model': 'my-existing-model', 'runtimePath': str(legacy),
                   'credentialFile': str(credential)}
            path = root / 'settings.json'
            original = json.dumps({**old, 'preferences': {'deepseek': old, 'codex': {'model': 'old-codex'}}})
            path.write_text(original, encoding='utf-8')
            with patch('host.backends.registry.shutil.which', side_effect=lambda name: str(detected) if name == 'dsh' else None):
                registry = HarnessRegistry()
            settings = UserSettings(path, registry=registry)
            expected = {**old, 'runtimePath': None}
            self.assertEqual(expected, settings.read())
            self.assertIsNone(settings.preferences()['deepseek']['runtimePath'])
            self.assertEqual('old-codex', settings.preferences()['codex']['model'])
            self.assertEqual(original, path.read_text(encoding='utf-8'))
            self.assertEqual('acp', registry.get_spec('deepseek').driver)
            self.assertEqual((str(detected.resolve()), '--profile', 'acp'), registry.resolve_command('deepseek'))
            with patch.dict(os.environ, {'FOCUS_BACKEND_BIN': '', 'FOCUS_MODEL': ''}):
                startup = resolve_startup(settings, backend='deepseek')
            self.assertIsNone(startup.error)
            self.assertEqual({**expected, 'runtimePath': str(detected.resolve())}, startup.configuration)
            settings.save({**old, 'runtimePath': str(explicit)})
            reloaded = UserSettings(path, registry=registry)
            self.assertEqual(str(explicit), reloaded.read()['runtimePath'])
            self.assertEqual(str(explicit), reloaded.preferences()['deepseek']['runtimePath'])

    def test_legacy_implicit_key_is_fallback_and_explicit_credentials_take_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fallback = root / '.env'
            fallback.write_text('DEEPSEEK_API_KEY=legacy-fixture\nOTHER_SECRET=excluded\n', encoding='utf-8')
            explicit = root / 'explicit.env'
            explicit.write_text('DEEPSEEK_API_KEY=explicit-fixture\nOTHER_SECRET=excluded\n', encoding='utf-8')
            spec = replace(HarnessRegistry().get_spec('deepseek'), legacy_credential_file=fallback)
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual('legacy-fixture', backend_environment(spec)['DEEPSEEK_API_KEY'])
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'ambient-fixture'}, clear=True):
                self.assertEqual('ambient-fixture', backend_environment(spec)['DEEPSEEK_API_KEY'])
                effective = backend_environment(spec, credential_file=explicit)
                self.assertEqual('explicit-fixture', effective['DEEPSEEK_API_KEY'])
                self.assertNotIn('OTHER_SECRET', effective)
