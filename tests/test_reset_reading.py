"""Confirmed reading reset through the public Host boundary."""
import json
from pathlib import Path
import shutil
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


class DelayedDiscussion(DiscussionRuntime):
    def release(self):
        self.entered.set()


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

    def test_switch_restores_live_rounds_after_host_reopen(self):
        source = 'fixture-paper'
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': 'first-round-advance'})
        self.host.source_note_create(source, {'requestId': 'first-round-note',
            'kind': 'thought', 'origin': 'user', 'content': 'Original note'})
        original_document = self.host.source_document(source)
        markdown = original_document['markdown']
        self.host.source_note_create(source, {'requestId': 'first-round-cross-chunk-note', 'kind': 'thought',
            'origin': 'user', 'content': 'Shared between chunks', 'selection': {'layer': 'source', 'planId': 'plan-001',
                'bundleVersion': original_document['bundleVersion'],
                'ranges': [{'start': markdown.index('Figure 1:'), 'end': markdown.index('Relocation') + len('Relocation')}]}})
        self.host.source_highlight_create(source, {'requestId': 'first-round-highlight',
            'chunk': {'planId': 'plan-001', 'chunkId': 'chunk-001'}, 'layer': 'source',
            'range': {'start': 0, 'end': 5}, 'quote': {'exact': 'Alias', 'prefix': '', 'suffix': ''}})
        original = self.host.snapshot()
        bookmark = {'readingVersion': 1, 'bundleVersion': original_document['bundleVersion'], 'line': 2, 'offset': 5}
        self.host.reading_view_bookmark(source, payload=bookmark)
        runtime = stage4.PlanningRuntime(self.rebuild_draft())
        self.host.reading_app.runtime = runtime
        reset = self.host.reset_source_reading(source, {'requestId': 'two-editable-rounds', 'confirmed': True})
        self.host.reading_workers[source].join(3)
        second = self.host.snapshot()

        self.assertEqual([
            {'readingVersion': 1, 'selected': False, 'ready': True, 'backedUpAt': reset['clearOperation']['backedUpAt']},
            {'readingVersion': 2, 'selected': True, 'ready': True, 'backedUpAt': None},
        ], self.host.list_reading_versions(source))
        note = second['sourceNotes'][0]
        self.host.source_note_change(source, note['noteId'], {'content': 'Updated copy',
            'expectedRevision': note['revision'], 'requestId': 'second-round-edit'}, 'edit')

        first = self.host.switch_reading_version(source, 1)
        self.assertEqual(original['navigationCurrent'], first['navigationCurrent'])
        self.assertEqual(original['readingProgress'], first['readingProgress'])
        self.assertEqual(original['discussionId'], first['discussionId'])
        self.assertEqual(original['sourceNotes'], first['sourceNotes'])
        self.assertEqual(['chunk-001', 'chunk-002'], first['sourceNotes'][1]['selection']['chunkIds'])
        self.assertEqual(original['sourceHighlights'], first['sourceHighlights'])
        self.assertEqual(original['timeline'], first['timeline'])
        self.assertEqual(original_document['translation'], self.host.source_document(source)['translation'])
        self.assertEqual(bookmark, self.host.reading_view_bookmark(source))
        delayed = self.host.source_note_create(source, {'readingVersion': 2, 'requestId': 'late-second-round-note',
            'kind': 'thought', 'origin': 'user', 'content': 'Arrived after switching'})
        self.assertIsNone(delayed['noteOperation'])
        self.assertEqual(original['sourceNotes'], delayed['sourceNotes'])
        self.assertEqual('Arrived after switching', self.host.source_note_request(
            source, 'late-second-round-note', reading_version=2)['note']['content'])
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': 'first-round-resumed'})
        resumed = self.host.snapshot()
        self.assertNotEqual(first['navigationCurrent'], resumed['navigationCurrent'])
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=runtime)
        reopened = self.host.snapshot()
        self.assertEqual(resumed['readingVersion'], reopened['readingVersion'])
        self.assertEqual(resumed['navigationCurrent']['chunkId'], reopened['navigationCurrent']['chunkId'])
        self.assertEqual(original['discussionId'], reopened['discussionId'])
        switched = self.host.switch_reading_version(source, 2)
        self.assertEqual(second['discussionId'], switched['discussionId'])
        self.assertEqual(second['navigationCurrent']['chunkId'], switched['navigationCurrent']['chunkId'])
        self.assertEqual(['Updated copy', 'Arrived after switching'], [note['content'] for note in switched['sourceNotes']])
        self.assertEqual(1, runtime.calls.count('plan'))

    def test_clear_only_erases_the_selected_round(self):
        source = 'fixture-paper'
        runtime = stage4.PlanningRuntime(self.rebuild_draft())
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=runtime,
            backend_factory=lambda workspace, **kwargs: DiscussionRuntime(
                workspace, answer='Archived answer', item_id='answer-before-clear', **kwargs))
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': 'advance-before-clear'})
        self.host.source_note_create(source, {'requestId': 'note-before-clear',
            'kind': 'thought', 'origin': 'user', 'content': 'Keep this prior-round note'})
        first = self.host.snapshot()
        self.host.start({'sourceId': source, 'discussionId': first['discussionId'], 'readingVersion': 1,
                         'requestId': 'first-question-before-clear', 'content': 'Keep this prior-round question'})
        self.host.worker.join(3)
        first = self.host.snapshot()
        self.host.reset_source_reading(source, {'requestId': 'reread-before-clear', 'confirmed': True})
        self.host.reading_workers[source].join(3)
        second = self.host.snapshot()
        self.host.start({'sourceId': source, 'discussionId': second['discussionId'], 'readingVersion': 2,
                         'requestId': 'second-question-before-clear', 'content': 'Clear this current-round question'})
        self.host.worker.join(3)
        cleared = self.host.clear_source(source, {'requestId': 'clear-second-round', 'confirmed': True,
                                                  'resetReading': True})
        self.assertEqual(second['discussionId'], cleared['discussionId'])
        self.assertEqual([], cleared['conversation'])
        self.assertEqual([], cleared['sourceNotes'])
        self.assertEqual([], cleared['readingProgress'])
        prior = self.host.switch_reading_version(source, 1)
        self.assertEqual(first['discussionId'], prior['discussionId'])
        self.assertEqual(first['conversation'], prior['conversation'])
        self.assertEqual(first['sourceNotes'], prior['sourceNotes'])
        self.assertEqual(first['readingProgress'], prior['readingProgress'])
        self.assertEqual(second['discussionId'], self.host.switch_reading_version(source, 2)['discussionId'])

    def test_closed_host_cannot_save_a_bookmark_after_reopen(self):
        source = 'fixture-paper'
        old = self.host
        document = old.source_document(source)
        old.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host')

        bookmark = {'readingVersion': 1, 'bundleVersion': document['bundleVersion'], 'line': 2}
        with self.assertRaises(WorkspaceError) as expired:
            old.reading_view_bookmark(source, payload=bookmark)
        self.assertEqual('workspace_instance_expired', expired.exception.error_id)
        self.assertIsNone(self.host.reading_view_bookmark(source))

    def test_reset_from_library_backs_up_the_sources_saved_structure(self):
        source = 'fixture-paper'
        structure = self.host.snapshot()['structure']
        self.assertTrue(structure)
        self.host.close()
        second = self.workspace / 'sources/second-paper'
        shutil.copytree(self.workspace / 'sources/fixture-paper', second)
        metadata = second / 'source.yaml'
        value = json.loads(metadata.read_text(encoding='utf-8'))
        metadata.write_text(json.dumps({**value, 'source_id': 'second-paper', 'identity': 'fixture:second'}), encoding='utf-8')
        state_path = self.workspace / 'state.json'
        state = json.loads(state_path.read_text(encoding='utf-8'))
        state['sources']['second-paper'] = dict(state['sources'][source])
        state_path.write_text(json.dumps(state), encoding='utf-8')

        runtime = stage4.PlanningRuntime(self.rebuild_draft())
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=runtime)
        self.host.open_prepared_reading('second-paper', request_id='open-while-resetting-another')
        reset = self.host.reset_source_reading(source, {'requestId': 'reread-from-library', 'confirmed': True})
        self.host.reading_workers[source].join(3)
        self.assertEqual('second-paper', reset['source']['sourceId'])
        backup = self.host.reading_version_backup(source, 1)
        self.assertEqual(structure, backup['structure'])
        self.assertEqual('chunk-001', backup['current']['chunkId'])

    def test_reopens_and_continues_a_round_after_the_parser_bundle_changes(self):
        source = 'fixture-paper'
        view = self.host.snapshot()
        old_document = self.host.source_document(source)
        self.host.reading_app.runtime = stage4.PlanningRuntime(self.rebuild_draft())
        self.host.reset_source_reading(source, {'requestId': 'first-reset-before-reparse', 'confirmed': True})
        self.host.reading_workers[source].join(3)
        self.host.close()
        path = self.workspace / 'sources/fixture-paper/parser-bundle/content.md'
        path.write_text(path.read_text(encoding='utf-8').replace(
            'The alias address keeps source order.', 'The replacement label keeps source order.'), encoding='utf-8')
        runtime = stage4.PlanningRuntime(self.rebuild_draft())
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=runtime,
            backend_factory=lambda workspace, **kwargs: DiscussionRuntime(
                workspace, answer='Archived answer', item_id='answer-old-bundle', **kwargs))

        self.assertTrue(self.host.list_reading_versions(source)[0]['ready'])
        first = self.host.switch_reading_version(source, 1)
        self.assertEqual(view['discussionId'], first['discussionId'])
        for key in ('planId', 'chunkId', 'sourceMarkdown', 'translation'):
            self.assertEqual(view['current'][key], first['current'][key])
        self.assertIn(f"/{old_document['bundleVersion']}/", first['current']['images'][0]['src'])
        document = self.host.source_document(source)
        self.assertEqual(old_document['markdown'], document['markdown'])
        self.assertEqual(old_document['translation'], document['translation'])
        self.assertEqual(document['bundleVersion'], first['sourceBundleVersion'])

        note = self.host.source_note_create(source, {'requestId': 'archived-bundle-note', 'readingVersion': 1,
            'kind': 'thought', 'origin': 'user', 'content': 'Saved against the original text',
            'chunk': {'planId': 'plan-001', 'chunkId': 'chunk-001'}, 'quote': 'alias address'})
        self.assertEqual('current', note['sourceNotes'][0]['referenceStatus'])
        self.host.start({'sourceId': source, 'discussionId': first['discussionId'], 'readingVersion': 1,
                         'requestId': 'archived-bundle-question', 'content': 'Cite the original alias wording'})
        self.host.worker.join(3)
        followed_up = self.host.snapshot()
        self.assertEqual(document['bundleVersion'], followed_up['conversation'][-1]['evidence'][0]['bundleVersion'])
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': 'advance-archived-bundle'})
        self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])
        self.host.reset_source_reading(source, {'requestId': 'newest-bundle-reset', 'confirmed': True})
        self.host.reading_workers[source].join(3)
        latest = self.host.source_document(source)
        self.assertIn('replacement label', latest['markdown'])
        self.assertNotEqual(document['bundleVersion'], latest['bundleVersion'])
        self.assertEqual(3, latest['readingVersion'])
        self.assertEqual(['Saved against the original text'],
                         [item['content'] for item in self.host.switch_reading_version(source, 1)['sourceNotes']])

    def test_switch_while_new_round_is_translating_preserves_both_rounds(self):
        source = 'fixture-paper'
        before = self.host.snapshot()
        original = self.host.source_document(source)['translation']
        runtime = DelayedPreparation(self.rebuild_draft())
        self.host.reading_app.runtime = runtime
        self.host.reset_source_reading(source, {'requestId': 'reset-delayed-translation', 'confirmed': True})
        worker = self.host.reading_workers[source]
        try:
            self.assertTrue(runtime.entered.wait(3))
            first = self.host.switch_reading_version(source, 1)
            self.assertEqual(before['discussionId'], first['discussionId'])
            self.assertEqual(before['current'], first['current'])
        finally:
            runtime.release.set()
            worker.join(3)
        first = self.host.snapshot()
        self.assertEqual(1, first['readingVersion'])
        self.assertEqual(before['current'], first['current'])
        self.assertEqual(original, self.host.source_document(source)['translation'])
        self.assertTrue(self.host.list_reading_versions(source)[1]['ready'])
        second = self.host.switch_reading_version(source, 2)
        self.assertEqual('旧准备的译文', second['current']['translation'])
        self.assertEqual(1, runtime.calls.count('plan'))

    def test_ready_prior_round_can_be_selected_when_rereading_failed(self):
        source = 'fixture-paper'
        old = self.host.snapshot()
        runtime = ResetPlanningRuntime(self.rebuild_draft())
        self.host.reading_app.runtime = runtime
        self.host.reset_source_reading(source, {'requestId': 'reset-failing-round', 'confirmed': True})
        self.host.reading_workers[source].join(3)
        versions = self.host.list_reading_versions(source)
        self.assertFalse(versions[1]['ready'])
        self.assertTrue(versions[1]['selected'])
        restored = self.host.switch_reading_version(source, 1)
        self.assertEqual(old['current'], restored['current'])
        self.assertEqual(old['discussionId'], restored['discussionId'])
        self.assertTrue(restored['preparations'][source]['ready'])
        with self.assertRaises(WorkspaceError) as unavailable:
            self.host.switch_reading_version(source, 2)
        self.assertEqual('reading_not_ready', unavailable.exception.error_id)
        self.assertEqual(1, self.host.snapshot()['readingVersion'])

    def test_switch_while_answer_is_pending_preserves_original_discussion(self):
        source = 'fixture-paper'
        runtime = stage4.PlanningRuntime(self.rebuild_draft())
        started = threading.Event()
        discussions = []

        def factory(workspace, **kwargs):
            if len(discussions) == 1:
                backend = DelayedDiscussion(workspace, answer='Archived answer', item_id='answer-delayed', **kwargs)
                backend.entered = started
            else:
                backend = DiscussionRuntime(workspace, answer='Archived answer', item_id=f'answer-{len(discussions)}', **kwargs)
            discussions.append(backend)
            return backend

        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=runtime, backend_factory=factory)
        before = self.host.snapshot()

        def send(view, content, request_id):
            self.host.start({'sourceId': source, 'sessionId': view['sessionId'], 'discussionId': view['discussionId'],
                             'requestId': request_id, 'content': content})

        send(before, 'Original question', 'first-round-original-question')
        self.host.worker.join(3)
        archived = self.host.snapshot()
        evidence = archived['conversation'][1]['evidence'][0]
        self.host.reset_source_reading(source, {'requestId': 'reset-after-original-answer', 'confirmed': True})
        self.host.reading_workers[source].join(3)
        second = self.host.snapshot()
        first = self.host.switch_reading_version(source, 1)
        self.assertEqual(archived['conversation'], first['conversation'])
        send(first, 'Follow-up question', 'first-round-follow-up')
        self.assertTrue(started.wait(3))
        self.assertIn('Original question', discussions[-1].prompt)
        try:
            alternate = self.host.switch_reading_version(source, 2)
            self.assertEqual(second['discussionId'], alternate['discussionId'])
            self.assertIsNone(alternate['agent']['run'])
            self.assertEqual([], alternate['conversation'])
        finally:
            DiscussionRuntime.release(discussions[-1])
            self.host.worker.join(3)
        alternate = self.host.snapshot()
        self.assertEqual([], alternate['conversation'])
        first = self.host.switch_reading_version(source, 1)
        self.assertEqual(['Original question', 'Follow-up question'],
                         [message['content'] for message in first['conversation'] if message['role'] == 'user'])
        self.assertEqual(evidence, first['conversation'][1]['evidence'][0])
        self.assertEqual('alias address', first['conversation'][-1]['evidence'][0]['quote']['exact'])

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

    def test_rereading_the_first_round_replaces_its_backup_only_after_success(self):
        source = 'fixture-paper'
        runtime = stage4.PlanningRuntime(self.rebuild_draft())
        self.host.reading_app.runtime = runtime
        monday = 1795392000
        friday = 1795737600
        self.host.clock = lambda: monday
        self.host.source_note_create(source, {'requestId': 'monday-note', 'kind': 'thought',
            'origin': 'user', 'content': 'Monday interpretation'})
        first = self.host.snapshot()
        first_request = {'requestId': 'monday-reread', 'confirmed': True, 'readingVersion': 1}
        self.host.reset_source_reading(source, first_request)
        self.host.reading_workers[source].join(3)
        monday_backup = self.host.reading_version_backup(source, 1)
        self.assertEqual(monday * 1000, monday_backup['backedUpAt'])
        self.assertEqual(['Monday interpretation'], [note['content'] for note in monday_backup['sourceNotes']])

        self.host.source_note_create(source, {'requestId': 'second-round-only-note', 'kind': 'thought',
            'origin': 'user', 'content': 'Second round only'})
        self.host.continue_cached({'receipt': self.receipt(), 'requestId': 'second-round-progress'})
        second = self.host.snapshot()
        self.host.switch_reading_version(source, 1)
        note = first['sourceNotes'][0]
        self.host.source_note_change(source, note['noteId'], {'content': 'Friday interpretation',
            'expectedRevision': note['revision'], 'requestId': 'friday-edit'}, 'edit')
        friday_state = self.host.snapshot()
        self.host.clock = lambda: friday
        request = {'requestId': 'friday-reread', 'confirmed': True, 'readingVersion': 1}
        replace = Path.replace
        state = self.workspace / 'state.json'

        def interrupt_replacement(path, target):
            if target == state:
                raise OSError('Stop before publishing the replacement backup')
            return replace(path, target)

        with patch.object(Path, 'replace', interrupt_replacement):
            with self.assertRaises(WorkspaceError) as failure:
                self.host.reset_source_reading(source, request)
            self.assertEqual('clear_incomplete', failure.exception.error_id)
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=runtime, clock=lambda: friday)
        self.assertEqual(1, self.host.snapshot()['readingVersion'])
        self.assertEqual(friday_state['navigationCurrent']['planId'], self.receipt()['planId'])
        self.assertEqual(friday_state['navigationCurrent']['chunkId'], self.receipt()['chunkId'])
        self.assertEqual(friday_state['sourceNotes'], self.host.snapshot()['sourceNotes'])
        preserved_backup = self.host.reading_version_backup(source, 1)
        for field in ('sourceId', 'readingVersion', 'bundleVersion', 'backedUpAt', 'sourceNotes', 'cursor', 'conversation'):
            self.assertEqual(monday_backup[field], preserved_backup[field])
        self.assertEqual([monday * 1000, None], [item['backedUpAt'] for item in self.host.list_reading_versions(source)])

        reset = self.host.reset_source_reading(source, request)
        self.host.reading_workers[source].join(3)
        third = self.host.snapshot()
        self.assertEqual(3, third['readingVersion'])
        self.assertEqual([], third['readingProgress'])
        self.assertEqual([], third['conversation'])
        self.assertEqual('chunk-001', third['navigationCurrent']['chunkId'])
        self.assertEqual(['Friday interpretation'], [note['content'] for note in third['sourceNotes']])
        self.assertNotEqual(note['noteId'], third['sourceNotes'][0]['noteId'])
        friday_backup = self.host.reading_version_backup(source, 1)
        self.assertEqual(friday * 1000, friday_backup['backedUpAt'])
        self.assertEqual(friday_state['sourceNotes'], friday_backup['sourceNotes'])
        self.assertEqual(first['discussionId'], friday_backup['discussionId'])
        self.assertEqual([
            {'readingVersion': 1, 'ready': True, 'selected': False, 'backedUpAt': friday * 1000},
            {'readingVersion': 2, 'ready': True, 'selected': False, 'backedUpAt': None},
            {'readingVersion': 3, 'ready': True, 'selected': True, 'backedUpAt': None},
        ], self.host.list_reading_versions(source))

        self.host.switch_reading_version(source, 2)
        replay = self.host.reset_source_reading(source, request)
        self.assertEqual(reset['clearOperation'], replay['clearOperation'])
        self.assertEqual(2, replay['readingVersion'])
        for field in ('discussionId', 'navigationCurrent', 'readingProgress', 'sourceNotes'):
            self.assertEqual(second[field], replay[field])
        original_replay = self.host.reset_source_reading(source, first_request)
        self.assertEqual(2, original_replay['clearOperation']['readingVersion'])
        self.assertEqual(2, original_replay['readingVersion'])
        self.assertEqual(friday_backup, self.host.reading_version_backup(source, 1))
        self.assertEqual([1, 2, 3], [item['readingVersion'] for item in self.host.list_reading_versions(source)])
        self.assertEqual(2, runtime.calls.count('plan'))

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

        # An updated parser must not change the recovered text or evidence ranges of the saved round.
        source = 'fixture-paper'
        content = self.workspace / 'sources' / source / 'parser-bundle' / 'content.md'
        content.write_text('Updated source text.\n' + content.read_text(encoding='utf-8'), encoding='utf-8')
        self.assertEqual(backup['bundleVersion'], self.host.source_document(source)['bundleVersion'])
        recovery = self.host.reading_version_backup(source, 1)
        self.assertEqual(backup['document'], recovery['document'])
        self.assertEqual(evidence, recovery['conversation'][1]['evidence'][0])
        start, end = evidence['sourceLines']
        restored_lines = recovery['document']['markdown'].splitlines()[start - 1:end]
        self.assertEqual(1, '\n'.join(restored_lines).count(evidence['quote']['exact']))

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
