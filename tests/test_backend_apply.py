"""Backend application, exercised by two clients of the same workbench."""
import http.client
import json
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import reading_fixture
from host.server import Server
from host.workbench import Workbench
from test_backend_verification import Protocol
from workspace_fixture import publish_workspace


class BackendApplyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reading_fixture.ReadingFixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        workspace = self.fixture._workspace()[0]
        publish_workspace(workspace)
        self.settings = self.fixture.root / 'machine.json'
        self.settings.write_text(json.dumps({'backend': 'codex', 'model': 'old-model',
                                              'runtimePath': sys.executable}), encoding='utf-8')
        self.app = Workbench(settings_path=self.settings, workspace=workspace)
        self.addCleanup(self.app.close)
        self.server = Server(('127.0.0.1', 0), self.app)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.instance = self.app.status()['workspace']['instanceId']

    def request(self, method, path, value=None):
        client = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            client.request(method, path, body=None if value is None else json.dumps(value),
                           headers={'Content-Type': 'application/json', 'X-FOCUS-Instance': self.instance})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def test_browsing_remains_live_and_second_tab_cannot_send_apply_or_rebind(self):
        entered = threading.Event()
        release = threading.Event()

        class StalledProbe(Protocol):
            instances = []
            source_read = True

            def request(self, method, params, timeout=60):
                if method == 'turn/start' and self.probe:
                    entered.set()
                    release.wait(7)
                return super().request(method, params, timeout=timeout)

        target = {'backend': 'codex', 'model': 'checked-model', 'runtimePath': sys.executable,
                  'requestId': 'apply-test-request'}
        with patch('host.backends.codex.AppServer', StalledProbe), ThreadPoolExecutor() as pool:
            applying = pool.submit(self.request, 'POST', '/reader/configuration', target)
            try:
                self.assertTrue(entered.wait(2), 'apply did not initiate a source probe')
                self.assertFalse(applying.done())
                status, window = self.request('GET', '/reader/window')
                self.assertEqual(200, status)
                self.assertEqual('old-model', window['value']['configuration']['effective']['model'])
                self.assertEqual('old-model', json.loads(self.settings.read_text(encoding='utf-8'))['model'])
                for path, value in (
                    ('/reader/messages', {'requestId': 'second-tab-message', 'content': 'Do not send yet'}),
                    ('/reader/configuration', {**target, 'model': 'second-model'}),
                    ('/reader/backend/setup', {**target, 'action': 'check'}),
                    ('/library/sources/fixture-paper/blog/generate', {'requestId': 'second-tab-blog'}),
                    ('/reader/workspace', {'mode': 'create', 'path': str(self.fixture.root),
                                           'generation': self.app.generation}),
                ):
                    with self.subTest(path=path):
                        status, result = self.request('POST', path, value)
                        self.assertEqual(409, status)
                        self.assertTrue(result['error']['retryable'])
                self.assertEqual(1, len(StalledProbe.instances))
            finally:
                release.set()
            status, response = applying.result(timeout=6)
        self.assertEqual(200, status)
        first = response['value']['configuration']
        status, second = self.request('GET', '/reader/configuration')
        self.assertEqual(200, status)
        self.assertEqual(first['effective'], second['value']['effective'])
        self.assertEqual(first['saved'], second['value']['saved'])
        self.assertEqual('checked-model', first['effective']['model'])
        self.assertFalse(first['busy'])

    def test_probe_and_disk_failure_preserve_saved_and_effective_and_success_receipt_is_reused(self):
        initial = self.settings.read_bytes()
        before = self.request('GET', '/reader/configuration')[1]['value']
        choice = {'backend': 'codex', 'model': 'candidate-model', 'runtimePath': sys.executable}
        with patch('host.backends.codex.AppServer', Protocol), patch.object(Protocol, 'source_read', False), \
                patch.object(Protocol, 'instances', []):
            status, failed = self.request('POST', '/reader/configuration', choice)
            self.assertEqual(400, status)
            self.assertIn('临时原文', failed['error']['message'])
            self.assertEqual(before, self.request('GET', '/reader/configuration')[1]['value'])
            self.assertEqual(initial, self.settings.read_bytes())

            Protocol.source_read = True
            status, checked = self.request('POST', '/reader/backend/setup', {**choice, 'action': 'check'})
            self.assertEqual(200, status)
            self.assertEqual('success', checked['value']['status'])
            self.assertEqual(2, len(Protocol.instances))
            with patch.object(self.app.host.settings, 'write', side_effect=OSError('fake disk failure')):
                status, failed = self.request('POST', '/reader/configuration', choice)
                self.assertEqual(500, status)
                self.assertEqual(before, self.request('GET', '/reader/configuration')[1]['value'])
                self.assertEqual(initial, self.settings.read_bytes())
            status, applied = self.request('POST', '/reader/configuration', choice)
            self.assertEqual(200, status)
            self.assertEqual('candidate-model', applied['value']['configuration']['saved']['model'])
            self.assertEqual(2, len(Protocol.instances), 'apply must reuse the matching read-range receipt')

    def test_only_speculative_summary_can_be_cancelled_before_apply_and_late_result_is_ignored(self):
        host = self.app.host
        selected = host.select_discussion_source('fixture-paper')
        discussion_id = selected['discussionId']
        with host.lock:
            host.state['conversation'].extend({
                'messageId': f'history-{i}', 'discussionId': discussion_id, 'sourceId': 'fixture-paper',
                'role': 'assistant' if i % 2 else 'user', 'chunkId': '', 'content': f'turn-{i} ' + 'x' * 300,
            } for i in range(30))
            host.changed()
        entered, release, stopped = threading.Event(), threading.Event(), threading.Event()

        class SlowSummary(Protocol):
            source_read = True
            summary = False

            def request(self, method, params, timeout=60):
                if method == 'turn/start' and params['input'][0]['text'].startswith('{"task": "summarize_discussion"'):
                    self.summary = True
                    entered.set()
                    release.wait(6)
                    self.complete('{"summary":"This late result must be ignored"}')
                    return {'turn': {'id': 'late-summary'}}
                return super().request(method, params, timeout=timeout)

            def close(self):
                super().close()
                if self.summary:
                    stopped.set()

        with patch('host.backends.codex.AppServer', SlowSummary):
            host.start({'requestId': 'summary-prefetch', 'sourceId': 'fixture-paper', 'content': 'Explain the text.'})
            host.worker.join(4)
            self.assertFalse(host.worker.is_alive())
            try:
                self.assertTrue(entered.wait(3))
                prior = host.snapshot()
                status, response = self.request('POST', '/reader/configuration',
                    {'backend': 'codex', 'runtimePath': sys.executable, 'model': 'fresh-model'})
                self.assertEqual(200, status)
                self.assertTrue(stopped.wait(2), 'applying should stop speculative runtime immediately')
                self.assertEqual(prior['conversation'], response['value']['conversation'])
                self.assertEqual(prior['readingRevision'], response['value']['readingRevision'])
                self.assertEqual(prior['sourceNotes'], response['value']['sourceNotes'])
            finally:
                release.set()
                if host._summary_worker:
                    host._summary_worker.join(5)
            self.assertIsNone(host.state['discussions'][discussion_id]['summaryThrough'])
