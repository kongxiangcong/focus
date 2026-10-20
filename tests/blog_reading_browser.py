"""Isolated real Host/Core browser flow with a deterministic writing Runtime."""
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / ".agents"), str(ROOT / "tests")]
from test_blog_host import BlogHostTests, Server

fixture = BlogHostTests()
fixture.setUp()
original = fixture.runtime.write_artifact
attempts = []


def fail_once(**kwargs):
    attempts.append(kwargs["artifact"])
    if len(attempts) == 1:
        raise RuntimeError("Browser fixture: first writing attempt failed")
    return original(**kwargs)


fixture.runtime.write_artifact = fail_once
server = Server(("127.0.0.1", 0), fixture.host)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    result = subprocess.run(
        ["node", str(ROOT / "tests/blog_reading_browser.mjs")],
        env={**os.environ, "FOCUS_TEST_URL": f"http://127.0.0.1:{server.server_port}"},
    )
    if result.returncode == 0:
        assert attempts == ["reading_blog", "reading_blog"], attempts
        assert fixture.host.blog_status("Fixture-paper")["methodVersion"] == "article-blog-v2"
        print("PASS: only reading writer invoked; v2 metadata published", flush=True)
finally:
    server.shutdown()
    server.server_close()
    thread.join()
    fixture.tearDown()
sys.exit(result.returncode)
