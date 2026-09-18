"""Preparation persists assets without simulating reading or starting models."""
import json
import unittest
from unittest.mock import patch

import test_web_host
from test_web_host import ProtocolDouble
from core.reading_workspace import WorkspaceError


class PreparedReadingTests(unittest.TestCase):
    setUp = test_web_host.WebHostTests.setUp
    tearDown = test_web_host.WebHostTests.tearDown
    finish = test_web_host.WebHostTests.finish

    def prepare_all(self):
        core = self.host.core.core
        status = core.preparation_status(source_id='fixture-paper')
        for chunk in status['pending']:
            core.save_prepared_translation(source_id='fixture-paper', plan_id=status['plan_id'], chunk_id=chunk, translation='已准备的译文')

    def test_prepare_does_not_move_cursor_or_change_notes_and_resumes_missing(self):
        core = self.host.core.core
        state = (self.workspace / 'state.json').read_bytes()
        status = core.preparation_status(source_id='fixture-paper')
        self.assertEqual(3, len(status['pending']))
        core.save_prepared_translation(source_id='fixture-paper', plan_id='plan-001', chunk_id='chunk-002', translation='第二段译文')
        core.save_prepared_translation(source_id='fixture-paper', plan_id='plan-001', chunk_id='chunk-002', translation='不应覆盖')
        chunk = core.preparation_chunk(source_id='fixture-paper', plan_id='plan-001', chunk_id='chunk-002')
        self.assertEqual('第二段译文', chunk['translation'])
        self.assertEqual(['chunk-001', 'chunk-003'], core.preparation_status(source_id='fixture-paper')['pending'])
        self.assertEqual(state, (self.workspace / 'state.json').read_bytes())
        with self.assertRaises(WorkspaceError):
            core.save_prepared_translation(source_id='fixture-paper', plan_id='plan-999', chunk_id='chunk-001', translation='过期')

    def test_chinese_paper_is_ready_without_translations(self):
        path = self.workspace / 'sources/fixture-paper/parser-bundle/metadata.json'
        meta = json.loads(path.read_text()); meta['language'] = 'zh'; path.write_text(json.dumps(meta))
        core = self.host.core.core
        self.assertTrue(core.preparation_status(source_id='fixture-paper')['ready'])
        self.assertEqual('source_ready', core.get_current_chunk()['status'])
        with self.assertRaises(WorkspaceError):
            core.save_prepared_translation(source_id='fixture-paper', plan_id='plan-001', chunk_id='chunk-001', translation='重复中文')
        self.host.library_read('fixture-paper')
        self.host.start({'requestId': 'chinese-next-123', 'receipt': self.receipt}, continuing=True)
        self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])
        self.assertIsNone(self.host.snapshot()['current']['translation'])
        self.assertEqual([], ProtocolDouble.instances)

    def test_mixed_plan_requires_only_foreign_chunks(self):
        path = self.workspace / 'sources/fixture-paper/reading/plans/plan-001/chunks.jsonl'
        chunks = [json.loads(line) for line in path.read_text().splitlines()]
        chunks[0]['language'] = 'zh'; chunks[1]['language'] = 'en'; chunks[2]['language'] = 'mixed'
        path.write_text('\n'.join(json.dumps(c) for c in chunks)+'\n')
        self.assertEqual(['chunk-002', 'chunk-003'], self.host.core.core.preparation_status(source_id='fixture-paper')['pending'])
        self.assertEqual('source-ready', self.host.snapshot()['current']['presentationStatus'])
        self.prepare_all()
        self.assertTrue(self.host.core.core.preparation_status(source_id='fixture-paper')['ready'])

    def test_cached_read_continue_restart_never_construct_backend(self):
        self.prepare_all()
        core = self.host.core.core
        core.append_note(expected_plan_id='plan-001', expected_chunk_id='chunk-001', kind='thought', origin='user', content='保留笔记')
        with patch.object(self.host, '_build_backend', side_effect=AssertionError('Unexpected Agent')):
            self.host.library_read('fixture-paper')
            payload = {'requestId': 'cached-continue-123', 'receipt': self.receipt}
            self.host.start(payload, continuing=True)
            self.host.start(payload, continuing=True)
            self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])
            self.host.library_read('fixture-paper', reread=True)
        self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])
        record = json.loads((self.workspace / 'sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json').read_text())
        self.assertEqual('保留笔记', record['notes'][0]['content'])
        self.assertEqual('已准备的译文', record['translation'])
        self.assertEqual([], ProtocolDouble.instances)

    def test_missing_preparation_never_advances_and_failed_preparation_retains_assets(self):
        with self.assertRaisesRegex(ValueError, '尚未准备完成'):
            self.host.start({'requestId': 'unprepared-next', 'receipt': self.receipt}, continuing=True)
        self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])
        self.host.library_read('fixture-paper')
        self.finish()
        self.assertEqual('failed', self.host.state['run']['status'])
        self.assertIn('全文准备未完成', self.host.state['run']['error'])
        self.assertEqual('plan-001', self.host.core.core.get_reading_state()['plan_id'])

    def test_replan_preserves_previous_assets(self):
        self.prepare_all()
        path = self.workspace / 'sources/fixture-paper/reading/plans/plan-001'
        before = {str(p): p.read_bytes() for p in path.rglob('*') if p.is_file()}
        with patch('host.service.check_backend', return_value='test'):
            self.host.library_read('fixture-paper', replan=True)
        self.finish()
        self.assertEqual(before, {str(p): p.read_bytes() for p in path.rglob('*') if p.is_file()})
        self.assertFalse(self.host.core.core.preparation_status(source_id='fixture-paper')['ready'])

    def test_agent_preparation_tool_calls_complete_before_reading_begins(self):
        host = self.host
        initial = (self.workspace / 'state.json').read_bytes()

        class PreparingDouble(ProtocolDouble):
            pending = ['chunk-001', 'chunk-002', 'chunk-003']

            def request(self, method, params, timeout=60):
                if method == 'turn/start':
                    self.calls.append({'method': method, 'params': params})
                    self.next_chunk()
                    return {'turn': {'id': 'preparing-turn'}}
                return super().request(method, params, timeout)

            def next_chunk(self):
                if self.pending:
                    chunk_id = self.pending.pop(0)
                    self.events.put({'id': 800, 'method': 'item/tool/call', 'params': {'tool': 'focus', 'arguments': {
                        'action': 'prepare_translation', 'arguments': json.dumps({'source_id': 'fixture-paper',
                        'plan_id': 'plan-001', 'chunk_id': chunk_id, 'translation': '准备好的译文'})}}})
                else:
                    self.complete()

            def send(self, value):
                self.calls.append(value)
                if value.get('id') == 800 and 'result' in value:
                    if not value['result']['success']:
                        raise AssertionError(value)
                    if (host.workspace / 'state.json').read_bytes() != initial:
                        raise AssertionError('Preparation changed reading state')
                    self.next_chunk()

        with patch('host.backends.codex.AppServer', side_effect=PreparingDouble):
            self.host.library_read('fixture-paper')
            self.finish()
        self.assertEqual('completed', self.host.state['run']['status'])
        self.assertTrue(self.host.core.core.preparation_status(source_id='fixture-paper')['ready'])
        self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])
        self.assertEqual('准备好的译文', self.host.snapshot()['current']['translation'])
        self.assertTrue(json.loads((self.workspace / 'state.json').read_text())['sources']['fixture-paper']['reading_started'])

    def test_cli_prepares_arbitrary_chunk_without_starting_reading(self):
        import subprocess
        import sys
        from pathlib import Path
        script = Path(__file__).resolve().parents[1] / '.agents/skills/focus-map/scripts/focus_map.py'
        base = [sys.executable, str(script), 'prepare', '--workspace', str(self.workspace), '--source-id', 'fixture-paper']
        state = (self.workspace / 'state.json').read_bytes()
        status = json.loads(subprocess.check_output(base, text=True))
        self.assertEqual(3, status['total'])
        command = base + ['--plan-id', 'plan-001', '--chunk-id', 'chunk-003']
        chunk = json.loads(subprocess.check_output(command, text=True))
        self.assertEqual('translation_required', chunk['status'])
        result = subprocess.run(command + ['--translation-stdin'], input='第三段译文', text=True, capture_output=True, check=True)
        self.assertEqual(1, json.loads(result.stdout)['completed'])
        self.assertEqual(state, (self.workspace / 'state.json').read_bytes())

    def test_topic_preflight_never_advances_into_unprepared_source(self):
        import shutil
        from host.core_bridge import SourceLibrary
        source = self.workspace / 'sources/fixture-paper'
        second = self.workspace / 'sources/second-paper'
        shutil.copytree(source, second)
        path = second / 'source.yaml'
        metadata = json.loads(path.read_text()); metadata['source_id'] = 'second-paper'; metadata['identity'] = 'fixture:second'
        path.write_text(json.dumps(metadata))
        path = self.workspace / 'state.json'
        state = json.loads(path.read_text()); state['sources']['second-paper'] = dict(state['sources']['fixture-paper'])
        path.write_text(json.dumps(state))
        library = SourceLibrary(self.workspace)
        library.attach('fixture-paper', topic_title='Test', topic_id='test-topic')
        library.attach('second-paper', topic_title='Test', topic_id='test-topic')
        self.prepare_all()
        self.host.core.core.select_topic('test-topic')
        with self.assertRaisesRegex(ValueError, '尚未准备完成'):
            self.host.continue_cached({'requestId': 'topic-next-missing', 'receipt': self.receipt})
        self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])
        status = self.host.core.core.preparation_status(source_id='second-paper')
        for chunk_id in status['pending']:
            self.host.core.core.save_prepared_translation(source_id='second-paper', plan_id='plan-001', chunk_id=chunk_id, translation='第二份材料译文')
        for i in range(3):
            current = self.host.snapshot()['current']
            self.host.continue_cached({'requestId': f'topic-next-ready-{i}', 'receipt': {k: current[k] for k in ('sourceId','planId','chunkId')}})
        self.assertEqual('second-paper', self.host.snapshot()['current']['sourceId'])
        self.assertEqual('第二份材料译文', self.host.snapshot()['current']['translation'])
        self.assertEqual([], ProtocolDouble.instances)
