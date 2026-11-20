"""Public settings and Discussion behavior for manifest registrations."""
import json
import sys
import unittest

import reading_fixture
from host.workbench import Workbench
from workspace_fixture import publish_workspace


class BackendRegistryTests(unittest.TestCase):
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
        (backends / 'custom-codex.json').write_text(json.dumps({
            'id': 'custom-codex', 'label': 'Codex (custom)', 'driver': 'codex-app-server',
            'command': ['uninstalled-program', str(script), str(log), '--first', '--second', 'app-server'],
            'defaultModel': 'manifest-model',
        }), encoding='utf-8')
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
