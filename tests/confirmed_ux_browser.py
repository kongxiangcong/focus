import sys, json, shutil, uuid, threading, time, queue, tempfile, subprocess, os
from pathlib import Path
repo = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo), str(repo/'tests'), str(repo/'.agents')]
from test_focus_read import FocusReadTests
from test_stage4_reading import ReadingRuntimeDouble, QuestionRuntime
from test_blog_host import ControlledBlogRuntime, ParserDouble
from workspace_fixture import HostService
from host.server import Server
fixture=FocusReadTests();fixture.setUp();workspace,source,plan=fixture._workspace()
root=Path(tempfile.mkdtemp(prefix='focus-browser-'))
shutil.copytree(workspace,root/'knowledge-base',dirs_exist_ok=True);fixture.tearDown()
workspace=root/'knowledge-base';source=workspace/'sources/fixture-paper';plan=source/'reading/plans/plan-001'
metadata=json.loads((source/'source.yaml').read_text())
metadata['title']='A very long research material title for compact toolbar layout ' * 5
(source/'source.yaml').write_text(json.dumps(metadata))
lines=[];chunks=[]
for i in range(1,10):
    lines.extend([f'## Section {i}', f'Paragraph {i}: source evidence and readable material.'])
    chunks.append({'chunk_id': f'chunk-{i:03}', 'index':i, 'section_path':[f'Section {i}'], 'source_lines':[i*2-1,i*2], 'images':[]})
shutil.rmtree(source/'parser-bundle/images');(source/'parser-bundle/images').mkdir()
(source/'parser-bundle/content.md').write_text('\n'.join(lines)+'\n')
(plan/'chunks.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in chunks));(plan/'glossary.tsv').write_text('')
for c in chunks:
 (plan/'records'/f"{c['chunk_id']}.json").write_text(json.dumps({'chunk_id':c['chunk_id'],'translation':None,'notes':[]}))
figure_translations = {}
if os.environ.get('FOCUS_BROWSER_FIGURES') == '1':
 from reader_figures_fixture import configure
 figure_translations = configure(workspace, source, plan)
class Reading(ReadingRuntimeDouble):
 def translate(self, **kwargs):
  if figure_translations: return figure_translations[kwargs['chunk']['index']]
  index=kwargs['chunk']['index'];return f'第 {index} 段译文。'+ ('\n\n'.join(['这是较长的阅读内容，用于验证滚动和大字号下的可读性。']*25) if index==2 else '这是一段供测试阅读、回看与提问的内容。')
 def progress(self, **kwargs): return {'topic': '确定性测试记录'}
class Streaming(QuestionRuntime):
 def interrupt(self): self.closed=True;self.events.put({"method":"turn/completed","params":{"status":"interrupted"}})
 def start_turn(self, **kwargs):
  if '记下来' in kwargs['prompt']:return super().start_turn(**kwargs)
  item=uuid.uuid4().hex
  def emit():
   if figure_translations and '图片讨论验收' in kwargs['prompt']:
    self.events.put({'method':'message/delta','params':{'itemId':item,'delta':'See Figure 1 and Figure 5.\n\n![architecture](images/image-001.png)\n\n![External illustration](https://example.invalid/extra.png)'}})
    self.events.put({'method':'turn/completed','params':{'status':'completed'}});return
   for n in range(20):
    if self.closed:return
    self.events.put({'method':'message/delta','params':{'itemId':item,'delta':f'回复第{n+1}句。\n\n'}});time.sleep(.10)
   self.events.put({'method':'turn/completed','params':{'status':'completed'}})
  threading.Thread(target=emit,daemon=True).start()
host=HostService(workspace,root/'host',backend_factory=Streaming,reading_runtime=Reading(), progress_runtime=Reading(),ingestion_parser=ParserDouble(),blog_runtime=ControlledBlogRuntime(),settings_path=root/'settings.json')
host.source_notes.save('fixture-paper', bundle=host.source_notes.bundle_version('fixture-paper'),
 request_id='browser-note-001', intent_id='browser-note-intent', content='Browser note before editing',
 kind='conclusion', origin='user', evidence_role='explanation')
host.prepare_reading('fixture-paper',request_id=uuid.uuid4().hex);host.reading_workers['fixture-paper'].join(5);host.open_prepared_reading('fixture-paper',request_id=uuid.uuid4().hex)
if figure_translations:
 host.prepare_reading('second-paper',request_id=uuid.uuid4().hex);host.reading_workers['second-paper'].join(5)
# Published-blog UI fixture; the browser supplies deterministic iframe HTML.
# Model generation is outside this layout suite.
blog_fixture={'sourceId':'fixture-paper','generated':True,'runStatus':'completed','methodVersion':'ui-fixture',
 'artifacts':{name:{'status':'completed','updatedAt':None} for name in ('value_analysis','reading_blog','html')},
 'valueAnalysis':{'applicable':True,'reason':''},'verificationLevel':'paper_reading','warnings':[],'error':None}
host._blog_summary=lambda: {'fixture-paper':blog_fixture}
if os.environ.get('FOCUS_BROWSER_FAILED_PREPARATION') == '1':
 run=host.reading_app.begin('fixture-paper',request_id=uuid.uuid4().hex,rebuild=True)
 host.reading_app.core.fail('fixture-paper',run['run_id'],run['attempt'],run['bundle'],'Runtime timed out',timed_out=True)
server=Server(('127.0.0.1',int(os.environ.get('FOCUS_BROWSER_PORT', '8765'))),host)
print('ISOLATED SERVER READY',flush=True)
try:
 if os.environ.get('FOCUS_BROWSER_SCRIPT'):
  worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
  result=subprocess.run(['node',os.environ['FOCUS_BROWSER_SCRIPT']], env={**os.environ,'XDG_CACHE_HOME':'/tmp/focus-browser-cache'})
  server.shutdown();worker.join();exit_code = result.returncode
 else:server.serve_forever()
finally:
 server.server_close();host.close();shutil.rmtree(root)
if os.environ.get('FOCUS_BROWSER_SCRIPT'): sys.exit(exit_code)
