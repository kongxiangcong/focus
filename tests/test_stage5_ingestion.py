"""Stage 5 acceptance through the real startup and HTTP boundary."""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import threading
from urllib.parse import urlencode, quote

from host.service import HostService
from host.server import Server
from test_blog_host import ControlledBlogRuntime, ParserDouble
from test_html_ingestion import saved_html

ROOT = Path(__file__).resolve().parents[1]


class SingleIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = ControlledBlogRuntime()
        self.start_host()

    def start_host(self):
        self.host = HostService(self.root / 'knowledge-base', self.root / 'host',
                                ingestion_parser=ParserDouble(), blog_runtime=self.runtime)
        self.server = Server(('127.0.0.1', 0), self.host)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop_host(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.host.close()

    def tearDown(self):
        self.runtime.release.set()
        self.stop_host()
        self.temp.cleanup()

    def request(self, method, path, body=None, *, expected_status=None):
        headers = {}
        if isinstance(body, dict):
            body = json.dumps(body)
            headers['Content-Type'] = 'application/json'
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request(method, quote(path, safe="/?=&%+"), body, headers)
            response = conn.getresponse()
            data = response.read()
            if expected_status is None:
                self.assertLess(response.status, 400, data)
            else:
                self.assertEqual(expected_status, response.status, data)
            decoded = json.loads(data)
            return decoded.get('value', decoded.get('error'))
        finally:
            conn.close()

    def wait_blog(self, item_id, expected='completed'):
        deadline = time.monotonic() + 20
        status = None
        while time.monotonic() < deadline:
            item = next(i for i in self.request('GET', '/library/inbox') if i['item_id'] == item_id)
            if item.get('source_id'):
                status = self.request('GET', '/library/sources/' + item['source_id'] + '/blog')
                if status['runStatus'] == expected and not status.get('executing'):
                    return item, status
            time.sleep(.05)
        self.fail(str(status or item))

    def test_confirmed_scope_survives_restart_before_processing(self):
        item = self.request('POST', '/library/inbox?name=test.pdf&topic=Systems', b'%PDF restarted')
        self.request('POST', '/library/inbox/' + item['item_id'] + '/confirm', {'generateBlog': True})
        self.stop_host()
        self.start_host()
        self.assertEqual([], self.runtime.calls)
        self.request('POST', '/library/inbox/' + item['item_id'] + '/process', {'requestId': 'restart'})
        self.wait_blog(item['item_id'])

    def test_explicit_reconfirmation_of_changed_model_can_complete(self):
        item = self.request('POST', '/library/inbox?name=test.pdf&topic=Systems', b'%PDF model change')
        self.request('POST', '/library/inbox/' + item['item_id'] + '/confirm', {'generateBlog': True})
        self.runtime.model = 'replacement-model'
        self.request('POST', '/library/inbox/' + item['item_id'] + '/start', {'requestId': 'new-model-confirm'})
        self.wait_blog(item['item_id'])

    def test_unclassified_parse_only_publishes_but_damaged_html_does_not(self):
        item = self.request('POST', '/library/inbox?name=test.pdf', b'%PDF no topic')
        batch = self.request('POST', '/library/batches', {'itemIds': [item['item_id']], 'requestId': 'no-topic', 'generateBlog': False})
        self.host.batch_workers[batch['batchId']].join(10)
        self.assertEqual([], self.request('GET', '/library/sources')[0]['topicIds'])
        item = self.request('POST', '/library/inbox?name=bad.html&topic=Systems', saved_html(missing=True).encode())
        self.request('POST', '/library/inbox/' + item['item_id'] + '/start', {'requestId': 'bad-html'})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            current = next(i for i in self.request('GET', '/library/inbox') if i['item_id'] == item['item_id'])
            if current['status'] == 'failed':
                break
            time.sleep(.05)
        self.assertEqual('article_image_missing', current['error']['error_id'])
        self.assertEqual(1, len(self.request('GET', '/library/sources')))
        self.assertEqual([], self.runtime.calls)

    def test_classification_service_failure_is_persisted_and_recoverable(self):
        original = self.runtime.classify
        def fail(**kwargs):
            raise RuntimeError('provider unavailable')
        self.runtime.classify = fail
        item = self.request('POST', '/library/inbox?name=test.pdf&topic=Systems', b'%PDF classification')
        self.request('POST', '/library/inbox/' + item['item_id'] + '/start', {'requestId': 'classify-fail'})
        item, status = self.wait_blog(item['item_id'], 'failed')
        self.assertEqual('blog_classification_failed', status['error']['error_id'])
        self.stop_host()
        self.start_host()
        status = self.request('GET', '/library/sources/' + item['source_id'] + '/blog')
        self.assertEqual('failed', status['runStatus'])
        self.runtime.classify = original
        self.request('POST', '/library/sources/' + item['source_id'] + '/blog/generate', {'requestId': 'classify-retry'})
        self.wait_blog(item['item_id'])

    def test_failed_blog_retry_keeps_published_original_and_successful_artifacts(self):
        good_body = self.runtime.reading_body
        self.runtime.reading_body = '# invalid'
        item = self.request('POST', '/library/inbox?name=test.pdf&topic=Systems', b'%PDF blog failure')
        self.request('POST', '/library/inbox/' + item['item_id'] + '/start', {'requestId': 'failure'})
        item, _ = self.wait_blog(item['item_id'], 'failed')
        source = self.root / 'knowledge-base/sources' / item['source_id']
        before = {p.name: p.read_bytes() for p in (source / 'parser-bundle').iterdir() if p.is_file()}
        self.runtime.reading_body = good_body
        retry_path = '/library/sources/' + item['source_id'] + '/blog/regenerate'
        self.request('POST', retry_path, {'requestId': 'retry', 'artifact': 'reading_blog'})
        self.wait_blog(item['item_id'])
        calls = list(self.runtime.calls)
        self.request('POST', retry_path, {'requestId': 'retry', 'artifact': 'reading_blog'})
        self.wait_blog(item['item_id'])
        self.assertEqual(calls, self.runtime.calls)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (source / 'parser-bundle').iterdir() if p.is_file()})

    def test_automatic_blog_cancellation_and_explicit_retry(self):
        self.runtime.release.clear()
        item = self.request('POST', '/library/inbox?name=test.pdf&topic=Systems', b'%PDF cancel')
        self.request('POST', '/library/inbox/' + item['item_id'] + '/start', {'requestId': 'cancel'})
        self.assertTrue(self.runtime.entered.wait(10))
        item = next(i for i in self.request('GET', '/library/inbox') if i['item_id'] == item['item_id'])
        self.request('POST', '/library/sources/' + item['source_id'] + '/blog/cancel', {})
        self.runtime.release.set()
        self.wait_blog(item['item_id'], 'cancelled')
        for worker in list(self.host.blog_workers.values()):
            worker.join(10)
        self.request('POST', '/library/sources/' + item['source_id'] + '/blog/generate', {'requestId': 'retry-cancel'})
        self.wait_blog(item['item_id'])

    def test_single_confirmation_publishes_blog_and_replay_survives_restart(self):
        staged = self.request('POST', '/library/inbox?' + urlencode({'name': 'paper.pdf', 'topic': '  Systems  '}), b'%PDF example')
        item_id = staged['item_id']
        path = '/library/inbox/' + item_id + '/start'
        self.request('POST', path, {'requestId': 'single-1'})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            sources = self.request('GET', '/library/sources')
            if sources:
                status = self.request('GET', '/library/sources/' + sources[0]['sourceId'] + '/blog')
                if status['runStatus'] in ('completed', 'failed'):
                    break
            time.sleep(.05)
        self.assertEqual('completed', status['runStatus'], status)
        self.assertEqual('completed', status['artifacts']['html']['status'])
        self.assertIsNone(sources[0]['progress']['planId'])
        self.assertEqual('Systems', self.request('GET', '/library/topics')[0]['title'])
        calls = list(self.runtime.calls)
        self.stop_host()
        self.start_host()
        self.request('POST', path, {'requestId': 'single-1'})
        self.assertEqual(calls, self.runtime.calls)
        self.assertEqual(1, len(self.request('GET', '/library/sources')))
        self.assertEqual('completed', self.request('GET', '/library/sources/' + sources[0]['sourceId'] + '/blog')['runStatus'])

    def test_local_html_variants_and_normalized_topic_share_one_public_path(self):
        self.runtime.applicable = False
        self.runtime.reading_body = self.runtime.reading_body.replace("第 1 节指出", "文章指出").replace("Table 1", "原文表格")
        for index, (with_image, caption) in enumerate(((True, True), (False, False), (True, False))):
            with self.subTest(with_image=with_image, caption=caption):
                html = saved_html(image=with_image, url=f'https://example.com/article-{index}')
                if not caption:
                    html = html.replace('Figure caption', '')
                body = self.runtime.reading_body
                if not with_image:
                    self.runtime.reading_body = body.replace('![Figure 1](assets/image-001.png)', '')
                staged = self.request('POST', '/library/inbox?' + urlencode({'name': f'{index}.html', 'topic': '  SYSTEMS ' if index == 0 else 'systems'}), html.encode())
                self.request('POST', '/library/inbox/' + staged['item_id'] + '/start', {'requestId': f'html-{index}'})
                deadline = time.monotonic() + 20
                status = None
                while time.monotonic() < deadline:
                    item = next(i for i in self.request('GET', '/library/inbox') if i['item_id'] == staged['item_id'])
                    if item['status'] == 'failed':
                        self.fail(str(item.get('error')))
                    if item.get('source_id'):
                        status = self.request('GET', '/library/sources/' + item['source_id'] + '/blog')
                        if status['runStatus'] in ('completed', 'failed'):
                            break
                    time.sleep(.05)
                self.assertIsNotNone(status)
                self.assertEqual('completed', status['runStatus'], status)
                self.assertFalse(status['valueAnalysis']['applicable'])
                self.runtime.reading_body = body
        topics = self.request('GET', '/library/topics')
        self.assertEqual(1, len(topics))
        self.assertEqual(3, len(topics[0]['sourceIds']))


