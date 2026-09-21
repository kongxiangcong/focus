"""File-backed acceptance for the Topic Library workflow; no remote parser calls."""
import tempfile
import unittest
from pathlib import Path

from host.core_bridge import SourceLibrary, WorkspaceError
from core.library_import import import_markdown
from core.reading_workspace import WorkspaceCore


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.original = self.root / 'note.md'
        self.original.write_text('# 示例\n\n第一段内容。\n\n第二段内容。\n', encoding='utf-8')
        self.library = SourceLibrary(self.workspace)

    def tearDown(self):
        self.tmp.cleanup()

    def register(self):
        return import_markdown(self.workspace, self.original, short_name='示例', topic='计算系统', uploader='孔祥聪')['source_id']

    def test_same_original_reuses_one_bundle_across_two_topics(self):
        sid = self.register()
        self.assertEqual(self.original.read_text(encoding='utf-8'), (self.workspace / 'sources' / sid / 'parser-bundle/content.md').read_text(encoding='utf-8'))
        second = import_markdown(self.workspace, self.original, topic='阅读方法')
        self.assertEqual(sid, second['source_id'])
        self.assertEqual(1, len(list((self.workspace / 'sources').iterdir())))
        self.assertEqual(2, len(self.library.overview()[0]['topicIds']))
        self.assertEqual(self.original.read_bytes(), (self.workspace / 'sources' / sid / 'parser-bundle/source.md').read_bytes())

    def test_missing_local_image_leaves_no_source_or_topic(self):
        self.original.write_text('# 示例\n\n![图](missing.png)', encoding='utf-8')
        with self.assertRaises(WorkspaceError):
            self.register()
        self.assertEqual([], self.library.overview())
        self.assertEqual([], self.library.topics())
        self.assertEqual([], list(self.workspace.glob('.markdown-*')))

    def test_metadata_and_topic_names_are_stable(self):
        sid = self.register()
        self.library.describe(sid, venue='测试期刊', published_at='2026-09')
        self.library.attach(sid, topic_title='计算系统')
        self.assertEqual(1, len(self.library.topics()))
        self.library.attach(sid, topic_title='A B')
        self.library.attach(sid, topic_title='A-B')
        self.assertEqual(3, len(self.library.topics()))
        view = self.library.overview()[0]
        self.assertEqual(('2026-09', '测试期刊', '孔祥聪'), (view['publishedAt'], view['venue'], view['uploader']))

    def test_plan_start_continue_complete_reread_use_one_state(self):
        sid = self.register()
        core = WorkspaceCore(self.workspace)
        self.assertEqual('unplanned', self.library.overview()[0]['readingStatus'])
        draft = {'chunks': [{'section_path': ['示例'], 'source_lines': [1, 5], 'images': []}], 'glossary': []}
        core.map_reading_plan(sid, draft=draft)
        self.assertEqual('ready', self.library.overview()[0]['readingStatus'])
        before = (self.workspace / 'state.json').read_bytes()
        self.assertEqual('source_ready', core.get_current_chunk()['status'])
        core.reading_window()
        self.assertEqual(before, (self.workspace / 'state.json').read_bytes())
        self.library.start_reading(sid)
        self.assertEqual('reading', self.library.overview()[0]['readingStatus'])
        core.continue_reading(expected_plan_id='plan-001', expected_chunk_id='chunk-001', pending_notes=[])
        self.assertEqual('completed', self.library.overview()[0]['readingStatus'])
        self.library.reset_reading(sid)
        core.map_reading_plan(sid, draft=draft)
        view = self.library.overview()[0]
        self.assertEqual('ready', view['readingStatus'])
        self.assertEqual('plan-002', view['progress']['planId'])
