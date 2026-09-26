"""Shared public Host operations, with only external protocol clients replaced."""
import json
import unittest
import uuid
import re
import queue
import time
import threading
from pathlib import Path
from urllib.request import Request, urlopen
from types import SimpleNamespace
from unittest.mock import patch

import test_focus_read
from host.service import HostService


class HarnessCandidates:
    requests = []

    def __init__(self, **options):
        self.options = options

    def start(self):
        pass

    def start_session(self, session_id):
        self.start()
        return self

    def close(self):
        pass

    def run(self, prompt, **options):
        request = json.loads(prompt)
        self.requests.append(request)
        task, data = request['task'], request['input']
        if 'whole-source context' in task:
            candidate = {'structure': 'Method, Runtime, Results', 'terms': [], 'symbols': [], 'references': []}
        elif 'Translate foreign text' in task:
            candidate = '已经准备的中文译文。'
        elif 'Check all chunks' in task:
            candidate = {'passed': True, 'issues': {}, 'coverage': [c['chunk_id'] for c in data['chunks']]}
        else:
            raise AssertionError('Unexpected task: ' + task)
        return SimpleNamespace(final_response=json.dumps(candidate), finish_reason='completed', events=[])


class HarnessDiscussion(HarnessCandidates):
    replies = []

    def run(self, prompt, **options):
        patch_text = Path(self.options['patches'][0]).read_text(encoding='utf-8')
        url = re.search(r'url: (http://[^\s]+)', patch_text).group(1)
        def invoke(action, arguments):
            body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
                'name': 'focus', 'arguments': {'action': action, 'arguments': json.dumps(arguments)}}}).encode()
            with urlopen(Request(url, body, {'Content-Type': 'application/json'}), timeout=5) as response:
                return json.loads(response.read())['result']
        self.replies.append(invoke('read_range', {'source_id': 'another-paper', 'start': 1, 'end': 2}))
        self.replies.append(invoke('source_note', {'content': '共同讨论的例子和结论。',
            'kind': 'conclusion', 'origin': 'dialogue', 'evidence_role': 'explanation'}))
        return SimpleNamespace(final_response='已记录。', finish_reason='completed', events=[])


class HarnessHistory(HarnessCandidates):
    summaries = []
    def run(self, prompt, **options):
        if prompt.startswith('{"task": "summarize_discussion"'):
            data = json.loads(prompt)
            self.summaries.append(data)
            remembered = '量子香蕉' in prompt
            return SimpleNamespace(final_response=json.dumps({'summary': '保留量子香蕉例子。' if remembered else '没有特别例子。'}),
                                   finish_reason='completed', events=[])
        answer = '记得上次的量子香蕉。' if '量子香蕉' in prompt else '上下文缺失。'
        return SimpleNamespace(final_response=answer, finish_reason='completed', events=[])


class HarnessInteraction(HarnessCandidates):
    replies = []

    def run(self, prompt, **options):
        text = Path(self.options['patches'][0]).read_text(encoding='utf-8')
        url = re.search(r'url: (http://[^\s]+)', text).group(1)
        for name, arguments in [('focus_user_input', {'questions': [{'id': 'topic', 'header': '重点', 'question': '重点解释哪一部分？', 'options': []}]}),
                                ('focus_confirm', {'title': '确认讨论范围', 'detail': '是否按选择的部分继续解释？'})]:
            body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}).encode()
            with urlopen(Request(url, body, {'Content-Type': 'application/json'}), timeout=8) as response:
                self.replies.append(json.loads(response.read())['result'])
        return SimpleNamespace(final_response='已收到选择和拒绝。', finish_reason='completed', events=[])


class HarnessBlog(HarnessCandidates):
    def run(self, prompt, **options):
        from test_blog_application import READING_BLOG_BODY, EVIDENCE_BODY
        if 'applicable=true' in prompt:
            result = {'applicable': False, 'direction': None, 'reason': '测试非架构来源。'}
        else:
            assets = re.search('可用图片文件名：(.*?)\\n', prompt).group(1).split(', ')
            body = READING_BLOG_BODY.replace('assets/image-001.png', 'assets/' + assets[0])
            result = {'evidence_map': EVIDENCE_BODY, 'blog': body}
        return SimpleNamespace(final_response=json.dumps(result), finish_reason='completed', events=[])


