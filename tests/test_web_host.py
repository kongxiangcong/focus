"""Host/Core integration with a protocol double. No model or MinerU calls."""
import http.client
import json
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import test_focus_read
from host.core_bridge import CoreBridge
from host.service import HostService
from host.server import Server
from host.store import Store
from host.runtime import AppServer


class ProtocolDouble:
    instances = []
    mode = 'answer'

    def __init__(self, command, cwd):
        self.events = queue.Queue()
        self.calls = []
        self.closed = False
        self.__class__.instances.append(self)

    def initialize(self):
        return {}

    def send(self, value):
        self.calls.append(value)
        if 'result' in value and self.mode in ('approval', 'tool', 'advance', 'translate'):
            self.complete()

    def request(self, method, params, timeout=60):
        self.calls.append({'method': method, 'params': params})
        if method.startswith('thread/'):
            return {'thread': {'id': 'thread-fixture'}}
        if method == 'turn/interrupt':
            self.events.put({'method': 'turn/completed', 'params': {'turn': {'status': 'interrupted'}}})
            return {}
        if method == 'turn/start':
            if self.mode == 'answer':
                self.events.put({'method': 'item/agentMessage/delta', 'params': {'itemId': 'assistant-'+str(len(self.instances)), 'delta': '真实 Core，协议替身。'}})
                self.complete()
            elif self.mode == 'approval':
                self.events.put({'id': 700, 'method': 'item/commandExecution/requestApproval',
                                 'params': {'command': 'python demo.py', 'reason': 'test'}})
            elif self.mode in ('tool', 'advance', 'translate'):
                args = {'action': 'append_note', 'arguments': json.dumps({'expected_plan_id': 'plan-001', 'expected_chunk_id': 'chunk-001',
                    'kind': 'clarification', 'origin': 'dialogue', 'content': '固定别名维持源顺序。'})}
                if self.mode == 'advance':
                    args = {'action': 'continue', 'arguments': json.dumps({'source_id': 'fixture-paper', 'expected_plan_id': 'plan-001', 'expected_chunk_id': 'chunk-001'})}
                elif self.mode == 'translate':
                    args = {'action': 'translate', 'arguments': json.dumps({'expected_plan_id': 'plan-001',
                        'expected_chunk_id': 'chunk-001', 'translation': '保存给阅读卡片的译文。'})}
                self.events.put({'id': 701, 'method': 'item/tool/call', 'params': {'tool': 'focus', 'arguments': args}})
            return {'turn': {'id': 'turn-fixture'}}
        raise AssertionError(method)

    def complete(self):
        self.events.put({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})

    def close(self):
        self.closed = True
        self.events.put({'method': '_transport_error', 'params': {'message': 'closed'}})


class WebHostTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_focus_read.FocusReadTests()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.data = self.fixture.root / 'host'
        ProtocolDouble.instances = []
        ProtocolDouble.mode = 'answer'
        self.patch = patch('host.service.codex_command', return_value=['protocol-double'])
        self.patch.start()
        self.host = HostService(self.workspace, self.data, runtime_factory=ProtocolDouble)
        self.receipt = {'sourceId': 'fixture-paper', 'planId': 'plan-001', 'chunkId': 'chunk-001'}

    def tearDown(self):
        self.host.close()
        self.patch.stop()
        self.fixture.tearDown()

    def wait(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate():
            if time.monotonic() > deadline:
                self.fail('Timed out: '+str(self.host.snapshot()['agent']))
            time.sleep(.01)

    def finish(self):
        self.host.worker.join(3)
        self.assertFalse(self.host.worker.is_alive())

    def start(self, **extra):
        return self.host.start({'requestId': 'request-1234', 'receipt': self.receipt, 'content': '解释一下', **extra})

    def test_question_stream_persistence_and_resume_never_advance(self):
        self.start(); self.finish()
        self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])
        self.assertEqual('真实 Core，协议替身。', self.host.snapshot()['conversation'][-1]['content'])
        self.host.close()
        self.host = HostService(self.workspace, self.data, runtime_factory=ProtocolDouble)
        self.start(requestId='request-5678'); self.finish()
        self.assertEqual('thread/resume', ProtocolDouble.instances[-1].calls[1]['method'])
        self.assertEqual(4, len(self.host.snapshot()['conversation']))

    def test_continue_is_idempotent_and_checks_source(self):
        p = {'requestId': 'continue-123', 'receipt': self.receipt}
        self.host.start(p, continuing=True); self.finish()
        self.host.start(p, continuing=True)
        self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])
        with self.assertRaises(Exception):
            self.host.start({**p, 'requestId': 'continue-456'}, continuing=True)
        with self.assertRaises(Exception):
            self.host.core.check_receipt({**self.receipt, 'sourceId': 'other-paper', 'chunkId': 'chunk-002'})

    def test_explicit_continue_in_chat_advances_once(self):
        self.start(content='继续阅读'); self.finish()
        self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])

    def assert_web_presentation_contract(self, method):
        calls = ProtocolDouble.instances[-1].calls
        params = next(c['params'] for c in calls if c.get('method') == method)
        instructions = params['developerInstructions']
        for rule in (
            'The card, not chat, presents ordinary reading content.',
            'then stop and wait for the user.',
            'Do not repeat source or translation in chat',
            'An earlier request to explain does not authorize automatic explanation',
            'If the current user request explicitly asks for explanation, summary, interpretation or retranslation, fulfill that request normally.',
            'Necessary parsing progress, questions needed to proceed, and failure messages are allowed.',
        ):
            self.assertIn(rule, instructions)
        return next(c['params']['input'][0]['text'] for c in calls if c.get('method') == 'turn/start')

    def test_attachment_start_delivers_card_contract_and_projects_saved_translation(self):
        # Scripted tool call verifies real Core/card projection, not model compliance.
        ProtocolDouble.mode = 'translate'
        self.host.store.put('upload:paper', {'name': 'paper.pdf', 'path': str(self.workspace / 'paper.pdf')})
        self.start(content='请阅读附件', receipt=None, attachmentIds=['paper']); self.finish()
        prompt = self.assert_web_presentation_contract('thread/start')
        self.assertTrue(prompt.startswith('请阅读附件\n'))
        self.assertIn('paper.pdf', prompt)
        self.assertNotIn('开始讲解', prompt)
        window = self.host.snapshot()
        self.assertEqual('chunk-001', window['current']['chunkId'])
        self.assertEqual('保存给阅读卡片的译文。', window['current']['translation'])
        self.assertEqual('completed', window['agent']['run']['status'])
        self.assertFalse(any(m['role'] == 'assistant' for m in window['conversation']))

    def test_continue_overrides_previous_explanation_on_resume(self):
        self.start(content='请阅读附件并开始讲解'); self.finish()
        self.host.start({'requestId': 'continue-after-explanation', 'receipt': self.receipt}, continuing=True)
        self.finish()
        prompt = self.assert_web_presentation_contract('thread/resume')
        self.assertTrue(prompt.startswith('继续阅读\n'))
        self.assertIn('由阅读卡片展示原文／译文，然后停止并等待用户操作', prompt)
        self.assertIn('之前的讲解请求不是本轮继续讲解的授权', prompt)
        self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])

    def test_chat_next_delivers_same_card_contract(self):
        self.start(content='下一段'); self.finish()
        prompt = self.assert_web_presentation_contract('thread/start')
        self.assertIn('不要在聊天中重复原文或译文，也不要自动讲解', prompt)
        self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])

    def test_explicit_explanation_summary_and_retranslation_are_not_suppressed(self):
        for index, content in enumerate(('请讲解这段', '总结这段', '解释这个公式', '请重新翻译这段')):
            with self.subTest(content=content):
                self.start(content=content, requestId=f'explicit-request-{index}'); self.finish()
                prompt = self.assert_web_presentation_contract('thread/start' if index == 0 else 'thread/resume')
                self.assertTrue(prompt.startswith(content + '\n'))
                self.assertNotIn('然后停止并等待用户操作', prompt)
                window = self.host.snapshot()
                self.assertEqual('chunk-001', window['current']['chunkId'])
                self.assertEqual('真实 Core，协议替身。', window['conversation'][-1]['content'])

    def test_core_note_written_without_chat_or_cursor(self):
        ProtocolDouble.mode = 'tool'
        self.start(); self.finish()
        record = json.loads((self.workspace / 'sources/fixture-paper/reading/plans/plan-001/records/chunk-001.json').read_text())
        self.assertEqual('固定别名维持源顺序。', record['notes'][0]['content'])
        self.assertEqual({'chunk_id', 'translation', 'notes'}, set(record))
        self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])

    def test_unauthorized_agent_advance_requires_confirmation(self):
        ProtocolDouble.mode = 'advance'
        self.start()
        self.wait(lambda: bool(self.host.state['run']['approvals']))
        approval = self.host.snapshot()['agent']['run']['approvals'][0]
        self.assertEqual('continue', approval['kind'])
        self.host.approve({'approvalId': approval['id'], 'decision': 'decline'})
        self.finish()
        self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])
        response = next(c for c in ProtocolDouble.instances[-1].calls if 'result' in c)
        self.assertFalse(response['result']['success'])

    def test_approval_recovery_decline_and_serialization(self):
        ProtocolDouble.mode = 'approval'
        self.start()
        self.wait(lambda: bool(self.host.state['run']['approvals']))
        approval = self.host.snapshot()['agent']['run']['approvals'][0]
        with self.assertRaises(ValueError):
            self.start(requestId='different-1234')
        self.host.approve({'approvalId': approval['id'], 'decision': 'decline'})
        self.finish()
        self.assertIn({'id': 700, 'result': {'decision': 'decline'}}, ProtocolDouble.instances[-1].calls)
        with self.assertRaises(ValueError):
            self.host.approve({'approvalId': approval['id'], 'decision': 'accept'})

    def test_stop_reaches_runtime_while_approval_pending(self):
        ProtocolDouble.mode = 'approval'
        self.start()
        self.wait(lambda: bool(self.host.state['run']['approvals']))
        self.host.stop(); self.finish()
        self.assertEqual('interrupted', self.host.snapshot()['agent']['run']['status'])
        self.assertTrue(any(c.get('method') == 'turn/interrupt' for c in ProtocolDouble.instances[-1].calls))

    def test_reset_keeps_core_assets_but_starts_new_thread_and_survives_restart(self):
        self.start(); self.finish()
        before = {str(p.relative_to(self.workspace)): p.read_bytes() for p in self.workspace.rglob('*') if p.is_file()}
        old = self.host.state['sessionId']
        window = self.host.new_session({'sessionId': old})
        self.assertNotEqual(old, window['sessionId'])
        self.assertTrue(window['sessionFresh'])
        self.assertEqual([], window['timeline'])
        self.assertEqual([], window['conversation'])
        self.assertIsNone(self.host.state['threadId'])
        self.assertIsNotNone(self.host.store.get('session:' + old))
        self.assertEqual(before, {str(p.relative_to(self.workspace)): p.read_bytes() for p in self.workspace.rglob('*') if p.is_file()})
        self.host.close()
        self.host = HostService(self.workspace, self.data, runtime_factory=ProtocolDouble)
        self.assertTrue(self.host.snapshot()['sessionFresh'])
        new = self.host.state['sessionId']
        self.assertEqual(new, self.host.new_session({'sessionId': old})['sessionId'])
        with self.assertRaisesRegex(ValueError, '会话已更新'):
            self.start(sessionId=old)
        self.host.resume_reading({'sessionId': new})
        self.assertEqual('reading', self.host.snapshot()['timeline'][0]['kind'])
        self.start(sessionId=new); self.finish()
        self.assertTrue(any(c.get('method') == 'thread/start' for c in ProtocolDouble.instances[-1].calls))
        self.assertFalse(any(c.get('method') == 'thread/resume' for c in ProtocolDouble.instances[-1].calls))

    def test_stop_and_reset_closes_approvals_and_isolates_old_events(self):
        ProtocolDouble.mode = 'approval'
        self.start()
        self.wait(lambda: bool(self.host.state['run']['approvals']))
        approval = self.host.state['run']['approvals'][0]['id']
        old = self.host.state['sessionId']
        old_rpc = ProtocolDouble.instances[-1]
        result = self.host.new_session({'sessionId': old})
        self.assertTrue(old_rpc.closed)
        self.assertEqual([], result['conversation'])
        old_rpc.events.put({'method': 'item/agentMessage/delta', 'params': {'itemId': 'late', 'delta': 'late answer'}})
        self.host._notification('item/agentMessage/delta', {'threadId': 'old', 'itemId': 'late', 'delta': 'late answer'})
        self.assertEqual([], self.host.snapshot()['conversation'])
        with self.assertRaises(ValueError):
            self.host.approve({'approvalId': approval, 'decision': 'accept'})

    def test_historical_reference_is_passed_to_agent_without_advancing(self):
        self.host.start({'requestId': 'advance-first', 'receipt': self.receipt}, continuing=True); self.finish()
        self.start(requestId='review-old'); self.finish()
        self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])
        call = next(c for c in ProtocolDouble.instances[-1].calls if c.get('method') == 'turn/start')
        self.assertIn('User question reference', call['params']['input'][0]['text'])
        self.assertEqual(self.receipt, self.host.state['conversation'][-2]['reference'])
        timeline = self.host.snapshot()['timeline']
        self.assertEqual(['reading', 'message', 'reading', 'message', 'message', 'message'], [e['kind'] for e in timeline])

    def test_loopback_direct_access_preserves_origin_checks(self):
        server = Server(('127.0.0.1', 0), self.host)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            connection.request('GET', '/reader/window')
            response = connection.getresponse(); self.assertEqual(200, response.status); response.read()
            connection.request('GET', '/reader/window', headers={'Origin': 'https://evil.example'})
            response = connection.getresponse(); self.assertEqual(403, response.status); response.read()
        finally:
            connection.close(); server.shutdown(); server.server_close()

    def test_restart_marks_active_run_interrupted(self):
        self.host.state['run'] = {'runId': 'old', 'status': 'running', 'error': None, 'approvals': [], 'activity': []}
        self.host.store.save()
        another = Store(self.data, self.workspace)
        self.assertEqual('interrupted', another.state['run']['status'])
        another.close()
        self.host.state['run'] = None

    def test_empty_workspace_and_traversal(self):
        empty = self.fixture.root / 'empty'; empty.mkdir()
        self.assertEqual('empty', CoreBridge(empty).window()['status'])
        for source, path in [('..', 'state.json'), ('fixture-paper', '../../state.json')]:
            with self.assertRaises(Exception):
                self.host.core.image(source, path)

    def test_http_auth_upload_sse_and_core_projection(self):
        server = Server(('127.0.0.1', 0), self.host, token='test-token')
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        try:
            connection.request('GET', '/reader/window')
            r = connection.getresponse(); self.assertEqual(401, r.status); r.read()
            headers = {'Authorization': 'Bearer test-token'}
            connection.request('GET', '/reader/window', headers=headers)
            r = connection.getresponse(); self.assertEqual('reading', json.loads(r.read())['value']['status'])
            connection.request('POST', '/reader/upload?name=paper.pdf', b'%PDF test', headers)
            r = connection.getresponse(); upload = json.loads(r.read())['value']
            saved = self.host.store.get('upload:' + upload['attachmentId'])
            self.assertEqual(b'%PDF test', Path(saved['path']).read_bytes())
            connection.request('POST', '/reader/upload?name=..%2Fsecret.pdf', b'x', headers)
            r = connection.getresponse(); self.assertEqual(400, r.status); r.read()
            connection.request('GET', '/reader/window', headers={**headers, 'Origin': 'https://evil.example'})
            r = connection.getresponse(); self.assertEqual(403, r.status); r.read()
            connection.request('GET', '/reader/events', headers=headers)
            r = connection.getresponse(); self.assertEqual(200, r.status)
            self.assertEqual(b'event: snapshot\n', r.fp.readline())
            self.assertIn(b'"sourceId": "fixture-paper"', r.fp.readline())
        finally:
            connection.close(); server.shutdown(); server.server_close()


class RuntimeTransportTests(unittest.TestCase):
    def test_rpc_roundtrip_and_process_exit_fail_pending_requests(self):
        import sys
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / 'double.py'
            script.write_text('''import json,sys
for line in sys.stdin:
 v=json.loads(line)
 if v.get('method') == 'exit': break
 if 'id' in v: print(json.dumps({'id':v['id'],'result':{'echo':v['method']}}),flush=True)
''')
            rpc = AppServer([sys.executable, str(script)], Path(d))
            try:
                self.assertEqual({'echo': 'initialize'}, rpc.initialize())
                with self.assertRaisesRegex(RuntimeError, 'exited'):
                    rpc.request('exit', {}, timeout=2)
            finally:
                rpc.close()
