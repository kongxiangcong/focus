"""Isolated real HTTP/UI acceptance with controlled planning and translation."""
import json
import sys
import uuid
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo), str(repo / 'tests'), str(repo / '.agents')]
from reading_fixture import ReadingFixture
from test_stage4_reading import PlanningRuntime, with_structure
from workspace_fixture import HostService
from host.server import Server

fixture = ReadingFixture()
fixture.setUp()
workspace, source, plan = fixture._workspace()
chunks = [json.loads(line) for line in (plan / 'chunks.jsonl').read_text(encoding="utf-8").splitlines()]
draft = with_structure({'chunks': [{k: c[k] for k in ('section_path', 'source_lines', 'images')} for c in chunks], 'glossary': []})
titles = {'Paper': '文章概览', 'Method': '方法设计', 'Runtime': '运行机制', 'Results': '实验结果'}
for node in draft['structure']['nodes']:
    node['title'] = titles.get(node['title'], '研究背景')
    node['description'] = {'方法设计': '介绍方案及关键设计选择。', '运行机制': '解释方案如何执行。',
                           '实验结果': '用实验检验方案的效果。'}.get(node['title'], '交代研究问题，串联方法与验证。')
meta = json.loads((source / 'source.yaml').read_text(encoding="utf-8"))
meta['title'] = '理解文章全局：方法、运行与验证'
(source / 'source.yaml').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
host = HostService(workspace, fixture.root / 'host', reading_runtime=PlanningRuntime(draft))
server = None
try:
    host.prepare_reading('fixture-paper', request_id=uuid.uuid4().hex, rebuild=True)
    host.reading_workers['fixture-paper'].join(10)
    candidate = host.snapshot()['preparations']['fixture-paper']
    assert candidate['ready'], candidate
    host.activate_reading_candidate('fixture-paper', {'planId': candidate['plan_id'],
        'readingRevision': host.snapshot()['readingRevision'], 'requestId': uuid.uuid4().hex})
    server = Server(('127.0.0.1', 8879), host)
    print('STRUCTURE ACCEPTANCE http://127.0.0.1:8879/reading', flush=True)
    server.serve_forever()
finally:
    if server:
        server.server_close()
    host.close()
    fixture.tearDown()
