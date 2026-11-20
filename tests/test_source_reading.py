"""Real Core/Host provenance, persistence and source-level opening contracts."""
import json
import queue
import unittest
from pathlib import Path
import reading_fixture
from workspace_fixture import HostService
from core.source_reading import SourceReading
from core.reading_workspace import WorkspaceError
from host.backends.task_tools import discussion_tools, library_tools


class SourceReadingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reading_fixture.ReadingFixture()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.host = HostService(self.workspace, self.fixture.root / 'host')
        self.app = SourceReading(self.workspace)
        self.source = 'fixture-paper'

    def tearDown(self):
        self.host.close()
        self.fixture.tearDown()

    def scope(self):
        return {**self.host.discussion_app.bind(source_id=self.source, request_id='evidence-test-request', content='解释方法'), 'discussionId': 'test-discussion'}

    def test_citation_is_advertised_only_in_source_discussion_tools(self):
        self.assertIn('cite', discussion_tools()[0]['inputSchema']['properties']['action']['enum'])
        self.assertNotIn('cite', library_tools()[0]['inputSchema']['properties']['action']['enum'])

    def test_document_without_plan_and_opening_does_not_change_cursor(self):
        before = (self.workspace / 'state.json').read_bytes()
        doc = self.app.document(self.source)
        class Runtime:
            calls = 0
            def opening(inner, **kwargs):
                inner.calls += 1
                return {'structure': [{'id': 'method', 'parentId': None, 'title': '方法', 'sourceLines': [1, doc['lineCount']]}], 'guide': '本文介绍方法，并说明实验的边界。'}
        runtime = Runtime()
        result = self.app.generate(self.source, runtime)
        self.assertEqual('ready', result['status'])
        self.assertEqual(result, self.app.generate(self.source, runtime))
        self.assertEqual(1, runtime.calls)
        self.assertEqual(before, (self.workspace / 'state.json').read_bytes())

    def test_evidence_rejects_wrong_quote_range_version_and_generation(self):
        scope = self.scope()
        candidate = {'start': 4, 'end': 4, 'quote': 'The alias address keeps source order.'}
        valid = self.app.cite(scope, candidate)
        self.assertEqual(scope['bundle'], valid['bundleVersion'])
        for changed in ({'quote': 'fabricated'}, {'start': 3, 'end': 3}, {'start': True}, {'sourceId': 'other'}):
            with self.subTest(changed=changed), self.assertRaises((ValueError, WorkspaceError)):
                self.app.cite(scope, {**candidate, **changed})
        for changed in ({'bundle': '0' * 64}, {'generation': scope['generation'] + 1}):
            with self.assertRaises(WorkspaceError):
                self.app.cite({**scope, **changed}, candidate)

    def test_host_binds_only_returned_markers_and_persists_revision(self):
        scope = self.scope()
        evidence = self.app.cite(scope, {'start': 4, 'end': 4, 'quote': 'alias address'})
        scope['evidence'] = {evidence['evidenceId']: evidence}
        self.host.active_discussion = scope
        self.host.state['run'] = {'status': 'running', 'activity': []}
        text = '保持顺序。' + evidence['marker'] + ' fake [[e:' + 'f' * 24 + ']]'
        self.host._notification('message/completed', {'itemId': 'answer1', 'text': text})
        message = self.host.state['conversation'][-1]
        self.assertEqual(1, len(message['evidence']))
        self.assertEqual('answer1', message['evidence'][0]['messageId'])
        self.assertEqual(message['answerRevision'], message['evidence'][0]['answerRevision'])
        self.host._notification('message/completed', {'itemId': 'answer1', 'text': '修订后没有引用'})
        self.assertEqual([], message['evidence'])
        self.host.active_discussion = None
        self.host.state['run'] = None

    def test_cancelled_opening_never_publishes(self):
        doc = self.app.document(self.source)
        class Runtime:
            def opening(inner, **kwargs):
                return {'structure': [{'id': 'one', 'parentId': None, 'title': '方法', 'sourceLines': [1, doc['lineCount']]}], 'guide': '文章导读。'}
        with self.assertRaises(WorkspaceError):
            self.app.generate(self.source, Runtime(), stopped=lambda: True)
        self.assertEqual('missing', self.app.opening(self.source)['status'])

    def test_completion_is_idempotent_and_clear_revokes_it_without_advancing_cursor(self):
        doc = self.app.document(self.source)
        before = (self.workspace / 'state.json').read_bytes()
        payload = {'requestId': 'complete-test-request', 'bundleVersion': doc['bundleVersion'], 'generation': doc['generation']}
        saved = self.app.completion(self.source, payload)
        self.assertEqual(saved, self.app.completion(self.source, payload))
        self.assertEqual(before, (self.workspace / 'state.json').read_bytes())
        self.host.source_notes.clear(self.source, request_id='clear-test-request')
        self.assertIsNone(self.app.completion(self.source))
        with self.assertRaises(WorkspaceError):
            self.app.completion(self.source, payload)

    def test_quote_ambiguity_requires_exact_context(self):
        scope = self.scope()
        # The same phrase appears in Method and Runtime in the actual fixture.
        with self.assertRaises(ValueError):
            self.app.cite(scope, {'start': 1, 'end': 12, 'quote': 'alias address'})
        result = self.app.cite(scope, {'start': 1, 'end': 12, 'quote': 'alias address', 'prefix': 'resolves the '})
        self.assertEqual('alias address', result['quote']['exact'])
        self.assertEqual([9, 9], result['sourceLines'])

    def test_runtime_tool_stream_and_restart_keep_evidence_bound(self):
        class Runtime:
            def __init__(inner, *args, **kwargs):
                inner.events = queue.Queue()
            def open_session(inner, *args, **kwargs):
                return 'evidence-session'
            def start_turn(inner, **kwargs):
                inner.events.put({'id': 1, 'method': 'tool/call', 'params': {'tool': 'focus', 'arguments': {
                    'action': 'cite', 'arguments': json.dumps({'start': 4, 'end': 4, 'quote': 'alias address'})}}})
            def send(inner, reply):
                value = json.loads(reply['result']['text'])
                text = '地址顺序。' + value['marker']
                inner.events.put({'method': 'message/delta', 'params': {'itemId': 'runtime-answer', 'delta': text}})
                inner.events.put({'method': 'message/completed', 'params': {'itemId': 'runtime-answer', 'text': text}})
                inner.events.put({'method': 'turn/completed', 'params': {'status': 'completed'}})
            def close(inner):
                pass
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', backend_factory=Runtime)
        selected = self.host.select_discussion_source(self.source)
        self.host.start({'sourceId': self.source, 'sessionId': selected['sessionId'], 'receipt': None,
                         'requestId': 'runtime-evidence-request', 'content': '继续阅读'})
        self.host.worker.join(8)
        self.assertFalse(self.host.worker.is_alive())
        window = self.host.snapshot()
        self.assertEqual('completed', window['agent']['run']['status'])
        evidence = window['conversation'][-1]['evidence']
        self.assertEqual(1, len(evidence))
        self.assertEqual(window['discussionId'], evidence[0]['discussionId'])
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host')
        self.assertEqual(evidence, self.host.snapshot()['conversation'][-1]['evidence'])


if __name__ == '__main__':
    unittest.main()
