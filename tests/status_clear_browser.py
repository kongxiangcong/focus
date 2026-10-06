"""Browser acceptance using real Host/Core files and controlled external parsing."""
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.agents'), str(ROOT / 'tests')]
from test_stage5_ingestion import SingleIngestionTests
from core.mineru import ParserError

fixture = SingleIngestionTests()
fixture.setUp()
try:
    failed = fixture.request('POST', '/library/inbox?name=failed.pdf', b'%PDF failed')
    with patch.object(fixture.host.ingestion.parser, 'parse', side_effect=ParserError('Controlled failure', recoverable=False, error_id='parser_failed')):
        fixture.request('POST', '/library/batches', {'itemIds':[failed['item_id']], 'requestId':'failed', 'generateBlog':False})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            batches = fixture.request('GET', '/library/batches')
            if batches[0]['status'] in ('partial','paused') and not batches[0]['executing']:
                break
            time.sleep(.05)
    completed = fixture.request('POST', '/library/inbox?name=completed.pdf', b'%PDF completed')
    fixture.request('POST', '/library/batches', {'itemIds':[completed['item_id']], 'requestId':'completed', 'generateBlog':False})
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        batches = fixture.request('GET', '/library/batches')
        if any(batch['status'] == 'completed' and not batch['executing'] for batch in batches):
            break
        time.sleep(.05)
    fixture.request('POST', '/library/inbox?name=waiting.pdf', b'%PDF waiting')
    result = subprocess.run(['node', str(ROOT / 'tests/status_clear_browser.mjs')], env={**os.environ,
        'FOCUS_TEST_URL':f'http://127.0.0.1:{fixture.server.server_port}'}, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90)
    print(result.stdout)
    print(result.stderr)
    sys.exit(result.returncode)
finally:
    fixture.tearDown()
