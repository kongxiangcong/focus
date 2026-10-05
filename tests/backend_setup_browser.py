"""Real browser and storage; external inference, discovery and login are doubled."""
import sys, os, json, threading, subprocess
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.agents'), str(ROOT / 'tests')]
from host.backend_setup import BackendSetup
from host.workbench import Workbench
from host.server import Server
from test_workspace_portability import test_directory

calls = []
catalog_fail = [True]
deepseek_fail = [True]
def infer(self, payload):
    calls.append(('infer', payload['backend'], payload['model']))
    if payload['backend'] == 'deepseek' and deepseek_fail[0]:
        deepseek_fail[0] = False
        return {**self.inspect(payload), 'status': 'failed', 'message': '受控连接失败，可使用默认进入。'}
    return {**self.inspect(payload), 'status': 'success', 'message': '最小连接已通过。'}
def discover(self, payload, status):
    calls.append(('catalog', payload['backend']))
    if payload['backend'] == 'codex' and catalog_fail[0]:
        catalog_fail[0] = False
        raise OSError('controlled catalog failure')
    return ['real-' + payload['backend']]

def login_operation(self, action, payload):
    calls.append((action, payload['backend']))
    return {'backend': 'codex', 'runtimePath': None,
            'status': 'waiting' if action == 'login-start' else 'cancelled' if action == 'login-cancel' else 'authenticated',
            'message': 'controlled authorization', 'loginId': 'controlled-login',
            **({'authUrl': 'https://example.invalid/authorize'} if action == 'login-start' else {})}

with test_directory() as root, patch.object(BackendSetup, 'infer', infer), patch.object(BackendSetup, 'discover', discover), patch.object(BackendSetup, 'login_operation', login_operation):
    app = Workbench(settings_path=root / 'machine/settings.json')
    server = Server(('127.0.0.1', 0), app)
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    try:
        result = subprocess.run(['node', str(ROOT / 'tests/backend_setup_browser.mjs')], env={**os.environ,
            'FOCUS_BROWSER_OUTPUT': str(ROOT / 'tmp/workspace-portability'),
            'FOCUS_TEST_URL': f'http://127.0.0.1:{server.server_port}', 'FOCUS_TEST_ROOT': str(root)},
            timeout=120, capture_output=True, text=True, encoding='utf-8')
        print(result.stdout, result.stderr)
        (ROOT / 'tmp/workspace-portability/backend-browser-calls.json').write_text(json.dumps(calls), encoding='utf-8')
    finally:
        server.shutdown(); server.server_close(); worker.join(); app.close()
    sys.exit(result.returncode)
