"""Backend setup through Host public operations; only external processes are doubled."""
import tempfile
import queue
import os
import sys
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

from host.service import HostService


class AccountRuntime:
    instances = []
    account_type = 'chatgpt'

    def __init__(self, command, cwd, *, env=None):
        self.command, self.env = command, env
        self.events = queue.Queue()
        self.closed = False
        self.calls = []
        self.instances.append(self)

    def initialize(self):
        return {}

    def send(self, value):
        pass

    def request(self, method, params, timeout=60):
        self.calls.append((method, params))
        if method == 'account/read':
            return {'account': {'type': self.account_type} if self.account_type else None}
        if method == 'account/login/start':
            return {'loginId': 'login-1', 'authUrl': 'https://auth.openai.com/test'}
        if method == 'account/login/cancel':
            return {'status': 'canceled'}
        raise AssertionError(method)

    def close(self):
        self.closed = True


class HarnessRuntime:
    instances = []

    def __init__(self, **kwargs):
        self.options = kwargs
        self.closed = False
        self.instances.append(self)

    def start(self):
        pass

    def run(self, prompt, *, session_id):
        return SimpleNamespace(final_response='FOCUS_OK', finish_reason='completed', events=[])

    def close(self):
        self.closed = True


class BackendSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.host = HostService(self.root / 'kb', self.root / 'host')

    def tearDown(self):
        self.host.close()
        self.temporary.cleanup()

    def test_explicit_missing_runtime_is_reported_without_fallback_or_business_changes(self):
        before = self.host.snapshot()
        result = self.host.backend_setup('inspect', {
            'backend': 'codex', 'runtimePath': str(self.root / 'missing.exe'),
        })
        self.assertEqual('unavailable', result['status'])
        self.assertEqual(str(self.root / 'missing.exe'), result['runtimePath'])
        self.assertEqual(before, self.host.snapshot())

    def test_account_check_uses_selected_runtime_shared_home_and_never_api_key_login(self):
        binary = self.root / 'codex.exe'
        binary.touch()
        AccountRuntime.account_type = 'chatgpt'
        with patch('host.backend_setup.AppServer', AccountRuntime), patch.dict('os.environ', {
            'OPENAI_API_KEY': 'must-not-reach-runtime', 'CODEX_HOME': str(self.root / 'personal-codex'),
        }):
            result = self.host.backend_setup('account', {'backend': 'codex', 'runtimePath': str(binary)})
        self.assertEqual('authenticated', result['status'])
        runtime = AccountRuntime.instances[-1]
        self.assertEqual(str(binary), runtime.command[0])
        self.assertNotIn('OPENAI_API_KEY', runtime.env)
        self.assertEqual(str(self.root / 'personal-codex'), runtime.env['CODEX_HOME'])
        self.assertEqual(['account/read'], [method for method, _ in runtime.calls])
        self.assertTrue(runtime.closed)

    def test_deepseek_check_loads_host_credential_file_and_does_not_activate_or_append(self):
        binary = self.root / 'dsh.exe'
        binary.touch()
        secret = self.root / '.env'
        secret.write_text('DEEPSEEK_API_KEY="fixture-key"\n', encoding='utf-8')
        before = self.host.snapshot()
        with patch('deepseek_harness.DeepSeekHarness', HarnessRuntime):
            result = self.host.backend_setup('check', {'backend': 'deepseek',
                'runtimePath': str(binary), 'credentialFile': str(secret), 'model': 'deepseek-v4-flash'})
        self.assertEqual('success', result['status'])
        self.assertEqual(before, self.host.snapshot())
        self.assertNotIn('fixture-key', str(result))
        self.assertEqual('fixture-key', HarnessRuntime.instances[-1].options['api_key'])
        self.assertTrue(HarnessRuntime.instances[-1].closed)

    def test_browser_login_requires_completion_and_account_recheck_and_can_cancel(self):
        binary = self.root / 'codex.exe'
        binary.touch()
        config = {'backend': 'codex', 'runtimePath': str(binary)}
        AccountRuntime.account_type = None
        with patch('host.backend_setup.AppServer', AccountRuntime):
            started = self.host.backend_setup('login-start', config)
            self.assertEqual('waiting', started['status'])
            runtime = AccountRuntime.instances[-1]
            waiting = self.host.backend_setup('login-status', {**config, 'loginId': started['loginId']})
            self.assertEqual('waiting', waiting['status'])
            cancelled = self.host.backend_setup('login-cancel', {**config, 'loginId': started['loginId']})
            self.assertEqual('cancelled', cancelled['status'])
            self.assertTrue(runtime.closed)

    def test_prepare_reports_explicit_bad_path_without_installing_or_logging_in(self):
        with patch('subprocess.run') as process:
            result = self.host.backend_setup('prepare', {'backend': 'deepseek',
                'runtimePath': str(self.root / 'missing.exe')})
        self.assertEqual('unavailable', result['status'])
        process.assert_not_called()

    def test_provider_failure_is_actionable_without_echoing_secret_diagnostics(self):
        binary = self.root / 'dsh.exe'
        binary.touch()
        with patch('deepseek_harness.DeepSeekHarness', side_effect=RuntimeError('quota exhausted sk-private-token')), \
                patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'fixture-key'}):
            result = self.host.backend_setup('check', {'backend': 'deepseek', 'runtimePath': str(binary)})
        self.assertEqual('failed', result['status'])
        self.assertIn('额度不足', result['message'])
        self.assertNotIn('sk-private-token', str(result))

    def test_oauth_completion_is_not_success_until_runtime_reports_chatgpt_account(self):
        binary = self.root / 'codex.exe'
        binary.touch()
        config = {'backend': 'codex', 'runtimePath': str(binary)}
        for account_type, expected in [('apiKey', 'failed'), ('chatgpt', 'authenticated')]:
            with self.subTest(account_type=account_type), patch('host.backend_setup.AppServer', AccountRuntime):
                started = self.host.backend_setup('login-start', config)
                AccountRuntime.account_type = account_type
                runtime = AccountRuntime.instances[-1]
                runtime.events.put({'method': 'account/login/completed', 'params': {'loginId': started['loginId'], 'success': True}})
                result = self.host.backend_setup('login-status', {**config, 'loginId': started['loginId']})
                self.assertEqual(expected, result['status'])
                self.assertTrue(runtime.closed)

    def test_failed_install_is_independent_of_other_ready_backend(self):
        binary = self.root / 'codex.exe'
        binary.touch()
        import subprocess
        with patch('host.backend_setup.shutil.which', return_value=None), \
                patch('deepseek_harness_runtime.bundled_runtime_path', side_effect=FileNotFoundError()), \
                patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, ['pip'])):
            failed = self.host.backend_setup('prepare', {'backend': 'deepseek'})
            ready = self.host.backend_setup('prepare', {'backend': 'codex', 'runtimePath': str(binary)})
        self.assertEqual('failed', failed['status'])
        self.assertEqual('installed', ready['status'])

    def test_business_turn_refuses_stored_api_key_authentication(self):
        AccountRuntime.account_type = 'apiKey'
        with patch('host.backends.codex.AppServer', AccountRuntime):
            self.host.start({'requestId': 'auth-test-001', 'content': 'hello'})
            self.host.worker.join(timeout=5)
        self.assertEqual('failed', self.host.snapshot()['agent']['run']['status'])
        self.assertFalse(any(method == 'turn/start' for method, _ in AccountRuntime.instances[-1].calls))

    def test_connectivity_turn_keeps_no_tools_readonly_and_no_approval_policy(self):
        class ModelRuntime(AccountRuntime):
            def request(self, method, params, timeout=60):
                if method == 'thread/start':
                    self.calls.append((method, params))
                    return {'thread': {'id': 'check-thread'}}
                if method == 'turn/start':
                    self.calls.append((method, params))
                    self.events.put({'method': 'item/completed', 'params': {
                        'item': {'type': 'agentMessage', 'id': 'answer', 'text': 'FOCUS_OK'}}})
                    self.events.put({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})
                    return {'turn': {'id': 'check-turn'}}
                return super().request(method, params, timeout)
        binary = self.root / 'codex.exe'
        binary.touch()
        AccountRuntime.account_type = 'chatgpt'
        with patch('host.backends.codex.AppServer', ModelRuntime):
            result = self.host.backend_setup('check', {'backend': 'codex', 'runtimePath': str(binary)})
        self.assertEqual('success', result['status'])
        calls = dict(ModelRuntime.instances[-1].calls)
        self.assertEqual([], calls['thread/start']['dynamicTools'])
        self.assertEqual('readOnly', calls['turn/start']['sandboxPolicy']['type'])
        self.assertEqual('never', calls['turn/start']['approvalPolicy'])

    @unittest.skipUnless(os.name == 'nt', 'Windows command launcher lifecycle')
    def test_unresponsive_windows_launcher_child_is_released_after_check(self):
        script = self.root / 'blocked-runtime.py'
        pid_file = self.root / 'child.pid'
        script.write_text('import os,time\nfrom pathlib import Path\n'
                          f'Path({str(pid_file)!r}).write_text(str(os.getpid()))\ntime.sleep(120)\n', encoding='utf-8')
        launcher = self.root / 'codex.cmd'
        launcher.write_text(f'@"{sys.executable}" "{script}"\n', encoding='utf-8')
        result = self.host.backend_setup('check', {'backend': 'codex', 'runtimePath': str(launcher)})
        self.assertEqual('failed', result['status'])
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x00100000, False, int(pid_file.read_text()))
        if handle:
            try:
                self.assertEqual(0, kernel.WaitForSingleObject(ctypes.c_void_p(handle), 5000))
            finally:
                kernel.CloseHandle(ctypes.c_void_p(handle))


if __name__ == '__main__':
    unittest.main()
