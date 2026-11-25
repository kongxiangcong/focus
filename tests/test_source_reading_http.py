"""Local HTTP boundary for the unified reader; no model or Internet required."""
from contextlib import closing, contextmanager
from functools import partial
import hashlib
import http.client
import json
import queue
import shutil
import threading
import time
import unittest
import reading_fixture
from core.workspace_lifecycle import WorkspaceLease
from host.server import Server
from host.store import Store
from workspace_fixture import HostService, publish_workspace


class LineCitationRuntime:
    def __init__(self, *args, answer_id='new-answer', **kwargs):
        self.events = queue.Queue()
        self.answer_id = answer_id

    def open_session(self, *args, **kwargs):
        return 'legacy-discussion-session'

    def call(self, call_id, action, arguments):
        self.events.put({'id': call_id, 'method': 'tool/call', 'params': {'tool': 'focus', 'arguments': {
            'action': action, 'arguments': json.dumps(arguments)}}})

    def start_turn(self, **kwargs):
        self.call(1, 'read_range', {'start': 4, 'end': 4})

    def send(self, reply):
        result = reply['result']
        if not result['success']:
            self.events.put({'method': 'turn/completed', 'params': {'status': 'failed', 'error': result['text']}})
            return
        value = json.loads(result['text'])
        if reply['id'] == 1:
            self.call(2, 'cite', {'start': 4, 'end': 4, 'quote': value['source_text']})
            return
        self.events.put({'method': 'message/completed', 'params': {
            'itemId': self.answer_id, 'text': '固定别名保持源顺序。' + value['marker']}})
        self.events.put({'method': 'turn/completed', 'params': {'status': 'completed'}})

    def close(self):
        pass


class SourceReadingHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reading_fixture.ReadingFixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.workspace, self.source_root, _ = self.fixture._workspace()

    @contextmanager
    def serve(self, **kwargs):
        with closing(HostService(self.workspace, self.fixture.root / 'host', **kwargs)) as host, \
                Server(('127.0.0.1', 0), host) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                yield server.server_port
            finally:
                server.shutdown()
                worker.join(5)

    def request(self, port, path, payload=None):
        with closing(http.client.HTTPConnection('127.0.0.1', port, timeout=5)) as connection:
            connection.request('GET' if payload is None else 'POST', path,
                               body=None if payload is None else json.dumps(payload),
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, response.read()

    def value(self, port, path, payload=None):
        status, body = self.request(port, path, payload)
        self.assertEqual(200, status, body.decode())
        return json.loads(body)['value']

    def continue_discussion(self, port, session_id, request_id):
        self.value(port, '/reader/messages', {'requestId': request_id, 'sourceId': 'fixture-paper',
                                              'sessionId': session_id, 'receipt': None, 'content': '为什么要固定别名？'})
        deadline = time.monotonic() + 5
        while True:
            window = self.value(port, '/reader/window')
            run = window['agent']['run']
            if run is None or run['status'] != 'running' or time.monotonic() >= deadline:
                self.assertIsNone(run)
                return window
            time.sleep(.01)

    def test_document_completion_and_version_bound_images(self):
        with self.serve() as port:
            doc = self.value(port, '/library/sources/fixture-paper/document')
            self.assertIn('The alias address', doc['markdown'])
            image = '/reader/assets/fixture-paper/images/image-001.png?bundle='
            self.assertEqual((200, b'image'), self.request(port, image + doc['bundleVersion']))
            self.assertEqual(400, self.request(port, image + '0' * 64)[0])
            before = (self.workspace / 'state.json').read_bytes()
            recorded = self.value(port, '/library/sources/fixture-paper/completion', {
                'requestId': 'http-complete-test', 'bundleVersion': doc['bundleVersion'], 'generation': doc['generation']})
            self.assertNotIn('sourceCompletion', recorded)
            self.assertNotIn('sourceCompletion', self.value(port, '/reader/window'))
            self.assertEqual(before, (self.workspace / 'state.json').read_bytes())

    def test_original_and_figure_requests_resolve_the_requested_bundle(self):
        with self.serve() as port:
            source = '/library/sources/fixture-paper'
            bundle = self.source_root / 'parser-bundle'
            old = self.value(port, source + '/document')['bundleVersion']
            archived = self.source_root / 'reading' / 'bundles' / old
            original = (bundle / 'source.pdf').read_bytes()
            shutil.copytree(bundle, archived)
            (bundle / 'source.pdf').write_bytes(b'%PDF updated fixture')
            (bundle / 'images/image-001.png').write_bytes(b'updated image')

            self.assertEqual((200, original), self.request(port,
                f"{source}/original?bundle={old}&pdfHash={hashlib.sha256(original).hexdigest()}"))
            self.assertEqual((200, b'%PDF updated fixture'), self.request(port, source + '/original'))
            image = '/reader/assets/fixture-paper/images/image-001.png'
            self.assertEqual((200, b'image'), self.request(port, f'{image}?bundle={old}'))
            self.assertEqual((200, b'updated image'), self.request(port, image))

    def test_legacy_discussion_can_append_line_citations_without_rewriting_the_bundle(self):
        from pypdf import PdfWriter

        source_url = '/library/sources/fixture-paper'
        passage = 'The alias address keeps source order.'
        legacy_text = f'旧回答引用了论文中的这句话：\n\n> {passage}'
        publish_workspace(self.workspace)
        with closing(WorkspaceLease(self.workspace)), closing(Store(self.workspace / 'discussions', self.workspace)) as store:
            store.state['conversation'].append({'messageId': 'legacy-answer', 'chunkId': '', 'role': 'assistant',
                                                'sourceId': 'fixture-paper', 'content': legacy_text})
            store.state['timeline'].append({'kind': 'message', 'messageId': 'legacy-answer'})
            store.save()

        bundle = self.source_root / 'parser-bundle'
        pdf = PdfWriter()
        pdf.add_blank_page(612, 792)
        pdf.write(bundle / 'source.pdf')
        marker_box = [0.13, 0.25, 0.47, 0.33]
        old_sidecar = bundle / 'mineru' / 'middle_json.json'
        old_sidecar.parent.mkdir()
        old_sidecar.write_text(json.dumps({'pages': [{'page_idx': 0, 'blocks': [
            {'index': 0, 'type': 'text', 'content': passage, 'bbox': marker_box},
        ]}]}), encoding='utf-8')

        def bundle_files():
            return {path.relative_to(bundle): (path.stat().st_mtime_ns, path.read_bytes())
                    for path in bundle.rglob('*') if path.is_file()}

        before = bundle_files()
        with self.serve(backend_factory=LineCitationRuntime) as port:
            doc = self.value(port, source_url + '/document')
            self.assertIn(passage, doc['markdown'])
            history = self.value(port, source_url + '/discuss', {})
            old_answer, = history['conversation']
            self.assertEqual(legacy_text, old_answer['content'])
            self.assertFalse(old_answer.get('evidence'))
            window = self.continue_discussion(port, history['sessionId'], 'continue-legacy-discussion')
            old_answer, question, answer = window['conversation']
            self.assertEqual(legacy_text, old_answer['content'])
            self.assertEqual('为什么要固定别名？', question['content'])
            self.assertEqual('new-answer', answer['messageId'])
            evidence, = answer['evidence']
            self.assertEqual(passage, evidence['quote']['exact'])
            self.assertEqual([4, 4], evidence['sourceLines'])
            self.assertEqual(doc['bundleVersion'], evidence['bundleVersion'])
            self.assertEqual(doc['pdf']['version'], evidence['layoutVersion'])
            self.assertEqual([{'pageIndex': 0, 'pageNumber': 1, 'bboxes': [marker_box], 'granularity': 'block'}],
                             evidence['pdfRegions'])
        with self.serve() as port:
            reopened = self.value(port, source_url + '/discuss', {})
            self.assertEqual(history['discussionId'], reopened['discussionId'])
            self.assertEqual(window['conversation'], reopened['conversation'])
        self.assertEqual(before, bundle_files())

        # A damaged optional layout cannot invalidate the Markdown or saved quotation.
        old_sidecar.write_text('{"pages": [', encoding='utf-8')
        changed = bundle_files()
        with self.serve(backend_factory=partial(LineCitationRuntime, answer_id='fallback-answer')) as port:
            current = self.value(port, source_url + '/document')
            self.assertEqual(evidence['bundleVersion'], current['bundleVersion'])
            self.assertNotEqual(evidence['layoutVersion'], current['pdf']['version'])
            self.assertEqual([], current['pdf']['blocks'])
            reopened = self.value(port, source_url + '/discuss', {})
            self.assertEqual(window['conversation'], reopened['conversation'])
            fallback = self.continue_discussion(port, reopened['sessionId'], 'continue-with-damaged-layout')
            new_evidence, = fallback['conversation'][-1]['evidence']
            self.assertEqual(passage, new_evidence['quote']['exact'])
            self.assertEqual([], new_evidence['pdfRegions'])
        self.assertEqual(changed, bundle_files())
