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
def complete(text):
    print(json.dumps({'method': 'item/completed', 'params': {'item': {
        'id': 'answer-1', 'type': 'agentMessage', 'text': text}}}), flush=True)
    print(json.dumps({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}}), flush=True)

probe = False
with open(sys.argv[1], 'a', encoding='utf-8') as log:
    print(json.dumps(sys.argv[2:]), file=log, flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        params = request.get('params', {})
        method = request.get('method')
        print(json.dumps([method, params]), file=log, flush=True)
        if request.get('id') == 401 and 'result' in request:
            reply = json.loads(request['result']['contentItems'][0]['text'])
            complete(reply['source_text'])
            continue
        if 'id' not in request:
            continue
        result = {
            'account/read': {'account': {'type': 'chatgpt'}},
            'thread/start': {'thread': {'id': 'thread-1'}},
            'turn/start': {'turn': {'id': 'turn-1'}},
        }.get(method, {})
        print(json.dumps({'id': request['id'], 'result': result}), flush=True)
        if method == 'thread/start':
            probe = params['dynamicTools'][0]['inputSchema']['properties']['action']['enum'] == ['read_range']
        if method == 'turn/start':
            if probe:
                print(json.dumps({'id': 401, 'method': 'item/tool/call', 'params': {'tool': 'focus',
                    'arguments': {'action': 'read_range', 'arguments': '{"start":1,"end":1}'}}}), flush=True)
            else:
                complete('Manifest discussion answer.')
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
        records = list(map(json.loads, log.read_text(encoding='utf-8').splitlines()))
        self.assertEqual([['--first', '--second', 'app-server']] * 2,
                         [record[:3] for record in records if record[0] == '--first'])
        self.assertEqual(['saved-model'] * 2,
                         [record[1]['model'] for record in records if record[0] == 'thread/start'])
        prompts = [record[1]['input'][0]['text'] for record in records if record[0] == 'turn/start']
        self.assertNotIn('Explain this source.', prompts[0])
        self.assertIn('Explain this source.', prompts[1])
