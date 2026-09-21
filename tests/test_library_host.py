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

    def test_reread_keeps_notes_and_translation_and_plan(self):
        self.prepare_all()
        core = self.host.core.core
        core.append_note(expected_plan_id='plan-001', expected_chunk_id='chunk-001', kind='thought', origin='user', content='保留笔记')
        root = self.workspace / 'sources/fixture-paper'
        records = {str(p): p.read_bytes() for p in (root / 'reading/plans').rglob('*') if p.is_file()}
        core.continue_reading(expected_plan_id='plan-001', expected_chunk_id='chunk-001')
        self.host.library_read('fixture-paper', reread=True)
        self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])
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
        self.assertEqual('reading', self.host.snapshot()['status'])
