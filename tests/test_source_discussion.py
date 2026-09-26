"""Host discussion exercises the public snapshot/start boundary with real Core."""
import json
import queue
import shutil
import threading
import unittest
from pathlib import Path

import test_focus_read
from core.source_library import SourceLibrary
from core.reading_workspace import _read_document, _write_document
from core.reading_workspace import WorkspaceError
from host.service import HostService
from host.core_bridge import TOOL


class CandidateRuntime:
    def __init__(self, workspace, *, paused=False, **kwargs):
        self.events = queue.Queue()
        self.closed = False
        self.replies = []
        self.paused = paused

    def open_session(self, resume_key, *, instructions, skills=()):
        return "discussion-thread"

    def start_turn(self, *, prompt, skills=()):
        if not self.paused:
            self.release()

    def release(self):
        # A real model can only select actions advertised by the backend schema.
        if 'source_note' not in TOOL['inputSchema']['properties']['action']['enum']:
            self.events.put({'method': 'turn/completed', 'params': {'status': 'completed'}})
            return
        self.events.put({'id': 42, 'method': 'tool/call', 'params': {'tool': 'focus', 'arguments': {
            'action': 'source_note', 'arguments': json.dumps({'content': 'An example and conclusion.',
                'kind': 'conclusion', 'origin': 'dialogue', 'evidence_role': 'explanation'})}}})

    def send(self, message):
        self.replies.append(message)
        self.events.put({'method': 'turn/completed', 'params': {'status': 'completed'}})

    def close(self):
        self.closed = True

    def interrupt(self):
        self.events.put({'method': 'turn/completed', 'params': {'status': 'interrupted'}})


class DiscussionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_focus_read.FocusReadTests()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        old = self.workspace / 'sources' / 'fixture-paper'
        other = self.workspace / 'sources' / 'fixture-b-paper'
        shutil.copytree(old, other)
        source = _read_document(other / 'source.yaml')
        source.update(source_id='fixture-b-paper', title='Fixture B', identity='fixture:b')
        _write_document(other / 'source.yaml', source)
        state_path = self.workspace / 'state.json'
        state = _read_document(state_path)
        state['sources']['fixture-b-paper'] = {'current_plan_id': None, 'current_chunk_id': None}
        _write_document(state_path, state)
        SourceLibrary(self.workspace).unselect_plan('fixture-paper')
        self.runtime = None
        self.runtime_ready = threading.Event()
        self.pause_runtime = False

        def factory(workspace, **kwargs):
            self.runtime = CandidateRuntime(workspace, paused=self.pause_runtime, **kwargs)
            self.runtime_ready.set()
            return self.runtime

        self.host = HostService(self.workspace, self.fixture.root / 'host', backend_factory=factory)

    def tearDown(self):
        self.host.close()
        self.fixture.tearDown()

    def test_no_plan_discussion_saves_only_explicit_note_and_replays(self):
        selected = self.host.select_discussion_source('fixture-paper')
        self.assertEqual('fixture-paper', selected['source']['sourceId'])
        self.assertIsNone(selected['current'])
        self.host.start({'requestId': 'request-1234', 'sourceId': 'fixture-paper',
                         'sessionId': selected['sessionId'], 'receipt': None, 'content': '请记下来'})
        self.host.worker.join(3)
        self.assertFalse(self.host.worker.is_alive())
        notes = self.host.snapshot()['sourceNotes']
        self.assertEqual(1, len(notes))
        self.assertEqual('An example and conclusion.', notes[0]['content'])
        self.assertEqual('completed', self.host.snapshot()['agent']['run']['status'])
        self.host.start({'requestId': 'request-1234', 'sourceId': 'fixture-paper',
                         'sessionId': selected['sessionId'], 'receipt': None, 'content': '请记下来'})
        self.assertEqual(1, len(self.host.snapshot()['sourceNotes']))
        with self.assertRaises(ValueError):
            self.host.start({'requestId': 'request-1234', 'sourceId': 'fixture-paper',
                             'sessionId': selected['sessionId'], 'receipt': None, 'content': '改成另一条，记下来'})

    def test_model_tool_call_without_user_intent_cannot_save(self):
        selected = self.host.select_discussion_source('fixture-paper')
        self.host.start({'requestId': 'request-4321', 'sourceId': 'fixture-paper',
                         'sessionId': selected['sessionId'], 'receipt': None, 'content': '解释这个概念'})
        self.host.worker.join(3)
        self.assertEqual([], self.host.snapshot()['sourceNotes'])
        self.assertFalse(self.runtime.replies[0]['result']['success'])

    def test_switching_source_during_answer_does_not_rebind_save(self):
        self.pause_runtime = True
        a = self.host.select_discussion_source('fixture-paper')
        self.host.start({'requestId': 'request-a123', 'sourceId': 'fixture-paper',
                         'sessionId': a['sessionId'], 'receipt': None, 'content': '记下来'})
        b = self.host.select_discussion_source('fixture-b-paper')
        self.assertEqual([], b['sourceNotes'])
        self.assertTrue(self.runtime_ready.wait(3))
        self.runtime.release()
        self.host.worker.join(3)
        self.assertEqual([], self.host.snapshot()['sourceNotes'])
        self.assertEqual([], self.host.snapshot()['conversation'])
        self.host.start({'requestId': 'request-a123', 'sourceId': 'fixture-paper',
                         'sessionId': a['sessionId'], 'receipt': None, 'content': '记下来'})
        self.assertEqual([], self.host.snapshot()['sourceNotes'])
        a = self.host.select_discussion_source('fixture-paper')
        self.assertEqual(1, len(a['sourceNotes']))
        self.assertEqual('fixture-paper', a['conversation'][0]['sourceId'])

    def test_scoped_search_read_and_cancelled_candidate(self):
        app = self.host.discussion_app
        scope = app.bind(source_id='fixture-paper', request_id='request-scope', content='请记下来')
        match = app.candidate(scope, 'search', {'query': 'alias'})
        self.assertEqual('fixture-paper', match['source_id'])
        read = app.candidate(scope, 'read_range', {'start': 3, 'end': 4})
        self.assertIn('alias address', read['source_text'])
        for action, args in [('search', {'query': 'alias', 'source_id': 'fixture-b-paper'}),
                             ('read_range', {'start': 1, 'end': 2, 'bundle_version': 'wrong'})]:
            with self.assertRaises(WorkspaceError) as caught:
                app.candidate(scope, action, args)
            self.assertEqual('source_scope_invalid', caught.exception.error_id)
        app.cancel(scope)
        with self.assertRaises(WorkspaceError) as caught:
            app.candidate(scope, 'source_note', {'content': 'Late', 'kind': 'thought', 'origin': 'dialogue', 'evidence_role': 'explanation'})
        self.assertEqual('note_cancelled', caught.exception.error_id)
        self.assertEqual([], app.notes.list('fixture-paper'))

    def test_negative_note_request_is_not_authorization(self):
        scope = self.host.discussion_app.bind(source_id='fixture-paper', request_id='request-negate',
                                               content='先不要记下来，只解释')
        self.assertFalse(scope['saveIntent'])
        positive = self.host.discussion_app.bind(source_id='fixture-paper', request_id='request-pos123',
                                                 content='把别名地址的结论记下来')
        self.assertTrue(positive['saveIntent'])

    def test_host_note_edit_conflict_delete_and_reopen_undo(self):
        selected = self.host.select_discussion_source('fixture-paper')
        self.host.start({'requestId': 'request-edit', 'sourceId': 'fixture-paper',
                         'sessionId': selected['sessionId'], 'receipt': None, 'content': '记下来'})
        self.host.worker.join(3)
        note = self.host.snapshot()['sourceNotes'][0]
        changed = self.host.source_note_change('fixture-paper', note['noteId'],
            {'requestId': 'edit-host1', 'expectedRevision': 1, 'content': 'My correction'}, 'edit')
        self.assertEqual('My correction', changed['sourceNotes'][0]['content'])
        conflict = self.host.source_note_change('fixture-paper', note['noteId'],
            {'requestId': 'edit-host2', 'expectedRevision': 1, 'content': 'Unsaved input'}, 'edit')
        self.assertEqual('conflict', conflict['noteOperation']['status'])
        self.assertEqual('Unsaved input', conflict['noteOperation']['attemptedContent'])
        self.assertEqual('My correction', conflict['noteOperation']['current']['content'])
        self.assertEqual(conflict['noteOperation']['attemptedContent'],
                         self.host.source_note_request('fixture-paper', 'edit-host2')['attemptedContent'])
        self.host.source_note_change('fixture-paper', note['noteId'],
            {'requestId': 'delete-h1', 'expectedRevision': 2}, 'delete')
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', backend_factory=lambda workspace, **kwargs: CandidateRuntime(workspace, **kwargs))
        reopened = self.host.select_discussion_source('fixture-paper')
        self.assertTrue(reopened['sourceNotes'][0]['deleted'])
        restored = self.host.source_note_change('fixture-paper', note['noteId'],
            {'requestId': 'undo-host1', 'expectedRevision': 3}, 'undo')
        self.assertEqual('My correction', restored['sourceNotes'][0]['content'])
        self.assertEqual(4, restored['sourceNotes'][0]['revision'])


if __name__ == '__main__':
    unittest.main()
