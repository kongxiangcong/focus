"""Saved/effective configuration through public Host operations and real Core."""
import unittest
import uuid
import threading
from pathlib import Path
from unittest.mock import patch

import test_focus_read
from test_stage6b_workflows import HarnessHistory, CodexHistory, HarnessCandidates, HarnessBlog, CodexCandidates
from workspace_fixture import HostService
from host.server import Server
from test_blog_host import ParserDouble, ControlledBlogRuntime
import test_stage5_ingestion as single


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_focus_read.FocusReadTests()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.settings = self.fixture.root / 'user-settings.json'
        self.host = None

    def tearDown(self):
        if self.host:
            self.host.close()
        self.fixture.tearDown()

    def test_one_save_applies_backend_and_preserves_discussion(self):
        with patch('host.backends.codex.AppServer', CodexHistory), patch('deepseek_harness.DeepSeekHarness', HarnessHistory):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex', settings_path=self.settings)
            before = self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '请记住量子香蕉'})
            self.host.worker.join(5)
            original = self.host.snapshot()
            self.assertIn('Codex', original['conversation'][-1]['content'])
            refreshed = self.host.save_configuration({'backend': 'deepseek', 'model': 'deepseek-v4-flash'})
            self.assertEqual('deepseek', refreshed['agent']['backend'])
            self.assertFalse(refreshed['configuration']['pending'])
            self.assertEqual(before['discussionId'], refreshed['discussionId'])
            self.assertEqual(original['conversation'], refreshed['conversation'])
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '上次的例子叫什么？'})
            self.host.worker.join(5)
            self.assertIn('量子香蕉', self.host.snapshot()['conversation'][-1]['content'])

    def test_busy_reading_blocks_apply_and_leaves_both_configurations_unchanged(self):
        entered, released = threading.Event(), threading.Event()
        class WaitingHarness(HarnessCandidates):
            def run(self, prompt, **options):
                entered.set()
                released.wait(5)
                return super().run(prompt, **options)
        with patch('deepseek_harness.DeepSeekHarness', WaitingHarness):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek', settings_path=self.settings)
            self.host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex)
            self.assertTrue(entered.wait(3))
            try:
                with self.assertRaisesRegex(ValueError, '任务运行中'):
                    self.host.save_configuration({'backend': 'codex', 'model': 'another-model'})
                busy = self.host.refresh_configuration()['configuration']
                self.assertFalse(busy['refreshBlocked'])
                self.assertEqual('deepseek', busy['effective']['backend'])
                self.assertEqual('deepseek', busy['effective']['backend'])
            finally:
                released.set()
                self.host.reading_workers['fixture-paper'].join(10)
            self.assertTrue(self.host.snapshot()['preparations']['fixture-paper']['ready'])
            self.assertEqual('deepseek', self.host.snapshot()['agent']['backend'])
            self.assertEqual('codex', self.host.save_configuration({'backend': 'codex'})['agent']['backend'])

    def test_reverting_saved_configuration_clears_pending_and_settings_cross_knowledge_bases(self):
        self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex', settings_path=self.settings)
        original = self.host.snapshot()['configuration']['effective']
        self.host.save_configuration({'backend': 'deepseek', 'model': 'deepseek-v4-flash'})
        restored = self.host.save_configuration(original)
        self.assertFalse(restored['configuration']['pending'])
        self.host.save_configuration({'backend': 'deepseek', 'model': 'deepseek-v4-flash'})
        other = HostService(self.fixture.root / 'another-kb', self.fixture.root / 'another-host', settings_path=self.settings)
        try:
            self.assertEqual('deepseek', other.snapshot()['agent']['backend'])
            self.assertFalse((other.workspace / 'settings.json').exists())
        finally:
            other.close()

    def test_missing_runtime_can_be_saved_but_ai_reports_it_without_fallback(self):
        self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex', settings_path=self.settings)
        self.host.save_configuration({'backend': 'deepseek', 'runtimePath': str(self.fixture.root / 'missing.exe')})
        state = self.host.snapshot()['configuration']
        self.assertEqual('deepseek', state['effective']['backend'])
        self.assertFalse(state['pending'])
        with self.assertRaisesRegex(Exception, 'Runtime'):
            self.host._build_backend()

    def test_standalone_blog_worker_blocks_configuration_until_cancellation_settles(self):
        runtime = ControlledBlogRuntime()
        runtime.release.clear()
        self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex',
                                settings_path=self.settings, blog_runtime=runtime)
        self.host.save_configuration({'backend': 'deepseek'})
        self.host.blog_generate('fixture-paper', request_id=uuid.uuid4().hex)
        self.assertTrue(runtime.entered.wait(5))
        try:
            with self.assertRaisesRegex(ValueError, '任务运行中'):
                self.host.save_configuration({'backend': 'codex'})
            self.assertFalse(self.host.refresh_configuration()['configuration']['refreshBlocked'])
            self.host.blog_cancel('fixture-paper')
        finally:
            runtime.release.set()
            for worker in list(self.host.blog_workers.values()):
                worker.join(5)
        self.assertEqual('deepseek', self.host.snapshot()['agent']['backend'])
        self.assertEqual('codex', self.host.save_configuration({'backend': 'codex'})['agent']['backend'])

    def test_progress_worker_blocks_configuration_after_cursor_has_advanced(self):
        from test_reading_progress import ProgressRuntime
        from test_stage4_reading import ReadingRuntimeDouble
        runtime = ProgressRuntime()
        runtime.pause = True
        self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex',
                                settings_path=self.settings, reading_runtime=ReadingRuntimeDouble(), progress_runtime=runtime)
        self.host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex)
        self.host.reading_workers['fixture-paper'].join(5)
        view = self.host.open_prepared_reading('fixture-paper', request_id=uuid.uuid4().hex)
        with patch('host.backends.codex.AppServer', CodexHistory):
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '量子香蕉',
                             'receipt': {'sourceId': 'fixture-paper', 'planId': view['current']['planId'],
                                         'chunkId': view['current']['chunkId']}})
            self.host.worker.join(5)
        self.host.save_configuration({'backend': 'deepseek'})
        request_id = uuid.uuid4().hex
        self.host.continue_cached({'requestId': request_id, 'receipt': {
            'sourceId': 'fixture-paper', 'planId': view['current']['planId'],
            'chunkId': view['current']['chunkId'], 'readingRevision': view['readingRevision']}})
        self.assertTrue(runtime.entered.wait(3))
        try:
            with self.assertRaisesRegex(ValueError, '任务运行中'):
                self.host.save_configuration({'backend': 'codex'})
            self.assertFalse(self.host.refresh_configuration()['configuration']['refreshBlocked'])
        finally:
            runtime.release.set()
            self.host.progress_workers[request_id].join(5)
        before = self.host.snapshot()['current']
        after = self.host.refresh_configuration()
        self.assertEqual(before, after['current'])
        self.assertEqual('deepseek', after['agent']['backend'])


