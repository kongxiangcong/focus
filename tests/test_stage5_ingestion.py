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

    def request(self, method, path, body=None):
        headers = {}
        if isinstance(body, dict):
            body = json.dumps(body)
            headers['Content-Type'] = 'application/json'
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request(method, quote(path, safe="/?=&%+"), body, headers)
            response = conn.getresponse()
            data = response.read()
            self.assertLess(response.status, 400, data)
            return json.loads(data)['value']
        finally:
            conn.close()

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
