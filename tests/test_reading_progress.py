"""Committed navigation produces durable, separately generated read progress."""
import json
import shutil
import threading
import unittest
import uuid

import reading_fixture
from workspace_fixture import HostService
from core.reading_progress import ReadingProgress
from core.reading_workspace import WorkspaceError
from test_stage4_reading import ReadingRuntimeDouble, PlanningRuntime


class ProgressRuntime:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.entered = threading.Event()
        self.release = threading.Event()
        self.pause = False

    def progress(self, **kwargs):
        self.calls.append(kwargs)
        self.entered.set()
        if self.pause:
            self.release.wait(3)
        if self.fail:
            raise RuntimeError('model unavailable')
        return {'topic': '别名地址的例子'}

    def cancel(self):
        self.release.set()


class ReadingProgressTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reading_fixture.ReadingFixture()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.runtime = ProgressRuntime()
        self.host = HostService(self.workspace, self.fixture.root / 'host',
            reading_runtime=ReadingRuntimeDouble(), progress_runtime=self.runtime)
        self.host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex)
        self.host.reading_workers['fixture-paper'].join(3)
        self.host.open_prepared_reading('fixture-paper', request_id=uuid.uuid4().hex)
        from test_stage4_reading import enter_body
        enter_body(self.host)

    def tearDown(self):
        self.host.close()
        self.fixture.tearDown()

    def receipt(self):
        view = self.host.snapshot()
        return {'sourceId': 'fixture-paper', 'planId': view['current']['planId'],
                'chunkId': view['current']['chunkId'], 'readingRevision': view['readingRevision']}

    def test_continue_and_finish_record_exact_chunks_without_runtime(self):
        first = self.receipt()
        request_id = uuid.uuid4().hex
        result = self.host.continue_cached({'receipt': first, 'requestId': request_id})
        self.host.progress_workers[request_id].join(3)
        entries = self.host.snapshot()['readingProgress']
        self.assertEqual(1, len(entries))
        self.assertEqual(('chunk-001', 1, 'saved', None),
            (entries[0]['chunk_id'], entries[0]['reading_pass'], entries[0]['status'], entries[0]['topic']))
        self.assertEqual([], self.runtime.calls)
        self.host.continue_cached({'receipt': first, 'requestId': request_id})
        self.assertEqual(1, len(self.host.snapshot()['readingProgress']))
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': uuid.uuid4().hex})
        last = self.receipt()
        finish_id = uuid.uuid4().hex
        self.host.finish_reading({'receipt': last, 'requestId': finish_id})
        self.host.progress_workers[finish_id].join(3)
        self.assertEqual('chunk-003', self.host.progress_core.get(finish_id)['chunk_id'])
        self.assertEqual('completed', self.host.snapshot()['status'])
        state = json.loads((self.workspace / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual(request_id, state['reading_progress'][request_id]['trigger_request_id'])
        self.assertEqual(result['readingOperation']['progress_id'], request_id)

    def test_finish_rejects_a_previous_sources_frontier_and_replays_without_an_extra_record(self):
        for _ in range(2):
            self.host.continue_cached({'receipt': self.receipt(), 'requestId': uuid.uuid4().hex})
        view = self.host.snapshot()
        payload = {'receipt': self.receipt(), 'requestId': uuid.uuid4().hex, 'sessionId': view['sessionId']}
        sources = self.workspace / 'sources'
        other = sources / 'fixture-b-paper'
        shutil.copytree(sources / 'fixture-paper', other)
        shutil.rmtree(other / 'reading')
        metadata = json.loads((other / 'source.yaml').read_text(encoding='utf-8'))
        metadata['source_id'] = 'fixture-b-paper'
        (other / 'source.yaml').write_text(json.dumps(metadata), encoding='utf-8')
        self.host.select_discussion_source('fixture-b-paper')

        with self.assertRaisesRegex(WorkspaceError, '阅读位置已改变'):
            self.host.finish_reading(payload)
        self.assertEqual('fixture-b-paper', self.host.snapshot()['source']['sourceId'])
        restored = self.host.open_prepared_reading('fixture-paper', request_id=uuid.uuid4().hex)
        self.assertEqual('chunk-003', restored['navigationCurrent']['chunkId'])
        self.assertEqual(2, len(restored['readingProgress']))

        payload['receipt'] = self.receipt()
        result = self.host.finish_reading(payload)
        self.assertEqual('completed', result['status'])
        self.assertEqual(3, len(result['readingProgress']))
        self.host.select_discussion_source('fixture-b-paper')
        replay = self.host.finish_reading(payload)
        self.assertEqual(result['readingOperation'], replay['readingOperation'])
        self.assertEqual('fixture-b-paper', replay['source']['sourceId'])
        self.host.open_prepared_reading('fixture-paper', request_id=uuid.uuid4().hex)
        with self.assertRaisesRegex(WorkspaceError, '阅读位置已改变'):
            self.host.finish_reading({**payload, 'requestId': uuid.uuid4().hex})
        self.assertEqual(3, len(self.host.snapshot()['readingProgress']))

    def test_failed_generation_retry_does_not_advance_and_edit_fences_late_candidate(self):
        self.runtime.fail = True
        self.host.state['conversation'].extend([
            {'messageId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001', 'reference': {'planId': 'plan-001'}, 'readingPass': 1,
             'role': 'user', 'content': '我理解了别名地址的作用'},
            {'messageId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001', 'reference': {'planId': 'plan-001'}, 'readingPass': 1,
             'role': 'assistant', 'content': '这里有一个例子。'},
        ])
        request_id = uuid.uuid4().hex
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': request_id})
        self.host.progress_workers[request_id].join(3)
        self.assertEqual('failed', self.host.progress_core.get(request_id)['status'])
        current = self.host.snapshot()['current']['chunkId']
        self.runtime.fail = False
        self.runtime.pause = True
        self.runtime.entered.clear()
        self.host.retry_progress(request_id, uuid.uuid4().hex)
        self.assertTrue(self.runtime.entered.wait(3))
        self.host.change_progress(request_id, {'expectedRevision': 1, 'requestId': uuid.uuid4().hex,
            'content': '用户更正的记录'}, 'edit')
        self.runtime.release.set()
        self.host.progress_workers[request_id].join(3)
        entry = self.host.progress_core.get(request_id)
        self.assertEqual(('saved', '用户更正的记录', 2), (entry['status'], entry['topic'], entry['revision']))
        self.assertEqual(current, self.host.snapshot()['current']['chunkId'])

    def test_reread_new_pass_keeps_old_entry_and_delete_cannot_revive(self):
        request_id = uuid.uuid4().hex
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': request_id})
        self.host.progress_workers[request_id].join(3)
        self.host.change_progress(request_id, {'expectedRevision': 1, 'requestId': uuid.uuid4().hex}, 'delete')
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': uuid.uuid4().hex})
        self.host.finish_reading({'receipt': self.receipt(), 'requestId': uuid.uuid4().hex})
        self.host.reread_reading({'receipt': {'sourceId': 'fixture-paper', 'planId': 'plan-001',
            'chunkId': None, 'readingRevision': self.host.snapshot()['readingRevision']},
            'requestId': uuid.uuid4().hex})
        from test_stage4_reading import enter_body
        enter_body(self.host)
        second = uuid.uuid4().hex
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': second})
        self.host.progress_workers[second].join(3)
        self.assertEqual(1, self.host.progress_core.get(request_id)['reading_pass'])
        self.assertTrue(self.host.progress_core.get(request_id)['deleted'])
        self.assertEqual(2, self.host.progress_core.get(second)['reading_pass'])

    def test_restart_keeps_pending_without_automatic_runtime_call(self):
        core = ReadingProgress(self.workspace)
        request_id = uuid.uuid4().hex
        receipt = self.receipt()
        # A process exit immediately after Core's navigation commit has no Host worker.
        self.host.reading_app.continue_reading(source_id=receipt['sourceId'], plan_id=receipt['planId'],
            chunk_id=receipt['chunkId'], reading_revision=receipt['readingRevision'], request_id=request_id)
        self.assertEqual('pending', core.get(request_id)['status'])
        self.host.close()
        self.runtime.calls.clear()
        self.host = HostService(self.workspace, self.fixture.root / 'host',
            reading_runtime=ReadingRuntimeDouble(), progress_runtime=self.runtime)
        self.assertEqual([], self.runtime.calls)
        self.assertEqual('pending', self.host.progress_core.get(request_id)['status'])
        self.host.retry_progress(request_id, uuid.uuid4().hex)
        self.host.progress_workers[request_id].join(3)
        self.assertEqual('saved', self.host.progress_core.get(request_id)['status'])
        self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])

    def test_discussion_from_previous_pass_is_not_reused(self):
        self.host.state['conversation'].extend([
            {'messageId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001',
             'reference': {'planId': 'plan-001'}, 'readingPass': 1, 'role': 'user', 'content': '我理解了旧轮次'},
            {'messageId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001',
             'reference': {'planId': 'plan-001'}, 'readingPass': 1, 'role': 'assistant', 'content': '旧轮次的解释'},
        ])
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': uuid.uuid4().hex})
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': uuid.uuid4().hex})
        self.host.finish_reading({'receipt': self.receipt(), 'requestId': uuid.uuid4().hex})
        self.host.reread_reading({'receipt': {'sourceId': 'fixture-paper', 'planId': 'plan-001',
            'chunkId': None, 'readingRevision': self.host.snapshot()['readingRevision']},
            'requestId': uuid.uuid4().hex})
        from test_stage4_reading import enter_body
        enter_body(self.host)
        second = uuid.uuid4().hex
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': second})
        self.host.progress_workers[second].join(3)
        self.assertIsNone(self.host.progress_core.get(second)['user_understanding'])
        self.assertIsNone(self.host.progress_core.get(second)['topic'])

    def test_cancel_fences_late_progress_candidate(self):
        self.runtime.pause = True
        self.host.state['conversation'].extend([
            {'messageId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001',
             'reference': {'planId': 'plan-001'}, 'readingPass': 1, 'role': 'user', 'content': '解释第一段'},
            {'messageId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001',
             'reference': {'planId': 'plan-001'}, 'readingPass': 1, 'role': 'assistant', 'content': '这里是一个例子'},
        ])
        request_id = uuid.uuid4().hex
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': request_id})
        self.assertTrue(self.runtime.entered.wait(3))
        self.host.cancel_progress(request_id)
        self.runtime.release.set()
        self.host.progress_workers[request_id].join(3)
        entry = self.host.progress_core.get(request_id)
        self.assertEqual('interrupted', entry['status'])
        self.assertIsNone(entry['topic'])
        self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])

    def test_question_about_understanding_is_not_recorded_as_understood(self):
        self.host.state['conversation'].extend([
            {'messageId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001',
             'reference': {'planId': 'plan-001'}, 'readingPass': 1, 'role': 'user', 'content': '我理解了吗？请再举例。'},
            {'messageId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'chunkId': 'chunk-001',
             'reference': {'planId': 'plan-001'}, 'readingPass': 1, 'role': 'assistant', 'content': '这里有另一个例子'},
        ])
        request_id = uuid.uuid4().hex
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': request_id})
        self.host.progress_workers[request_id].join(3)
        self.assertEqual('别名地址的例子', self.host.progress_core.get(request_id)['topic'])
        self.assertIsNone(self.host.progress_core.get(request_id)['user_understanding'])

    def test_new_plan_same_chunk_keeps_prior_plan_progress_queryable(self):
        first_id = uuid.uuid4().hex
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': first_id})
        self.host.progress_workers[first_id].join(3)
        plan_path = self.workspace / 'sources/fixture-paper/reading/plans/plan-001/chunks.jsonl'
        chunks = [json.loads(line) for line in plan_path.read_text(encoding='utf-8').splitlines()]
        draft = {'chunks': [{key: chunk[key] for key in ('section_path', 'source_lines', 'images')}
                            for chunk in chunks], 'glossary': []}
        self.host.reading_app.runtime = PlanningRuntime(draft)
        self.host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex, rebuild=True)
        self.host.reading_workers['fixture-paper'].join(3)
        candidate = self.host.snapshot()['preparations']['fixture-paper']['plan_id']
        self.assertNotEqual('plan-001', candidate)
        self.host.activate_reading_candidate('fixture-paper', {'planId': candidate,
            'readingRevision': self.host.snapshot()['readingRevision'], 'requestId': uuid.uuid4().hex})
        from test_stage4_reading import enter_body
        enter_body(self.host)
        second_id = uuid.uuid4().hex
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': second_id})
        self.host.progress_workers[second_id].join(3)
        self.assertEqual(['chunk-001'], [e['chunk_id'] for e in self.host.progress_core.list('fixture-paper', 'plan-001')])
        self.assertEqual(['chunk-001'], [e['chunk_id'] for e in self.host.progress_core.list('fixture-paper', candidate)])
        self.assertEqual('plan-001', self.host.progress_core.get(first_id)['plan_id'])


if __name__ == '__main__':
    unittest.main()