class BatchConfigurationTests(unittest.TestCase):
    request = single.SingleIngestionTests.request

    def test_stop_after_three_switch_and_resume_only_unfinished_work(self):
        import tempfile
        entered, release = threading.Event(), threading.Event()
        calls = []

        class WaitingHarness(HarnessBlog):
            def run(self, prompt, **options):
                calls.append('deepseek')
                if len(calls) == 7:  # three classify + blog pairs are complete
                    self.waiting = True
                    entered.set()
                    release.wait(20)
                return super().run(prompt, **options)

            def close(self):
                if getattr(self, 'waiting', False):
                    release.set()

        class RecordingCodex(CodexCandidates):
            def request(self, method, params, **options):
                if method == 'turn/start':
                    calls.append('codex')
                return super().request(method, params, **options)

        with tempfile.TemporaryDirectory() as directory, patch('deepseek_harness.DeepSeekHarness', WaitingHarness), patch('host.backends.codex.AppServer', RecordingCodex):
            root = Path(directory)
            host = HostService(root / 'kb', root / 'host', backend='deepseek',
                               settings_path=root / 'settings.json', ingestion_parser=ParserDouble())
            self.server = Server(('127.0.0.1', 0), host)
            server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            server_thread.start()
            try:
                ids = [self.request('POST', f'/library/inbox?name=paper{i}.pdf&topic=Systems', f'%PDF paper {i}'.encode())['item_id'] for i in range(4)]
                batch = self.request('POST', '/library/batches', {'itemIds': ids, 'requestId': 'first'})
                self.assertTrue(entered.wait(15))
                snapshot = self.request('GET', '/library/batches')[0]
                self.assertEqual(['completed'] * 3, [item['status'] for item in snapshot['items'][:3]])
                preserved = {str(p): p.read_bytes() for item in snapshot['items'][:3]
                             for p in (host.workspace / 'sources' / item['sourceId']).rglob('*') if p.is_file()}
                config = {'backend': 'codex', 'model': 'gpt-6-astra'}
                self.request('POST', '/reader/configuration', config, expected_status=400)
                self.request('POST', f"/library/batches/{batch['batchId']}/stop", {'requestId': 'stop'})
                release.set()
                for worker in list(host.batch_workers.values()):
                    worker.join(15)
                    self.assertFalse(worker.is_alive())
                self.request('POST', '/reader/configuration', config)
                refreshed = self.request('POST', '/reader/configuration/refresh', {})
                self.assertEqual('codex', refreshed['configuration']['effective']['backend'])
                self.assertEqual('paused', self.request('GET', '/library/batches')[0]['status'])
                self.assertNotIn('codex', calls)
                self.request('POST', f"/library/batches/{batch['batchId']}/continue", {'requestId': 'resume'})
                for worker in list(host.batch_workers.values()):
                    worker.join(15)
                    self.assertFalse(worker.is_alive())
                result = self.request('GET', '/library/batches')[0]
                self.assertEqual('completed', result['status'], result)
                self.assertEqual(2, calls.count('codex'))
                self.assertEqual(preserved, {p: Path(p).read_bytes() for p in preserved})
            finally:
                release.set()
                self.server.shutdown()
                self.server.server_close()
                server_thread.join()
                host.close()


if __name__ == '__main__':
    unittest.main()
