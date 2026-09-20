"""Source IDs retain their registered spelling across Core and Host boundaries."""
import json
import unittest
from unittest.mock import patch

import test_source_library_topic
import test_web_host
from core.reading_workspace import WorkspaceError, _identifier, validate_source_id
from core.source_library import SourceLibrary
from host.core_bridge import CoreBridge


NAMES = [
    ('  Model   A  ', 'Model A-paper'),
    ('Model_v1.2 (A+B), #1 & test', 'Model_v1.2 (A+B), #1 & test-paper'),
    ('中文 架构研究', '中文 架构研究-paper'),
    ('Model: A/B', 'Model： A／B-paper'),
]
INVALID_IDS = [f'a{char}b-paper' for char in '<>:"/\\|?*\x00\n\t'] + [
    '../outside-paper', '..\\outside-paper', '/absolute-paper',
    ' leading-paper', '.hidden-paper', 'trailing-paper ', 'trailing-paper.',
    '', 'missing-suffix', 'x' * 175 + '-paper',
]


class SourceIdContractTests(unittest.TestCase):
    setUp = test_source_library_topic.SourceLibraryTopicTests.setUp
    tearDown = test_source_library_topic.SourceLibraryTopicTests.tearDown
    _bundle = test_source_library_topic.SourceLibraryTopicTests._bundle
    _register = test_source_library_topic.SourceLibraryTopicTests._register
    _map = test_source_library_topic.SourceLibraryTopicTests._map

    def test_registered_ids_survive_plan_preparation_reading_and_topic(self):
        bridge = CoreBridge(self.workspace)
        for index, (name, sid) in enumerate(NAMES):
            with self.subTest(source_id=sid):
                result = self._register(str(index), short_name=name, identity=f'paper:{index}')
                self.assertEqual(sid, result['source_id'])
                root = self.workspace / 'sources' / sid
                original = (root / 'source.yaml').read_bytes()
                self._map(sid)
                self.assertTrue(self.core.map_reading_plan(sid, draft=None)['reused'])
                state = (self.workspace / 'state.json').read_bytes()
                status = self.core.preparation_status(source_id=sid)
                for chunk_id in status['pending']:
                    args = dict(source_id=sid, plan_id=status['plan_id'], chunk_id=chunk_id)
                    self.assertEqual(sid, bridge.tool('prepare_chunk', json.dumps(args))['source_id'])
                    bridge.tool('prepare_translation', json.dumps({**args, 'translation': '准备译文'}))
                self.assertTrue(self.core.preparation_status(source_id=sid)['ready'])
                self.assertEqual(state, (self.workspace / 'state.json').read_bytes())
                self.core.switch_source(sid)
                current = self.core.get_current_chunk()
                self.assertEqual(sid, current['source_id'])
                receipt = dict(sourceId=sid, planId=current['plan_id'], chunkId=current['chunk_id'])
                self.assertEqual('准备译文', bridge.reference(receipt)['translation'])
                self.assertEqual(sid, self.core.read_source_range(source_id=sid, start=1, end=3)['source_id'])
                topic = f'topic-{index}'
                self.library.attach(sid, topic_title='Topic', topic_id=topic)
                self.assertEqual(sid, self.core.select_topic(topic)['source_id'])
                self.assertEqual(sid, self.core.read_topic_range(topic_id=topic, source_id=sid, start=1, end=3)['source_id'])
                self.assertEqual(sid, self.core.search_topic(topic_id=topic, query='Evidence')['matches'][0]['source_id'])
                self.core.continue_reading(expected_plan_id=current['plan_id'], expected_chunk_id=current['chunk_id'])
                self.assertEqual('chunk-002', self.core.get_current_chunk()['chunk_id'])
                self.assertEqual(original, (root / 'source.yaml').read_bytes())
        self.assertEqual({sid for _, sid in NAMES}, {p.name for p in (self.workspace / 'sources').iterdir()})

    def test_invalid_ids_rejected_at_every_source_boundary_without_mutation(self):
        self._register('valid', short_name='Valid', identity='paper:valid')
        self._map('Valid-paper')
        bridge = CoreBridge(self.workspace)
        operations = {
            'validator': validate_source_id,
            'library': self.library.get,
            'attach': lambda sid: self.library.attach(sid, topic_title='Topic'),
            'map': lambda sid: self.core.map_reading_plan(sid, draft=None),
            'preparation': lambda sid: self.core.preparation_status(source_id=sid),
            'prepare_chunk': lambda sid: self.core.preparation_chunk(source_id=sid, plan_id='plan-001', chunk_id='chunk-001'),
            'translation': lambda sid: self.core.save_prepared_translation(source_id=sid, plan_id='plan-001', chunk_id='chunk-001', translation='译文'),
            'range': lambda sid: self.core.read_source_range(source_id=sid, start=1, end=3),
            'switch': self.core.switch_source,
            'reference': lambda sid: bridge.reference(dict(sourceId=sid, planId='plan-001', chunkId='chunk-001')),
            'image': lambda sid: bridge.image(sid, 'image.png'),
        }
        before = {str(p): p.read_bytes() for p in self.workspace.rglob('*') if p.is_file()}
        for sid in INVALID_IDS:
            for name, operation in operations.items():
                with self.subTest(source_id=sid, operation=name):
                    with self.assertRaises(WorkspaceError) as caught:
                        operation(sid)
                    self.assertEqual('source_id_invalid', caught.exception.error_id)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.workspace.rglob('*') if p.is_file()})

    def test_strict_identifiers_remain_strict(self):
        self._register('valid', short_name='Valid Name', identity='paper:valid')
        self._map('Valid Name-paper')
        bridge = CoreBridge(self.workspace)
        for value in ['has space', 'has.dot', 'has_underscore', 'has（括号）', '../escape', '-leading', 'trailing-']:
            for kind in ['plan_id', 'chunk_id', 'topic_id']:
                with self.subTest(value=value, kind=kind):
                    with self.assertRaises(WorkspaceError):
                        _identifier(value, kind)
                    with self.assertRaises(WorkspaceError):
                        if kind == 'topic_id':
                            self.library.attach('Valid Name-paper', topic_title='Topic', topic_id=value)
                        else:
                            args = dict(source_id='Valid Name-paper', plan_id='plan-001', chunk_id='chunk-001')
                            args[kind] = value
                            self.core.preparation_chunk(**args)
                    if kind != 'topic_id':
                        receipt = dict(sourceId='Valid Name-paper', planId='plan-001', chunkId='chunk-001')
                        receipt[{'plan_id': 'planId', 'chunk_id': 'chunkId'}[kind]] = value
                        with self.assertRaises(WorkspaceError):
                            bridge.reference(receipt)
        self.assertEqual('中文-123', _identifier('中文-123', 'topic_id'))
        self.assertEqual('Readable Name-article', validate_source_id('Readable Name-article'))


