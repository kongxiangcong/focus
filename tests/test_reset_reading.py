"""Confirmed reading reset through the public Host boundary."""
import json
from pathlib import Path
import threading
import unittest
import uuid
from unittest.mock import patch

import test_stage4_reading as stage4
from core.reading_workspace import WorkspaceError
from test_source_discussion import CandidateRuntime
from workspace_fixture import HostService


class ResetPlanningRuntime(stage4.PlanningRuntime):
    fail_generation = True

    def plan(self, **kwargs):
        if self.fail_generation:
            raise TimeoutError('Preparation timed out')
        return super().plan(**kwargs)


class DiscussionRuntime(CandidateRuntime):
    def __init__(self, workspace, *, answer, item_id, **kwargs):
        super().__init__(workspace, **kwargs)
        self.answer = answer
        self.item_id = item_id

    def release(self):
        if self.item_id.startswith('answer-') and self.answer.startswith('Archived'):
            self.events.put({'id': 42, 'method': 'tool/call', 'params': {'tool': 'focus', 'arguments': {
                'action': 'cite', 'arguments': json.dumps({'start': 4, 'end': 4, 'quote': 'alias address'})}}})
        else:
            self.complete(self.answer)

    def send(self, response):
        evidence = json.loads(response['result']['text'])
        self.complete(self.answer + ' ' + evidence['marker'])

    def complete(self, answer):
        self.events.put({'method': 'message/completed', 'params': {'itemId': self.item_id, 'text': answer}})
        self.events.put({'method': 'turn/completed', 'params': {'status': 'completed'}})


class DelayedPreparation(stage4.PlanningRuntime):
    def __init__(self, draft):
        super().__init__(draft)
        self.entered = threading.Event()
        self.release = threading.Event()

    def translate(self, **kwargs):
        if not self.entered.is_set():
            self.entered.set()
            if not self.release.wait(8):
                raise TimeoutError('Original preparation was never released')
            return '旧准备的译文'
        return super().translate(**kwargs)


