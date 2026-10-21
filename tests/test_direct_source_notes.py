"""Direct note creation through real Host/Core and HTTP; synthetic source, no AI calls."""
import copy
import http.client
import json
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.agents')]
from host.service import HostService
from host.server import Server
from host.workbench import Workbench
from core.library_import import import_markdown
from core.reading_workspace import WorkspaceError
from tests.test_article_overview import Runtime

class DirectSourceNoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='focus-direct-notes-')
        self.root = Path(self.tmp.name)
        self.runtime = Runtime()
        self.host = HostService(self.root/'kb', self.root/'hostdata', reading_runtime=self.runtime, settings_path=self.root/'settings.json')
        article = self.root/'article.md'
        article.write_text('# 数据搬运\n计算必须等待数据。\n## Method\n提前搬运，双缓冲轮换，需要同步。\n## Evaluation\n只做模型分析，真实设备仍待验证。\n')
        self.source = import_markdown(self.host.workspace, article, short_name='direct-note')['source_id']
        self.host.prepare_article_overview(self.source, request_id=uuid.uuid4().hex)
        self.host.reading_workers[self.source].join(8)
        self.window = self.host.open_prepared_reading(self.source, request_id=uuid.uuid4().hex)
        self.chunk = self.window['navigationCurrent']
        self.payload = {'requestId': uuid.uuid4().hex, 'content': '我的理解', 'kind': 'thought', 'origin': 'user',
                        'chunk': {k: self.chunk[k] for k in ('planId', 'chunkId')}, 'quote': '计算必须等待数据。'}
    def tearDown(self):
        self.runtime.release.set(); self.host.close(); self.tmp.cleanup()
    def save(self, **changes):
        return self.host.source_note_create(self.source, {**self.payload, **changes})
    def test_anchor_replay_and_no_reading_or_discussion_side_effects(self):
        state=(self.host.workspace/'state.json').read_bytes()
        history=copy.deepcopy(self.host.state['timeline'])
        conversation=copy.deepcopy(self.host.snapshot()['conversation'])
        with patch.object(self.host, '_library_idle', side_effect=AssertionError('notes must work while discussion is busy')):
            first=self.save(); second=self.save()
        self.assertEqual(first['noteOperation']['note']['noteId'],second['noteOperation']['note']['noteId'])
        self.assertEqual(1,len(second['sourceNotes']))
        note=first['noteOperation']['note']
        self.assertEqual(self.source,note['sourceId']); self.assertEqual('saved',first['noteOperation']['status'])
        self.assertEqual({'sourceId':self.source,'bundle':self.chunk['bundleVersion'],'sourceLines':list(self.chunk['sourceLines']),'quote':self.payload['quote']},note['anchor'])
        self.assertEqual(state,(self.host.workspace/'state.json').read_bytes())
        self.assertEqual(history,self.host.state['timeline']);self.assertEqual(conversation,second['conversation'])
        with self.assertRaises(WorkspaceError): self.save(content='另一份内容')
    def test_whole_source_and_question(self):
        result=self.save(chunk=None, quote=None, kind='question', origin='dialogue')
        note=result['noteOperation']['note']
        self.assertIsNone(note['anchor']);self.assertEqual('unresolved_question',note['evidenceRole'])
    def test_invalid_candidate_and_source_are_rejected(self):
        for changes in ({'kind':'concept'},{'origin':'system'},{'content':''},{'quote':'不存在的引文'}, {'chunk':{'planId':'../../bad','chunkId':'chunk-001'}}):
            with self.subTest(changes=changes), self.assertRaises((ValueError,WorkspaceError)): self.save(**changes)
        with self.assertRaises(ValueError): self.host.source_note_create('other-source',self.payload)
        self.assertEqual([],self.host.source_notes.list(self.source))
    def test_changed_bundle_can_be_saved_as_whole_source(self):
        path=self.host.workspace/'sources'/self.source/'parser-bundle/content.md'
        path.write_text(path.read_text()+'\n新增段落。\n')
        with self.assertRaises(WorkspaceError) as caught: self.save()
        self.assertEqual('note_bundle_changed',caught.exception.error_id)
        self.assertIsNone(self.save(chunk=None,quote=None)['noteOperation']['note']['anchor'])
    def test_bundle_projection_cache_reads_once_per_plan_and_invalidates(self):
        self.assertEqual(self.host.source_notes.bundle_version(self.source),self.chunk['bundleVersion'])
        self.host.core._plan_bundle_cache.clear()
        original=Path.read_text; reads=[]
        def read(path,*args,**kwargs):
            if path.name=='provenance.json': reads.append(path)
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',read):
            one=self.host.core.plan_bundle(self.source,self.chunk['planId'])
            two=self.host.core.plan_bundle(self.source,self.chunk['planId'])
        self.assertEqual(one,two);self.assertEqual(1,len(reads))
        path=self.host.workspace/'sources'/self.source/'reading/plans'/self.chunk['planId']/'provenance.json'
        data=json.loads(path.read_text());data['bundle']='different-version';path.write_text(json.dumps(data))
        self.assertEqual('different-version',self.host.core.plan_bundle(self.source,self.chunk['planId']))
    def test_direct_note_reuses_edit_delete_undo_and_clear_semantics(self):
        note=self.save()['noteOperation']['note']
        def change(operation, **extra):
            nonlocal note
            result=self.host.source_note_change(self.source,note['noteId'],
                {'requestId':uuid.uuid4().hex,'expectedRevision':note['revision'],**extra},operation)
            note=result['noteOperation']['note']
            return note
        self.assertEqual('修改后的理解',change('edit',content='修改后的理解')['content'])
        self.assertTrue(change('delete')['deleted'])
        self.assertFalse(change('undo')['deleted'])
        self.assertEqual('修改后的理解',note['content'])
        self.host.clear_source(self.source,{'requestId':uuid.uuid4().hex,'confirmed':True})
        self.assertEqual([],self.host.source_notes.list(self.source,include_deleted=True))
        self.assertEqual('cancelled',self.host.source_notes.result(self.source,self.payload['requestId'])['status'])

    def test_http_auth_and_bundle_changed_error(self):
        token=uuid.uuid4().hex
        app=Workbench(settings_path=self.root/'binding.json',workspace=self.host.workspace,service_factory=lambda *args,**kwargs:self.host)
        instance=app.status()['workspace']['instanceId']
        server=Server(('127.0.0.1',0),app,token=token)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(payload,authorized=True,bound=True):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            headers={'Content-Type':'application/json'}
            if authorized: headers['Authorization']='Bearer '+token
            if bound: headers['X-FOCUS-Instance']=instance
            connection.request('POST',f'/library/sources/{self.source}/notes',json.dumps(payload),headers)
            response=connection.getresponse();result=(response.status,json.loads(response.read()));connection.close();return result
        try:
            self.assertEqual(401,post(self.payload,False)[0])
            self.assertEqual(400,post(self.payload,bound=False)[0])
            status,body=post(self.payload);self.assertEqual(201,status);self.assertTrue(body['ok'])
            path=self.host.workspace/'sources'/self.source/'parser-bundle/content.md';path.write_text(path.read_text()+'\n变化。\n')
            status,body=post({**self.payload,'requestId':uuid.uuid4().hex})
            self.assertEqual(409,status);self.assertEqual('note_bundle_changed',body['error']['code'])
        finally:server.shutdown();server.server_close();thread.join()
