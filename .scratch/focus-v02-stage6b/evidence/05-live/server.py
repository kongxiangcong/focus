import sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from host.service import HostService
from host.server import Server
name=sys.argv[1]; port=int(sys.argv[2])
root=Path('.scratch/focus-v02-stage6b/evidence/05-live')/name
root.mkdir(parents=True,exist_ok=True)
h=HostService(root/'kb',root/'host',backend=name,model={'codex':'gpt-6-astra','deepseek':'deepseek-v4-flash'}[name],network=True,settings_path=root/'settings.json',codex_bin=str(Path('.venv/Lib/site-packages/codex_cli_bin/bin/codex.exe').resolve()))
s=Server(('127.0.0.1',port),h)
print('READY',name,port,flush=True)
try:s.serve_forever()
finally:h.close();s.server_close()
