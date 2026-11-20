"""Explicit candidate inspection through the Host and Runtime boundaries."""
from __future__ import annotations

import json
import queue
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from host.backends.base import Backend, BackendError
from host.backends.codex import CodexBackend
from host.ingestion_inspector import IngestionInspector
from host.runtime import AppServer
from host.service import HostService


class TextRuntime(Backend):
    """A text-only runtime with controlled replies at the Backend boundary."""

    def __init__(self, workspace, *, reply=None, failed=False, **options):
        super().__init__(workspace, **options)
        self.reply = reply if reply is not None else {
            "title_matches": True, "image_observed": True, "notes": "matches",
        }
        self.failed = failed

    def open_session(self, resume_key, *, instructions):
        self.resume_key = resume_key

    def start_turn(self, *, prompt):
        self.prompt = prompt
        self.emit("message/completed", {"itemId": "result", "text": json.dumps(self.reply)})
        self.emit("turn/completed", {"status": "failed" if self.failed else "completed"})


class IngestionRuntimeCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def candidate(self, *, images: int = 0) -> Path:
        bundle = self.root / "candidate"
        bundle.mkdir(exist_ok=True)
        (bundle / "source.pdf").write_bytes(b"%PDF-1.4\npaper\n")
        (bundle / "content.md").write_text("# Stored Paper\n\nBody.\n", encoding="utf-8")
        (bundle / "metadata.json").write_text(
            json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "article-parser",
                        "batch_id": "fixture-batch"}),
            encoding="utf-8",
        )
        for index in range(1, images + 1):
            (bundle / "images").mkdir(exist_ok=True)
            (bundle / "images" / f"image-{index:03d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        return bundle

    def test_invalid_candidates_never_reach_the_runtime(self):
        def backend_factory(**options):
            self.fail("Invalid candidate reached the backend factory")

        inspector = IngestionInspector(backend_factory)

        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(RuntimeError, "inspection inputs"):
            inspector.inspect(empty)

        untitled = self.candidate()
        (untitled / "content.md").write_text("Body without a title.\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "inspectable title"):
            inspector.inspect(untitled)

        wrong_provenance = self.candidate()
        (wrong_provenance / "metadata.json").write_text(
            json.dumps({"source_kind": "paper_pdf", "language": "en", "parser": "other"}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "provenance"):
            inspector.inspect(wrong_provenance)

    def test_wrong_result_shape_or_types_are_visible(self):
        candidate = self.candidate()
        for reply in ({"title_matches": True, "image_observed": False},
                      {"title_matches": 1, "image_observed": False, "notes": "match"},
                      {"title_matches": True, "image_observed": False, "notes": "x" * 501},
                      ["title_matches", "image_observed", "notes"]):
            with self.subTest(reply=reply):
                inspector = IngestionInspector(lambda workspace, purpose, tools: TextRuntime(workspace, reply=reply))
                with self.assertRaisesRegex(BackendError, "result shape is invalid"):
                    inspector.inspect(candidate)

    def test_failed_runtime_cannot_publish_a_result(self):
        inspector = IngestionInspector(lambda workspace, purpose, tools: TextRuntime(workspace, failed=True))
        with self.assertRaisesRegex(BackendError, "Runtime 调用失败"):
            inspector.inspect(self.candidate())
        self.assertFalse(inspector.cancel())

    def test_text_only_backend_reports_an_unobserved_figure(self):
        inspector = IngestionInspector(lambda workspace, purpose, tools: TextRuntime(workspace))
        result = inspector.inspect(self.candidate(images=1))

        self.assertFalse(result["image_observed"])
        self.assertEqual("backend_image_input_unavailable", result["image_observation_reason"])

    def test_host_explicit_inspection_uses_the_active_backend_without_business_tools(self):
        launched = []

        def factory(workspace, *, purpose, model, tools, **options):
            runtime = TextRuntime(workspace, model=model, tools=tools)
            launched.append((purpose, runtime))
            return runtime

        host = HostService(self.root / "workspace", self.root / "data", model="active-model",
                           backend_factory=factory, settings_path=self.root / "settings.json")
        self.addCleanup(host.close)
        candidate = self.candidate()
        with (candidate / "content.md").open("a", encoding="utf-8") as stream:
            stream.write("x" * 4000 + "outside excerpt")
        self.assertEqual([], launched)

        result = host.ingestion_inspector.inspect(candidate)

        purpose, runtime = launched[0]
        self.assertEqual("candidate", purpose)
        self.assertEqual("active-model", runtime.model)
        self.assertEqual([], runtime.tools)
        self.assertIsNone(runtime.resume_key)
        self.assertIn("# Stored Paper", runtime.prompt)
        self.assertNotIn("outside excerpt", runtime.prompt)
        self.assertTrue(result["title_matches"])
        self.assertFalse(result["image_observed"])
        self.assertEqual("no_figure", result["image_observation_reason"])
        self.assertFalse(runtime.workspace.exists())
        self.assertTrue(runtime.closed)

    def test_codex_inspection_attaches_a_copy_in_a_read_only_session(self):
        calls = {}

        class Protocol:
            def __init__(self, command, cwd, *, env):
                self.events = queue.Queue()
                self.cwd = cwd

            def initialize(self):
                pass

            def send(self, value):
                pass

            def request(self, method, params, timeout=60):
                calls[method] = params
                if method == "account/read":
                    return {"account": {"type": "chatgpt"}}
                if method == "thread/start":
                    return {"thread": {"id": "thread"}}
                if method == "turn/start":
                    for item in params["input"]:
                        if item["type"] == "localImage":
                            calls["image_copy"] = Path(item["path"]).read_bytes()
                    self.events.put({"method": "item/completed", "params": {"item": {
                        "type": "agentMessage", "id": "result", "text": json.dumps({
                            "title_matches": True, "image_observed": True, "notes": "legible",
                        }),
                    }}})
                    self.events.put({"method": "turn/completed", "params": {"turn": {"status": "completed"}}})
                    return {"turn": {"id": "turn"}}
                raise AssertionError(method)

            def close(self):
                calls["closed"] = True

        with patch("host.backends.codex.AppServer", Protocol):
            inspector = IngestionInspector(lambda **options: CodexBackend(model="fixture", **options))
            result = inspector.inspect(self.candidate(images=1))

        self.assertTrue(result["image_observed"])
        self.assertIsNone(result["image_observation_reason"])
        thread = calls["thread/start"]
        self.assertEqual([], thread["dynamicTools"])
        self.assertEqual("read-only", thread["sandbox"])
        self.assertEqual("never", thread["approvalPolicy"])
        self.assertTrue(thread["ephemeral"])
        figure = Path(calls["turn/start"]["input"][1]["path"])
        self.assertEqual(Path(thread["cwd"]), figure.parent)
        self.assertFalse(figure.parent.exists())
        self.assertEqual(b"\x89PNG\r\n\x1a\n", calls["image_copy"])
        self.assertTrue(calls["closed"])

    def test_cancel_releases_runtime_during_session_startup(self):
        entered = threading.Event()
        released = threading.Event()
        temporary = []

        class StalledProtocol:
            def __init__(self, command, cwd, *, env):
                temporary.append(cwd)

            def initialize(self):
                entered.set()
                released.wait(5)
                raise OSError("Runtime disconnected")

            def close(self):
                released.set()

        with patch("host.backends.codex.AppServer", StalledProtocol), ThreadPoolExecutor(2) as executor:
            inspector = IngestionInspector(lambda **options: CodexBackend(**options))
            inspected = executor.submit(inspector.inspect, self.candidate())
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(executor.submit(inspector.cancel).result(timeout=2))
                self.assertTrue(released.is_set())
                with self.assertRaisesRegex(BackendError, "已取消"):
                    inspected.result(timeout=2)
            finally:
                released.set()
        self.assertFalse(temporary[0].exists())

    def test_handshake_timeout_reaps_the_process_and_removes_the_temporary_directory(self):
        script = self.root / "stalled.py"
        script.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
        processes = []

        def launch(command, cwd, *, env):
            transport = AppServer([sys.executable, str(script)], cwd, env=env)
            processes.append((transport.process, cwd))
            return transport

        with patch("host.backends.codex.AppServer", launch):
            inspector = IngestionInspector(lambda **options: CodexBackend(**options), timeout=0.25)
            start = time.monotonic()
            with self.assertRaisesRegex(TimeoutError, "等待超时"):
                inspector.inspect(self.candidate())
            self.assertLess(time.monotonic() - start, 8)

        process, directory = processes[0]
        self.assertIsNotNone(process.poll())
        self.assertFalse(directory.exists())


if __name__ == "__main__":
    unittest.main()
