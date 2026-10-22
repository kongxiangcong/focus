"""Article structure validation and persisted first-entry semantics."""
import copy
import json
import unittest
import uuid
import test_stage4_reading as stage4
from workspace_fixture import HostService
from core.reading_structure import validate_structure, legacy_structure
from core.reading_workspace import WorkspaceError


class StructureValidationTests(unittest.TestCase):
    def setUp(self):
        self.chunks = [{'source_lines': [1, 4], 'section_path': ['Paper', 'Method']},
                       {'source_lines': [5, 8], 'section_path': ['Paper', 'Results']}]
        self.tree = legacy_structure(self.chunks)
        for node in self.tree['nodes']:
            node['description'] = '解释本部分的作用。'

    def test_tree_and_exact_binding(self):
        self.assertEqual(self.tree, validate_structure(self.tree, self.chunks))
        self.assertEqual(['section-002', 'section-003'], self.tree['chunk_nodes'])

    def test_rejects_unbound_cycles_outside_anchors_and_reordering(self):
        variants = []
        for field, value in [('parent_id', 'section-003'), ('source_lines', [1, 9]), ('title', '长' * 33)]:
            tree = copy.deepcopy(self.tree)
            tree['nodes'][0][field] = value
            variants.append(tree)
        tree = copy.deepcopy(self.tree); tree['chunk_nodes'][1] = 'section-002'; variants.append(tree)
        tree = copy.deepcopy(self.tree); tree['chunk_nodes'].pop(); variants.append(tree)
        tree = copy.deepcopy(self.tree); tree['nodes'][2]['source_lines'] = [4, 8]; variants.append(tree)
        for value in [None, {}, *variants]:
            with self.subTest(value=value), self.assertRaises(WorkspaceError):
                validate_structure(value, self.chunks)

    def test_repeated_heading_occurrences_get_distinct_ids(self):
        chunks = [*self.chunks, {'source_lines': [9, 12], 'section_path': ['Paper', 'Method']}]
        tree = legacy_structure(chunks)
        self.assertNotEqual(tree['chunk_nodes'][0], tree['chunk_nodes'][2])
        self.assertTrue(all(n['description'] == '' for n in tree['nodes']))


class StructureEntryTests(unittest.TestCase):
    setUp = stage4.Stage4PreparationTests.setUp
    tearDown = stage4.Stage4PreparationTests.tearDown

    def prepare(self):
        self.host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex)
        self.host.reading_workers['fixture-paper'].join(3)
        return self.host.open_prepared_reading('fixture-paper', request_id=uuid.uuid4().hex)

    def test_intro_survives_restart_then_start_is_idempotent_and_versioned(self):
        view = self.prepare()
        self.assertTrue(view['structureIntro'])
        self.assertIsNone(view['current'])
        self.assertFalse(view['readingStarted'])
        self.assertFalse(view['readingProgress'])
        self.assertFalse([e for e in view['timeline'] if e['kind'] == 'reading'])
        self.assertTrue(all(n['description'] == '' for n in view['structure']))
        self.host.close()
        self.host = HostService(self.workspace, self.fixture.root / 'host', reading_runtime=self.runtime)
        self.assertTrue(self.host.snapshot()['structureIntro'])
        receipt = {k: view['navigationCurrent'][k] for k in ('sourceId', 'planId', 'chunkId')}
        receipt['readingRevision'] = view['readingRevision']
        payload = {'receipt': receipt, 'beginBody': True, 'requestId': uuid.uuid4().hex}
        started = self.host.continue_cached(payload)
        self.assertEqual('chunk-001', started['current']['chunkId'])
        self.assertFalse(started['structureIntro'])
        self.assertFalse(started['readingProgress'])
        replay = self.host.continue_cached(payload)
        self.assertEqual(started['readingOperation'], replay['readingOperation'])
        self.assertEqual(len(started['timeline']), len(replay['timeline']))
        with self.assertRaises(WorkspaceError):
            self.host.continue_cached({**payload, 'requestId': uuid.uuid4().hex})
        reopened = self.host.open_prepared_reading('fixture-paper', request_id=uuid.uuid4().hex)
        self.assertFalse(reopened['structureIntro'])

    def test_unread_review_is_blocked_on_intro(self):
        view = self.prepare()
        with self.assertRaises(WorkspaceError):
            self.host.review_chunk('fixture-paper', view['navigationCurrent']['planId'], 'chunk-001')

    def test_new_structure_is_saved_and_readiness_covers_its_content(self):
        plan = self.workspace / 'sources/fixture-paper/reading/plans/plan-001'
        chunks = [json.loads(line) for line in (plan / 'chunks.jsonl').read_text(encoding="utf-8").splitlines()]
        draft = {'chunks': [{k: c[k] for k in ('section_path', 'source_lines', 'images')} for c in chunks], 'glossary': []}
        self.host.reading_app.runtime = stage4.PlanningRuntime(draft)
        self.host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex, rebuild=True)
        self.host.reading_workers['fixture-paper'].join(3)
        ready = self.host.snapshot()['preparations']['fixture-paper']
        self.assertTrue(ready['ready'])
        root = plan.parent / ready['plan_id']
        saved = json.loads((root / 'structure.json').read_text(encoding='utf-8'))
        self.assertEqual(len(chunks), len(saved['chunk_nodes']))
        activated = self.host.activate_reading_candidate('fixture-paper', {'planId': ready['plan_id'],
            'readingRevision': self.host.snapshot()['readingRevision'], 'requestId': uuid.uuid4().hex})
        self.assertTrue(activated['structureIntro'])
        self.assertEqual(saved['chunk_nodes'], [c['nodeId'] for c in activated['outline']])
        self.assertTrue(all(n['description'] for n in activated['structure']))
        saved['nodes'][0]['description'] = '未经重新准备的修改。'
        (root / 'structure.json').write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
        self.assertFalse(self.host.reading_app.core._plan_ready('fixture-paper', ready['plan_id']))
