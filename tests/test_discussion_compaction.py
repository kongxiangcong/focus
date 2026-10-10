"""Lossless Source discussion compaction contract without live model calls."""
import copy
import json
import unittest

from host import discussions


def fixture(count=16, size=200, covered=0):
    messages = [{'messageId': f'message-{i:03}', 'discussionId': 'thread',
                 'role': 'user' if i % 2 else 'assistant',
                 'content': f'{i}: ' + 'x' * size} for i in range(count)]
    return {'conversation': messages, 'discussions': {'thread': {
        'sourceId': 'paper', 'summary': 'Previously covered' if covered else '',
        'summaryThrough': f'message-{covered-1:03}' if covered else None}}}


class SummaryContextTests(unittest.TestCase):
    def test_covered_prefix_is_never_replayed_or_summarized_twice(self):
        state = fixture(16, covered=4)
        snapshot = discussions.plan(state, 'thread')
        ids = [item['messageId'] for item in snapshot['pending'] + snapshot['recent']]
        self.assertEqual([f'message-{i:03}' for i in range(4, 16)], ids)
        whole = discussions.inline_context(snapshot, budget=100000)
        self.assertEqual(12, len(whole['recentMessages']))
        state = fixture(16, covered=16)
        snapshot = discussions.plan(state, 'thread')
        calls = []
        self.assertEqual('message-015',
            discussions.compact_snapshot(snapshot, lambda *args: calls.append(args))['summaryThrough'])
        self.assertFalse(calls)

    def test_small_history_bypasses_model_compaction(self):
        state = fixture(16, size=1000)
        snapshot = discussions.plan(state, 'thread')
        projected = discussions.inline_context(snapshot, budget=48000)
        self.assertEqual(16, len(projected['recentMessages']))
        self.assertIsNone(state['discussions']['thread']['summaryThrough'])

    def test_large_history_must_be_compacted_without_omitting_messages(self):
        state = fixture(17, size=7000)
        snapshot = discussions.plan(state, 'thread')
        self.assertIsNone(discussions.inline_context(snapshot, budget=48000))
        processed = []
        def summarize(previous, batch):
            processed.extend(item['content'] for item in batch)
            return 'Summary covering all batch items'
        result = discussions.compact_snapshot(snapshot, summarize)
        self.assertEqual([item['content'] for item in snapshot['pending']], processed)
        self.assertEqual(snapshot['pending'][-1]['messageId'], result['summaryThrough'])
        after = discussions.inline_context({**snapshot, 'summary': result['summary'], 'pending': []}, budget=100000)
        self.assertEqual(len(snapshot['recent']), len(after['recentMessages']))

    def test_timeout_never_commits_partial_batches(self):
        state = fixture(17, size=9500)
        original = copy.deepcopy(state)
        calls = []
        def summarize(previous, batch):
            calls.append(batch)
            if len(calls) > 1:
                raise TimeoutError('controlled summary timeout')
            return 'Partial first batch'
        with self.assertRaises(TimeoutError):
            discussions.context(state, 'thread', summarize)
        self.assertEqual(original, state)

    def test_stale_or_invalid_coverage_is_rejected(self):
        state = fixture(16, covered=2)
        state['discussions']['thread']['summaryThrough'] = 'deleted'
        with self.assertRaisesRegex(ValueError, '覆盖标记'):
            discussions.plan(state, 'thread')

    def test_current_question_never_replayed_as_prior_history(self):
        state = fixture(16)
        state['conversation'].append({'messageId': 'new-question', 'discussionId': 'thread',
                                      'role': 'user', 'content': 'current private question'})
        value = discussions.inline_context(
            discussions.plan(state, 'thread', exclude_message_id='new-question'), budget=100000)
        self.assertNotIn('current private question', json.dumps(value))


if __name__ == '__main__':
    unittest.main()
