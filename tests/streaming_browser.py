"""Production UI, real HTTP/EventSource, synthetic Codex protocol and on-disk history."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / '.agents')]
from test_streaming import StreamingTests
from host.server import Server
from host.backends.codex import CodexBackend

fixture = StreamingTests(); fixture.setUp(); host = fixture.host
server = Server(('127.0.0.1', 0), host)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    state_path = host.workspace / 'state.json'
    state = json.loads(state_path.read_text()); state['sources']['fixture-paper']['reading_started'] = True
    state_path.write_text(json.dumps(state))
    with host.lock:
        discussion = host.active_discussion['discussionId']
        host.state['displayReading'] = True
        host.state['conversation'] = [{'messageId': str(i), 'role': 'user', 'content': '历史消息' * 300, 'chunkId': '', 'discussionId': discussion} for i in range(170)]
        host.state['timeline'] = [{'kind': 'message', 'messageId': str(i)} for i in range(170)] + [
            {'kind': 'reading', 'eventId': str(i), 'discussionId': discussion, 'receipt': {'sourceId': 'fixture-paper', 'planId': 'plan-001', 'chunkId': 'chunk-003'}} for i in range(83)]
        host._conversation_entry('browser-stream')
        host.changed()
    process = subprocess.Popen(['node', str(Path(__file__).with_suffix('.mjs'))], stdout=subprocess.PIPE, text=True,
                               env={**os.environ, 'FOCUS_TEST_URL': f'http://127.0.0.1:{server.server_port}'})
    assert process.stdout.readline().strip() == 'READY'
    backend = CodexBackend(host.workspace)
    applied = []; start = time.perf_counter(); epoch = time.time()*1000
    for i in range(300):
        time.sleep(max(0, start+i*.01-time.perf_counter()))
        backend._translate({'method': 'item/agentMessage/delta', 'params': {'itemId': 'browser-stream', 'delta': chr(0x4e00+i)}})
        event = backend.events.get(); host._notification(event['method'], event['params'])
        applied.append(time.perf_counter()-start)
    with host.lock:
        host.state['run']['status'] = 'completed'; host.changed()
    output, _ = process.communicate(timeout=60)
    print(output)
    assert process.returncode == 0
    assert host.store.get('session')['conversation'][-1]['content'] == ''.join(chr(0x4e00+i) for i in range(300))
    print(json.dumps({'host_start_epoch_ms': epoch, 'host_first_ms': applied[0]*1000, 'host_last_ms': applied[-1]*1000, 'persisted_characters': 300}))
finally:
    server.shutdown(); server.server_close(); fixture.tearDown()