class CodexHistory:
    def __init__(self, *args, **kwargs):
        self.events = queue.Queue()

    def initialize(self):
        pass

    def send(self, message):
        pass

    def close(self):
        pass

    def request(self, method, params, **kwargs):
        if method == 'account/read':
            return {'account': {'type': 'chatgpt'}}
        if method == 'thread/start':
            kinds = {tool.get('type') for tool in params.get('dynamicTools', [])}
            if len(kinds) > 1:
                raise ValueError('dynamic tools must use either canonical or legacy format consistently')
            return {'thread': {'id': 'new-codex-thread'}}
        if method == 'thread/resume':
            raise AssertionError('FOCUS discussion must never resume a native history branch')
        if method == 'turn/start':
            prompt = params['input'][0]['text']
            text = 'Codex 记得量子香蕉。' if '量子香蕉' in prompt else '上下文缺失。'
            self.events.put({'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'id': uuid.uuid4().hex, 'text': text}}})
            self.events.put({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})
            return {'turn': {'id': 'turn-one'}}
        raise AssertionError(method)


class CodexCandidates(CodexHistory):
    def request(self, method, params, **kwargs):
        if method != 'turn/start':
            return super().request(method, params, **kwargs)
        prompt = params['input'][0]['text']
        self_assertion = params['sandboxPolicy']['type']
        if self_assertion != 'readOnly':
            raise AssertionError('Candidate is not read-only')
        runtime = HarnessCandidates() if prompt.startswith('{"task"') else HarnessBlog()
        result = runtime.run(prompt)
        self.events.put({'method': 'item/completed', 'params': {'item': {
            'type': 'agentMessage', 'id': uuid.uuid4().hex, 'text': result.final_response}}})
        self.events.put({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}})
        return {'turn': {'id': 'candidate-turn'}}


class SharedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_focus_read.FocusReadTests()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.host = None
        HarnessCandidates.requests = []

    def tearDown(self):
        if self.host:
            self.host.close()
        self.fixture.tearDown()

    def test_stopping_deepseek_finishes_discussion_and_allows_new_discussion(self):
        entered, released = threading.Event(), threading.Event()
        class WaitingHarness(HarnessCandidates):
            def run(self, prompt, **options):
                entered.set()
                released.wait(8)
                return SimpleNamespace(final_response='late', finish_reason='completed', events=[])
            def close(self):
                released.set()
        with patch('deepseek_harness.DeepSeekHarness', WaitingHarness):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            original = self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '解释方法'})
            self.assertTrue(entered.wait(3))
            self.host.stop()
            self.host.worker.join(3)
            self.assertFalse(self.host.worker.is_alive(), 'Stop must wake the Host event consumer')
            self.assertEqual('interrupted', self.host.snapshot()['agent']['run']['status'])
            fresh = self.host.new_session({'sessionId': original['sessionId']})
            self.assertEqual([], fresh['conversation'])

    def test_business_startup_error_never_exposes_provider_credentials(self):
        class FailingHarness(HarnessCandidates):
            def start(self):
                raise RuntimeError('quota exhausted sk-private-token')
        with patch('deepseek_harness.DeepSeekHarness', FailingHarness):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '解释方法'})
            self.host.worker.join(4)
            snapshot = self.host.snapshot()
            self.assertEqual('failed', snapshot['agent']['run']['status'])
            self.assertNotIn('sk-private-token', json.dumps(snapshot))

    def test_stop_during_sdk_startup_releases_runtime_and_never_starts_prompt(self):
        entered, released = threading.Event(), threading.Event()
        instances = []
        class StartingHarness(HarnessCandidates):
            def __init__(self, **options):
                super().__init__(**options)
                self.closed = False
                self.prompts = 0
                instances.append(self)
            def start(self):
                entered.set()
                released.wait(5)
            def run(self, prompt, **options):
                self.prompts += 1
                return super().run(prompt, **options)
            def close(self):
                self.closed = True
        with patch('deepseek_harness.DeepSeekHarness', StartingHarness):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '解释方法'})
            self.assertTrue(entered.wait(3))
            self.host.stop()
            released.set()
            self.host.worker.join(4)
            self.assertFalse(self.host.worker.is_alive())
            self.assertTrue(instances[0].closed)
            self.assertEqual(0, instances[0].prompts)
            self.assertFalse(Path(instances[0].options['cwd']).exists())

    def test_codex_preparation_cancel_waits_for_process_before_removing_its_workdir(self):
        started, closing, released = threading.Event(), threading.Event(), threading.Event()
        instances = []
        class SlowClosingCodex(CodexCandidates):
            def __init__(self, command, cwd, **options):
                super().__init__(command, cwd, **options)
                self.cwd = Path(cwd)
                instances.append(self)
            def request(self, method, params, **options):
                if method == 'turn/start':
                    started.set()
                    return {'turn': {'id': 'waiting'}}
                if method == 'turn/interrupt':
                    return {}
                return super().request(method, params, **options)
            def close(self):
                closing.set()
                released.wait(5)
        with patch('host.backends.codex.AppServer', SlowClosingCodex):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex')
            self.host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex)
            self.assertTrue(started.wait(3))
            cancel = threading.Thread(target=lambda: self.host.cancel_preparation('fixture-paper'))
            cancel.start()
            try:
                self.assertTrue(closing.wait(3))
                time.sleep(1.1)
                self.assertTrue(instances[0].cwd.exists(), 'Live process still owns its temporary workdir')
            finally:
                released.set()
                cancel.join(5)
                self.host.reading_workers['fixture-paper'].join(5)
            self.assertFalse(instances[0].cwd.exists())

    def test_deepseek_prepares_full_source_without_moving_cursor(self):
        with patch('deepseek_harness.DeepSeekHarness', HarnessCandidates), patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'fixture-only'}):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            before = self.host.snapshot()['current']
            self.host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex)
            self.host.reading_workers['fixture-paper'].join(10)
            prepared = self.host.snapshot()['preparations']['fixture-paper']
            self.assertTrue(prepared['ready'], prepared)
            after = self.host.snapshot()['current']
            self.assertEqual({k: before[k] for k in ('sourceId', 'planId', 'chunkId')},
                             {k: after[k] for k in ('sourceId', 'planId', 'chunkId')})
            self.host.open_prepared_reading('fixture-paper', request_id=uuid.uuid4().hex)
            self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])

            before = self.host.snapshot()
            fresh = self.host.new_session({'sessionId': before['sessionId']})
            self.assertEqual(before['current'], fresh['current'])

    def test_codex_prepares_full_source_using_same_candidate_contract(self):
        with patch('host.backends.codex.AppServer', CodexCandidates):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex')
            self.host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex)
            self.host.reading_workers['fixture-paper'].join(10)
            self.assertTrue(self.host.snapshot()['preparations']['fixture-paper']['ready'])
            self.host.open_prepared_reading('fixture-paper', request_id=uuid.uuid4().hex)
            self.assertEqual('chunk-001', self.host.snapshot()['current']['chunkId'])

    def test_codex_blog_publishes_through_same_candidate_contract(self):
        from test_blog_application import png_bytes
        (self.workspace / 'sources/fixture-paper/parser-bundle/images/image-001.png').write_bytes(png_bytes(b'\0\0\0\0\xff'))
        with patch('host.backends.codex.AppServer', CodexCandidates):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex')
            self.host.blog_generate('fixture-paper', request_id=uuid.uuid4().hex)
            worker = self.host.blog_workers.get('fixture-paper')
            if worker:
                worker.join(15)
            self.assertTrue(Path(self.host.blog_open('fixture-paper')['path']).is_file())

    def test_deepseek_discussion_uses_host_note_guard_and_refuses_other_source(self):
        HarnessDiscussion.replies = []
        with patch('deepseek_harness.DeepSeekHarness', HarnessDiscussion), patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'fixture-only'}):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            selected = self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sessionId': selected['sessionId'],
                             'sourceId': 'fixture-paper', 'receipt': None, 'content': '请记下来'})
            self.host.worker.join(10)
            snapshot = self.host.snapshot()
            self.assertEqual('completed', snapshot['agent']['run']['status'], snapshot['agent']['run'])
            self.assertEqual('共同讨论的例子和结论。', snapshot['sourceNotes'][0]['content'])
            self.assertTrue(HarnessDiscussion.replies[0]['isError'])
            self.assertFalse(HarnessDiscussion.replies[1]['isError'])

    def test_sdk_tool_interactions_use_existing_input_and_approval_views(self):
        HarnessInteraction.replies = []
        with patch('deepseek_harness.DeepSeekHarness', HarnessInteraction):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '先问我重点。'})
            for kind in ('input', 'approval'):
                deadline = time.monotonic() + 4
                approval = None
                while time.monotonic() < deadline:
                    run = self.host.snapshot()['agent']['run']
                    approval = next((a for a in run['approvals'] if a['kind'] == kind), None)
                    if approval:
                        break
                    time.sleep(.02)
                self.assertIsNotNone(approval, run)
                answer = {'answers': {'topic': {'answers': ['方法']}}} if kind == 'input' else {'decision': 'decline'}
                self.host.approve({'approvalId': approval['id'], **answer})
            self.host.worker.join(5)
            self.assertEqual('completed', self.host.snapshot()['agent']['run']['status'])
            self.assertIn('decline', HarnessInteraction.replies[-1]['content'][0]['text'])

    def test_delayed_input_answer_is_not_lost_while_host_still_displays_it(self):
        HarnessInteraction.replies = []
        clock = SimpleNamespace(offset=0)
        with patch('deepseek_harness.DeepSeekHarness', HarnessInteraction), patch(
                'host.backends.tool_bridge.time', SimpleNamespace(monotonic=lambda: time.monotonic() + clock.offset)):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '先问重点'})
            for kind in ('input', 'approval'):
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    approvals = self.host.snapshot()['agent']['run']['approvals']
                    approval = next((a for a in approvals if a['kind'] == kind), None)
                    if approval:
                        break
                    time.sleep(.02)
                self.assertIsNotNone(approval)
                clock.offset += 121
                time.sleep(.35)
                self.host.approve({'approvalId': approval['id'], **(
                    {'answers': {'topic': {'answers': ['方法']}}} if kind == 'input' else {'decision': 'decline'})})
            self.host.worker.join(5)
            self.assertEqual('completed', self.host.snapshot()['agent']['run']['status'])
            self.assertTrue(all(not r['isError'] for r in HarnessInteraction.replies), HarnessInteraction.replies)

    def test_discussion_restores_visible_history_and_context_after_host_restart(self):
        with patch('deepseek_harness.DeepSeekHarness', HarnessHistory), patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'fixture-only'}):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '我们的例子叫量子香蕉。'})
            self.host.worker.join(5)
            old_messages = self.host.snapshot()['conversation']
            self.host.close()
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            restored = self.host.select_discussion_source('fixture-paper')
            self.assertEqual(old_messages, restored['conversation'])
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '上次的例子叫什么？'})
            self.host.worker.join(5)
            self.assertIn('量子香蕉', self.host.snapshot()['conversation'][-1]['content'])

    def test_long_discussion_carries_cumulative_summary_across_restart_and_backend(self):
        HarnessHistory.summaries = []
        with patch('deepseek_harness.DeepSeekHarness', HarnessHistory), patch('host.backends.codex.AppServer', CodexHistory):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            self.host.select_discussion_source('fixture-paper')
            for index in range(9):
                text = ('说明' * 350 + '例子叫量子香蕉') if index == 0 else '继续讨论第' + str(index) + '段'
                self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': text})
                self.host.worker.join(5)
            self.assertGreaterEqual(len(HarnessHistory.summaries), 2)
            self.assertIn('量子香蕉', HarnessHistory.summaries[0]['messages'][0]['content'])
            self.assertIn('量子香蕉', HarnessHistory.summaries[-1]['previousSummary'])
            before = self.host.snapshot()
            self.assertEqual(18, len(before['conversation']))
            self.host.close()
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex')
            selected = self.host.select_discussion_source('fixture-paper')
            self.assertEqual(before['conversation'], selected['conversation'])
            self.assertEqual([], selected['sourceNotes'])

    def test_new_source_discussion_retains_previous_history_and_can_restore_it(self):
        with patch('deepseek_harness.DeepSeekHarness', HarnessHistory), patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'fixture-only'}):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            selected = self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '量子香蕉'})
            self.host.worker.join(5)
            original = self.host.snapshot()
            fresh = self.host.new_session({'sessionId': selected['sessionId']})
            self.assertEqual('fixture-paper', fresh['source']['sourceId'])
            self.assertEqual([], fresh['conversation'])
            self.assertNotEqual(original['discussionId'], fresh['discussionId'])
            restored = self.host.select_discussion_source('fixture-paper', discussion_id=original['discussionId'])
            self.assertEqual(original['conversation'], restored['conversation'])

    def test_codex_then_deepseek_continue_one_focus_discussion(self):
        with patch('host.backends.codex.AppServer', CodexHistory), patch('deepseek_harness.DeepSeekHarness', HarnessHistory):
            for backend, prompt in [('codex', '请记住例子量子香蕉，但不要写 Notes。'),
                                    ('deepseek', '上次的例子叫什么？'), ('codex', '再复述同一个例子。')]:
                if self.host:
                    self.host.close()
                self.host = HostService(self.workspace, self.fixture.root / 'host', backend=backend)
                selected = self.host.select_discussion_source('fixture-paper')
                self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': prompt})
                self.host.worker.join(5)
                snapshot = self.host.snapshot()
                self.assertEqual('completed', snapshot['agent']['run']['status'])
                self.assertIn('量子香蕉', snapshot['conversation'][-1]['content'])
                self.assertEqual(selected['discussionId'], snapshot['discussionId'])
                self.assertEqual([], snapshot['sourceNotes'])
            self.assertEqual(6, len(snapshot['conversation']))

    def test_existing_switch_endpoint_keeps_source_discussion_identity_and_history(self):
        with patch('host.backends.codex.AppServer', CodexHistory), patch('deepseek_harness.DeepSeekHarness', HarnessHistory):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='codex')
            self.host.select_discussion_source('fixture-paper')
            self.host.start({'requestId': uuid.uuid4().hex, 'sourceId': 'fixture-paper', 'content': '例子叫量子香蕉'})
            self.host.worker.join(5)
            before = self.host.snapshot()
            after = self.host.select_backend({'sessionId': before['sessionId'], 'backend': 'deepseek'})
            self.assertEqual(before['discussionId'], after['discussionId'])
            self.assertEqual(before['conversation'], after['conversation'])
            self.assertEqual(before['sessionId'], after['sessionId'])

    def test_deepseek_blog_publishes_through_shared_core_and_opens_html(self):
        from test_blog_application import png_bytes
        (self.workspace / 'sources/fixture-paper/parser-bundle/images/image-001.png').write_bytes(
            png_bytes(b'\x00\x00\x00\x00\xff'))
        with patch('deepseek_harness.DeepSeekHarness', HarnessBlog), patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'fixture-only'}):
            self.host = HostService(self.workspace, self.fixture.root / 'host', backend='deepseek')
            self.host.blog_generate('fixture-paper', request_id=uuid.uuid4().hex)
            worker = self.host.blog_workers.get('fixture-paper')
            if worker:
                worker.join(15)
            result = self.host.blog_open('fixture-paper')
            self.assertTrue(Path(result['path']).is_file())


if __name__ == '__main__':
    unittest.main()
