"""Local HTTP boundary for the unified reader; no model or Internet required."""
import http.client
import json
import threading
import unittest
import reading_fixture
from workspace_fixture import HostService
from host.server import Server


class SourceReadingHTTPTests(unittest.TestCase):
    def test_document_completion_and_version_bound_images(self):
        fixture = reading_fixture.ReadingFixture()
        fixture.setUp()
        workspace = fixture._workspace()[0]
        host = HostService(workspace, fixture.root / 'host')
        server = Server(('127.0.0.1', 0), host)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        def request(path, payload=None):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request('GET' if payload is None else 'POST', path,
                                   body=None if payload is None else json.dumps(payload),
                                   headers={'Content-Type': 'application/json'})
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()
        try:
            status, body = request('/library/sources/fixture-paper/document')
            self.assertEqual(200, status)
            doc = json.loads(body)['value']
            self.assertIn('The alias address', doc['markdown'])
            image = '/reader/assets/fixture-paper/images/image-001.png?bundle='
            self.assertEqual((200, b'image'), request(image + doc['bundleVersion']))
            self.assertEqual(400, request(image + '0' * 64)[0])
            before = (workspace / 'state.json').read_bytes()
            status, body = request('/library/sources/fixture-paper/completion', {
                'requestId': 'http-complete-test', 'bundleVersion': doc['bundleVersion'], 'generation': doc['generation']})
            self.assertEqual(200, status)
            self.assertEqual(before, (workspace / 'state.json').read_bytes())
        finally:
            server.shutdown()
            server.server_close()
            worker.join(5)
            host.close()
            fixture.tearDown()
