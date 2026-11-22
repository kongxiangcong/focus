"""Backend setup through Host public operations; only external processes are doubled."""
import tempfile
import queue
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from acp_protocol_fixture import AcpProtocolFixture
from workspace_fixture import HostService


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


class CredentialRuntime(AcpProtocolFixture):
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instances.append(self)


class BackendSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.host = HostService(self.root / 'kb', self.root / 'host', backend='codex')

    def tearDown(self):
        self.host.close()
        self.temporary.cleanup()

    def business_state(self):
        return {key: value for key, value in self.host.snapshot().items() if key != 'revision'}

    def test_explicit_missing_runtime_is_reported_without_fallback_or_business_changes(self):
        before = self.business_state()
        result = self.host.backend_setup('inspect', {
            'backend': 'codex', 'runtimePath': str(self.root / 'missing.exe'),
        })
        self.assertEqual('unavailable', result['status'])
        self.assertEqual(str(self.root / 'missing.exe'), result['runtimePath'])
        self.assertEqual(before, self.business_state())

    def test_account_check_uses_selected_runtime_shared_home_and_never_api_key_login(self):
        binary = self.root / 'codex.exe'
        binary.touch()
        AccountRuntime.account_type = 'chatgpt'
        with patch('host.backends.codex.AppServer', AccountRuntime), patch.dict('os.environ', {
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
        binary.chmod(0o700)
        secret = self.root / '.env'
        secret.write_text('DEEPSEEK_API_KEY="fixture-key"\n', encoding='utf-8')
        before = self.business_state()
        with patch('host.backends.acp.JsonRpcStdioClient', CredentialRuntime):
            result = self.host.backend_setup('check', {'backend': 'deepseek',
                'runtimePath': str(binary), 'credentialFile': str(secret), 'model': 'deepseek-v4-flash'})
        self.assertEqual('success', result['status'])
        self.assertEqual(before, self.business_state())
        self.assertNotIn('fixture-key', str(result))
        runtime = CredentialRuntime.instances[-1]
        self.assertEqual('fixture-key', runtime.env['DEEPSEEK_API_KEY'])
        self.assertEqual(('--profile', 'acp'), runtime.command[1:])
        self.assertTrue(runtime.closed)

    def test_browser_login_requires_completion_and_account_recheck_and_can_cancel(self):
        binary = self.root / 'codex.exe'
        binary.touch()
        config = {'backend': 'codex', 'runtimePath': str(binary)}
        AccountRuntime.account_type = None
        with patch('host.backends.codex.AppServer', AccountRuntime):
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
        binary.chmod(0o700)
        with patch('host.backends.acp.JsonRpcStdioClient', side_effect=RuntimeError('quota exhausted sk-private-token')), \
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
            with self.subTest(account_type=account_type), patch('host.backends.codex.AppServer', AccountRuntime):
                started = self.host.backend_setup('login-start', config)
                AccountRuntime.account_type = account_type
                runtime = AccountRuntime.instances[-1]
                runtime.events.put({'method': 'account/login/completed', 'params': {'loginId': started['loginId'], 'success': True}})
                result = self.host.backend_setup('login-status', {**config, 'loginId': started['loginId']})
                self.assertEqual(expected, result['status'])
                self.assertTrue(runtime.closed)

    def test_missing_runtime_is_independent_of_other_ready_backend(self):
        binary = self.root / 'codex.exe'
        binary.touch()
        with patch('subprocess.Popen') as process:
            failed = self.host.backend_setup('prepare', {'backend': 'deepseek',
                'runtimePath': str(self.root / 'missing.exe')})
            ready = self.host.backend_setup('prepare', {'backend': 'codex', 'runtimePath': str(binary)})
            process.assert_not_called()
        self.assertEqual('unavailable', failed['status'])
        self.assertEqual('installed', ready['status'])

    def test_business_turn_refuses_stored_api_key_authentication(self):
        AccountRuntime.account_type = 'apiKey'
        with patch('host.backends.codex.AppServer', AccountRuntime):
            self.host.start({'requestId': 'auth-test-001', 'content': 'hello'})
            self.host.worker.join(timeout=5)
        self.assertEqual('failed', self.host.snapshot()['agent']['run']['status'])
        self.assertFalse(any(method == 'turn/start' for method, _ in AccountRuntime.instances[-1].calls))

    def test_connectivity_requires_the_temporary_source_mark_in_the_final_answer(self):
        class ModelRuntime(AccountRuntime):
            mode = 'final'

            def __init__(self, command, cwd, *, env=None):
                super().__init__(command, cwd, env=env)
                self.cwd = Path(cwd)
                self.marker = None

            def complete(self, text, item='answer'):
                self.events.put({'method': 'item/completed', 'params': {
                    'item': {'type': 'agentMessage', 'id': item, 'text': text}}})

            def finish(self):
                self.events.put({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})

            def request(self, method, params, timeout=60):
                if method == 'thread/start':
                    self.calls.append((method, params))
                    return {'thread': {'id': 'check-thread'}}
                if method == 'turn/start':
                    self.calls.append((method, params))
                    if self.mode == 'text-only':
                        self.complete('FOCUS_OK')
                        self.finish()
                    else:
                        tools = dict(self.calls)['thread/start']['dynamicTools']
                        if not tools:
                            self.complete('The runtime has no source tool.')
                            self.finish()
                            return {'turn': {'id': 'check-turn'}}
                        self.events.put({'id': 'read-source', 'method': 'item/tool/call', 'params': {'tool': 'focus',
                            'arguments': {'action': 'search' if self.mode == 'wrong-action' else 'read_range',
                                          'arguments': '{"start":1,"end":1}'}}})
                    return {'turn': {'id': 'check-turn'}}
                return super().request(method, params, timeout)

            def send(self, value):
                if value.get('id') != 'read-source':
                    return
                result = value.get('result', {})
                if self.mode == 'wrong-action':
                    assert not result.get('success'), value
                    self.complete('Wrong marker')
                else:
                    assert result['success'], value
                    self.marker = json.loads(result['contentItems'][0]['text'])['source_text']
                    if self.mode == 'wrong-answer':
                        self.complete('Wrong marker')
                    elif self.mode == 'superseded':
                        self.complete(self.marker, item='commentary')
                        self.complete('Final answer without the marker')
                    elif self.mode == 'stream':
                        for part in (self.marker[:5], self.marker[5:]):
                            self.events.put({'method': 'item/agentMessage/delta',
                                             'params': {'itemId': 'answer', 'delta': part}})
                    else:
                        self.complete(self.marker)
                self.finish()

        binary = self.root / 'codex.exe'
        binary.touch()
        AccountRuntime.account_type = 'chatgpt'
        before = self.business_state()
        markers = set()
        for mode, status in [('text-only', 'failed'), ('wrong-action', 'failed'), ('wrong-answer', 'failed'),
                             ('superseded', 'failed'), ('final', 'success'), ('stream', 'success')]:
            with self.subTest(mode=mode), patch('host.backends.codex.AppServer', ModelRuntime):
                ModelRuntime.mode = mode
                result = self.host.backend_setup('check', {'backend': 'codex', 'runtimePath': str(binary),
                                                           'model': 'fixture-model'})
                self.assertEqual(status, result['status'])
                runtime = ModelRuntime.instances[-1]
                calls = dict(runtime.calls)
                tools = calls['thread/start']['dynamicTools']
                self.assertEqual(['focus'], [tool['name'] for tool in tools])
                self.assertEqual(['read_range'], tools[0]['inputSchema']['properties']['action']['enum'])
                self.assertEqual('fixture-model', calls['thread/start']['model'])
                self.assertEqual('readOnly', calls['turn/start']['sandboxPolicy']['type'])
                self.assertEqual('never', calls['turn/start']['approvalPolicy'])
                self.assertTrue(runtime.closed)
                self.assertFalse(runtime.cwd.exists())
                self.assertEqual(before, self.business_state())
                if runtime.marker:
                    self.assertNotIn(runtime.marker, markers)
                    self.assertNotIn(runtime.marker, str(calls))
                    self.assertNotIn(runtime.marker, str(result))
                    markers.add(runtime.marker)

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
        handle = kernel.OpenProcess(0x00100000, False, int(pid_file.read_text(encoding="utf-8")))
        if handle:
            try:
                self.assertEqual(0, kernel.WaitForSingleObject(ctypes.c_void_p(handle), 5000))
            finally:
                kernel.CloseHandle(ctypes.c_void_p(handle))


if __name__ == '__main__':
    unittest.main()
