"""Reading Highlights exercise real storage through its public Core boundary."""
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import reading_fixture
from core.reading_workspace import WorkspaceError
from core.source_notes import SourceNotes, check_sentence
from core.source_highlights import SourceHighlights


class SourceHighlightsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reading_fixture.ReadingFixture()
        self.fixture.setUp()
        self.workspace = self.fixture._workspace()[0]
        self.notes = SourceNotes(self.workspace)
        self.highlights = SourceHighlights(self.notes)
        self.source = 'fixture-paper'
        self.bundle = self.notes.bundle_version(self.source)
        self.sentence = {'layer': 'source', 'range': {'start': 0, 'end': 7},
                         'quote': {'exact': '😀 text', 'prefix': '', 'suffix': ''}}
        self.locator = {'planId': 'plan-001', 'chunkId': 'chunk-001', **self.sentence}

    def tearDown(self):
        self.fixture.tearDown()

    def save(self, request_id='highlight-create', **changes):
        return self.highlights.save(self.source, **{'request_id': request_id,
            'plan_bundle': self.bundle, 'chunk_lines': [1, 6], 'locator': self.locator, **changes})

    def test_create_replay_reopen_and_public_fields(self):
        first = self.save()
        self.assertEqual(first, self.save())
        self.assertEqual(first, self.highlights.result(self.source, 'highlight-create'))
        highlight = first['highlight']
        self.assertEqual('saved', first['status'])
        self.assertEqual(self.locator, {key: highlight[key] for key in self.locator})
        self.assertEqual([1, 6], highlight['sourceLines'])
        self.assertEqual(self.bundle, highlight['bundle'])
        self.assertEqual(self.source, highlight['sourceId'])
        self.assertEqual(1, highlight['revision'])
        self.assertTrue(highlight['canUndo'])
        self.assertFalse(highlight['deleted'])
        self.assertFalse(highlight['sourceUpdated'])
        self.assertRegex(highlight['highlightId'], r'^[0-9a-f]{32}$')
        self.assertEqual([highlight], SourceHighlights(SourceNotes(self.workspace)).list(self.source))

    def change(self, highlight, operation, request_id, revision=None):
        return self.highlights.change(self.source, highlight_id=highlight['highlightId'],
            request_id=request_id, expected_revision=revision or highlight['revision'], operation=operation)

    def test_delete_undo_and_revision_conflicts_are_durable_and_replayable(self):
        created = self.save()['highlight']
        deleted = self.change(created, 'delete', 'highlight-delete')
        self.assertTrue(deleted['highlight']['deleted'])
        self.assertEqual([], self.highlights.list(self.source))
        self.assertEqual(deleted, self.change(created, 'delete', 'highlight-delete'))
        restored = self.change(deleted['highlight'], 'undo', 'highlight-restore')['highlight']
        self.assertEqual(3, restored['revision'])
        self.assertFalse(restored['deleted'])
        self.assertFalse(restored['canUndo'])
        for request, revision in [('highlight-stale', 1), ('highlight-no-undo', 3)]:
            conflict = self.change(restored, 'undo', request, revision)
            self.assertEqual({'status': 'conflict', 'current': restored}, conflict)
            self.assertEqual(conflict, self.highlights.result(self.source, request))
        fresh = self.save('highlight-second')['highlight']
        undone = self.change(fresh, 'undo', 'highlight-uncreate')['highlight']
        self.assertTrue(undone['deleted'])
        self.assertEqual(2, undone['revision'])
        self.assertEqual([restored], self.highlights.list(self.source))
        self.assertEqual(2, len(self.highlights.list(self.source, include_deleted=True)))

    def test_clear_erases_highlights_revokes_requests_and_fences_inflight_writes(self):
        generation = self.notes.generation(self.source)
        self.save()
        self.notes.clear(self.source, request_id='clear-highlights')
        self.assertEqual([], self.highlights.list(self.source, include_deleted=True))
        self.assertEqual({'status': 'cancelled'}, self.highlights.result(self.source, 'highlight-create'))
        with self.assertRaises(WorkspaceError) as caught:
            self.save('stale-highlight', expected_generation=generation)
        self.assertEqual('discussion_cleared', caught.exception.error_id)
        with self.assertRaises(WorkspaceError) as caught:
            self.save()
        self.assertEqual('note_cancelled', caught.exception.error_id)

    def test_locator_validation_accepts_utf16_and_rejects_invalid_selections(self):
        self.assertEqual(self.locator, check_sentence(self.sentence, plan_id='plan-001',
            chunk_id='chunk-001', has_translation=False, code='highlight_invalid'))
        invalid = [None, {**self.sentence, 'other': True}, {**self.sentence, 'layer': []},
            {**self.sentence, 'layer': 'other'}, {**self.sentence, 'layer': 'translation'},
            {**self.sentence, 'range': None}, {**self.sentence, 'range': {'start': 0, 'end': 1, 'other': 1}},
            *[{**self.sentence, 'range': {'start': start, 'end': end}}
              for start, end in [(-1, 1), (1, 1), (2, 1), (0, 2001), (True, 2), (0, 1.5)]],
            {**self.sentence, 'quote': None},
            *[{**self.sentence, 'quote': {**self.sentence['quote'], **change}}
              for change in [{'other': ''}, {'exact': ''}, {'exact': 'x' * 2001},
                             {'prefix': 'x' * 65}, {'suffix': 'x' * 65}, {'exact': 1}]]]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(WorkspaceError) as caught:
                check_sentence(value, plan_id='plan-001', chunk_id='chunk-001',
                               has_translation=False, code='note_sentence_invalid')
            self.assertEqual('note_sentence_invalid', caught.exception.error_id)
        translated = check_sentence({**self.sentence, 'layer': 'translation'},
            plan_id='plan-001', chunk_id='chunk-001', has_translation=True, code='highlight_invalid')
        self.assertEqual('translation', translated['layer'])

    def test_conflicting_requests_missing_highlights_and_changed_bundle(self):
        self.save()
        changed = {**self.locator, 'range': {'start': 3, 'end': 9}}
        with self.assertRaises(WorkspaceError) as caught:
            self.save(locator=changed)
        self.assertEqual('highlight_request_conflict', caught.exception.error_id)
        with self.assertRaises(WorkspaceError) as caught:
            self.change({'highlightId': '0' * 32, 'revision': 1}, 'delete', 'missing-highlight')
        self.assertEqual('highlight_not_found', caught.exception.error_id)
        for operation, revision in [('edit', 1), ('undo', True), ('undo', 0)]:
            with self.subTest(operation=operation, revision=revision), self.assertRaises(WorkspaceError) as caught:
                self.highlights.change(self.source, highlight_id='0' * 32, operation=operation,
                    expected_revision=revision, request_id='invalid-highlight')
            self.assertEqual('highlight_invalid', caught.exception.error_id)
        content = self.workspace / 'sources' / self.source / 'parser-bundle/content.md'
        content.write_text(content.read_text(encoding='utf-8') + '\nUpdated.\n', encoding='utf-8')
        self.assertTrue(self.highlights.list(self.source)[0]['sourceUpdated'])
        with self.assertRaises(WorkspaceError) as caught:
            self.save('changed-bundle')
        self.assertEqual('highlight_bundle_changed', caught.exception.error_id)

    def test_failed_receipt_write_rolls_back_highlight_and_can_retry(self):
        real_connect = sqlite3.connect
        class FailingReceipt(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql.startswith('INSERT INTO requests'):
                    raise sqlite3.OperationalError('injected receipt failure')
                return super().execute(sql, parameters)
        def connect(*args, **kwargs):
            return real_connect(*args, **kwargs, factory=FailingReceipt)
        with patch('sqlite3.connect', connect), self.assertRaises(sqlite3.OperationalError):
            self.save()
        self.assertEqual([], self.highlights.list(self.source, include_deleted=True))
        self.assertIsNone(self.highlights.result(self.source, 'highlight-create'))
        self.assertEqual('saved', self.save()['status'])

    def test_old_notes_database_migrates_sentence_and_highlight_storage(self):
        root = self.workspace / 'sources' / self.source / 'notes'
        root.mkdir()
        with closing(sqlite3.connect(root / 'notes.sqlite3')) as db, db:
            db.execute('CREATE TABLE notes (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, '
                       'content TEXT NOT NULL, kind TEXT NOT NULL, origin TEXT NOT NULL, '
                       'bundle TEXT NOT NULL, anchor TEXT, evidence_role TEXT NOT NULL, deleted INTEGER NOT NULL, undo TEXT)')
            db.execute('INSERT INTO notes VALUES (?, 1, ?, ?, ?, ?, NULL, ?, 0, NULL)',
                       ('a' * 32, 'Old note', 'thought', 'user', self.bundle, 'explanation'))
        self.assertIsNone(self.notes.list(self.source)[0]['sentence'])
        self.assertEqual('saved', self.save()['status'])
        saved = self.notes.save(self.source, bundle=self.bundle, request_id='migration-note',
            intent_id='migration-intent', content='New note', kind='thought', origin='user', evidence_role='explanation')
        self.assertIsNone(saved['note']['sentence'])
        self.assertEqual(2, len(self.notes.list(self.source)))


if __name__ == '__main__':
    unittest.main()