class SourceIdHostTests(unittest.TestCase):
    setUp = test_web_host.WebHostTests.setUp
    tearDown = test_web_host.WebHostTests.tearDown
    finish = test_web_host.WebHostTests.finish

    def test_upload_prepare_open_and_reference_preserve_registered_ids(self):
        import test_source_library_topic as fixtures
        fixture = fixtures.SourceLibraryTopicTests()
        fixture.root = self.fixture.root
        fixture.workspace = self.workspace
        fixture.library = SourceLibrary(self.workspace)
        fixture.core = self.host.core.core
        for index, (name, sid) in enumerate(NAMES):
            with self.subTest(source_id=sid):
                bundle = fixture._bundle(f'upload-bundle-{index}')
                original_bytes = f'%PDF unique source {index}'.encode()
                (bundle / 'source.pdf').write_bytes(original_bytes)
                fixture.library.register(bundle, source_kind='paper_pdf', title=name.strip(), short_name=name, identity=f'paper:upload-{index}')
                fixture._map(sid)
                root = self.workspace / 'uploads' / f'upload-{index}'
                root.mkdir(parents=True)
                original = root / 'selected.pdf'
                original.write_bytes(original_bytes)
                self.host.store.put(f'upload:upload-{index}', {'name': original.name, 'path': str(original)})
                bridge = self.host.core

                class PreparingDouble(test_web_host.ProtocolDouble):
                    def request(self, method, params, timeout=60):
                        if method == 'turn/start':
                            status = bridge.tool('preparation', json.dumps({'source_id': sid}))
                            for chunk_id in status['pending']:
                                args = dict(source_id=sid, plan_id=status['plan_id'], chunk_id=chunk_id)
                                bridge.tool('prepare_chunk', json.dumps(args))
                                bridge.tool('prepare_translation', json.dumps({**args, 'translation': '上传准备译文'}))
                        return super().request(method, params, timeout)

                with patch('host.backends.codex.AppServer', side_effect=PreparingDouble):
                    self.host.library_upload(f'upload-{index}', topic='Upload Topic')
                    self.finish()
                self.assertEqual('completed', self.host.state['run']['status'])
                self.assertFalse(root.exists())
                self.assertIn(sid, next(t for t in self.host.library_topics() if t['topicId'] == 'upload-topic')['sourceIds'])
                self.host.library_read(sid)
                current = self.host.snapshot()['current']
                self.assertEqual(sid, current['sourceId'])
                receipt = {k: current[k] for k in ('sourceId', 'planId', 'chunkId')}
                self.host.start({'requestId': f'question-{index}', 'receipt': receipt, 'content': '解释这段'})
                self.finish()
                self.assertEqual('completed', self.host.state['run']['status'])
                self.host.continue_cached({'requestId': f'continue-{index}', 'receipt': receipt})
                self.assertEqual('chunk-002', self.host.snapshot()['current']['chunkId'])
                self.assertTrue((self.workspace / 'sources' / sid).is_dir())
        for sid in INVALID_IDS:
            with self.subTest(invalid_source_id=sid):
                with self.assertRaises(WorkspaceError) as caught:
                    self.host.library_read(sid)
                self.assertEqual('source_id_invalid', caught.exception.error_id)
