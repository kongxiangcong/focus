"""Guarded deletion through HTTP with persisted references and replay."""
import unittest
from unittest.mock import patch

import test_stage5_management as management


class DeletionTests(unittest.TestCase):
    setUp = management.ManagementTests.setUp
    tearDown = management.ManagementTests.tearDown
    start_host = management.ManagementTests.start_host
    stop_host = management.ManagementTests.stop_host
    request = management.ManagementTests.request
    wait_blog = management.ManagementTests.wait_blog
    source = management.ManagementTests.source

    def test_delete_marks_history_cleans_references_and_old_batch_cannot_recreate(self):
        sid = self.source()
        item = self.request('GET', '/library/inbox')[0]
        batch = self.request('GET', '/library/batches')[0]
        # Historical conversation fixture in the real persistent Host store.
        self.host.state['discussionSourceId'] = sid
        self.host.state['conversation'].append({'messageId': 'historic', 'sourceId': sid, 'chunkId': '',
                                                'role': 'user', 'content': 'Preserve this question', 'reference': None})
        self.host.state['timeline'].append({'kind': 'message', 'messageId': 'historic'})
        self.host.store.save()
        impact = self.request('GET', '/library/sources/' + sid + '/deletion-impact')
        self.assertEqual(['Systems'], [t['title'] for t in impact['topics']])
        self.assertEqual({'bundle', 'blog', 'notes', 'plans', 'progress'}, set(impact['assets']))
        result = self.request('DELETE', '/library/sources/' + sid, None)
        self.assertEqual('Preserve this question', result['conversation'][0]['content'])
        self.assertTrue(result['conversation'][0]['sourceDeleted'])
        self.assertFalse((self.root / 'knowledge-base/sources' / sid).exists())
        self.stop_host()
        self.start_host()
        self.assertEqual([], self.request('GET', '/library/sources'))
        self.assertEqual([], self.request('GET', '/library/topics')[0]['sourceIds'])
        self.request('POST', '/library/batches/' + batch['batchId'] + '/continue', {'requestId': 'old-batch'})
        for worker in list(self.host.batch_workers.values()):
            worker.join(10)
        self.assertEqual([], self.request('GET', '/library/sources'))
        self.request('POST', '/library/inbox/' + item['item_id'] + '/start', {'requestId': 'old-item'}, expected_status=400)

    def test_busy_delete_rejected_and_relation_failure_rolls_back(self):
        sid = self.source()
        self.runtime.entered.clear()
        self.runtime.release.clear()
        started = self.request('POST', '/library/sources/' + sid + '/blog/regenerate', {'requestId': 'busy-delete', 'artifact': 'reading_blog'})
        self.assertTrue(started['executing'])
        self.assertTrue(self.runtime.entered.wait(10))
        self.request('DELETE', '/library/sources/' + sid, None, expected_status=400)
        self.request('POST', '/library/sources/' + sid + '/blog/cancel', {})
        self.runtime.release.set()
        for worker in list(self.host.blog_workers.values()):
            worker.join(10)
        from core import source_library
        write = source_library._write_document
        count = []
        def fail_second(path, value):
            count.append(path)
            if len(count) == 2:
                raise OSError('injected relationship failure')
            return write(path, value)
        with patch('core.source_library._write_document', side_effect=fail_second):
            with self.assertRaises(OSError):
                self.host.library_delete(sid)
        self.assertTrue((self.root / 'knowledge-base/sources' / sid / 'parser-bundle/source.pdf').is_file())
        self.assertEqual([sid], self.request('GET', '/library/topics')[0]['sourceIds'])
        self.stop_host()
        self.start_host()
        self.assertEqual(sid, self.request('GET', '/library/sources')[0]['sourceId'])

    def test_host_write_failure_reconciles_from_core_after_restart(self):
        sid = self.source()
        self.host.state['discussionSourceId'] = sid
        self.host.state['conversation'].append({'messageId': 'old', 'sourceId': sid, 'chunkId': '',
                                                'role': 'user', 'content': 'Keep history', 'reference': None})
        self.host.store.save()
        with patch.object(self.host.store, 'save', side_effect=OSError('Host disk failure')):
            with self.assertRaises(OSError):
                self.host.library_delete(sid)
        self.stop_host()
        self.start_host()
        view = self.host.snapshot()
        self.assertTrue(view['conversation'][0]['sourceDeleted'])
        self.assertEqual([], self.request('GET', '/library/sources'))
        self.assertEqual([], self.request('GET', '/library/topics')[0]['sourceIds'])

    def test_explicit_reupload_allocates_new_identity_and_late_publish_is_rejected(self):
        sid = self.source()
        item = self.request('GET', '/library/inbox')[0]
        self.request('DELETE', '/library/sources/' + sid, None)
        from core.ingestion import IngestionCore
        from core import WorkspaceError
        with self.assertRaises(WorkspaceError) as error:
            IngestionCore(self.root / 'knowledge-base').publish(
                self.root / 'missing-late-candidate', expected_version=0, request_id='late',
                writer_id='late', title='Late', short_name='Late', identity='late',
                item_path=self.root / 'knowledge-base/inbox' / item['item_id'] / 'item.json', attempt_id='old')
        self.assertEqual('source_deleted', error.exception.error_id)
        new = self.request('POST', '/library/inbox?name=new.pdf&topic=Systems', b'%PDF management')
        self.request('POST', '/library/inbox/' + new['item_id'] + '/start', {'requestId': 'explicit-new'})
        current, _ = self.wait_blog(new['item_id'])
        new_sid = current['source_id']
        self.assertNotEqual(sid, new_sid)

    def test_locked_files_remain_inaccessible_and_cleanup_retries_on_restart(self):
        sid = self.source()
        from core.source_library import SourceLibrary
        from core import WorkspaceError
        with patch('core.source_library.shutil.rmtree', side_effect=PermissionError('locked')):
            with self.assertRaises(WorkspaceError):
                self.host.library_delete(sid)
            self.assertEqual([], self.request('GET', '/library/sources'))
            self.assertTrue(SourceLibrary(self.root / 'knowledge-base').deleted_sources()[sid]['pending_cleanup'])
        self.stop_host()
        self.start_host()
        self.assertEqual([], self.request('GET', '/library/sources'))
        self.assertFalse(SourceLibrary(self.root / 'knowledge-base').deleted_sources()[sid]['pending_cleanup'])
        self.assertEqual([], list((self.root / 'knowledge-base/sources').glob('*.deleting')))

    def test_same_url_different_bytes_old_confirmation_cannot_recreate(self):
        from test_html_ingestion import saved_html
        self.runtime.reading_body = self.runtime.reading_body.replace('第 1 节指出', '文章指出').replace('Table 1', '表格')
        data = saved_html().encode()
        first = self.request('POST', '/library/inbox?name=one.html&topic=Systems', data)
        self.request('POST', '/library/inbox/' + first['item_id'] + '/start', {'requestId': 'html'})
        item, _ = self.wait_blog(first['item_id'])
        for worker in list(self.host.batch_workers.values()):
            worker.join(10)
        old = self.request('POST', '/library/inbox?name=two.html&topic=Systems', data + b'\n<!-- saved again -->')
        self.request('POST', '/library/inbox/' + old['item_id'] + '/confirm', {'generateBlog': True})
        self.request('DELETE', '/library/sources/' + item['source_id'], None)
        self.request('POST', '/library/inbox/' + old['item_id'] + '/process', {'requestId': 'revive'}, expected_status=400)
        self.assertEqual([], self.request('GET', '/library/sources'))
