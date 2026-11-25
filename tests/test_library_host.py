"""Library operations against real Core files and a protocol double (no external API)."""
import http.client
import json
import threading
from unittest.mock import patch

import unittest
import test_web_host
from host.server import Server
from host.core_bridge import SourceLibrary, WorkspaceError


class LibraryHostTests(unittest.TestCase):
    prepare_all = test_web_host.WebHostTests.prepare_all
    setUp = test_web_host.WebHostTests.setUp
    tearDown = test_web_host.WebHostTests.tearDown
    finish = test_web_host.WebHostTests.finish

    def test_library_projects_existing_assets_in_place(self):
        state = (self.workspace / 'state.json').read_bytes()
        sources = self.host.library_sources()
        self.assertEqual('fixture-paper', sources[0]['sourceId'])
        self.assertEqual({'completed': 0, 'total': 3, 'planId': 'plan-001', 'chunkId': 'chunk-001'}, sources[0]['progress'])
        self.assertEqual('ready', sources[0]['parseStatus'])
        self.assertEqual(state, (self.workspace / 'state.json').read_bytes())

    def test_independent_source_completion_does_not_count_with_or_without_a_current_plan(self):
        source_id = 'fixture-paper'
        self.prepare_all()
        document = self.host.source_document(source_id)
        self.host.complete_source(source_id, {
            'requestId': 'legacy-completion', 'bundleVersion': document['bundleVersion'],
            'generation': document['generation'],
        })
        archived = self.workspace / 'sources' / source_id / 'reading/source-completion.json'
        original = archived.read_bytes()

        selected = self.host.library_sources()[0]
        self.assertEqual('ready', selected['readingStatus'])
        self.assertEqual((0, 3), (selected['progress']['completed'], selected['progress']['total']))

        SourceLibrary(self.workspace).unselect_plan(source_id)
        unselected = self.host.library_sources()[0]
        self.assertEqual('unplanned', unselected['readingStatus'])
        self.assertEqual((0, 0), (unselected['progress']['completed'], unselected['progress']['total']))
        self.assertEqual(original, archived.read_bytes())

    def test_reopening_a_historical_in_progress_plan_preserves_reading_status(self):
        self.prepare_all()
        state_path = self.workspace / 'state.json'
        state = json.loads(state_path.read_text())
        state['sources']['fixture-paper']['current_chunk_id'] = 'chunk-002'
        state_path.write_text(json.dumps(state))
        initial = self.host.library_sources()[0]
        self.assertEqual('reading', initial['readingStatus'])

        opened = self.host.open_prepared_reading('fixture-paper', request_id='reopen-historical')
        self.assertTrue(opened['readingStarted'])
        self.assertEqual('chunk-002', opened['current']['chunkId'])
        self.assertEqual(initial['progress'], self.host.library_sources()[0]['progress'])
        self.assertEqual('reading', self.host.library_sources()[0]['readingStatus'])

    def test_entering_a_single_chunk_plan_counts_as_reading_at_zero(self):
        chunks = self.workspace / 'sources/fixture-paper/reading/plans/plan-001/chunks.jsonl'
        chunks.write_text(chunks.read_text().splitlines()[0] + '\n')
        self.prepare_all()

        view = self.host.open_prepared_reading('fixture-paper', request_id='open-single-chunk')
        self.assertEqual('ready', self.host.library_sources()[0]['readingStatus'])
        self.host.continue_cached({
            'requestId': 'enter-single-chunk', 'beginBody': True,
            'receipt': {**self.receipt, 'readingRevision': view['readingRevision']},
        })
        source = self.host.library_sources()[0]
        self.assertEqual('reading', source['readingStatus'])
        self.assertEqual((0, 1), (source['progress']['completed'], source['progress']['total']))

    def test_advancing_and_reviewing_preserve_progress_and_completed_plan_reopens_in_full(self):
        self.prepare_all()
        source_id = 'fixture-paper'
        view = self.host.open_prepared_reading(source_id, request_id='open-library-progress')

        def receipt():
            cursor = view['navigationCurrent']
            return {**{key: cursor[key] for key in ('sourceId', 'planId', 'chunkId')},
                    'readingRevision': view['readingRevision']}

        view = self.host.continue_cached({'receipt': receipt(), 'requestId': 'enter-library-progress'})
        view = self.host.continue_cached({'receipt': receipt(), 'requestId': 'advance-library-first'})
        view = self.host.continue_cached({'receipt': receipt(), 'requestId': 'advance-library-second'})
        self.assertEqual(2, self.host.library_sources()[0]['progress']['completed'])
        reviewed = self.host.review_chunk(source_id, 'plan-001', 'chunk-001')
        self.assertEqual('chunk-001', reviewed['reviewChunk']['chunkId'])
        self.assertEqual('chunk-003', reviewed['navigationCurrent']['chunkId'])
        self.assertEqual(2, self.host.library_sources()[0]['progress']['completed'])

        self.host.finish_reading({'receipt': receipt(), 'requestId': 'finish-library-progress'})
        finished = self.host.library_sources()[0]
        self.assertEqual('completed', finished['readingStatus'])
        self.assertEqual((3, 3), (finished['progress']['completed'], finished['progress']['total']))
        reopened = self.host.open_prepared_reading(source_id, request_id='reopen-library-progress')
        self.assertEqual('completed', reopened['status'])
        self.assertEqual(['chunk-001', 'chunk-002', 'chunk-003'], [chunk['chunkId'] for chunk in reopened['history']])

    def test_reread_keeps_notes_and_translation_and_plan(self):
        self.prepare_all()
        core = self.host.core.core
        core.append_note(expected_plan_id='plan-001', expected_chunk_id='chunk-001', kind='thought', origin='user', content='保留笔记')
        root = self.workspace / 'sources/fixture-paper'
        records = {str(p): p.read_bytes() for p in (root / 'reading/plans').rglob('*') if p.is_file()}
        core.continue_reading(expected_plan_id='plan-001', expected_chunk_id='chunk-001')
        view = self.host.snapshot()
        receipt = {**{k: view['navigationCurrent'][k] for k in ('sourceId', 'planId', 'chunkId')},
                   'readingRevision': view['readingRevision']}
        self.host.reread_reading({'receipt': {**receipt, 'chunkId': 'chunk-002'},
                                  'requestId': 'reread-library-test'})
        self.assertEqual('chunk-001', self.host.snapshot()['navigationCurrent']['chunkId'])
        self.assertEqual(records, {str(p): p.read_bytes() for p in (root / 'reading/plans').rglob('*') if p.is_file()})

    def test_delete_detaches_topics_and_clears_timeline(self):
        lib = SourceLibrary(self.workspace)
        lib.attach('fixture-paper', topic_title='Topic One', topic_id='topic-one')
        lib.attach('fixture-paper', topic_title='Topic Two', topic_id='topic-two')
        self.host.library_delete('fixture-paper')
        self.assertFalse((self.workspace / 'sources/fixture-paper').exists())
        self.assertEqual([], self.host.library_sources())
        self.assertTrue(all(t['sourceIds'] == [] for t in self.host.library_topics()))
        self.assertEqual('empty', self.host.snapshot()['status'])
        self.assertEqual([], self.host.snapshot()['timeline'])

    def test_mutations_reject_active_worker_and_traversal(self):
        self.host.state['run'] = {'status': 'running'}
        with self.assertRaises(ValueError):
            self.host.library_delete('fixture-paper')
        self.host.state['run'] = None
        with self.assertRaises(WorkspaceError):
            self.host.library_delete('../fixture-paper')
        self.assertTrue((self.workspace / 'sources/fixture-paper').is_dir())

    def test_reread_write_failure_rolls_back(self):
        state = (self.workspace / 'state.json').read_bytes()
        with patch('core.source_library._write_document', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                SourceLibrary(self.workspace).reset_reading('fixture-paper')
        self.assertEqual(state, (self.workspace / 'state.json').read_bytes())

    def test_library_http_inbox_resources_and_auth(self):
        server = Server(('127.0.0.1', 0), self.host)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
            conn.request('GET', '/library/sources')
            response = conn.getresponse(); self.assertEqual(200, response.status); response.read()
            conn.request('POST', '/library/inbox?name=test.html', b'html')
            response = conn.getresponse(); self.assertEqual(400, response.status); response.read()
            conn.close(); conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
            conn.request('POST', '/library/inbox?name=test.pdf&topic=Test', b'%PDF test')
            response = conn.getresponse(); self.assertEqual(201, response.status)
            item = json.loads(response.read())['value']
            self.assertEqual('awaiting_confirmation', item['status'])
            conn.request('GET', '/library/inbox')
            response = conn.getresponse(); self.assertEqual(200, response.status); self.assertEqual(1, len(json.loads(response.read())['value']))
            conn.request('GET', '/library/sources/fixture-paper/original')
            response = conn.getresponse(); self.assertEqual(200, response.status); self.assertTrue(response.read().startswith(b'%PDF'))
            conn.request('GET', '/library/sources/fixture-paper/content')
            response = conn.getresponse(); self.assertEqual(200, response.status); self.assertIn(b'Fixture Paper', response.read())
            conn.request('GET', '/library/sources/fixture-paper/images/image-001.png')
            response = conn.getresponse(); self.assertEqual(200, response.status); self.assertGreater(len(response.read()), 0)
            conn.request('GET', '/library/topics', headers={'Origin': 'https://evil.example'})
            response = conn.getresponse(); self.assertEqual(403, response.status); response.read()
            conn.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_delete_reference_write_failure_restores_directory(self):
        state = (self.workspace / 'state.json').read_bytes()
        with patch('core.source_library._write_document', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.host.library_delete('fixture-paper')
        self.assertTrue((self.workspace / 'sources/fixture-paper/parser-bundle/content.md').is_file())
        self.assertEqual(state, (self.workspace / 'state.json').read_bytes())
        self.assertEqual('empty', self.host.snapshot()['status'])
        self.assertEqual('chunk-001', self.host.snapshot()['navigationCurrent']['chunkId'])
