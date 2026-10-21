import ast,sys,types,runpy,os
from pathlib import Path
repo=Path.cwd();sys.path[:0]=[str(repo),str(repo/'tests'),str(repo/'.agents')]
# Compatibility harness only: legacy test class is used for _workspace(), not CLI tests.
p=repo/'tests/test_focus_read.py';tree=ast.parse(p.read_text());tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FOCUS_READ' for t in n.targets))]
m=types.ModuleType('test_focus_read');m.__file__=str(p);sys.modules[m.__name__]=m;exec(compile(tree,str(p),'exec'),m.__dict__)
script=(repo/'tests/confirmed_ux_browser.py').read_text()
if not os.environ.get('FOCUS_BROWSER_LEGACY_INTRO'):
 script=script.replace("server=Server(", "w=host.snapshot(); c=w['navigationCurrent']; host.continue_cached({'requestId':uuid.uuid4().hex,'sessionId':w['sessionId'],'beginBody':True,'receipt':{**{k:c[k] for k in ('sourceId','planId','chunkId')},'readingRevision':w['readingRevision']}})\nserver=Server(")
if os.environ.get('FOCUS_BROWSER_LEGACY_INTRO'):
 prefix="""
from core.reading_structure import legacy_structure
from test_article_overview import GUIDE

def overview_structure(self, **kwargs):
    tree=legacy_structure(kwargs['chunks'])
    for i,node in enumerate(tree['nodes']):
        node['title']='测试章节 '+str(i+1)
        node['description']='合成阅读测试章节。'
    return tree
Reading.overview_structure=overview_structure
Reading.overview_guide=lambda self,**kwargs:GUIDE
"""
 script=script.replace('host=HostService(',prefix+'\nhost=HostService(')
 script=script.replace('server=Server(',"host.prepare_article_overview('fixture-paper',request_id=uuid.uuid4().hex);host.reading_workers['fixture-paper'].join(10)\nserver=Server(")
exec(compile(script,'tests/confirmed_ux_browser.py','exec'),{'__name__':'__main__','__file__':str(repo/'tests/confirmed_ux_browser.py')})
