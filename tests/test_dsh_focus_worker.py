"""Cross-host and cancellation evidence for the managed DSH worker."""
from __future__ import annotations

import importlib.util
import re
import tempfile
import time
import unittest
from pathlib import Path

from host.service import HostService


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("focus_dsh_worker", ROOT / "integrations" / "dsh-focus" / "worker.py")
DSH = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(DSH)


def wait_host(host: HostService, source_id: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = host.blog_status(source_id)
        worker = host.blog_workers.get(source_id)
        if not (worker and worker.is_alive()) and status["runStatus"] in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.01)
    raise AssertionError("Standalone Host blog attempt did not finish")


class DshFocusWorkerTests(unittest.TestCase):
    def test_controlled_candidate_is_identical_across_dsh_and_standalone_hosts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dsh_workspace = root / "dsh"
            standalone_workspace = root / "standalone"
            dsh = DSH.Worker(ROOT, dsh_workspace)
            DSH.prepare_fixture(standalone_workspace)
            standalone = HostService(
                standalone_workspace,
                root / "standalone-host",
                blog_runtime=DSH.ControlledRuntime(),
            )
            try:
                standalone.blog_generate(DSH.SOURCE_ID, request_id="standalone-fixture", authorized_by="manual_trigger")
                standalone_status = wait_host(standalone, DSH.SOURCE_ID)
                dsh_status = dsh.status(DSH.SOURCE_ID)

                relative_assets = (
                    "blog.md",
                    "value-analysis.md",
                    "evidence/evidence-map.md",
                    "index.html",
                )
                for relative in relative_assets:
                    dsh_bytes = (dsh_workspace / "sources" / DSH.SOURCE_ID / "blog" / relative).read_bytes()
                    standalone_bytes = (standalone_workspace / "sources" / DSH.SOURCE_ID / "blog" / relative).read_bytes()
                    if relative == "index.html":
                        # Host execution time is the only allowed rendering difference.
                        dsh_bytes = re.sub(rb"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", b"<generated-at>", dsh_bytes)
                        standalone_bytes = re.sub(rb"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", b"<generated-at>", standalone_bytes)
                    self.assertEqual(dsh_bytes, standalone_bytes, relative)
                self.assertEqual("completed", dsh_status["runStatus"])
                self.assertEqual("completed", standalone_status["runStatus"])
                for artifact in ("reading_blog", "value_analysis", "html"):
                    self.assertEqual(
                        dsh_status["artifacts"][artifact]["status"],
                        standalone_status["artifacts"][artifact]["status"],
                    )
                    self.assertEqual(
                        dsh_status["artifacts"][artifact].get("warnings", []),
                        standalone_status["artifacts"][artifact].get("warnings", []),
                    )
            finally:
                standalone.close()

    def test_cancelled_dsh_attempt_cannot_publish_its_late_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "dsh"
            worker = DSH.Worker(ROOT, workspace)
            published = (workspace / "sources" / DSH.SOURCE_ID / "blog" / "blog.md").read_bytes()
            worker.runtime.reading_blog += "\n\n这个迟到候选不能发布。\n"

            worker.regenerate(DSH.SOURCE_ID, "cancel-request", "attempt-cancel", hold=True)
            receipt = worker.cancel(DSH.SOURCE_ID, "attempt-cancel")

            self.assertEqual("cancelled", receipt["runStatus"])
            self.assertEqual(published, (workspace / "sources" / DSH.SOURCE_ID / "blog" / "blog.md").read_bytes())
            self.assertIsNone(worker.active)


if __name__ == "__main__":
    unittest.main()
