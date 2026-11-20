"""Public CLI and Workbench responses for temporary Backend selection."""
import http.client
import json
import os
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from test_workspace_portability import test_directory as fixture_directory

ROOT = Path(__file__).resolve().parents[1]


def startup_environment(settings, **overrides):
    environment = {name: value for name, value in os.environ.items() if name not in {
        'FOCUS_BACKEND', 'FOCUS_BACKEND_BIN', 'FOCUS_MODEL', 'FOCUS_BACKENDS_DIR', 'FOCUS_WORKSPACE',
    }}
    return {**environment, 'FOCUS_SETTINGS_FILE': str(settings), 'PYTHONUTF8': '1', **overrides}


class BackendStartupTests(unittest.TestCase):
    def test_check_runtime_accepts_a_custom_backend_and_explicit_binary(self):
        with fixture_directory() as root:
            manifests = root / 'custom'
            self._manifest(manifests, 'example')
            result = subprocess.run([sys.executable, '-m', 'host', '--check-runtime',
                '--backends-dir', str(manifests), '--backend', 'example', '--backend-bin', sys.executable],
                cwd=ROOT, env=startup_environment(root / 'settings.json', FOCUS_BACKEND='unknown',
                    FOCUS_BACKEND_BIN=str(root / 'missing.exe')), capture_output=True, text=True, timeout=15)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('example:', result.stdout)
            self.assertIn(str(Path(sys.executable).resolve()), result.stdout)

    def test_overrides_survive_workspace_changes_and_restart_restores_saved_values(self):
        with fixture_directory() as root:
            settings = root / 'settings.json'
            stored = {'backend': 'codex', 'model': 'saved-model', 'runtimePath': sys.executable}
            settings.write_text(json.dumps(stored), encoding='utf-8')
            manifests = root / 'backends'
            self._manifest(manifests, 'example')
            self._manifest(manifests, 'environment')
            env_only = startup_environment(settings, FOCUS_BACKEND='environment',
                    FOCUS_BACKEND_BIN=str(Path(sys.executable).resolve()), FOCUS_MODEL='environment-model')
            with _start_host(env_only) as connection:
                config = _request(connection, '/reader/configuration')
                self.assertEqual('environment', config['effective']['backend'])
                self.assertEqual('environment-model', config['effective']['model'])
                self.assertEqual(str(Path(sys.executable).resolve()), config['effective']['runtimePath'])
                self.assertEqual('codex', config['saved']['backend'])
            env_conflict = {**env_only, 'FOCUS_BACKEND_BIN': str(root / 'missing.exe')}
            with _start_host(env_conflict, '--backend', 'example', '--backend-bin', sys.executable,
                             '--model', 'cli-model') as connection:
                for name in ('first', 'second'):
                    binding = _request(connection, '/reader/workspace')
                    _request(connection, '/reader/workspace', {
                        'mode': 'create', 'path': str(root), 'name': name, 'generation': binding['generation'],
                    })
                    config = _request(connection, '/reader/configuration')
                    self.assertEqual('example', config['effective']['backend'])
                    self.assertEqual('cli-model', config['effective']['model'])
                    self.assertEqual(str(Path(sys.executable).absolute()), config['effective']['runtimePath'])
                    self.assertEqual('saved-model', config['saved']['model'])
            self.assertEqual(stored, {key: json.loads(settings.read_text(encoding='utf-8'))[key] for key in stored})
            with _start_host(startup_environment(settings)) as connection:
                config = _request(connection, '/reader/configuration')
                self.assertEqual('codex', config['effective']['backend'])
                self.assertEqual('saved-model', config['effective']['model'])

    def test_invalid_explicit_backend_leaves_library_and_rejects_ai_without_fallback(self):
        with fixture_directory() as root:
            settings = root / 'settings.json'
            settings.write_text(json.dumps({'backend': 'codex', 'model': 'saved-model', 'runtimePath': sys.executable}),
                                encoding='utf-8')
            manifests = root / 'backends'
            self._manifest(manifests, 'example')
            for args, reason in ((('--backend', 'missing-id'), 'missing-id'),
                                 (('--backend', 'example', '--backend-bin', str(root / 'missing.exe')), 'missing.exe')):
                with self.subTest(reason=reason), _start_host(startup_environment(settings), *args) as connection:
                    binding = _request(connection, '/reader/workspace')
                    if not binding['bound']:
                        binding = _request(connection, '/reader/workspace', {
                            'mode': 'create', 'path': str(root), 'name': 'library', 'generation': binding['generation'],
                        })
                    headers = {'X-FOCUS-Instance': binding['workspace']['instanceId']}
                    config = _request(connection, '/reader/configuration')
                    self.assertIn(reason, config['startupError'])
                    self.assertEqual([], _request(connection, '/library/topics', headers=headers))
                    error = _request(connection, '/reader/messages', {
                        'requestId': 'not-routed', 'content': 'Do not send this to any other Backend.',
                    }, headers=headers, expected=400)
                    self.assertIn(reason, error['message'])
                    self.assertEqual([], _request(connection, '/reader/window', headers=headers)['conversation'])

    @staticmethod
    def _manifest(folder, identifier):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f'{identifier}.json').write_text(json.dumps({
            'id': identifier, 'driver': 'acp', 'label': identifier,
            'command': [sys.executable, 'not-a-runtime.py'], 'defaultModel': 'manifest-model',
        }), encoding='utf-8')


@contextmanager
def _start_host(environment, *arguments):
    with subprocess.Popen([sys.executable, '-m', 'host', '--port', '0', *arguments],
            cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8') as process:
        try:
            announcement = process.stdout.readline()
            if not announcement.startswith('FOCUS http://'):
                raise AssertionError('Host startup failed: ' + process.stderr.read())
            port = urlsplit(announcement.removeprefix('FOCUS ').strip()).port
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
            try:
                yield connection
            finally:
                connection.close()
        finally:
            process.terminate()
            process.communicate(timeout=10)


def _request(connection, path, value=None, *, headers=None, expected=200):
    headers = dict(headers or {})
    if value is not None:
        headers['Content-Type'] = 'application/json'
    connection.request('GET' if value is None else 'POST', path, json.dumps(value) if value is not None else None,
                       headers=headers)
    response = connection.getresponse()
    body = json.loads(response.read())
    if response.status != expected:
        raise AssertionError(f'{path}: expected {expected}, received {response.status}: {body}')
    return body['value'] if body['ok'] else body['error']
