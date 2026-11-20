"""First-send admission at the Host and selected Runtime protocol boundaries."""
import json
import os
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from host.service import HostService


class Protocol:
    instances = []
    source_read = False

    def __init__(self, command, cwd, *, env):
        self.command = command
        self.cwd = Path(cwd)
        self.events = queue.Queue()
        self.prompt = None
        self.tools = []
        self.closed = False
        self.instances.append(self)

    def initialize(self):
        pass

    def send(self, message):
        if message.get('id') == 401:
            reply = json.loads(message['result']['contentItems'][0]['text'])
            self.complete(reply['source_text'])

    def request(self, method, params, timeout=60):
        if method == 'account/read':
            return {'account': {'type': 'chatgpt'}}
        if method == 'thread/start':
            self.tools = params.get('dynamicTools', [])
            self.model = params.get('model')
            return {'thread': {'id': 'fixture-thread'}}
        if method == 'turn/start':
            self.prompt = params['input'][0]['text']
            if self.probe and self.source_read:
                self.events.put({'id': 401, 'method': 'item/tool/call', 'params': {'tool': 'focus',
                    'arguments': {'action': 'read_range', 'arguments': '{"start":1,"end":1}'}}})
            else:
                self.complete('ordinary answer')
            return {'turn': {'id': 'fixture-turn'}}
        raise AssertionError(method)

    @property
    def probe(self):
        return bool(self.tools and self.tools[0]['inputSchema']['properties']['action']['enum'] == ['read_range'])

    def complete(self, text):
        self.events.put({'method': 'item/completed', 'params': {'item': {
            'type': 'agentMessage', 'id': 'fixture-answer', 'text': text}}})
        self.events.put({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})

    def close(self):
        self.closed = True


class BackendVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        Protocol.instances = []
        Protocol.source_read = False
        stack = patch('host.backends.codex.AppServer', Protocol)
        stack.start()
        self.addCleanup(stack.stop)
        self.host = HostService(self.root / 'workspace', None, backend='codex', model='fixture-model',
                                codex_bin=sys.executable, settings_path=self.root / 'settings.json')
        self.addCleanup(self.host.close)

    def send(self, request_id, content, *, host=None, source=None):
        host = host or self.host
        initial = host.start({'requestId': request_id, 'content': content, 'sourceId': source})
        host.worker.join(8)
        self.assertFalse(host.worker.is_alive())
        return initial, host.snapshot()

    def test_failed_first_send_admits_no_question_and_retry_sends_once_after_probe(self):
        initial, rejected = self.send('fixture-first', 'PRIVATE-QUESTION')
        self.assertEqual('正在检测 Backend', initial['agent']['run']['progress']['label'])
        self.assertEqual('failed', rejected['agent']['run']['status'])
        self.assertIn('临时原文', rejected['agent']['run']['error'])
        self.assertEqual([], rejected['conversation'])
        self.assertEqual(1, len(Protocol.instances))
        self.assertTrue(Protocol.instances[0].probe)
        self.assertNotIn('PRIVATE-QUESTION', Protocol.instances[0].prompt)

        Protocol.source_read = True
        _, accepted = self.send('fixture-first', 'PRIVATE-QUESTION')
        self.assertEqual('completed', accepted['agent']['run']['status'], accepted['agent']['run'])
        self.assertEqual([True, True, False], [runtime.probe for runtime in Protocol.instances])
        self.assertEqual(['PRIVATE-QUESTION'], [m['content'] for m in accepted['conversation'] if m['role'] == 'user'])
        self.assertIn('PRIVATE-QUESTION', Protocol.instances[-1].prompt)

        self.send('fixture-second', 'Follow-up')
        self.assertEqual([True, True, False, False], [runtime.probe for runtime in Protocol.instances])

    def test_ordinary_check_does_not_apply_and_exact_receipts_survive_host_rebind(self):
        Protocol.source_read = True
        folder = self.root / 'backends'
        folder.mkdir()
        manifest = folder / 'fixture.json'
        other_binary = self.root / 'alternate.exe'
        other_binary.touch(mode=0o755)
        receipt_cache = self.host.setup.verification
        original = ('example', sys.executable, 'fixture-a', ['app-server', '--first', '--second'])
        cases = [original, ('example-b', *original[1:]), (original[0], str(other_binary), *original[2:]),
                 (*original[:2], 'fixture-b', original[3]), (*original[:3], ['app-server', '--second', '--first']), original]
        for index, (backend_id, binary, model, argv) in enumerate(cases):
            with self.subTest(backend=backend_id, binary=binary, model=model, argv=argv):
                manifest.write_text(json.dumps({'id': backend_id, 'label': 'Fixture', 'driver': 'codex-app-server',
                    'command': [binary, *argv], 'defaultModel': model}), encoding='utf-8')
                settings = self.root / 'choices.json'
                if index == 0:
                    # Legacy text-check metadata comes from neither this process's probe nor its receipt store.
                    settings.write_text(json.dumps({'environmentId': 'legacy-text-check'}), encoding='utf-8')
                    with_host = HostService(self.root / 'settings-check', None, backend='codex', codex_bin=sys.executable,
                                            settings_path=settings, verification=receipt_cache)
                    try:
                        checked = with_host.backend_setup('check', {'backend': backend_id, 'model': model})
                        self.assertEqual('success', checked['status'])
                        self.assertEqual('codex', with_host.configuration_status()['effective']['backend'])
                        self.assertEqual(1, len(Protocol.instances))
                        self.assertTrue(Protocol.instances[-1].probe)
                    finally:
                        with_host.close()
                runtime_count = len(Protocol.instances)
                host = HostService(self.root / f'workspace-{index}', None, backend=backend_id,
                                   settings_path=settings, verification=receipt_cache)
                try:
                    _, view = self.send(f'fixture-receipt-{index}', 'Question after settings check', host=host)
                    self.assertEqual('completed', view['agent']['run']['status'])
                    self.assertEqual([False] if index in (0, 5) else [True, False],
                                     [runtime.probe for runtime in Protocol.instances[runtime_count:]])
                finally:
                    host.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows transient staging rename')
    def test_a_transient_probe_staging_failure_retries_only_local_registration(self):
        from host.backend_probe import import_markdown

        error = PermissionError('fixture Windows staging lock')
        error.winerror = 5
        staged = []

        def stage(workspace, *args, **options):
            staged.append(workspace)
            if len(staged) == 1:
                raise error
            return import_markdown(workspace, *args, **options)

        Protocol.source_read = True
        with patch('host.backend_probe.import_markdown', side_effect=stage):
            checked = self.host.backend_setup('check', {'backend': 'codex', 'model': 'fixture-model'})
        self.assertEqual('success', checked['status'], checked)
        self.assertEqual(2, len(set(staged)))
        self.assertTrue(all(not workspace.exists() for workspace in staged))
        self.assertEqual(1, len(Protocol.instances))
