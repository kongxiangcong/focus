from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import json
import os
import shutil
import unittest
import urllib.error
import uuid
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PARSER = importlib.import_module("core.mineru")
WORKSPACE_CORE = importlib.import_module("core.reading_workspace")
SOURCE_LIBRARY = importlib.import_module("core.source_library")


class MinerUTransportTests(unittest.TestCase):
    def setUp(self):
        test_runs = ROOT / "tmp" / "test-runs"
        test_runs.mkdir(parents=True, exist_ok=True)
        self.root = test_runs / f"mineru-transport-{uuid.uuid4().hex}"
        self.root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_normalize_builds_compact_bundle_and_rewrites_images_in_reference_order(self):
        source = self.root / "input.pdf"
        source.write_bytes(b"%PDF-1.4\nfixture\n")
        archive = self.root / "result.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(
                "paper/full.md",
                "# Fixture Paper\n\n![Second](images/z.png)\n\n![First](images/a.jpg)\n",
            )
            bundle.writestr("paper/images/a.jpg", b"first-image")
            bundle.writestr("paper/images/z.png", b"second-image")
            bundle.writestr("paper/images/unreferenced.png", b"unused-image")
            bundle.writestr("paper/fixture_content_list.json", "[]")
        output = self.root / "output"

        PARSER._normalize(source, archive, output, "batch-fixture", "vlm", "en")

        self.assertEqual(source.read_bytes(), (output / "source.pdf").read_bytes())
        paper = (output / "content.md").read_text(encoding="utf-8")
        self.assertIn("![Second](images/image-001.png)", paper)
        self.assertIn("![First](images/image-002.jpg)", paper)
        self.assertEqual(b"second-image", (output / "images" / "image-001.png").read_bytes())
        self.assertEqual(b"first-image", (output / "images" / "image-002.jpg").read_bytes())
        self.assertFalse((output / "raw").exists())
        self.assertFalse((output / "images" / "unreferenced.png").exists())
        metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual("article-parser", metadata["parser"])
        self.assertEqual("source-reference-order", metadata["image_naming"])
        self.assertNotIn("token", json.dumps(metadata).lower())
        self.assertNotIn("hash", json.dumps(metadata).lower())
        validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
        self.assertTrue(validation["ok"])
        self.assertNotIn("hash", json.dumps(validation).lower())

    def test_ingestion_adapter_persists_reference_and_uses_evidenced_deepstack_short_name(self):
        source = self.root / "input.pdf"
        source.write_bytes(b"%PDF fixture")
        candidate = self.root / "candidate"

        class Hosted:
            def start(self, source, *, model, language, ocr, on_reference):
                on_reference("batch-fixture")
                return "batch-fixture"

            def complete(self, source, output, **kwargs):
                (output / "images").mkdir(parents=True)
                shutil.copy2(source, output / "source.pdf")
                (output / "content.md").write_text(
                    "# DeepStack: Scalable Design Space Exploration\n", encoding="utf-8"
                )
                (output / "metadata.json").write_text(
                    '{"source_kind":"paper_pdf","language":"en","parser":"article-parser","batch_id":"batch-fixture"}',
                    encoding="utf-8",
                )
                (output / "validation.json").write_text('{"ok":true,"warnings":[]}', encoding="utf-8")

        checkpoints = []
        result = PARSER.MinerUIngestionParser(hosted=Hosted()).parse(
            source, candidate, checkpoint=checkpoints.append
        )
        self.assertEqual("DeepStack", result["short_name"])
        self.assertEqual(
            [{"reference_kind": "batch_id", "reference_id": "batch-fixture"}], checkpoints
        )

    def test_safe_extract_rejects_path_traversal(self):
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../escape.txt", "bad")
        with self.assertRaises(PARSER.ParserError):
            PARSER._safe_extract(archive, self.root / "output")

    def test_signed_upload_url_is_passed_to_curl_over_stdin(self):
        source = self.root / "input.pdf"
        source.write_bytes(b"%PDF fixture")
        signed_url = "https://storage.example/upload?signature=secret"

        with mock.patch.object(PARSER.shutil, "which", return_value="curl.exe"):
            with mock.patch.object(PARSER.subprocess, "run") as run:
                run.return_value.returncode = 0
                PARSER._upload(signed_url, source)

        args, kwargs = run.call_args
        self.assertNotIn(signed_url, args[0])
        self.assertIn(signed_url, kwargs["input"])
        self.assertIn(json.dumps(str(source)), kwargs["input"])

    def test_token_falls_back_to_dotenv_without_overriding_environment(self):
        (self.root / ".env").write_text("# local secret\nMINERU_API_TOKEN=dotenv-token\n", encoding="utf-8")
        previous_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("MINERU_API_TOKEN", None)
                self.assertEqual("dotenv-token", PARSER._token())
            with mock.patch.dict(os.environ, {"MINERU_API_TOKEN": "environment-token"}):
                self.assertEqual("environment-token", PARSER._token())
        finally:
            os.chdir(previous_cwd)

    def test_http_errors_do_not_relay_remote_body_that_may_contain_credentials(self):
        remote_error = urllib.error.HTTPError(
            "https://mineru.net/api/v4/file-urls/batch",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b"echoed-token-value"),
        )
        try:
            with mock.patch.object(PARSER.urllib.request, "urlopen", side_effect=remote_error):
                with self.assertRaises(PARSER.ParserError) as caught:
                    PARSER._request("GET", "https://mineru.net/api/v4/file-urls/batch", token="token")
        finally:
            remote_error.close()

        self.assertNotIn("echoed-token-value", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
