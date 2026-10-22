"""Real Host/Core flow; controlled model candidates, no retired CLI dependency."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / '.agents')]
from host.service import HostService
from core.library_import import import_markdown
from core.reading_structure import legacy_structure
from core.article_overview import ArticleOverview, validate_chinese_structure, validate_guide
from core.reading_workspace import WorkspaceError

GUIDE = ('我们常以为，只要计算单元足够快，程序就能跟着变快。但这篇文章先从等待数据的问题出发：'
         '如果计算需要的内容还没送到，增加计算能力也无法消除等待。作者因此把注意力转向数据如何搬运，'
         '而不是先增加运算单元。\n\n'
         '在“方法设计”中，作者提出先把即将使用的数据搬到近处，再让计算与后续搬运重叠。'
         '难点是两部分必须配合：搬得太晚仍要等待，搬得太早又会占住有限空间。'
         '于是文章继续解释缓冲区怎样轮换，以及什么时候需要同步。这样，读者就能理解，'
         '看似简单的提前搬运为什么还需要一套执行安排。\n\n'
         '最后的“效果验证”通过模型分析比较等待时间，而不是报告流片后的实测性能。'
         '这些结果支持在文中假设下减少等待的可能性，但真实设备的带宽、冲突和调度开销是否满足假设，'
         '仍需要进一步验证。阅读时可以沿着数据什么时候到、计算什么时候开始这条线，检查结论的适用范围。')

class Runtime:
    def __init__(self):
        self.structure_calls = 0
        self.guide_calls = 0
        self.entered = threading.Event()
        self.release = threading.Event(); self.release.set()
        self.fail = False
        self.source_text = ''
    def context(self, **kwargs):
        return {'structure': '方法与验证', 'terms': [], 'symbols': [], 'references': []}
    def plan(self, **kwargs):
        chunks = [{'section_path': ['数据搬运'], 'source_lines': [1, 2], 'images': []},
                  {'section_path': ['数据搬运', 'Method'], 'source_lines': [3, 4], 'images': []},
                  {'section_path': ['数据搬运', 'Evaluation'], 'source_lines': [5, 6], 'images': []}]
        tree = legacy_structure(chunks)
        for n in tree['nodes']: n['description'] = '本部分的论证作用。'
        return {'chunks': chunks, 'glossary': [], 'excluded_ranges': [], 'structure': tree}
    def translate(self, **kwargs): raise AssertionError('Chinese needs no translation')
    def check(self, **kwargs): return {'passed': True, 'issues': {}, 'coverage': [c['chunk_id'] for c in kwargs['chunks']]}
    def overview_structure(self, **kwargs):
        self.structure_calls += 1
        self.source_text = '\n'.join(r['source_text'] for r in kwargs['ranges'])
        self.entered.set()
        if not self.release.wait(5): raise TimeoutError('test barrier')
        if self.fail: raise RuntimeError('controlled generation failure')
        tree = legacy_structure(kwargs['chunks'])
        for n in tree['nodes']:
            n['title'] = {'Method': '方法设计', 'Evaluation': '效果验证'}.get(n['title'], n['title'])
            n['description'] = '解释这部分如何推进全文论证。'
        return tree
    def overview_guide(self, **kwargs):
        self.guide_calls += 1
        assert kwargs['structure']['nodes'][1]['title'] == '方法设计'
        return GUIDE
    def cancel(self, source_id=None): self.release.set()

class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = Runtime()
        self.host = HostService(self.root/'workspace', self.root/'host', reading_runtime=self.runtime,
                                settings_path=self.root/'settings.json')
        article = self.root/'article.md'
        article.write_text('# 数据搬运\n计算必须等待数据。\n## Method\n提前搬运，双缓冲轮换，需要同步。\n## Evaluation\n只做模型分析，真实设备仍待验证。\n', encoding="utf-8")
        self.sid = import_markdown(self.host.workspace, article, short_name='overview-test')['source_id']
    def tearDown(self):
        self.runtime.release.set(); self.host.close(); self.tmp.cleanup()
    def state(self): return (self.host.workspace/'state.json').read_bytes()
    def prepare(self):
        result = self.host.prepare_article_overview(self.sid, request_id=uuid.uuid4().hex)
        self.host.reading_workers[self.sid].join(8)
        self.assertFalse(self.host.reading_workers[self.sid].is_alive())
        return self.host.article_overview(self.sid)
    def test_new_source_shared_asset_no_cursor_write_then_intro(self):
        before = self.state()
        data = self.prepare()
        self.assertEqual('ready', data['status'], data)
        self.assertEqual(before, self.state())
        self.assertIn('真实设备仍待验证', self.runtime.source_text)
        self.assertTrue(300 <= len(GUIDE.replace('\n','')) <= 500)
        opened = self.host.open_prepared_reading(self.sid, request_id=uuid.uuid4().hex)
        self.assertTrue(opened['structureIntro']); self.assertIsNone(opened['current'])
        self.assertEqual(data, opened['articleOverview'])
        self.assertEqual(data['structure'], opened['structure'])
        started = self.host.continue_cached({'beginBody': True, 'requestId':uuid.uuid4().hex,
            'receipt': {**{k:opened['navigationCurrent'][k] for k in ('sourceId','planId','chunkId')},
                        'readingRevision': opened['readingRevision']}})
        self.assertTrue(started['readingStarted']); self.assertEqual(1, started['current']['index'])
        before = self.state()
        self.prepare(); self.assertEqual(before, self.state()); self.assertEqual(1,self.runtime.structure_calls)
    def test_completed_reopen_projects_all_chunks_without_cursor_or_event_writes(self):
        self.prepare()
        h = self.host
        window = h.open_prepared_reading(self.sid, request_id=uuid.uuid4().hex)
        def payload(window):
            chunk = window['navigationCurrent']
            return {'requestId': uuid.uuid4().hex, 'receipt': {
                **{k: chunk[k] for k in ('sourceId', 'planId', 'chunkId')},
                'readingRevision': window['readingRevision']}}
        window = h.continue_cached({**payload(window), 'beginBody': True})
        while window['navigationCurrent']['index'] < window['navigationCurrent']['total']:
            window = h.continue_cached(payload(window))
        window = h.finish_reading(payload(window))
        h.new_session({'sessionId': window['sessionId']})
        self.assertEqual([], h.snapshot()['timeline'])  # New session still clears the display.
        window = h.open_prepared_reading(self.sid, request_id=uuid.uuid4().hex)
        before = self.state()
        events = json.dumps(h.state['timeline'])
        for _ in range(2):
            window = h.snapshot()
            self.assertEqual('completed', window['status'])
            self.assertEqual([1, 2, 3], [e['chunk']['index'] for e in window['timeline'] if e['kind'] == 'reading'])
            self.assertIsNone(window['navigationCurrent'])
        self.assertEqual(before, self.state())
        self.assertEqual(events, json.dumps(h.state['timeline']))

    def test_existing_chinese_plan_tree_is_reused_for_guide(self):
        original = self.runtime.plan
        def chinese_plan(**kwargs):
            draft = original(**kwargs)
            for node in draft['structure']['nodes']:
                node['title'] = {'Method': '方法设计', 'Evaluation': '效果验证'}.get(node['title'], node['title'])
            return draft
        self.runtime.plan = chinese_plan
        self.assertEqual('ready', self.prepare()['status'])
        self.assertEqual(0, self.runtime.structure_calls)
        self.assertEqual(1, self.runtime.guide_calls)

    def test_concurrent_entry_deduplicates_and_replan_is_blocked(self):
        self.runtime.release.clear()
        self.host.prepare_article_overview(self.sid, request_id=uuid.uuid4().hex)
        self.assertTrue(self.runtime.entered.wait(4))
        for _ in range(3):
            self.assertEqual('running', self.host.prepare_article_overview(self.sid, request_id=uuid.uuid4().hex)['status'])
        with self.assertRaises(WorkspaceError): self.host.prepare_reading(self.sid, request_id=uuid.uuid4().hex, rebuild=True)
        self.runtime.release.set(); self.host.reading_workers[self.sid].join(5)
        self.assertEqual(1,self.runtime.structure_calls); self.assertEqual(1,self.runtime.guide_calls)
    def test_failure_retry_does_not_reset_ready_plan_or_cursor(self):
        before=self.state(); self.runtime.fail=True
        self.assertEqual('failed', self.prepare()['status'])
        self.assertEqual(before,self.state())
        self.runtime.fail=False
        self.assertEqual('ready',self.prepare()['status']); self.assertEqual(before,self.state())
    def test_legacy_backfill_preserves_started_plan_records_and_readiness(self):
        self.prepare()
        opened=self.host.open_prepared_reading(self.sid,request_id=uuid.uuid4().hex)
        receipt={**{k:opened['navigationCurrent'][k] for k in ('sourceId','planId','chunkId')},'readingRevision':opened['readingRevision']}
        self.host.continue_cached({'receipt':receipt,'requestId':uuid.uuid4().hex,'beginBody':True})
        root=ArticleOverview(self.host.workspace, self.host.reading_app).target(self.sid)[0]
        (root/'overview.json').unlink()
        before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
        state=self.state()
        self.assertEqual('ready',self.prepare()['status']); self.assertEqual(state,self.state())
        for p,data in before.items(): self.assertEqual(data,(root/p).read_bytes())
        self.assertTrue(self.host.reading_app.core._plan_ready(self.sid,root.name))
        view=self.host.snapshot(); self.assertFalse(view['structureIntro'])
        self.host.review_chunk(self.sid,root.name,'chunk-001')
    def test_http_preview_endpoint_is_cursor_neutral(self):
        import http.client
        from host.server import Server
        server = Server(('127.0.0.1', 0), self.host)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        before = self.state()
        try:
            def request(method):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_address[1])
                payload = json.dumps({'requestId': uuid.uuid4().hex}) if method == 'POST' else None
                conn.request(method, '/library/sources/' + self.sid + '/overview', body=payload,
                             headers={'Content-Type': 'application/json'})
                response = conn.getresponse(); body = json.loads(response.read()); conn.close()
                self.assertEqual(200, response.status, body)
                return body['value']
            self.assertEqual('missing', request('GET')['status'])
            request('POST'); self.host.reading_workers[self.sid].join(5)
            self.assertEqual('ready', request('GET')['status'])
            self.assertEqual(before, self.state())
        finally:
            server.shutdown(); worker.join(2); server.server_close()

    def test_stale_corrupt_asset_and_language_validation(self):
        self.prepare()
        root,chunks,_=ArticleOverview(self.host.workspace, self.host.reading_app).target(self.sid)
        p=root/'overview.json'; data=json.loads(p.read_text(encoding="utf-8")); data['chunksRevision']='wrong'; p.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual('stale',self.host.article_overview(self.sid)['status'])
        self.prepare(); data=json.loads(p.read_text(encoding="utf-8")); data['structure']['nodes'][0]['title']='Introduction'; p.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual('failed',self.host.article_overview(self.sid)['status'])
        with self.assertRaises(WorkspaceError): validate_chinese_structure(data['structure'], chunks)
        with self.assertRaises(WorkspaceError): validate_guide('文'*501)
        p.write_text('{', encoding="utf-8"); self.assertEqual('failed',self.host.article_overview(self.sid)['status'])

if __name__ == '__main__': unittest.main()
