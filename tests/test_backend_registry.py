"""Public settings and Discussion behavior for manifest registrations."""
import json
import os
import sys
import unittest
from unittest.mock import patch

import reading_fixture
from host.workbench import Workbench
from workspace_fixture import publish_workspace
from test_workspace_portability import test_directory as fixture_directory


class BackendRegistryTests(unittest.TestCase):
    def test_first_workspace_binding_does_not_launch_or_select_a_backend(self):
        with fixture_directory() as root, patch('host.backends.registry.shutil.which', return_value=None), \
                patch('host.backends.registry._codex_bundled', side_effect=FileNotFoundError), \
                patch('host.backends.registry._legacy_dsh_bundled', side_effect=FileNotFoundError), \
                patch('subprocess.Popen') as runtime:
            app = Workbench(settings_path=root / 'settings.json')
            try:
                config = app.configuration_status()
                self.assertEqual({'codex', 'deepseek', 'agy', 'cursor'}, {item['id'] for item in config['backends']})
                self.assertFalse(any(item['available'] for item in config['backends']))
                app.bind({'mode': 'create', 'path': str(root), 'configuration': {'backend': 'codex'}})
                app.host.library_manage('create-topic', title='Read without AI')
                config = app.configuration_status()
                self.assertIsNone(config['saved'])
                self.assertIsNone(config['effective'])
                self.assertNotIn('backend', app.settings.document())
                runtime.assert_not_called()
            finally:
                app.close()

    def test_explicit_manifest_directory_and_rescan_report_local_errors(self):
        with fixture_directory() as root, patch('subprocess.Popen') as runtime:
            settings = root / 'data' / 'settings.json'
            adjacent = settings.parent / 'backends'
            adjacent.mkdir(parents=True)
            override = root / 'extra'
            override.mkdir()
            (adjacent / 'adjacent.json').write_text(json.dumps(self._manifest('adjacent')), encoding='utf-8')
            (override / 'local.json').write_text(json.dumps(self._manifest('local')), encoding='utf-8')
            app = Workbench(settings_path=settings, backends_dir=override)
            try:
                descriptions = {item['id']: item for item in app.configuration_status()['backends']}
                self.assertNotIn('adjacent', descriptions)
                self.assertTrue(descriptions['local']['available'])
                (override / 'broken.json').write_text('{broken', encoding='utf-8')
                (override / 'collision.json').write_text(json.dumps(self._manifest('codex')), encoding='utf-8')
                (override / 'another.json').write_text(json.dumps(self._manifest('another')), encoding='utf-8')
                result = app.backend_setup('rescan', {})
                descriptions = {item['id']: item for item in result['backends']}
                self.assertEqual('Codex', descriptions['codex']['label'])
                self.assertTrue(descriptions['another']['available'])
                self.assertEqual({'broken.json', 'collision.json'}, {item['file'] for item in result['backendErrors']})
                self.assertTrue(all(item['message'] for item in result['backendErrors']))
                self.assertIsNone(app.configuration_status()['effective'])
                runtime.assert_not_called()
            finally:
                app.close()

    def test_manifests_follow_actual_settings_path(self):
        with fixture_directory() as root, patch.dict(os.environ, {'LOCALAPPDATA': str(root)}):
            os.environ.pop('FOCUS_SETTINGS_FILE', None)
            default_dir = root / 'FOCUS' / 'backends'
            default_dir.mkdir(parents=True)
            (default_dir / 'default.json').write_text(json.dumps(self._manifest('machine-default')), encoding='utf-8')
            app = Workbench()
            try:
                self.assertIn('machine-default', {item['id'] for item in app.configuration_status()['backends']})
            finally:
                app.close()
            custom = root / 'testing' / 'other-settings.json'
            os.environ['FOCUS_SETTINGS_FILE'] = str(custom)
            custom_dir = custom.parent / 'backends'
            custom_dir.mkdir(parents=True)
            (custom_dir / 'custom.json').write_text(json.dumps(self._manifest('custom')), encoding='utf-8')
            app = Workbench()
            try:
                choices = {item['id'] for item in app.configuration_status()['backends']}
                self.assertIn('custom', choices)
                self.assertNotIn('machine-default', choices)
            finally:
                app.close()

    @staticmethod
    def _manifest(identifier):
        return {'id': identifier, 'label': identifier, 'driver': 'acp', 'command': [sys.executable, 'fixture']}

    def test_saved_custom_backend_preserves_command_and_runs_discussion(self):
        fixture = reading_fixture.ReadingFixture()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        workspace = fixture._workspace()[0]
        publish_workspace(workspace)
        settings = fixture.root / 'settings.json'
        backends = fixture.root / 'backends'
        backends.mkdir()
        log = fixture.root / 'runtime.jsonl'
        script = fixture.root / 'app_server.py'
        script.write_text("""
import json, sys
with open(sys.argv[1], 'a', encoding='utf-8') as log:
    print(json.dumps(sys.argv[2:]), file=log, flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        params = request.get('params', {})
        method = request.get('method')
        print(json.dumps([method, params]), file=log, flush=True)
        if 'id' not in request:
            continue
        result = {
            'account/read': {'account': {'type': 'chatgpt'}},
            'thread/start': {'thread': {'id': 'thread-1'}},
            'turn/start': {'turn': {'id': 'turn-1'}},
        }.get(method, {})
        print(json.dumps({'id': request['id'], 'result': result}), flush=True)
        if method == 'turn/start':
            print(json.dumps({'method': 'item/completed', 'params': {'item': {
                'id': 'answer-1', 'type': 'agentMessage', 'text': 'Manifest discussion answer.'}}}), flush=True)
            print(json.dumps({'method': 'turn/completed', 'params': {
                'turn': {'status': 'completed'}}}), flush=True)
""", encoding='utf-8')
        manifest_path = backends / 'custom-codex.json'
        manifest = {
            'id': 'custom-codex', 'label': 'Codex (custom)', 'driver': 'codex-app-server',
            'command': ['uninstalled-program', str(script), str(log), '--first', '--second', 'app-server'],
            'defaultModel': 'manifest-model',
        }
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        settings.write_text(json.dumps({
            'backend': 'custom-codex', 'runtimePath': sys.executable, 'model': 'saved-model',
        }), encoding='utf-8')

        app = Workbench(settings_path=settings, workspace=workspace)
        self.addCleanup(app.close)
        config = app.configuration_status()
        self.assertEqual('custom-codex', config['effective']['backend'])
        self.assertEqual('saved-model', config['effective']['model'])
        choices = config['backends']
        self.assertEqual(1, sum(choice['id'] == 'codex' for choice in choices))
        self.assertEqual('Codex (custom)', next(choice['label'] for choice in choices if choice['id'] == 'custom-codex'))
        manifest['label'] = 'Codex (edited)'
        manifest['command'][4] = '--changed'
        manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        scan = app.backend_setup('rescan', {})
        self.assertEqual('Codex (edited)', next(choice['label'] for choice in scan['backends'] if choice['id'] == 'custom-codex'))
        self.assertEqual(config['effective'], app.configuration_status()['effective'])
        self.assertFalse(log.exists())
        selected = app.host.select_discussion_source('fixture-paper')
        app.host.start({'requestId': 'registry-discussion', 'sourceId': 'fixture-paper',
                        'sessionId': selected['sessionId'], 'content': 'Explain this source.'})
        app.host.worker.join(8)
        result = app.host.snapshot()
        self.assertEqual('completed', result['agent']['run']['status'])
        self.assertIn('Manifest discussion answer.', json.dumps(result))
        arguments, *calls = map(json.loads, log.read_text(encoding='utf-8').splitlines())
        self.assertEqual(['--first', '--second', 'app-server'], arguments[:3])
        self.assertEqual('saved-model', next(params['model'] for method, params in calls if method == 'thread/start'))
