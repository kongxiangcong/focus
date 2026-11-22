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

    def test_tool_search_and_range_keep_headers_separate_from_canonical_markdown(self):
        content = self.workspace / 'sources' / self.source / 'parser-bundle' / 'content.md'
        original = '# Result\r\n\r\n**Result** 😀 [detail](https://example.org).\r\n\r\nFinal detail.\r\n\r\n![Architecture](images/image-001.png)\r\n'
        content.write_bytes(original.encode())
        search = self.host.core.tool('search', json.dumps({'source_id': self.source, 'query': 'detail'}))
        first = search['matches'][0]
        self.assertEqual('**Result** 😀 [detail](https://example.org).', first['source_text'])
        block = first['blocks'][0]
        self.assertEqual([3, 3], block['source_lines'])
        self.assertEqual(f"[{block['block_id']} | L3-3]", block['header'])
        by_lines = self.host.core.tool('read_range', json.dumps({'source_id': self.source, 'start': 3, 'end': 3}))
        by_block = self.host.core.tool('read_range', json.dumps({'source_id': self.source, 'block_ids': [block['block_id']]}))
        self.assertEqual(first['source_text'], by_lines['source_text'])
        self.assertEqual(first['source_text'], by_block['source_text'])

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

    def test_block_bound_quotes_are_contiguous_canonical_markdown(self):
        bundle = self.workspace / 'sources' / self.source / 'parser-bundle'
        paragraphs = [
            '# Results', '**Gain** 😀 [details](https://example.org).', '$$x^2$$',
            '| Value |\n| --- |\n| **42** |', '![](images/image-001.png)', 'Figure 1: Throughput.',
        ]
        canonical = '\n\n'.join(paragraphs)
        for newline in ('\r\n', '\n'):
            with self.subTest(newline=repr(newline)):
                (bundle / 'content.md').write_bytes(canonical.replace('\n', newline).encode())
                scope = self.scope()
                read = self.host.discussion_app.candidate(scope, 'read_range', {'start': 1, 'end': 13})
                blocks = {b['source_lines'][0]: b['block_id'] for b in read['blocks']}
                combined = paragraphs[1] + newline * 2 + paragraphs[2]
                evidence = self.app.cite(scope, {'block_ids': [blocks[3], blocks[5]], 'quote': combined})
                self.assertEqual(paragraphs[1] + '\n\n' + paragraphs[2], evidence['quote']['exact'])
                self.assertEqual([3, 5], evidence['sourceLines'])
                self.assertEqual([blocks[3], blocks[5]], evidence['blockIds'])
                self.assertEqual(['section-1'], evidence['sectionIds'])
                self.assertEqual('block', evidence['renderGranularity'])
                for quote, line in ((paragraphs[3], 7), (paragraphs[5], 13)):
                    evidence = self.app.cite(scope, {'block_ids': [blocks[line]], 'quote': quote})
                    self.assertEqual(quote, evidence['quote']['exact'])
                for invalid in (
                    {'start': 3, 'end': 3, 'quote': 'Gain 😀 details.'},
                    {'start': 11, 'end': 11, 'quote': paragraphs[4]},
                    {'start': 11, 'end': 11, 'quote': 'images/image-001.png'},
                    {'block_ids': [blocks[3], blocks[7]], 'quote': '\n\n'.join(paragraphs[1:4])},
                ):
                    with self.assertRaises((ValueError, WorkspaceError)):
                        self.app.cite(scope, invalid)
                sparse = self.host.discussion_app.candidate(scope, 'read_range', {'block_ids': [blocks[3], blocks[7]]})
                self.assertEqual([paragraphs[1], paragraphs[3]], [r['source_text'] for r in sparse['ranges']])

    def test_pdf_block_selection_disambiguates_same_line_and_reports_page(self):
        bundle = self.workspace / 'sources' / self.source / 'parser-bundle'
        (bundle / 'content.md').write_text(
            '# Results\n\nLeft block: result. Right block: result.\n\n![Architecture](images/image-001.png)\n')
        (bundle / 'mineru').mkdir()
        (bundle / 'mineru' / 'middle_json.json').write_text(json.dumps({'pages': [
            {'page_idx': 0, 'blocks': [{'type': 'text', 'index': 0, 'content': 'Left block: result.'}]},
            {'page_idx': 1, 'blocks': [{'type': 'text', 'index': 0, 'content': 'Right block: result.'}]},
        ]}))
        scope = self.scope()
        matches = self.host.discussion_app.candidate(scope, 'search', {'query': 'result.'})['matches']
        self.assertEqual(['[0-0 | p.1 | L3-3]', '[1-0 | p.2 | L3-3]'], [b['header'] for b in matches[1]['blocks']])
        read = self.host.discussion_app.candidate(scope, 'read_range', {'block_ids': ['1-0']})
        self.assertEqual('Right block: result.', read['source_text'])
        evidence = self.app.cite(scope, {'start': 3, 'end': 3, 'block_ids': ['1-0'], 'quote': 'result.'})
        self.assertEqual(['1-0'], evidence['blockIds'])
        self.assertEqual([{'pageIndex': 1, 'pageNumber': 2, 'bboxes': [], 'granularity': 'page'}], evidence['pdfRegions'])
        with self.assertRaises(ValueError):
            self.app.cite(scope, {'block_ids': ['1-0'], 'quote': 'Left block'})

    def test_runtime_tool_stream_and_restart_keep_evidence_bound(self):
        class Runtime:
            def __init__(inner, *args, **kwargs):
                inner.events = queue.Queue()
            def open_session(inner, *args, **kwargs):
                return 'evidence-session'
            def call(inner, request, action, arguments):
                inner.events.put({'id': request, 'method': 'tool/call', 'params': {'tool': 'focus', 'arguments': {
                    'action': action, 'arguments': json.dumps(arguments)}}})
            def start_turn(inner, **kwargs):
                inner.call(1, 'search', {'query': 'alias address'})
            def send(inner, reply):
                value = json.loads(reply['result']['text'])
                if reply['id'] == 1:
                    match = value['matches'][0]
                    passage = next(b['block_id'] for b in match['blocks']
                                   if b['source_lines'][0] <= match['match_line'] <= b['source_lines'][1])
                    inner.call(2, 'read_range', {'block_ids': [passage]})
                    return
                if reply['id'] == 2:
                    inner.call(3, 'cite', {'block_ids': [value['blocks'][0]['block_id']], 'quote': value['source_text']})
                    return
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
        self.assertEqual('The alias address keeps source order.', evidence[0]['quote']['exact'])
        self.assertEqual('runtime-answer', evidence[0]['messageId'])
        self.assertEqual(window['conversation'][-1]['answerRevision'], evidence[0]['answerRevision'])
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host')
        self.assertEqual(evidence, self.host.snapshot()['conversation'][-1]['evidence'])


if __name__ == '__main__':
    unittest.main()
