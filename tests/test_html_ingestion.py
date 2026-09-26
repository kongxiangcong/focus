from __future__ import annotations

import base64
import importlib.util
import io
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from core import IngestionApplication, SourceLibrary, WorkspaceError
from core.html_article import LocalHTMLParser
from core.reading_workspace import _validate_parser_bundle


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
        from host.service import HostService
        from host.server import Server
        service = HostService(self.workspace, self.root / "host-data", ingestion_parser=NoRemoteParser())
        server = Server(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
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
            self.assertEqual(self.source.read_bytes(), response.read())
            self.assertIn("sandbox;", response.getheader("Content-Security-Policy"))
            self.assertNotIn("allow-scripts", response.getheader("Content-Security-Policy"))
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            service.close()
            thread.join(5)
