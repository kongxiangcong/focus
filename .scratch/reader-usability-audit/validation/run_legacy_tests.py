import ast,sys,types,runpy,os
from pathlib import Path
repo=Path.cwd();sys.path[:0]=[str(repo),str(repo/'tests'),str(repo/'.agents')]
# Compatibility harness only: legacy test class is used for _workspace(), not CLI tests.
p=repo/'tests/test_focus_read.py';tree=ast.parse(p.read_text());tree.body=[n for n in tree.body if not(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FOCUS_READ' for t in n.targets))]
m=types.ModuleType('test_focus_read');m.__file__=str(p);sys.modules[m.__name__]=m;exec(compile(tree,str(p),'exec'),m.__dict__)

import unittest
suite=unittest.defaultTestLoader.loadTestsFromNames(["tests.test_web_host","tests.test_source_notes"])
result=unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(not result.wasSuccessful())