class ResetReadingTests(unittest.TestCase):
    setUp = stage4.Stage4NavigationTests.setUp
    tearDown = stage4.Stage4NavigationTests.tearDown
    receipt = stage4.Stage4NavigationTests.receipt
    rebuild_draft = stage4.Stage4NavigationTests.rebuild_draft

    def test_reset_preserves_source_and_whole_notes_and_enters_a_new_plan(self):
        old = self.host.snapshot()
        receipt = self.receipt()
        self.host.continue_cached({'receipt': receipt, 'requestId': uuid.uuid4().hex})
        self.host.source_note_create('fixture-paper', {'requestId': 'reset-whole-note',
            'kind': 'thought', 'origin': 'user', 'content': 'Keep this whole-source note'})
        self.host.source_note_create('fixture-paper', {'requestId': 'reset-local-note',
            'kind': 'thought', 'origin': 'user', 'content': 'Remove this chunk note',
            'chunk': {'planId': 'plan-001', 'chunkId': 'chunk-001'}})
        selection = {'layer': 'source', 'range': {'start': 0, 'end': 5},
                     'quote': {'exact': 'Alias', 'prefix': '', 'suffix': ''}}
        chunk = {'planId': 'plan-001', 'chunkId': 'chunk-001'}
        self.host.source_note_create('fixture-paper', {'requestId': 'reset-sentence-note',
            'kind': 'thought', 'origin': 'user', 'content': 'Remove this sentence note',
            'chunk': chunk, 'sentence': selection})
        self.host.source_highlight_create('fixture-paper', {
            'requestId': 'reset-highlight', 'chunk': chunk, **selection})
        document = self.host.source_document('fixture-paper')
        markdown = document['markdown']
        cross = {'layer': 'source', 'planId': 'plan-001', 'bundleVersion': document['bundleVersion'],
                 'ranges': [{'start': markdown.index('Figure 1:'), 'end': markdown.index('Relocation') + len('Relocation')}]}
        shared = self.host.source_note_create('fixture-paper', {'requestId': 'reset-shared-note',
            'kind': 'thought', 'origin': 'user', 'content': 'One note across two chunks', 'selection': cross})['noteOperation']['note']
        bookmark = {'readingVersion': 1, 'bundleVersion': document['bundleVersion'], 'line': 1, 'offset': 5}
        self.host.reading_view_bookmark('fixture-paper', payload=bookmark)
        document = self.host.source_document('fixture-paper')
        before = self.host.snapshot()
        runtime = stage4.PlanningRuntime(self.rebuild_draft())
        self.host.reading_app.runtime = runtime
        payload = {'requestId': 'reset-this-source', 'confirmed': True}

        replace = Path.replace

        def corrupt_staging(path, target):
            result = replace(path, target)
            if target.name == 'backup.json':
                (target.parent / 'parser-bundle' / 'content.md').write_text('Incomplete copy', encoding='utf-8')
            return result

        with patch.object(Path, 'replace', corrupt_staging):
            with self.assertRaises(WorkspaceError) as failure:
                self.host.reset_source_reading('fixture-paper', payload)
            self.assertEqual('clear_incomplete', failure.exception.error_id)
        self.assertEqual(before['sourceNotes'], self.host.snapshot()['sourceNotes'])
        self.assertEqual(before['navigationCurrent'], self.host.snapshot()['navigationCurrent'])

        reset = self.host.reset_source_reading('fixture-paper', payload)
        self.host.reading_workers['fixture-paper'].join(3)
        result = self.host.snapshot()

        self.assertNotEqual(old['discussionId'], result['discussionId'])
        self.assertEqual({old['discussionId'], result['discussionId']},
                         {item['discussionId'] for item in result['discussions']})
        self.assertEqual(['Keep this whole-source note'], [note['content'] for note in result['sourceNotes']])
        self.assertNotEqual(before['sourceNotes'][0]['noteId'], result['sourceNotes'][0]['noteId'])
        self.assertEqual([], result['sourceHighlights'])
        self.assertEqual([], result['readingProgress'])
        self.assertEqual([], result['conversation'])
        self.assertTrue(result['readingStarted'])
        self.assertEqual('chunk-001', result['current']['chunkId'])
        self.assertNotEqual('plan-001', result['current']['planId'])
        self.assertEqual(document['markdown'], self.host.source_document('fixture-paper')['markdown'])
        self.assertEqual(document['bundleVersion'], self.host.source_document('fixture-paper')['bundleVersion'])
        backup = self.host.reading_version_backup('fixture-paper', 1)
        self.assertEqual('fixture-paper', backup['sourceId'])
        self.assertEqual(1, backup['readingVersion'])
        self.assertEqual(document['bundleVersion'], backup['bundleVersion'])
        self.assertEqual(reset['clearOperation']['backedUpAt'], backup['backedUpAt'])
        self.assertEqual(document, backup['document'])
        self.assertEqual(before['navigationCurrent'], backup['current'])
        self.assertEqual(before['readingProgress'], backup['readingProgress'])
        self.assertEqual(before['sourceNotes'], backup['sourceNotes'])
        self.assertEqual(before['sourceHighlights'], backup['sourceHighlights'])
        self.assertEqual(['chunk-001', 'chunk-002'], shared['selection']['chunkIds'])
        self.assertEqual([shared], [note for note in backup['sourceNotes'] if note['noteId'] == shared['noteId']])
        self.assertEqual(bookmark, backup['bookmark'])
        self.assertIsNone(self.host.reading_view_bookmark('fixture-paper'))
        with self.assertRaises(WorkspaceError):
            self.host.review_chunk('fixture-paper', 'plan-001', 'chunk-001')
        with self.assertRaises(WorkspaceError):
            self.host.continue_cached({'receipt': receipt, 'requestId': 'late-advance-request'})

        replay = self.host.reset_source_reading('fixture-paper', payload)
        self.assertEqual(result['discussionId'], replay['discussionId'])
        self.assertEqual(result['current'], replay['current'])
        self.assertEqual(1, runtime.calls.count('plan'))

    def test_interrupted_reset_recovers_on_restart_and_retry_keeps_the_new_discussion(self):
        runtimes = []
        old_summary = 'Archived compact discussion context'

        def factory(workspace, *, purpose, **kwargs):
            if purpose == 'candidate':
                return DiscussionRuntime(workspace, answer=json.dumps({'summary': old_summary}), item_id='candidate', **kwargs)
            count = len(runtimes)
            answer = 'Archived answer ' + 'x' * 32000 if count < 3 else 'Fresh answer'
            runtime = DiscussionRuntime(workspace, answer=answer, item_id=f'answer-{count % 3}', **kwargs)
            runtimes.append(runtime)
            return runtime

        runtime = ResetPlanningRuntime(self.rebuild_draft())
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=runtime, backend_factory=factory)
        old = self.host.snapshot()

        def send(view, content, request_id):
            result = self.host.start({'sourceId': 'fixture-paper', 'sessionId': view['sessionId'],
                'discussionId': view['discussionId'], 'requestId': request_id, 'content': content})
            self.host.worker.join(3)
            self.assertFalse(self.host.worker.is_alive())
            return result

        for n in range(3):
            send(old, f'Archived question {n}', f'archived-request-{n}')
        self.assertTrue(old_summary in runtimes[-1].prompt, 'The original discussion has a compacted prefix')
        original = self.host.snapshot()
        evidence = original['conversation'][1]['evidence'][0]
        self.assertEqual('alias address', evidence['quote']['exact'])
        self.assertEqual([4, 4], evidence['sourceLines'])
        self.assertEqual(original['conversation'][1]['answerRevision'], evidence['answerRevision'])
        request = {'requestId': 'interrupted-reset', 'confirmed': True}

        replace = Path.replace
        state = self.workspace / 'state.json'

        def unavailable(path, target):
            if target == state:
                raise OSError('Stop before publishing the backup and new reading version')
            return replace(path, target)

        with patch.object(Path, 'replace', unavailable):
            with self.assertRaises(WorkspaceError) as failure:
                self.host.reset_source_reading('fixture-paper', request)
            self.assertEqual('clear_incomplete', failure.exception.error_id)
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=runtime, backend_factory=factory)
        reopened = self.host.snapshot()
        self.assertEqual(original['discussionId'], reopened['discussionId'])
        self.assertEqual({**original['current'], 'images': []}, {**reopened['current'], 'images': []})
        self.assertEqual(original['conversation'], reopened['conversation'])
        with self.assertRaises(WorkspaceError) as missing:
            self.host.reading_version_backup('fixture-paper', 1)
        self.assertEqual('reading_backup_missing', missing.exception.error_id)
        reset = self.host.reset_source_reading('fixture-paper', request)
        self.assertEqual(2, reset['clearOperation']['readingVersion'])
        self.host.reading_workers['fixture-paper'].join(3)
        failed = self.host.snapshot()
        self.assertEqual('failed', failed['preparations']['fixture-paper']['status'])
        self.assertFalse(failed['readingStarted'])
        self.assertIsNone(failed['current'])
        self.assertEqual([], failed['conversation'])
        self.assertNotEqual(old['discussionId'], failed['discussionId'])
        replay = self.host.reset_source_reading('fixture-paper', request)
        self.assertEqual(failed['discussionId'], replay['discussionId'])
        self.assertEqual(reset['clearOperation'], replay['clearOperation'])
        with self.assertRaises(WorkspaceError):
            send({**failed, 'discussionId': old['discussionId']}, 'Delayed question', 'archived-request-late')
        with self.assertRaises(WorkspaceError):
            self.host.source_note_create('fixture-paper', {'requestId': 'reset-late-note',
                'kind': 'thought', 'origin': 'user', 'content': 'Old annotation',
                'chunk': {'planId': 'plan-001', 'chunkId': 'chunk-001'}})
        with self.assertRaises(WorkspaceError) as waiting:
            send(failed, 'First fresh question', 'fresh-request')
        self.assertEqual('reading_not_ready', waiting.exception.error_id)

        backup = self.host.reading_version_backup('fixture-paper', 1)
        self.assertEqual(original['conversation'], backup['conversation'])
        self.assertEqual(old_summary, backup['discussion']['summary'])
        self.assertIn(backup['discussion']['summaryThrough'], ('answer-0', 'answer-1'))

        runtime.fail_generation = False
        self.host.resume_preparation('fixture-paper', request_id='retry-reset-preparation')
        self.host.reading_workers['fixture-paper'].join(3)
        ready = self.host.snapshot()
        self.assertEqual(failed['discussionId'], ready['discussionId'])
        self.assertEqual('chunk-001', ready['current']['chunkId'])
        self.assertEqual(2, len(ready['discussions']))
        send(ready, 'First fresh question', 'fresh-request')
        fresh_prompt = runtimes[-1].prompt
        self.assertIn('"earlierSummary": "", "recentMessages": []', fresh_prompt)
        self.assertNotIn(old_summary, fresh_prompt)
        self.assertNotIn('Archived question', fresh_prompt)

    def test_running_preparation_cannot_commit_after_confirmed_reset(self):
        runtime = DelayedPreparation(self.rebuild_draft())
        self.host.reading_app.runtime = runtime
        self.host.prepare_reading('fixture-paper', request_id='old-preparation', rebuild=True)
        old_worker = self.host.reading_workers['fixture-paper']
        self.assertTrue(runtime.entered.wait(3))
        old_plan = self.host.snapshot()['preparations']['fixture-paper']['plan_id']
        payload = {'requestId': 'reset-busy-preparation', 'confirmed': True}

        try:
            queued = self.host.reset_source_reading('fixture-paper', payload)
            self.assertEqual('running', queued['preparations']['fixture-paper']['status'])
            self.assertIsNone(queued['preparations']['fixture-paper']['plan_id'])
            self.assertFalse(queued['readingStarted'])
            replay = self.host.reset_source_reading('fixture-paper', payload)
            self.assertEqual(queued['discussionId'], replay['discussionId'])
        finally:
            runtime.release.set()
            old_worker.join(3)
        self.host.reading_workers['fixture-paper'].join(3)
        ready = self.host.snapshot()
        self.assertNotIn(ready['current']['planId'], {'plan-001', old_plan})
        self.assertEqual('已准备的译文', ready['current']['translation'])
        with self.assertRaises(WorkspaceError):
            self.host.review_chunk('fixture-paper', old_plan, 'chunk-001')
