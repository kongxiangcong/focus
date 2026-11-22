from __future__ import annotations

import base64
import importlib.util
import io
import http.client
import json
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from bs4 import BeautifulSoup
from core import IngestionApplication, SourceLibrary, WorkspaceError
from core.html_article import LocalHTMLParser
from core.reading_workspace import _validate_parser_bundle
from core.source_ir import IRSerializer, load_source_ir
from core.source_reading import SourceReading
from core.workspace_lifecycle import create_workspace


def saved_html(*, missing=False, image=True, url="https://example.com/article"):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "PNG")
    data = "https://example.com/missing.png" if missing else "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    prose = "A carefully written article about deterministic scheduling, with evidence and limitations. " * 6
    return f'''<!doctype html><html><head><meta property="og:title" content="Scheduling article">
    <meta property="og:url" content="{url}"></head><body class="comment_feature">
    <nav>Private messages and notifications</nav><main><article><h1>Scheduling article</h1>
    <p>{prose}</p><h2>Method</h2><p>{prose}</p>
    <p><section>{f'<img src="{data}" alt="architecture">' if image else ''}</section>Figure caption</p>
    <table><tr><th>Unit</th><th>Cycles</th></tr><tr><td>ALU</td><td>2</td></tr></table>
    <pre><code>def schedule():\n    return 42\n</code></pre><p>{prose}</p>
    <div class="advertisement"><img src="https://example.com/ad.png">BUY NOW</div>
    <section class="Comments"><p>COMMENT SECRET {prose}</p></section>
    <div role="dialog">SIGN IN</div><div class="sf-hidden">HIDDEN SECRET</div>
    <h2>Conclusion</h2><p>{prose}</p></article></main><aside>RECOMMENDED SECRET</aside></body></html>'''


class NoRemoteParser:
    def parse(self, *args, **kwargs):
        raise AssertionError("HTML must never invoke a remote PDF parser")


class HTMLIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.source = self.root / "saved.html"
        self.source.write_text(saved_html(), encoding="utf-8")

    def app(self):
        return IngestionApplication(self.workspace, parser=NoRemoteParser(), writer_id="test")

    def ingest(self, app):
        staged = app.stage_file(self.source)
        app.confirm(staged["item_id"], services=["local-html"], purpose="read article", scope="ingestion")
        return app.process(staged["item_id"], request_id=staged["item_id"])

    def test_offline_structure_and_media_survive_without_noise(self):
        self.source.write_text(saved_html().replace('<h2>Conclusion</h2>',
            '<h2>Conclusion</h2><a href="https://example.com/notes"><div>https://example.com/notes</div></a>'),
            encoding='utf-8')
        candidate = self.root / "candidate"
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            LocalHTMLParser().parse(self.source, candidate)
        metadata = _validate_parser_bundle(candidate)
        content = (candidate / "content.md").read_text(encoding="utf-8")
        self.assertEqual(1, metadata["image_count"])
        self.assertEqual(self.source.read_bytes(), (candidate / "source.html").read_bytes())
        for noise in ("BUY NOW", "COMMENT SECRET", "SIGN IN", "HIDDEN SECRET", "RECOMMENDED SECRET"):
            self.assertNotIn(noise, content)
        for retained in ("images/image-001.png", "Figure caption", "| ALU | 2 |", "    return 42", "## Conclusion"):
            self.assertIn(retained, content)
        self.assertNotIn("batch_id", metadata)
        ir = load_source_ir(candidate, content)
        archived = BeautifulSoup(self.source.read_text(encoding='utf-8'), 'lxml')
        for excerpt, tag in [('| ALU | 2 |', 'table'), ('    return 42', 'pre'), ('<https://example.com/notes>', 'a')]:
            block = next(block for block in ir['blocks'] if excerpt in block['markdown'])
            anchors = block['anchors']['html']
            self.assertEqual([tag], [archived.select_one(selector).name for selector in anchors['selectors']])

    def test_missing_article_image_fails_before_publication(self):
        self.source.write_text(saved_html(missing=True), encoding="utf-8")
        result = self.ingest(self.app())
        self.assertEqual("failed", result["status"])
        self.assertEqual("article_image_missing", result["error"]["error_id"])
        self.assertFalse((self.workspace / "sources").exists())

    def test_no_image_article_is_legal(self):
        self.source.write_text(saved_html(image=False), encoding="utf-8")
        result = self.ingest(self.app())
        self.assertEqual("completed", result["status"])

    def test_reuses_original_task_and_canonical_url_source(self):
        app = self.app()
        first = app.stage_file(self.source)
        self.assertEqual(first["item_id"], app.stage_file(self.source)["item_id"])
        result = self.ingest(app)
        self.assertEqual("completed", result["status"])
        self.source.write_text(saved_html(url="https://example.com/article?utm_source=changed") + "\n", encoding="utf-8")
        second = self.ingest(app)
        self.assertEqual(result["source_id"], second["source_id"])
        source = SourceLibrary(self.workspace).get(result["source_id"])
        self.assertEqual("article_html", source["source_kind"])
        self.assertEqual("https://example.com/article", source["source_url"])

    def test_core_rejects_remote_image_even_with_success_flag(self):
        candidate = self.root / "candidate"
        LocalHTMLParser().parse(self.source, candidate)
        with (candidate / "content.md").open("a", encoding="utf-8") as stream:
            stream.write("\n![missing](https://example.com/missing.png)\n")
        with self.assertRaises(WorkspaceError):
            _validate_parser_bundle(candidate)

    def test_original_tampering_invalidates_confirmation(self):
        app = self.app()
        staged = app.stage_file(self.source)
        app.confirm(staged["item_id"], services=["local-html"], purpose="read", scope="ingestion")
        (self.workspace / "inbox" / staged["item_id"] / "source.html").write_text("changed", encoding="utf-8")
        with self.assertRaises(WorkspaceError):
            app.process(staged["item_id"], request_id="tamper")

    def test_html_blog_preparation_keeps_source_kind_and_assets(self):
        result = self.ingest(self.app())
        path = Path(__file__).resolve().parents[1] / "methods/article-blog/scripts/article2blog.py"
        spec = importlib.util.spec_from_file_location("html_blog_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        candidate = self.root / "blog"
        prepared = module._prepare_registered(self.workspace, result["source_id"], candidate)
        self.assertEqual("article_html", prepared["metadata"]["source_kind"])
        self.assertTrue((candidate / "assets/image-001.png").is_file())
        self.assertFalse((candidate / "source.html").exists())

    def test_http_upload_and_host_confirmation_use_local_html_service(self):
        from workspace_fixture import HostService
        from host.server import Server

        class Runtime:
            def __init__(self, *args, **kwargs):
                self.events = queue.Queue()

            def open_session(self, *args, **kwargs):
                return 'html-evidence-session'

            def call(self, request, action, arguments):
                self.events.put({'id': request, 'method': 'tool/call', 'params': {'tool': 'focus', 'arguments': {
                    'action': action, 'arguments': json.dumps(arguments)}}})

            def start_turn(self, **kwargs):
                self.call(1, 'read_range', {'block_ids': [conclusion_block_id]})

            def send(self, reply):
                value = json.loads(reply['result']['text'])
                if reply['id'] == 1:
                    self.call(2, 'cite', {'block_ids': [value['blocks'][0]['block_id']],
                                          'quote': value['source_text'].removeprefix('After: ')})
                    return
                self.events.put({'method': 'message/completed', 'params': {'itemId': 'html-answer',
                                 'text': 'The conclusion repeats the finding. ' + value['marker']}})
                self.events.put({'method': 'turn/completed', 'params': {'status': 'completed'}})

            def close(self):
                pass

        service = HostService(self.workspace, self.root / 'host-data', ingestion_parser=NoRemoteParser(), backend_factory=Runtime)
        server = Server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            repeated = '**Repeat** [the result](https://example.com/method).'
            html = saved_html().replace('<h1>Scheduling article</h1>', '').replace(
                '<h2>Method</h2>', '<h2>Method</h2><p id="first">Before: <strong>Repeat</strong> '
                '<a href="/method">the result</a>.</p>').replace(
                '<h2>Conclusion</h2>', '<h2>Conclusion</h2><p hidden>Ignore this earlier sibling.</p>'
                '<p id="second">After: <strong>Repeat</strong> <a href="/method">the result</a>.</p>')
            self.source.write_bytes(html.replace('\n', '\r\n').encode('utf-8'))
            connection = http.client.HTTPConnection(*server.server_address)
            connection.request("POST", "/library/inbox?name=saved.html", self.source.read_bytes())
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(201, response.status, payload)
            staged = payload["value"]
            self.assertEqual(["local-html"], staged["services"])
            connection.request("POST", f"/library/inbox/{staged['item_id']}/confirm", b"{}")
            response = connection.getresponse()
            response.read()
            self.assertEqual(200, response.status)
            result = service.inbox_process(staged["item_id"], request_id="html-http")
            self.assertEqual("completed", result["status"])
            from urllib.parse import quote
            connection.request("GET", f"/library/sources/{quote(result['source_id'])}/original")
            response = connection.getresponse()
            original = response.read()
            self.assertEqual(self.source.read_bytes(), original)
            self.assertIn("sandbox;", response.getheader("Content-Security-Policy"))
            self.assertNotIn("allow-scripts", response.getheader("Content-Security-Policy"))
            connection.close()

            source_id = result['source_id']
            bundle = self.workspace / 'sources' / source_id / 'parser-bundle'
            markdown = service.source_document(source_id)['markdown']
            ir = load_source_ir(bundle, markdown)
            self.assertIsNotNone(ir)
            self.assertEqual('article_html', ir['source_kind'])
            self.assertIsNone(ir['blocks'][0]['anchors']['html'])
            serialized = IRSerializer.markdown(ir).encode('utf-8')
            self.assertEqual(serialized, (bundle / 'content.md').read_bytes())
            self.assertNotIn(b'\r', serialized)

            scope = service.discussion_app.bind(source_id=source_id, request_id='html-evidence', content='Compare the results')
            reader = SourceReading(self.workspace)
            full_range = {'start': 1, 'end': markdown.count('\n')}
            read = service.discussion_app.candidate(scope, 'read_range', full_range)
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                reader.cite(scope, {**full_range, 'quote': repeated})
            archived = BeautifulSoup(original, 'lxml')
            by_id = {block['block_id']: block for block in ir['blocks']}
            cited_lines = []
            for context, section, node_id in [('Before: ', 'Method', 'first'), ('After: ', 'Conclusion', 'second')]:
                line = read['source_text'].split('\n').index(context + repeated) + 1
                block_id = next(block['block_id'] for block in read['blocks'] if block['source_lines'] == [line, line])
                self.assertEqual(context + repeated,
                                 service.discussion_app.candidate(scope, 'read_range', {'block_ids': [block_id]})['source_text'])
                by_block = reader.cite(scope, {'block_ids': [block_id], 'quote': repeated, 'prefix': context})
                by_context = reader.cite(scope, {**full_range, 'quote': repeated, 'prefix': context})
                self.assertEqual([line, line], by_context['sourceLines'])
                self.assertEqual(by_block, by_context)
                self.assertEqual(repeated, by_block['quote']['exact'])
                self.assertEqual([block_id], by_block['blockIds'])
                block = by_id[block_id]
                self.assertEqual(['Scheduling article', section], block['section_path'])
                anchors = block['anchors']['html']
                self.assertEqual([node_id], [archived.select_one(selector)['id'] for selector in anchors['selectors']])
                cited_lines.append(line)
            self.assertLess(*cited_lines)

            conclusion_block_id = block_id
            selected = service.select_discussion_source(source_id)
            service.start({'sourceId': source_id, 'sessionId': selected['sessionId'], 'receipt': None,
                           'requestId': 'html-evidence-answer', 'content': 'What finding does the conclusion repeat?'})
            service.worker.join(8)
            self.assertFalse(service.worker.is_alive())
            answer = service.snapshot()['conversation'][-1]
            evidence, = answer['evidence']
            self.assertEqual('html-answer', evidence['messageId'])
            self.assertEqual(repeated, evidence['quote']['exact'])
            self.assertEqual([conclusion_block_id], evidence['blockIds'])
            self.assertEqual([cited_lines[1]] * 2, evidence['sourceLines'])

            cli_workspace = self.root / 'cli-workspace'
            create_workspace(cli_workspace)
            cli = Path(__file__).resolve().parents[1] / '.agents/skills/article-parser/scripts/article_parser.py'
            completed = subprocess.run([sys.executable, str(cli), 'parse-file', str(self.source),
                                        '--workspace', str(cli_workspace)], capture_output=True, text=True)
            self.assertEqual(0, completed.returncode, completed.stderr)
            cli_source = json.loads(completed.stdout)['source_id']
            cli_bundle = cli_workspace / 'sources' / cli_source / 'parser-bundle'
            self.assertEqual(serialized, (cli_bundle / 'content.md').read_bytes())
            self.assertEqual((bundle / 'source-ir.json').read_bytes(), (cli_bundle / 'source-ir.json').read_bytes())
        finally:
            server.shutdown()
            server.server_close()
            service.close()
            thread.join(5)
