"""Reading annotations cross real HTTP/Host/Core boundaries; no model is called."""
import http.client
import json
import shutil
import threading
import unittest
import uuid

import test_direct_source_notes as direct_notes
from host.server import Server
from host.workbench import Workbench


class ReadingHighlightHostTests(unittest.TestCase):
    def setUp(self):
        direct_notes.DirectSourceNoteTests.setUp(self)
        self.token = uuid.uuid4().hex
        app = Workbench(settings_path=self.root / 'highlight-binding.json', workspace=self.host.workspace,
                        service_factory=lambda *args, **kwargs: self.host)
        self.instance = app.status()['workspace']['instanceId']
        self.server = Server(('127.0.0.1', 0), app, token=self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.path = f'/library/sources/{self.source}/highlights'
        self.selection = {'layer': 'source', 'range': {'start': 0, 'end': 9},
                          'quote': {'exact': '计算必须等待数据。', 'prefix': '', 'suffix': ''}}
        self.highlight_payload = {'requestId': uuid.uuid4().hex, 'chunk': self.payload['chunk'], **self.selection}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        direct_notes.DirectSourceNoteTests.tearDown(self)

    def request(self, path, payload=None, *, authorized=True, instance=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers['Authorization'] = 'Bearer ' + self.token
        if instance:
            headers['X-FOCUS-Instance'] = self.instance if instance is True else instance
        connection.request('GET' if payload is None else 'POST', path,
                           None if payload is None else json.dumps(payload), headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_create_replay_and_request_receipt_include_chunk_scope_in_snapshot(self):
        status, body = self.request(self.path, self.highlight_payload)
        self.assertEqual(201, status, body)
        first = body['value']
        highlight = first['highlightOperation']['highlight']
        self.assertEqual('saved', first['highlightOperation']['status'])
        self.assertEqual(self.source, first['highlightOperation']['sourceId'])
        self.assertEqual(list(self.chunk['sourceLines']), highlight['sourceLines'])
        self.assertEqual(self.payload['chunk']['planId'], highlight['planId'])
        self.assertEqual(self.payload['chunk']['chunkId'], highlight['chunkId'])
        self.assertEqual([highlight], first['sourceHighlights'])
        status, replay = self.request(self.path, self.highlight_payload)
        self.assertEqual(201, status)
        self.assertEqual([highlight], replay['value']['sourceHighlights'])
        status, receipt = self.request(self.path + '/requests/' + self.highlight_payload['requestId'])
        self.assertEqual(200, status)
        self.assertEqual({'status': 'saved', 'highlight': highlight}, receipt['value'])
        self.assertIsNone(self.request(self.path + '/requests/unknown-request')[1]['value'])

    def test_delete_restore_and_stale_revision_return_annotation_operation(self):
        created = self.request(self.path, self.highlight_payload)[1]['value']['sourceHighlights'][0]
        path = self.path + '/' + created['highlightId']
        status, deleted = self.request(path + '/delete', {'requestId': uuid.uuid4().hex, 'expectedRevision': 1})
        self.assertEqual(200, status, deleted)
        self.assertEqual('delete', deleted['value']['highlightOperation']['operation'])
        self.assertTrue(deleted['value']['sourceHighlights'][0]['deleted'])
        status, restored = self.request(path + '/undo', {'requestId': uuid.uuid4().hex, 'expectedRevision': 2})
        self.assertEqual(200, status, restored)
        self.assertEqual('undo', restored['value']['highlightOperation']['operation'])
        self.assertFalse(restored['value']['sourceHighlights'][0]['deleted'])
        status, stale = self.request(path + '/delete', {'requestId': uuid.uuid4().hex, 'expectedRevision': 1})
        self.assertEqual(200, status, stale)
        self.assertEqual('conflict', stale['value']['highlightOperation']['status'])
        self.assertEqual(3, stale['value']['highlightOperation']['current']['revision'])

    def test_sentence_note_creation_keeps_remark_and_sentence_separate_from_anchor(self):
        payload = {key: value for key, value in self.payload.items() if key != 'quote'}
        payload['sentence'] = self.selection
        status, body = self.request(f'/library/sources/{self.source}/notes', payload)
        self.assertEqual(201, status, body)
        note = body['value']['sourceNotes'][-1]
        self.assertEqual({**self.payload['chunk'], **self.selection}, note['sentence'])
        self.assertEqual('我的理解', note['content'])
        self.assertEqual({'sourceId': self.source, 'bundle': self.chunk['bundleVersion'],
                          'sourceLines': list(self.chunk['sourceLines'])}, note['anchor'])
        self.assertEqual('explanation', note['evidenceRole'])
        self.assertIsNone(note['placement'])

    def test_validation_conflicts_bundle_drift_and_not_found_have_stable_http_errors(self):
        invalid_payloads = [[], {}, {**self.highlight_payload, 'extra': True},
                            {**self.highlight_payload, 'chunk': {}},
                            {**self.highlight_payload, 'chunk': {'planId': '../escape', 'chunkId': 'chunk-001'}}]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertEqual(400, self.request(self.path, payload)[0])
        status, invalid = self.request(self.path, {**self.highlight_payload, 'layer': 'translation'})
        self.assertEqual(400, status)
        self.assertEqual('highlight_invalid', invalid['error']['code'])
        self.request(self.path, self.highlight_payload)
        status, conflict = self.request(self.path, {**self.highlight_payload, 'range': {'start': 1, 'end': 9}})
        self.assertEqual(409, status)
        self.assertEqual('highlight_request_conflict', conflict['error']['code'])
        status, missing = self.request(self.path + '/' + '0' * 32 + '/delete',
                                      {'requestId': uuid.uuid4().hex, 'expectedRevision': 1})
        self.assertEqual(404, status)
        self.assertEqual('highlight_not_found', missing['error']['code'])
        archive = self.host.workspace / 'sources' / self.source / 'reading/bundles' / self.chunk['bundleVersion']
        shutil.rmtree(archive, ignore_errors=True)
        content = self.host.workspace / 'sources' / self.source / 'parser-bundle/content.md'
        content.write_text(content.read_text(encoding='utf-8') + '\n原文更新。\n', encoding='utf-8')
        status, changed = self.request(self.path, {**self.highlight_payload, 'requestId': uuid.uuid4().hex})
        self.assertEqual(409, status)
        self.assertEqual('highlight_bundle_changed', changed['error']['code'])

    def test_sentence_note_requires_chunk_user_thought_and_available_layer(self):
        payload = {key: value for key, value in self.payload.items() if key != 'quote'}
        payload['sentence'] = self.selection
        note_path = f'/library/sources/{self.source}/notes'
        for changes, code in [({'chunk': None}, 'note_sentence_invalid'),
                              ({'kind': 'conclusion'}, 'invalid-request'),
                              ({'origin': 'dialogue'}, 'invalid-request'),
                              ({'quote': self.payload['quote']}, 'invalid-request'),
                              ({'sentence': {**self.selection, 'layer': 'translation'}}, 'note_sentence_invalid')]:
            with self.subTest(changes=changes):
                status, body = self.request(note_path, {**payload, **changes})
                self.assertEqual(400, status, body)
                self.assertEqual(code, body['error']['code'])
        self.assertEqual([], self.host.snapshot()['sourceNotes'])

    def test_http_authorization_and_instance_binding_cover_every_highlight_route(self):
        requests = [(self.path, self.highlight_payload),
                    (self.path + '/requests/' + self.highlight_payload['requestId'], None),
                    (self.path + '/' + '0' * 32 + '/delete', {'requestId': uuid.uuid4().hex, 'expectedRevision': 1})]
        for path, payload in requests:
            with self.subTest(path=path):
                self.assertEqual(401, self.request(path, payload, authorized=False)[0])
                self.assertEqual(400, self.request(path, payload, instance=False)[0])
                self.assertEqual(400, self.request(path, payload, instance='wrong-instance')[0])

    def test_fresh_session_retains_annotations_but_clear_and_reset_erase_them_and_receipts(self):
        for reset in (False, True):
            with self.subTest(resetReading=reset):
                before = self.host.snapshot()
                highlight_payload = {**self.highlight_payload, 'requestId': uuid.uuid4().hex}
                highlight = self.request(self.path, highlight_payload)[1]['value']['sourceHighlights'][0]
                note_payload = {key: value for key, value in self.payload.items() if key != 'quote'}
                note_payload.update(requestId=uuid.uuid4().hex, sentence=self.selection)
                self.request(f'/library/sources/{self.source}/notes', note_payload)
                old_session = self.host.state['sessionId']
                self.host.new_session({'sessionId': old_session})
                self.assertNotEqual(old_session, self.host.state['sessionId'])
                self.host.select_discussion_source(self.source)
                fresh = self.host.snapshot()
                self.assertEqual(before['noteClearVersion'], fresh['noteClearVersion'])
                self.assertEqual(highlight['highlightId'], fresh['sourceHighlights'][0]['highlightId'])
                self.assertIsNotNone(fresh['sourceNotes'][0]['sentence'])
                # Re-establish a saved operation so clear must remove its recovery payload too.
                self.request(self.path, highlight_payload)
                result = self.host.clear_source(self.source, {'requestId': uuid.uuid4().hex,
                    'confirmed': True, 'resetReading': reset})
                self.assertEqual([], result['sourceHighlights'])
                self.assertEqual([], result['sourceNotes'])
                self.assertIsNone(result['highlightOperation'])
                self.assertEqual(before['noteClearVersion'] + 1, result['noteClearVersion'])
                self.assertEqual(before['resetVersion'] + int(reset), result['resetVersion'])
                self.assertEqual({'status': 'cancelled'}, self.request(
                    self.path + '/requests/' + highlight_payload['requestId'])[1]['value'])


if __name__ == '__main__':
    unittest.main()
