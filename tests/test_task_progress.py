import json
import unittest
from unittest.mock import patch

import test_web_host
from host.progress import activity_label
from host.backends.codex import CodexBackend


class TaskProgressTests(unittest.TestCase):
    setUp = test_web_host.WebHostTests.setUp
    tearDown = test_web_host.WebHostTests.tearDown
    finish = test_web_host.WebHostTests.finish

    def test_observed_events_update_stage_without_moving_cursor(self):
        state = (self.workspace / 'state.json').read_bytes()
        self.host.state['run'] = {'runId': 'test', 'status': 'running', 'error': None,
            'approvals': [], 'activity': [], 'progress': {'label': '连接助手', 'startedAt': 1, 'updatedAt': 1}}
        self.host._notification('activity', {'id': 'parse', 'title': 'commandExecution',
            'status': 'inProgress', 'detail': 'python mineru_precision.py parse selected.pdf'})
        self.assertEqual('解析材料', self.host.snapshot()['agent']['run']['progress']['label'])
        self.host._notification('message/delta', {'itemId': 'reply', 'delta': '正文'})
        self.assertEqual('正在生成回复', self.host.snapshot()['agent']['run']['progress']['label'])
        self.assertEqual(state, (self.workspace / 'state.json').read_bytes())
        self.host.state['run']['status'] = 'completed'

    def test_failed_verification_never_publishes_completed(self):
        seen = []
        changed = self.host.changed
        def observe():
            seen.append(self.host.state['run']['status'])
            changed()
        with patch.object(self.host, 'changed', side_effect=observe), patch.object(
                self.host, '_verify_library_task', side_effect=ValueError('verification failed')):
            self.host.start({'requestId': 'verify-progress', 'receipt': None, 'content': 'test'},
                library_task={'kind': 'read', 'sourceId': 'fixture-paper'})
            self.finish()
        self.assertNotIn('completed', seen)
        run = self.host.snapshot()['agent']['run']
        self.assertEqual('failed', run['status'])
        self.assertGreaterEqual(run['progress']['finishedAt'], run['progress']['startedAt'])

    def test_command_output_cannot_impersonate_parser_progress(self):
        self.assertEqual('执行操作', activity_label({'title': 'commandExecution',
            'detail': 'echo hello\nmineru_precision.py'}))

    def test_adapter_exposes_reasoning_status_without_reasoning_content(self):
        backend = object.__new__(CodexBackend)
        events = []
        backend.emit = lambda method, params: events.append((method, params))
        backend._translate_item('item/started', {'id': 'r', 'type': 'reasoning', 'text': 'private reasoning'})
        backend._translate_item('item/completed', {'id': 'r', 'type': 'reasoning', 'text': 'private reasoning'})
        self.assertEqual(['inProgress', 'completed'], [event[1]['status'] for event in events])
        self.assertNotIn('private reasoning', json.dumps(events))
