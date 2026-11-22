"""Run the public Workbench in Chrome with local ACP protocol fixtures."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.agents'), str(ROOT / 'tests')]
from host.backends.registry import HarnessRegistry
from host.server import Server
from host.workbench import Workbench
from test_workspace_portability import test_directory


def main():
    output = Path(os.getenv('FOCUS_BROWSER_OUTPUT') or ROOT / 'tmp/workspace-portability').resolve()
    output.mkdir(parents=True, exist_ok=True)
    with test_directory() as root:
        manifests = root / 'machine' / 'backends'
        manifests.mkdir(parents=True)
        process_log = root / 'wire.jsonl'
        fixture = ROOT / 'tests/acp_runtime_fixture.py'
        for name, label, command in (
            ('fixture-alpha', 'Fixture Alpha', [sys.executable, str(fixture), 'http', str(process_log)]),
            ('fixture-beta', 'Fixture Beta', [sys.executable, str(fixture), 'stdio', str(process_log)]),
            ('fixture-bad', 'Fixture Bad', [sys.executable, '-c', 'raise SystemExit(2)']),
        ):
            (manifests / f'{name}.json').write_text(json.dumps({
                'id': name, 'label': label, 'driver': 'acp', 'command': command,
                'defaultModel': 'selected-model', 'capabilities': {'modelDiscovery': 'acp-config-option'},
            }), encoding='utf-8')
        (manifests / 'invalid.json').write_text('{malformed', encoding='utf-8')
        (manifests / 'duplicate.json').write_text(json.dumps({
            'id': 'codex', 'label': 'Duplicate Codex', 'driver': 'acp', 'command': [sys.executable],
        }), encoding='utf-8')

        discover_binary = HarnessRegistry._discover_binary

        def fixture_binary(catalog, spec):
            return discover_binary(catalog, spec) if spec.id.startswith('fixture-') else None

        overrides = {name: '' for name in ('FOCUS_BACKEND', 'FOCUS_BACKEND_BIN', 'FOCUS_MODEL', 'FOCUS_BACKENDS_DIR')}
        with patch.dict(os.environ, overrides), patch.object(HarnessRegistry, '_discover_binary', fixture_binary):
            app = Workbench(settings_path=root / 'machine/settings.json')
            server = Server(('127.0.0.1', 0), app)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                env = {**os.environ, 'FOCUS_BROWSER_OUTPUT': str(output),
                       'FOCUS_TEST_URL': f'http://127.0.0.1:{server.server_port}', 'FOCUS_TEST_ROOT': str(root),
                       'FOCUS_FIXTURE_LOG': str(process_log)}
                result = subprocess.run(['node', str(ROOT / 'tests/backend_setup_browser.mjs')], env=env,
                                        timeout=120, capture_output=True, text=True, encoding='utf-8')
                print(result.stdout, end='')
                print(result.stderr, end='', file=sys.stderr)
            finally:
                server.shutdown()
                server.server_close()
                worker.join()
                app.close()
                events = ([json.loads(line) for line in process_log.read_text(encoding='utf-8').splitlines()]
                          if process_log.exists() else [])
                (output / 'backend-browser-calls.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
