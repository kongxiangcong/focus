"""Confirmed UX contract, using disposable Sources and deterministic runtimes."""
import json
import unittest
import uuid
from unittest.mock import patch
from core.reading_workspace import WorkspaceError
from core.source_library import SourceLibrary
from core.reading_progress import ProgressApplication
import test_stage4_reading as stage4
from test_reading_progress import ProgressRuntime
from host.service import HostService


class ConfirmedUXTests(unittest.TestCase):
    setUp = stage4.Stage4NavigationTests.setUp
    tearDown = stage4.Stage4NavigationTests.tearDown
    receipt = stage4.Stage4NavigationTests.receipt
    rebuild_draft = stage4.Stage4NavigationTests.rebuild_draft

    def advance(self, receipt=None):
        request = uuid.uuid4().hex
        result = self.host.continue_cached({'receipt': receipt or self.receipt(), 'requestId': request})
        worker = self.host.progress_workers.get(request)
        if worker:
            worker.join(3)
        return result

    def test_T5_review_continue_browses_without_duplicate_progress_or_rollback(self):
        self.advance()
        self.advance()
        before = self.host.snapshot()
        old = {**self.receipt(), 'chunkId': 'chunk-001'}
        result = self.advance(old)
        self.assertEqual('browse', result['readingOperation']['operation'])
        self.assertEqual('chunk-002', result['reviewChunk']['chunkId'])
        self.assertEqual(before['readingRevision'], result['readingRevision'])
        self.assertEqual(before['readingProgress'], result['readingProgress'])
        result = self.advance({**old, 'chunkId': 'chunk-002'})
        self.assertEqual('chunk-003', result['reviewChunk']['chunkId'])
        self.assertEqual('chunk-003', result['current']['chunkId'])

    def test_T7_T26_new_session_stays_blank_on_restart_then_advances_frontier(self):
        self.advance()
        self.host.review_chunk('fixture-paper', 'plan-001', 'chunk-001')
        old = self.host.snapshot()
        self.host.new_session({'sessionId': old['sessionId']})
        result = self.host.snapshot()
        self.assertIsNone(result['current'])
        self.assertEqual([], result['timeline'])
        self.assertEqual('chunk-002', result['navigationCurrent']['chunkId'])
        self.assertEqual(old['readingProgress'], result['readingProgress'])
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=stage4.ReadingRuntimeDouble())
        result = self.host.snapshot()
        self.assertTrue(result['sessionFresh'])
        self.assertIsNone(result['current'])
        advanced = self.advance({'sourceId': 'fixture-paper', 'planId': 'plan-001', 'chunkId': 'chunk-002', 'readingRevision': result['readingRevision']})
        self.assertEqual('chunk-003', advanced['current']['chunkId'])

    def test_T8_T11_reset_idempotent_clears_records_and_fences_late_results(self):
        self.advance()
        progress = self.host.snapshot()['readingProgress'][0]
        record = self.workspace / 'sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json'
        before = record.read_bytes()
        request_id = uuid.uuid4().hex
        payload = {'requestId': request_id, 'confirmed': True, 'resetReading': True}
        with patch.object(self.host.source_notes, 'clear', side_effect=OSError('interruption')):
            with self.assertRaises(WorkspaceError):
                self.host.clear_source('fixture-paper', payload)
        self.assertEqual('pending', self.host.store.get('sourceClears')[request_id]['status'])
        result = self.host.clear_source('fixture-paper', payload)
        revision = result['readingRevision']
        self.assertEqual([], result['readingProgress'])
        self.assertIsNone(result['current'])
        self.assertFalse(result['readingStarted'])
        self.assertEqual('chunk-001', result['navigationCurrent']['chunkId'])
        self.host.clear_source('fixture-paper', payload)
        self.assertEqual(revision, self.host.snapshot()['readingRevision'])
        with self.assertRaises(WorkspaceError):
            self.host.progress_core.finish(progress['progress_id'], attempt='late', expected_revision=1, topic='late', user_understanding=None)
        self.assertEqual(before, record.read_bytes())
        result = self.advance({'sourceId': 'fixture-paper', 'planId': 'plan-001', 'chunkId': 'chunk-001', 'readingRevision': revision})
        self.assertEqual('chunk-001', result['current']['chunkId'])
        self.assertEqual([], result['readingProgress'])

    def test_T10_reset_noncurrent_keeps_current_and_other_source_assets(self):
        library = SourceLibrary(self.workspace)
        other = self.workspace / 'sources/other-paper'
        import shutil
        shutil.copytree(self.workspace / 'sources/fixture-paper', other)
        source = json.loads((other / 'source.yaml').read_text())
        source['source_id'] = 'other-paper'
        (other / 'source.yaml').write_text(json.dumps(source))
        state_path = self.workspace / 'state.json'
        state = json.loads(state_path.read_text())
        state['sources']['other-paper'] = {'current_plan_id': 'plan-001', 'current_chunk_id': 'chunk-002', 'reading_started': True, 'reading_pass': 1}
        state_path.write_text(json.dumps(state))
        before = self.host.snapshot()['current']
        self.host.clear_source('other-paper', {'confirmed': True, 'resetReading': True, 'requestId': uuid.uuid4().hex})
        self.assertEqual(before, self.host.snapshot()['current'])
        self.assertEqual('chunk-001', json.loads(state_path.read_text())['sources']['other-paper']['current_chunk_id'])

    def test_T9_completed_review_continue_remains_completed(self):
        self.advance(); self.advance()
        self.host.finish_reading({'receipt': self.receipt(), 'requestId': uuid.uuid4().hex})
        result = self.advance({'sourceId': 'fixture-paper', 'planId': 'plan-001', 'chunkId': 'chunk-001', 'readingRevision': self.host.snapshot()['readingRevision']})
        self.assertEqual('completed', result['status'])
        with self.assertRaises(WorkspaceError):
            self.advance({'sourceId': 'fixture-paper', 'planId': 'plan-001', 'chunkId': 'chunk-003', 'readingRevision': result['readingRevision']})

    def test_A8_T3_review_has_independent_events_and_chronology(self):
        self.advance()
        first = self.host.review_chunk('fixture-paper', 'plan-001', 'chunk-001')
        second = self.host.review_chunk('fixture-paper', 'plan-001', 'chunk-001')
        timeline = second['timeline']
        self.assertEqual(['chunk-001', 'chunk-002', 'chunk-001', 'chunk-001'], [e['chunk']['chunkId'] for e in timeline])
        self.assertEqual(len(timeline), len({e['eventId'] for e in timeline}))

    def test_A9_T12_progress_excludes_same_ordinal_from_another_plan(self):
        runtime = ProgressRuntime()
        self.host.progress_app = ProgressApplication(self.host.progress_core, runtime)
        self.host.state['conversation'].extend([
            {'messageId': 'old-user', 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001', 'reference': {'planId': 'plan-old'}, 'readingPass': 1, 'role': 'user', 'content': '旧计划的问题'},
            {'messageId': 'old-answer', 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001', 'reference': {'planId': 'plan-old'}, 'readingPass': 1, 'role': 'assistant', 'content': '旧计划的回答'},
        ])
        self.advance()
        self.assertEqual([], runtime.calls)

    def test_T13_source_details_one_save_and_forward_recovery(self):
        library = SourceLibrary(self.workspace)
        topic = library.create_topic('UX topic')
        payload = {'requestId': uuid.uuid4().hex, 'title': 'Updated title', 'topicIds': [topic['topicId']]}
        with patch.object(SourceLibrary, 'attach', side_effect=OSError('interruption')):
            with self.assertRaises(OSError):
                self.host.save_source_details('fixture-paper', payload)
        self.host.save_source_details('fixture-paper', payload)
        self.assertEqual('Updated title', library.get('fixture-paper')['title'])
        self.assertIn('fixture-paper', next(t for t in library.topics() if t['topicId'] == topic['topicId'])['sourceIds'])

    def test_T11_reset_refuses_active_writer_and_stale_navigation(self):
        from unittest.mock import Mock
        self.host.reading_workers['fixture-paper'] = Mock(is_alive=lambda: True, join=lambda **kwargs: None)
        before = (self.workspace / 'state.json').read_bytes()
        with self.assertRaises(WorkspaceError) as caught:
            self.host.clear_source('fixture-paper', {'requestId': uuid.uuid4().hex, 'confirmed': True, 'resetReading': True})
        self.assertEqual('source_busy', caught.exception.error_id)
        self.assertEqual(before, (self.workspace / 'state.json').read_bytes())
        del self.host.reading_workers['fixture-paper']
        old = self.receipt()
        self.host.clear_source('fixture-paper', {'requestId': uuid.uuid4().hex, 'confirmed': True, 'resetReading': True})
        with self.assertRaises(WorkspaceError):
            self.advance(old)
        self.assertFalse(self.host.snapshot()['readingStarted'])

    def test_T7_history_restore_retains_old_reading_events_and_review_can_show_frontier(self):
        self.advance()
        old = self.host.snapshot()
        self.host.new_session({'sessionId': old['sessionId']})
        self.assertEqual([], self.host.snapshot()['timeline'])
        restored = self.host.select_discussion_source('fixture-paper', discussion_id=old['discussionId'])
        self.assertTrue(any(e['kind'] == 'reading' and e['chunk']['chunkId'] == 'chunk-001' for e in restored['timeline']))
        request = uuid.uuid4().hex
        result = self.host.review_chunk('fixture-paper', 'plan-001', 'chunk-002', request)
        count = len(result['timeline'])
        again = self.host.review_chunk('fixture-paper', 'plan-001', 'chunk-002', request)
        self.assertEqual(count, len(again['timeline']))
        self.assertEqual('chunk-002', again['timeline'][-1]['chunk']['chunkId'])

    def test_T17_progress_preparation_and_chat_visible_in_global_work(self):
        self.host.state['run'] = {'runId': 'fake-run', 'status': 'approval', 'sourceId': 'fixture-paper', 'approvals': [], 'error': None}
        work = self.host.snapshot()['workItems']
        self.assertEqual('approval', next(w for w in work if w['kind'] == 'chat')['status'])
        self.host.state['run']['status'] = 'completed'
        self.assertFalse(any(w['kind'] == 'chat' for w in self.host.snapshot()['workItems']))
        self.host.state['run'] = None


class ConfirmedUploadTests(unittest.TestCase):
    import test_stage5_ingestion as single
    setUp = single.SingleIngestionTests.setUp
    tearDown = single.SingleIngestionTests.tearDown
    start_host = single.SingleIngestionTests.start_host
    stop_host = single.SingleIngestionTests.stop_host
    request = single.SingleIngestionTests.request

    def test_T23_T24_parse_only_unclassified_can_attach_and_generate_later(self):
        import time
        from test_html_ingestion import saved_html
        item = self.request('POST', '/library/inbox?name=unclassified.html', saved_html().encode())
        batch = self.request('POST', '/library/batches', {'itemIds': [item['item_id']], 'requestId': uuid.uuid4().hex, 'generateBlog': False})
        self.host.batch_workers[batch['batchId']].join(10)
        batch = self.request('GET', '/library/batches')[0]
        self.assertEqual('completed', batch['status'])
        self.assertEqual([], self.runtime.calls)
        source = self.request('GET', '/library/sources')[0]
        self.assertEqual([], source['topicIds'])
        topic = SourceLibrary(self.host.workspace).create_topic('Later topic')
        self.host.save_source_details(source['sourceId'], {'title': source['title'], 'topicIds': [topic['topicId']], 'requestId': uuid.uuid4().hex})
        self.assertEqual(1, len(self.request('GET', '/library/sources')))
        self.assertEqual([topic['topicId']], self.request('GET', '/library/sources')[0]['topicIds'])
        self.host.blog_generate(source['sourceId'], request_id=uuid.uuid4().hex)
        worker = self.host.blog_workers.get(source['sourceId'])
        if worker: worker.join(10)
        self.assertTrue(self.runtime.calls)

    def test_T25_confirmed_scope_cannot_be_changed_by_replay(self):
        item = self.request('POST', '/library/inbox?name=scope.pdf', b'%PDF scope')
        request_id = uuid.uuid4().hex
        batch = self.request('POST', '/library/batches', {'itemIds': [item['item_id']], 'requestId': request_id, 'generateBlog': False})
        self.host.batch_workers[batch['batchId']].join(10)
        self.request('POST', '/library/batches', {'itemIds': [item['item_id']], 'requestId': request_id, 'generateBlog': True}, expected_status=400)
        self.assertEqual(1, len(self.request('GET', '/library/sources')))
        self.assertEqual([], self.runtime.calls)
