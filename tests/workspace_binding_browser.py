"""Isolated HTTP Workbench for the portability browser journey."""
import os
import sys
import threading
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.agents'), str(ROOT / 'tests')]
from test_workspace_portability import test_directory
from host.workbench import Workbench
from host.server import Server

with test_directory() as root:
    app = Workbench(settings_path=root / 'machine/settings.json', codex_bin=str(root / 'missing-runtime'))
    app.choose_directory = lambda: {'path': None}  # Picker cancellation; manual fallback remains real.
    server = Server(('127.0.0.1', 0), app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(['node', str(ROOT / 'tests/workspace_binding_browser.mjs')], env={**os.environ,
            'FOCUS_TEST_PYTHON': sys.executable, 'FOCUS_TEST_URL': f'http://127.0.0.1:{server.server_port}', 'FOCUS_TEST_ROOT': str(root)}, timeout=120, capture_output=True, text=True, encoding='utf-8')
        print(result.stdout)
        print(result.stderr)
        (ROOT / 'tmp/workspace-portability/browser-process.txt').write_text(str(result.returncode) + '\n' + result.stdout + '\n' + result.stderr, encoding='utf-8')
        if result.returncode == 0:
            old_path = app.host.workspace
            app.close()
            moved = root / '移动后的工作区'
            shutil.move(str(old_path), moved)
            app = Workbench(settings_path=root / 'machine/settings.json')
            server.service = server.workbench = app
            result = subprocess.run(['node', str(ROOT / 'tests/workspace_binding_browser.mjs')], env={**os.environ,
                'FOCUS_TEST_URL': f'http://127.0.0.1:{server.server_port}', 'FOCUS_TEST_ROOT': str(root),
                'FOCUS_TEST_RECOVERY': str(moved)}, timeout=60, capture_output=True, text=True, encoding='utf-8')
            print(result.stdout, result.stderr)
    finally:
        server.shutdown(); server.server_close(); thread.join(3); app.close()
    sys.exit(result.returncode)