class StartupTests(unittest.TestCase):
    def test_default_start_is_fresh_and_restart_preserves_new_knowledge_base(self):
        for old_exists in (False, True):
            with self.subTest(old_exists=old_exists), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                old = root / 'workspace'
                if old_exists:
                    old.mkdir()
                    (old / 'state.json').write_text('OLD DATA MUST NOT BE READ', encoding='utf-8')
                env = {k: v for k, v in os.environ.items()
                       if k not in ('FOCUS_WORKSPACE', 'FOCUS_HOST_DATA', 'FOCUS_BACKEND', 'FOCUS_CODEX_BIN')}
                env['PYTHONPATH'] = str(ROOT)
                for restart in (False, True):
                    with socket.socket() as sock:
                        sock.bind(('127.0.0.1', 0))
                        port = sock.getsockname()[1]
                    log = root / ('restart.log' if restart else 'startup.log')
                    with log.open('w', encoding='utf-8') as output:
                        proc = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', '-m', 'host', '--port', str(port)],
                                                cwd=root, env=env, stdout=output, stderr=output)
                        try:
                            deadline = time.monotonic() + 20
                            while True:
                                try:
                                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
                                    conn.request('GET', '/library/inbox')
                                    response = conn.getresponse()
                                    topics = json.loads(response.read())['value']
                                    conn.close()
                                    break
                                except (OSError, KeyError):
                                    conn.close()
                                    if proc.poll() is not None or time.monotonic() > deadline:
                                        self.fail(log.read_text(encoding='utf-8'))
                                    time.sleep(.1)
                            self.assertTrue((root / 'knowledge-base').is_dir())
                            if restart:
                                self.assertEqual('New Topic', topics[0]['topic_title'])
                            else:
                                self.assertEqual([], topics)
                                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                                conn.request('POST', '/library/inbox?name=new.pdf&topic=New%20Topic', b'%PDF new')
                                response = conn.getresponse()
                                body = response.read()
                                conn.close()
                                self.assertEqual(201, response.status, body)
                        finally:
                            if os.name == 'nt':
                                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
                            else:
                                proc.terminate()
                            proc.wait(timeout=10)
                if old_exists:
                    self.assertEqual('OLD DATA MUST NOT BE READ', (old / 'state.json').read_text(encoding='utf-8'))
                else:
                    self.assertFalse(old.exists())
