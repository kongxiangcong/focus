"""Workspace public lifecycle: format, process ownership and copied history."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

from host.service import HostService
from host.core_bridge import WorkspaceError


@contextmanager
def test_directory():
    root = Path(__file__).resolve().parents[1] / 'tmp' / ('portable-' + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


class WorkspacePortabilityTests(unittest.TestCase):
    def test_raw_mineru_array_evidence_survives_reopen(self):
        with test_directory() as root:
            host = HostService(root / 'workspace', None)
            evidence = host.workspace / 'sources/paper/parser-bundle/mineru/model_output.json'
            evidence.parent.mkdir(parents=True)
            evidence.write_text('[{"type":"text","content":"source evidence"}]')
            before = evidence.read_bytes()
            host.close()
            reopened = HostService(root / 'workspace', None)
            self.assertEqual(before, evidence.read_bytes())
            reopened.close()

    def test_uploaded_workspace_relative_reference_stages_actual_bytes(self):
        with test_directory() as root:
            host = HostService(root / 'workspace', None)
            try:
                upload = host.workspace / 'uploads/test.pdf'
                upload.parent.mkdir()
                upload.write_bytes(b'%PDF portable upload')
                host.store.put('upload:test', {'name': 'test.pdf', 'path': 'uploads/test.pdf'})
                staged = host.inbox_stage('test')
                item_root = host.workspace / 'inbox' / staged['item_id']
                self.assertIn(b'%PDF portable upload', [p.read_bytes() for p in item_root.iterdir() if p.is_file()])
            finally:
                host.close()

    def test_live_retention_writer_keeps_workspace_locked_on_close(self):
        from unittest.mock import patch
        with test_directory() as root:
            host = HostService(root / 'workspace', None)
            with patch.object(host.retention_worker, 'is_alive', return_value=True):
                with self.assertRaises(WorkspaceError) as caught:
                    host.close()
                self.assertEqual('workspace_stop_incomplete', caught.exception.error_id)
                self.assertFalse(host.lease.handle.closed)
                with self.assertRaises(WorkspaceError):
                    HostService(host.workspace, None)
            host.close()

    def test_supported_cli_entry_rejects_unversioned_layout_without_writing(self):
        from core.workspace_lifecycle import open_command_workspace
        with test_directory() as root:
            (root / 'state.json').write_text('{}')
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with self.assertRaises(WorkspaceError):
                open_command_workspace(root)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})

    def test_old_process_late_operation_rejected_after_takeover(self):
        with test_directory() as root:
            script = ('from pathlib import Path; import sys; from host.service import HostService; '
                'from core.source_library import SourceLibrary; '
                'h=HostService(Path(sys.argv[1]),Path("unused")); old=SourceLibrary(h.workspace); '
                'h.close(); print("released",flush=True); sys.stdin.readline(); '
                'exec("try:\\n old.create_topic(\'late\')\\nexcept Exception as e:\\n print(e.error_id,flush=True)")')
            child = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', script, str(root / 'workspace')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual('released', child.stdout.readline().strip())
                current = HostService(root / 'workspace', root / 'machine')
                try:
                    output, error = child.communicate('commit\n', timeout=10)
                    self.assertEqual(0, child.returncode, error)
                    self.assertIn('workspace_instance_expired', output)
                    self.assertEqual([], current.library_topics())
                finally:
                    current.close()
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate(timeout=5)

    def test_note_receipt_replays_after_reopen_with_new_writer(self):
        from test_source_discussion import DiscussionTests
        fixture = DiscussionTests()
        fixture.setUp()
        host = fixture.host
        try:
            host.select_discussion_source('fixture-paper')
            saved = host.source_notes.save('fixture-paper', bundle=host.source_notes.bundle_version('fixture-paper'),
                request_id='portable-note-request', intent_id='portable-note-intent', content='keep this',
                kind='conclusion', origin='user', evidence_role='explanation')
            note_id = saved['note']['noteId']
            payload = {'requestId': 'portable-note-edit', 'expectedRevision': 1, 'content': 'corrected'}
            first = host.source_note_change('fixture-paper', note_id, payload, 'edit')['noteOperation']
            host.close()
            fixture.host = HostService(fixture.workspace, fixture.fixture.root / 'other-machine')
            fixture.host.select_discussion_source('fixture-paper')
            repeated = fixture.host.source_note_change('fixture-paper', note_id, payload, 'edit')['noteOperation']
            self.assertEqual(first, repeated)
            self.assertEqual(1, len(fixture.host.snapshot()['sourceNotes']))
        finally:
            fixture.tearDown()

    def test_closed_core_cannot_write_after_new_instance_takes_over(self):
        with test_directory() as root:
            host = HostService(root / 'workspace', root / 'machine')
            old_library = __import__('core.source_library', fromlist=['SourceLibrary']).SourceLibrary(host.workspace)
            old_instance = host.lease.instance_id
            old_store = host.store
            host.close()
            reopened = HostService(root / 'workspace', root / 'new-machine')
            try:
                self.assertNotEqual(old_instance, reopened.lease.instance_id)
                with self.assertRaises(WorkspaceError) as caught:
                    old_library.create_topic('late result')
                self.assertEqual('workspace_instance_expired', caught.exception.error_id)
                self.assertEqual([], reopened.library_topics())
                with self.assertRaises(WorkspaceError) as store_error:
                    old_store.put('late', {'business': 'stale'})
                self.assertEqual('workspace_instance_expired', store_error.exception.error_id)
            finally:
                reopened.close()

    def test_incompatible_format_does_not_create_lock_or_business_store(self):
        with test_directory() as root:
            (root / 'focus-workspace.json').write_text(json.dumps({'workspaceId': str(uuid.uuid4()),
                'formatVersion': 99, 'minimumReader': 99, 'minimumWriter': 99}))
            with self.assertRaises(WorkspaceError):
                HostService(root, root / 'machine')
            self.assertEqual(['focus-workspace.json'], [p.name for p in root.iterdir()])

    def test_empty_workspace_gets_identity_and_copy_retains_discussions(self):
        with test_directory() as directory:
            root = Path(directory)
            workspace = root / '中文 workspace'
            host = HostService(workspace, root / 'machine')
            identity = host.snapshot()['workspace']['workspaceId']
            host.store.state['conversation'].append({'messageId': 'saved', 'role': 'user', 'content': 'portable'})
            host.store.save()
            host.close()
            shutil.copytree(workspace, root / 'restored')
            shutil.rmtree(workspace)
            restored = HostService(root / 'restored', root / 'new-machine')
            try:
                self.assertEqual(identity, restored.snapshot()['workspace']['workspaceId'])
                self.assertEqual('portable', restored.snapshot()['conversation'][0]['content'])
                self.assertFalse((root / 'new-machine').exists())
            finally:
                restored.close()

    def test_old_directory_rejected_before_any_write(self):
        with test_directory() as directory:
            workspace = Path(directory)
            (workspace / 'state.json').write_text('{}')
            before = {p.name: p.read_bytes() for p in workspace.iterdir()}
            with self.assertRaises(WorkspaceError):
                HostService(workspace, workspace.parent / 'unused-host')
            self.assertEqual(before, {p.name: p.read_bytes() for p in workspace.iterdir()})

    def test_second_process_refused_then_crash_takeover(self):
        with test_directory() as directory:
            workspace = Path(directory) / 'workspace'
            host = HostService(workspace, Path(directory) / 'machine')
            host.close()
            script = ('from pathlib import Path; from host.service import HostService; import time; '
                      'h=HostService(Path(__import__("sys").argv[1]), Path("unused")); '
                      'print("ready", flush=True); time.sleep(30)')
            child = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', script, str(workspace)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual('ready', child.stdout.readline().strip())
                with self.assertRaises(WorkspaceError) as caught:
                    HostService(workspace, Path(directory) / 'other-machine')
                self.assertEqual('workspace_busy', caught.exception.error_id)
            finally:
                child.kill()
                child.communicate(timeout=5)
            reopened = HostService(workspace, Path(directory) / 'other-machine')
            reopened.close()


if __name__ == '__main__':
    unittest.main()
