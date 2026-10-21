"""Real Host/browser regression; only initial external parser failures are controlled."""
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.agents'), str(ROOT / 'tests')]
from test_duplicate_ingestion_recovery import DuplicateIngestionRecoveryTests

for scenario in ['single', 'batch']:
    fixture = DuplicateIngestionRecoveryTests()
    fixture.setUp()
    try:
        first = fixture.upload(scenario + '.pdf', ('%PDF ' + scenario).encode())
        sibling = fixture.upload('sibling.pdf', b'%PDF sibling')
        with patch.object(fixture.host.ingestion.parser, 'parse', side_effect=RuntimeError('Controlled parser failure')):
            if scenario == 'single':
                for item in [first, sibling]:
                    fixture.request('POST', '/library/inbox/' + item['item_id'] + '/confirm', {})
                    fixture.request('POST', '/library/inbox/' + item['item_id'] + '/process', {'requestId': item['item_id']})
                    fixture.wait_finished()
            else:
                fixture.request('POST', '/library/batches', {'itemIds': [first['item_id'], sibling['item_id']],
                                'requestId': 'batch', 'generateBlog': False})
                fixture.wait_finished()
        result = subprocess.run(['node', str(ROOT / 'tests/duplicate_ingestion_browser.mjs')],
                                env={**os.environ, 'FOCUS_TEST_SCENARIO': scenario,
                                     'FOCUS_TEST_URL': f'http://127.0.0.1:{fixture.server.server_port}'},
                                cwd=ROOT, timeout=90)
        if result.returncode:
            sys.exit(result.returncode)
        fixture.wait_finished()
        fixture.assertEqual(2, len(fixture.request('GET', '/library/inbox')))
        fixture.assertEqual(int(scenario == 'batch'), len(fixture.request('GET', '/library/batches')))
        fixture.assertEqual(1, len(fixture.request('GET', '/library/sources')))
        fixture.assertEqual('completed', fixture.host.ingestion.get(first['item_id'])['status'])
        fixture.assertEqual('failed', fixture.host.ingestion.get(sibling['item_id'])['status'])
    finally:
        fixture.tearDown()
