"""Annotation occupancy is enforced by the shared public Core transaction boundary."""
import unittest
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import reading_fixture
from core.reading_workspace import WorkspaceError
from core.source_notes import SourceNotes
from core.source_highlights import SourceHighlights


class AnnotationOverlapTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reading_fixture.ReadingFixture(); self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.notes = SourceNotes(self.workspace)
        self.highlights = SourceHighlights(self.notes)
        self.source = 'fixture-paper'
        self.bundle = self.notes.bundle_version(self.source)
        self.locator = {'planId': 'plan-001', 'chunkId': 'chunk-001', 'layer': 'source',
                        'range': {'start': 0, 'end': 7}, 'quote': {'exact': 'Example', 'prefix': '', 'suffix': ''}}

    def tearDown(self):
        self.fixture.tearDown()

    def highlight(self, request, locator=None, store=None):
        return (store or self.highlights).save(self.source, request_id=request, plan_bundle=self.bundle,
            chunk_lines=[1, 6], locator=locator or self.locator)

    def note(self, request, locator=None, store=None):
        return (store or self.notes).save(self.source, request_id=request, intent_id=request,
            bundle=self.bundle, content='My own note', kind='thought', origin='user', evidence_role='explanation',
            anchor={'sourceId': self.source, 'bundle': self.bundle, 'sourceLines': [1, 6]}, sentence=locator or self.locator)

    def test_other_request_cannot_duplicate_highlight_but_original_request_replays(self):
        first = self.highlight('original-highlight')
        with self.assertRaises(WorkspaceError) as error:
            self.highlight('other-highlight')
        self.assertEqual('highlight_overlap', error.exception.error_id)
        self.assertEqual(first, self.highlight('original-highlight'))
        self.assertEqual([first['highlight']], self.highlights.list(self.source))
        self.assertIsNone(self.highlights.result(self.source, 'other-highlight'))

    def test_other_tab_cannot_create_a_duplicate_note_or_adopt_its_content(self):
        first = self.note('original-note')
        with self.assertRaises(WorkspaceError) as error:
            self.note('other-tab-note', store=SourceNotes(self.workspace, writer_id='other-tab'))
        self.assertEqual('note_sentence_overlap', error.exception.error_id)
        self.assertEqual(first, self.note('original-note'))
        self.assertEqual([first['note']], self.notes.list(self.source))
        self.assertIsNone(self.notes.result(self.source, 'other-tab-note'))

    def test_exact_cross_entity_pair_is_allowed_but_partial_or_contained_ranges_are_not(self):
        for first, second in [(self.highlight, self.note), (self.note, self.highlight)]:
            with self.subTest(first=first.__name__):
                self.notes.clear(self.source, request_id='clear-' + first.__name__)
                first('first-' + first.__name__)
                second('paired-' + first.__name__)
                for index, span in enumerate([(2, 9), (1, 6), (0, 8)]):
                    locator = {**self.locator, 'range': dict(zip(('start', 'end'), span))}
                    for create in (self.note, self.highlight):
                        with self.assertRaises(WorkspaceError):
                            create(f'overlap-{first.__name__}-{create.__name__}-{index}', locator)
                self.assertEqual(1, len(self.highlights.list(self.source)))
                self.assertEqual(1, len(self.notes.list(self.source)))

    def test_touching_ranges_and_other_layers_chunks_or_plans_are_independent(self):
        self.highlight('first-highlight')
        for index, change in enumerate([{'range': {'start': 7, 'end': 12}}, {'layer': 'translation'},
                                         {'chunkId': 'chunk-002'}, {'planId': 'plan-002'}]):
            self.assertEqual('saved', self.highlight(f'independent-{index}', {**self.locator, **change})['status'])

    def test_concurrent_tab_writes_share_occupancy(self):
        barrier = Barrier(2)
        def write(index):
            store = SourceHighlights(SourceNotes(self.workspace, writer_id=f'tab-{index}'))
            barrier.wait()
            try:
                return self.highlight(f'concurrent-{index}', store=store)['status']
            except WorkspaceError as error:
                return error.error_id
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(['saved', 'highlight_overlap'], pool.map(write, range(2)))
        self.assertEqual(1, len(self.highlights.list(self.source)))

    def test_independent_process_writers_share_the_same_transactional_occupancy(self):
        self.notes.generation(self.source)
        program = '''
import json, sys
from pathlib import Path
from core.source_notes import SourceNotes
from core.source_highlights import SourceHighlights
from core.reading_workspace import WorkspaceError
store = SourceHighlights(SourceNotes(Path(sys.argv[1])))
print('ready', flush=True)
sys.stdin.readline()
try:
    result = store.save(sys.argv[2], plan_bundle=sys.argv[3], locator=json.loads(sys.argv[4]),
                        request_id=sys.argv[5], chunk_lines=[1, 6])['status']
except WorkspaceError as error:
    result = error.error_id
print(result, flush=True)
'''
        processes = [subprocess.Popen([sys.executable, '-c', program, str(self.workspace), self.source,
                                      self.bundle, json.dumps(self.locator), f'process-{index}'],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for index in range(2)]
        try:
            for process in processes:
                self.assertEqual('ready', process.stdout.readline().strip())
            for process in processes:
                process.stdin.write('go\n'); process.stdin.flush()
            outcomes = [process.communicate(timeout=30) for process in processes]
            self.assertEqual([0, 0], [process.returncode for process in processes], outcomes)
            self.assertCountEqual(['saved', 'highlight_overlap'], [out.strip() for out, _ in outcomes])
            self.assertEqual(1, len(self.highlights.list(self.source)))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill(); process.communicate()

    def test_failed_restore_retains_deleted_record_revision_and_recovery_slot(self):
        for create, store, entity, id_key in [(self.highlight, self.highlights, 'highlight', 'highlightId'),
                                             (self.note, self.notes, 'note', 'noteId')]:
            with self.subTest(entity=entity):
                self.notes.clear(self.source, request_id='clear-undo-' + entity)
                old = create('old-' + entity)[entity]
                change = {id_key.replace('Id', '_id'): old[id_key], 'expected_revision': 1,
                          'operation': 'delete', 'request_id': 'delete-' + entity}
                deleted = store.change(self.source, **change)[entity]
                # A different entity with a partial overlap also prevents restoration.
                other = self.note if entity == 'highlight' else self.highlight
                occupied = other('occupier-' + entity, {**self.locator, 'range': {'start': 3, 'end': 10}})
                restore = {**change, 'expected_revision': 2, 'operation': 'undo', 'request_id': 'restore-' + entity}
                with self.assertRaises(WorkspaceError):
                    store.change(self.source, **restore)
                self.assertEqual([deleted], store.list(self.source, include_deleted=True))
                self.assertTrue(deleted['canUndo'])
                self.assertIsNone(store.result(self.source, 'restore-' + entity))
                other_entity = 'note' if entity == 'highlight' else 'highlight'
                other_store = self.notes if entity == 'highlight' else self.highlights
                other_id = 'note_id' if entity == 'highlight' else 'highlight_id'
                other_store.change(self.source, **{other_id: occupied[other_entity]['noteId' if entity == 'highlight' else 'highlightId'],
                    'expected_revision': 1, 'operation': 'delete', 'request_id': 'free-range-' + entity})
                restored = store.change(self.source, **restore)
                self.assertFalse(restored[entity]['deleted'])
                self.assertEqual(3, restored[entity]['revision'])
                self.assertEqual(restored, store.change(self.source, **restore))


if __name__ == '__main__':
    unittest.main()
