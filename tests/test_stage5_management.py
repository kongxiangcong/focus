"""Library management via HTTP and canonical persisted assets."""
import json
import unittest
from unittest.mock import patch

import test_stage5_ingestion as single
from test_html_ingestion import saved_html


class ManagementTests(unittest.TestCase):
    setUp = single.SingleIngestionTests.setUp
    tearDown = single.SingleIngestionTests.tearDown
    start_host = single.SingleIngestionTests.start_host
    stop_host = single.SingleIngestionTests.stop_host
    request = single.SingleIngestionTests.request
    wait_blog = single.SingleIngestionTests.wait_blog

    def source(self):
        item = self.request('POST', '/library/inbox?name=one.pdf&topic=Systems', b'%PDF management')
        self.request('POST', '/library/inbox/' + item['item_id'] + '/start', {'requestId': 'management'})
        item, _ = self.wait_blog(item['item_id'])
        for worker in list(self.host.batch_workers.values()):
            worker.join(10)
        return item['source_id']

    def test_rename_membership_and_delete_topic_preserve_assets(self):
        sid = self.source()
        source = self.root / 'knowledge-base/sources' / sid
        before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob('*') if p.is_file()}
        other = self.request('POST', '/library/topics', {'title': 'Other'})
        self.request('POST', '/library/topics/systems/rename', {'title': ' Architecture '})
        self.request('POST', '/library/topics/systems/rename', {'title': ' OTHER '}, expected_status=400)
        self.request('POST', '/library/sources/' + sid + '/title', {'title': 'Correct Original Title'})
        self.request('POST', '/library/topics/' + other['topicId'] + '/attach', {'sourceId': sid})
        current = self.request('GET', '/library/sources')[0]
        self.assertEqual({'systems', 'other'}, set(current['topicIds']))
        self.assertEqual('Correct Original Title', current['title'])
        after = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob('*') if p.is_file()}
        self.assertEqual({k: v for k, v in before.items() if k != 'source.yaml'}, {k: v for k, v in after.items() if k != 'source.yaml'})
        self.request('POST', '/library/topics/systems/detach', {'sourceId': sid})
        self.request('POST', '/library/topics/other/delete', {})
        self.assertEqual([], self.request('GET', '/library/sources')[0]['topicIds'])
        self.stop_host()
        self.start_host()
        self.assertEqual('Correct Original Title', self.request('GET', '/library/sources')[0]['title'])
        self.assertEqual('Architecture', self.request('GET', '/library/topics')[0]['title'])

    def test_topic_delete_write_failure_preserves_relationship_and_current_topic(self):
        sid = self.source()
        state_path = self.root / 'knowledge-base/state.json'
        state = json.loads(state_path.read_text())
        state['current_topic_id'] = 'systems'
        state_path.write_text(json.dumps(state), encoding='utf-8')
        from core.source_library import SourceLibrary
        with patch('core.source_library._write_document', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                SourceLibrary(self.root / 'knowledge-base').delete_topic('systems')
        self.assertEqual([sid], self.request('GET', '/library/topics')[0]['sourceIds'])
        self.assertEqual('systems', json.loads(state_path.read_text())['current_topic_id'])
        self.request('POST', '/library/topics/systems/delete', {})
        self.assertIsNone(json.loads(state_path.read_text())['current_topic_id'])
        self.assertEqual(1, len(self.request('GET', '/library/sources')))

    def test_topic_order_and_detach_failure_restore_current_reference(self):
        first = self.source()
        self.runtime.reading_body = self.runtime.reading_body.replace('第 1 节指出', '文章指出').replace('Table 1', '表格')
        item = self.request('POST', '/library/inbox?name=two.html&topic=Systems', saved_html().encode())
        self.request('POST', '/library/inbox/' + item['item_id'] + '/start', {'requestId': 'second'})
        item, _ = self.wait_blog(item['item_id'])
        for worker in list(self.host.batch_workers.values()):
            worker.join(10)
        second = item['source_id']
        self.request('POST', '/library/topics/systems/reorder', {'sourceIds': [second, first]})
        self.assertEqual([second, first], self.request('GET', '/library/topics')[0]['sourceIds'])
        self.request('POST', '/library/topics/systems/reorder', {'sourceIds': [first]}, expected_status=400)
        state_path = self.root / 'knowledge-base/state.json'
        state = json.loads(state_path.read_text())
        state['current_topic_id'], state['current_source_id'] = 'systems', first
        state_path.write_text(json.dumps(state), encoding='utf-8')
        from core import source_library
        write = source_library._write_document
        calls = []
        def fail_second(path, value):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('disk full after current Topic update')
            return write(path, value)
        with patch('core.source_library._write_document', side_effect=fail_second):
            with self.assertRaises(OSError):
                source_library.SourceLibrary(self.root / 'knowledge-base').detach('systems', first)
        self.assertEqual('systems', json.loads(state_path.read_text())['current_topic_id'])
        self.assertEqual([second, first], self.request('GET', '/library/topics')[0]['sourceIds'])

    def test_management_rejects_active_blog(self):
        sid = self.source()
        self.runtime.entered.clear()
        self.runtime.release.clear()
        self.request('POST', '/library/sources/' + sid + '/blog/regenerate', {'requestId': 'blocking', 'artifact': 'reading_blog'})
        self.assertTrue(self.runtime.entered.wait(10))
        self.request('POST', '/library/sources/' + sid + '/title', {'title': 'Forbidden'}, expected_status=400)
        self.request('POST', '/library/topics/systems/detach', {'sourceId': sid}, expected_status=400)
        self.request('POST', '/library/topics/systems/delete', {}, expected_status=400)
        self.assertEqual([sid], self.request('GET', '/library/topics')[0]['sourceIds'])
        self.assertEqual('Stored Paper', self.request('GET', '/library/sources')[0]['title'])
