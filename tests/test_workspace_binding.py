"""The public Workbench binding lifecycle with real Workspace/Core storage."""
import shutil
import json
import uuid
import threading
import http.client
import re
import os
import subprocess
import sys
import socket
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from test_workspace_portability import test_directory
from host.workbench import Workbench
from host.core_bridge import WorkspaceError


class WorkspaceBindingTests(unittest.TestCase):
    def test_corrupt_deletion_receipt_cannot_exempt_or_delete_other_assets(self):
        from core.workspace_lifecycle import create_workspace
        with test_directory() as root:
            app = Workbench(settings_path=root / 'settings.json')
            for relative in ('sources', 'blog', 'inbox', 'discussions', 'sources/active',
                             'blog/candidates/active-' + '1' * 32):
                target = root / str(uuid.uuid4())
                create_workspace(target)
                active = target / 'sources/active/keep.txt'
                active.parent.mkdir(parents=True)
                active.write_text('Another source must survive')
                (target / 'state.json').write_text(json.dumps({'current_source_id': None, 'sources': {},
                    'deleted_sources': {'removed': {'pending_cleanup': True, 'cleanup_paths': [relative]}}}))
                before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()}
                with self.assertRaises(WorkspaceError):
                    app.bind({'mode': 'import', 'path': str(target)})
                self.assertEqual(before, {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()})
            app.close()

    def test_original_close_failure_rolls_back_saved_target(self):
        with test_directory() as root:
            app = Workbench(settings_path=root / 'settings.json')
            first = app.bind({'mode': 'create', 'path': str(root), 'name': 'first'})
            before = app.settings.path.read_bytes()
            with patch.object(app.host, 'close', side_effect=OSError('checkpoint failed')):
                with self.assertRaises(OSError):
                    app.bind({'mode': 'create', 'path': str(root), 'name': 'second',
                              'configuration': {'backend': 'deepseek'}})
            self.assertEqual(before, app.settings.path.read_bytes())
            self.assertEqual(first['workspace'], app.status()['workspace'])
            app.host.library_manage('create-topic', title='still writable')
            app.close()

    def test_old_binding_generation_cannot_submit_workspace_or_backend_draft(self):
        with test_directory() as root:
            app = Workbench(settings_path=root / 'settings.json')
            initial = app.status()['generation']
            first = app.bind({'mode': 'create', 'path': str(root), 'name': 'first'}, expected_generation=initial)
            with self.assertRaises(WorkspaceError):
                app.bind({'mode': 'create', 'path': str(root), 'name': 'late',
                          'configuration': {'backend': 'deepseek'}}, expected_generation=initial)
            self.assertFalse((root / 'late').exists())
            self.assertEqual(first['workspace'], app.status()['workspace'])
            self.assertEqual('codex', app.configuration_status()['effective']['backend'])
            app.close()

    def test_corrupt_import_is_read_only_and_keeps_original_binding(self):
        from core.workspace_lifecycle import create_workspace
        with test_directory() as root:
            app = Workbench(settings_path=root / 'settings.json')
            first = app.bind({'mode': 'create', 'path': str(root), 'name': 'first'})
            for filename, content in [('state.json', '{invalid'), ('state.json', '[]'),
                                      ('discussions/host.sqlite3', 'not a database')]:
                target = root / str(uuid.uuid4())
                create_workspace(target)
                broken = target / filename
                broken.parent.mkdir(parents=True, exist_ok=True)
                broken.write_text(content)
                before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()}
                with self.assertRaises(WorkspaceError):
                    app.bind({'mode': 'import', 'path': str(target)})
                self.assertEqual(before, {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()})
                self.assertEqual(first['workspace'], app.status()['workspace'])
            app.close()

    def test_corrupt_session_schema_is_rejected_before_database_changes(self):
        import sqlite3
        from core.workspace_lifecycle import create_workspace
        with test_directory() as root:
            target = root / 'corrupt'
            create_workspace(target)
            database = target / 'discussions/host.sqlite3'
            database.parent.mkdir()
            connection = sqlite3.connect(database)
            connection.execute('CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            connection.execute('INSERT INTO state VALUES (?,?)', ('session', '{"conversation":[]}'))
            connection.commit(); connection.close()
            before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()}
            app = Workbench(settings_path=root / 'settings.json')
            with self.assertRaises(WorkspaceError):
                app.bind({'mode': 'import', 'path': str(target)})
            self.assertEqual(before, {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()})
            app.close()

    def test_project_copy_and_different_cwd_keep_external_workspace(self):
        repo = Path(__file__).resolve().parents[1]
        with test_directory() as root:
            settings = root / 'machine/settings.json'
            app = Workbench(settings_path=settings)
            first = app.bind({'mode': 'create', 'path': str(root), 'name': '阅读 data'})
            app.host.library_manage('create-topic', title='preserved topic')
            app.close()
            project = root / '移动 project'
            for directory in ('host', '.agents/core', 'methods', 'ui/apps/standalone/dist'):
                shutil.copytree(repo / directory, project / directory, ignore=shutil.ignore_patterns('__pycache__'))
            other_cwd = root / 'outside'
            other_cwd.mkdir()
            script = ('import sys,threading; from host.workbench import Workbench; from host.server import Server; '
                'app=Workbench(codex_bin="missing-optional-runtime"); server=Server(("127.0.0.1",0),app); '
                'worker=threading.Thread(target=server.serve_forever); worker.start(); '
                'print(server.server_port,flush=True); sys.stdin.readline(); '
                'server.shutdown(); worker.join(); server.server_close(); app.close()')
            child = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', '-c', script], cwd=other_cwd,
                env={**os.environ, 'PYTHONPATH': str(project), 'FOCUS_SETTINGS_FILE': str(settings)},
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                port = int(child.stdout.readline().strip())
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                conn.request('GET', '/reader/workspace')
                response = conn.getresponse()
                binding = json.loads(response.read())['value']
                self.assertEqual(first['workspace']['workspaceId'], binding['workspace']['workspaceId'])
                conn.request('GET', '/library/topics', headers={'X-FOCUS-Instance': binding['workspace']['instanceId']})
                response = conn.getresponse()
                self.assertEqual('preserved topic', json.loads(response.read())['value'][0]['title'])
                conn.request('GET', '/')
                response = conn.getresponse()
                self.assertEqual(200, response.status)
                self.assertIn(b'<html', response.read())
                conn.close()
                output, error = child.communicate('\n', timeout=10)
                self.assertEqual(0, child.returncode, error)
            finally:
                if child.poll() is None:
                    child.kill(); child.communicate(timeout=5)

    def test_unknown_remote_outcome_survives_copy_without_resubmission(self):
        from test_ingestion_application import UnknownAcceptanceParser
        with test_directory() as root:
            parser = UnknownAcceptanceParser()
            app = Workbench(settings_path=root / 'machine/settings.json', ingestion_parser=parser)
            app.bind({'mode': 'create', 'path': str(root), 'name': 'original'})
            original = root / 'pending.pdf'
            original.write_bytes(b'%PDF unknown')
            item = app.host.ingestion.stage_file(original)
            app.host.inbox_confirm(item['item_id'])
            app.host.ingestion.process(item['item_id'], request_id='remote-unknown')
            before = app.host.ingestion.get(item['item_id'])
            self.assertEqual('status_check_required', before['status'])
            app.close()
            shutil.copytree(root / 'original', root / 'copy')
            replacement = UnknownAcceptanceParser()
            restored = Workbench(settings_path=root / 'fresh/settings.json', ingestion_parser=replacement)
            try:
                restored.bind({'mode': 'import', 'path': str(root / 'copy')})
                after = restored.host.ingestion.get(item['item_id'])
                self.assertEqual(before['status'], after['status'])
                self.assertEqual(0, replacement.calls)
            finally:
                restored.close()

    def test_complete_stopped_copy_import_preserves_assets_and_can_continue(self):
        from test_stage4_reading import Stage4NavigationTests, ReadingRuntimeDouble
        from test_source_discussion import CandidateRuntime
        from test_blog_host import ControlledBlogRuntime, ParserDouble
        fixture = Stage4NavigationTests()
        fixture.setUp()
        root = fixture.fixture.root
        app = None
        try:
            host = fixture.host
            host.backend_factory = CandidateRuntime
            host.blog_runtime = ControlledBlogRuntime()
            host.blog = host.processing = host.batches = None
            host.ingestion.parser = ParserDouble()
            host.library_manage('create-topic', title='portable topic')
            topic = host.library_topics()[0]['topicId']
            host.library_manage('attach', topic_id=topic, source_id='fixture-paper')
            source = root / 'second.pdf'
            source.write_bytes(b'%PDF new material')
            item = host.ingestion.stage_file(source, topic_id=topic)
            batch = host.batch_start([item['item_id']], request_id=uuid.uuid4().hex)
            host.batch_workers[batch['batchId']].join(15)
            self.assertEqual('completed', host.batches.list()[0]['status'])
            host.select_discussion_source('fixture-paper')
            host.start({'requestId': 'portable-discussion-note', 'sourceId': 'fixture-paper', 'content': '记下来'})
            host.worker.join(5)
            host.state['discussions'][host.state['latestDiscussion']['fixture-paper']]['summary'] = '合成讨论摘要'
            host.store.save()
            before = host.snapshot()
            topic_before = host.library_topics()
            assets = {str(p.relative_to(host.workspace)): p.read_bytes() for p in host.workspace.rglob('*')
                      if p.is_file() and p.suffix in ('.pdf', '.md', '.png', '.html', '.tsv', '.jsonl')}
            host.close()
            copied = root / '中文 backup'
            shutil.copytree(fixture.workspace, copied)
            shutil.move(str(fixture.workspace), root / 'hidden-original')
            app = Workbench(settings_path=root / 'fresh-machine/settings.json', backend_factory=CandidateRuntime,
                            reading_runtime=ReadingRuntimeDouble(), ingestion_parser=ParserDouble(),
                            blog_runtime=ControlledBlogRuntime())
            app.bind({'mode': 'import', 'path': str(copied)})
            restored = app.host.snapshot()
            def logical(value):
                if isinstance(value, str):
                    return re.sub(r'\?instance=[0-9a-f]{32}', '', value)
                if isinstance(value, list):
                    return [logical(item) for item in value]
                if isinstance(value, dict):
                    return {key: logical(item) for key, item in value.items()}
                return value
            for field in ('sourceNotes', 'readingProgress', 'conversation', 'timeline', 'discussionId', 'outline', 'blog', 'navigationCurrent'):
                self.assertEqual(logical(before[field]), logical(restored[field]), field)
            self.assertEqual(topic_before, app.host.library_topics())
            self.assertEqual('合成讨论摘要', app.host.state['discussions'][restored['discussionId']]['summary'])
            for relative, content in assets.items():
                self.assertEqual(content, (copied / relative).read_bytes(), relative)
            receipt = {k: restored['navigationCurrent'][k] for k in ('sourceId', 'planId', 'chunkId')}
            receipt['readingRevision'] = restored['readingRevision']
            app.host.continue_cached({'requestId': uuid.uuid4().hex, 'receipt': receipt})
            app.host.start({'requestId': 'portable-more-note', 'sourceId': 'fixture-paper', 'content': '另一个例子，记下来'})
            app.host.worker.join(5)
            self.assertEqual(2, len(app.host.snapshot()['sourceNotes']))
            extra = root / 'third.pdf'
            extra.write_bytes(b'%PDF additional material')
            extra_item = app.host.ingestion.stage_file(extra, topic_id=topic)
            new_batch = app.host.batch_start([extra_item['item_id']], request_id=uuid.uuid4().hex)
            app.host.batch_workers[new_batch['batchId']].join(15)
            self.assertEqual('completed', app.host.ingestion.get(extra_item['item_id'])['status'])
        finally:
            if app:
                app.close()
            fixture.tearDown()

    def test_http_old_instance_and_busy_switch_are_rejected(self):
        from host.server import Server
        with test_directory() as root:
            app = Workbench(settings_path=root / 'machine/settings.json')
            first = app.bind({'mode': 'create', 'path': str(root), 'name': 'first'})
            server = Server(('127.0.0.1', 0), app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                app.host.batch_admissions = 1
                with self.assertRaises(WorkspaceError):
                    app.bind({'mode': 'create', 'path': str(root), 'name': 'busy-target'})
                self.assertFalse((root / 'busy-target').exists())
                app.host.batch_admissions = 0
                app.bind({'mode': 'create', 'path': str(root), 'name': 'second'})
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                conn.request('POST', '/library/topics', json.dumps({'title': 'stale'}),
                             {'Content-Type': 'application/json', 'X-FOCUS-Instance': first['workspace']['instanceId']})
                response = conn.getresponse()
                self.assertEqual(400, response.status)
                self.assertIn('工作区已更换', response.read().decode())
                conn.request('POST', '/reader/workspace', json.dumps({'mode': 'create', 'path': str(root),
                             'name': 'stale-selection', 'generation': first['generation'],
                             'configuration': {'backend': 'deepseek'}}), {'Content-Type': 'application/json'})
                response = conn.getresponse()
                self.assertEqual(400, response.status)
                self.assertIn('工作区已更换', response.read().decode())
                self.assertFalse((root / 'stale-selection').exists())
                conn.close()
                self.assertEqual([], app.host.library_topics())
            finally:
                server.shutdown(); server.server_close(); thread.join(3); app.close()

    def test_unbound_start_creates_no_workspace_then_create_restart_and_relocate(self):
        with test_directory() as root:
            settings = root / 'machine' / 'settings.json'
            app = Workbench(settings_path=settings)
            self.assertFalse(app.status()['bound'])
            self.assertEqual([], list(root.iterdir()))
            bound = app.bind({'mode': 'create', 'path': str(root), 'name': '中文 library'})
            identity = bound['workspace']['workspaceId']
            app.close()
            app = Workbench(settings_path=settings)
            self.assertTrue(app.status()['bound'])
            app.close()
            shutil.move(str(root / '中文 library'), root / 'restored')
            app = Workbench(settings_path=settings)
            self.assertFalse(app.status()['bound'])
            self.assertEqual(identity, app.status()['savedWorkspace']['workspaceId'])
            self.assertFalse((root / '中文 library').exists())
            relocated = app.bind({'mode': 'relocate', 'path': str(root / 'restored')})
            self.assertEqual(identity, relocated['workspace']['workspaceId'])
            app.close()

    def test_save_failure_retains_original_and_releases_target(self):
        with test_directory() as root:
            app = Workbench(settings_path=root / 'machine/settings.json')
            first = app.bind({'mode': 'create', 'path': str(root), 'name': 'first'})
            with patch.object(app.binding, 'save', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    app.bind({'mode': 'create', 'path': str(root), 'name': 'second'})
            self.assertEqual(first['workspace'], app.status()['workspace'])
            from host.service import HostService
            target = HostService(root / 'second', None, settings_path=root / 'other.json')
            target.close()
            app.close()
            restarted = Workbench(settings_path=root / 'machine/settings.json')
            self.assertEqual(first['workspace']['workspaceId'], restarted.status()['workspace']['workspaceId'])
            restarted.close()

    def test_backup_copy_with_same_identity_rejects_old_instance(self):
        with test_directory() as root:
            app = Workbench(settings_path=root / 'machine/settings.json')
            original = app.bind({'mode': 'create', 'path': str(root), 'name': 'original'})
            app.close()
            shutil.copytree(root / 'original', root / 'copy')
            app = Workbench(settings_path=root / 'machine/settings.json')
            old_instance = app.status()['workspace']['instanceId']
            copied = app.bind({'mode': 'import', 'path': str(root / 'copy')})
            self.assertEqual(original['workspace']['workspaceId'], copied['workspace']['workspaceId'])
            with self.assertRaises(WorkspaceError):
                app.require_instance(old_instance)
            app.close()


if __name__ == '__main__':
    unittest.main()
