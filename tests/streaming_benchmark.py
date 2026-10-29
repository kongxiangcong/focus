"""Fixed cadence Codex protocol events, real Host/Core and HTTP SSE. No credentials or inference."""
import http.client
import json
import queue
import shutil
import sys
import threading
import time
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / '.agents')]
from reading_fixture import ReadingFixture
from workspace_fixture import HostService
from host.server import Server, Handler
from host import discussions
from host.backends.codex import CodexBackend


def run(count=300, delay=.002):
    fixture = ReadingFixture(); fixture.setUp()
    workspace = fixture._workspace()[0]
    replica = workspace / 'sources' / 'second-paper'
    shutil.copytree(workspace / 'sources' / 'fixture-paper', replica)
    for path in replica.rglob('*'):
        if path.is_file() and path.suffix in ('.json', '.yaml', '.md'):
            path.write_text(path.read_text().replace('fixture-paper', 'second-paper'))
    host = HostService(workspace, fixture.root / 'host')
    server = Server(('127.0.0.1', 0), host)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=60)
    received = []; sent = []; lock_wait = []; applied = []; arrived = []; backlog = []; waiting = []; snapshots = []
    ready = threading.Event(); done = threading.Event(); events = queue.Queue()
    class Writer:
        def __init__(self, output): self.output = output
        def __getattr__(self, name): return getattr(self.output, name)
        def write(self, data):
            if data.startswith(b'event: '):
                value = json.loads(data.split(b'data: ', 1)[1]).get('value')
                if value is None: value = json.loads(data.split(b'data: ', 1)[1])
                for message in value.get('conversation', value.get('messages', [])):
                    if message['messageId'] == 'stream': sent.append((len(message['content']), time.perf_counter()))
            return self.output.write(data)
    class MeasuredHandler(Handler):
        def end_headers(self):
            super().end_headers()
            self.wfile = Writer(self.wfile)
    server.RequestHandlerClass = MeasuredHandler
    original = host.core.reference
    def costly(receipt):
        time.sleep(delay)  # Explicit controlled disk/validation cost, separate from real Core work.
        return original(receipt)
    host.core.reference = costly
    snapshot = host.event_snapshot if hasattr(host, "event_snapshot") else host.snapshot
    def measured():
        start = time.perf_counter(); value = snapshot(); snapshots.append(time.perf_counter()-start); return value
    if hasattr(host, "event_snapshot"): host.event_snapshot = measured
    else: host.snapshot = measured
    with host.lock:
        discussion_id = discussions.select(host.state, 'fixture-paper')
        host.active_discussion = {'sourceId': 'fixture-paper', 'discussionId': discussion_id}
        host.state['displayReading'] = False
        host.state['conversation'] = [{'messageId': str(i), 'role': 'user', 'content': '历史消息' * 300, 'chunkId': '', 'discussionId': discussion_id} for i in range(170)]
        host.state['timeline'] = [{'kind': 'message', 'messageId': str(i)} for i in range(170)] + [
            {'kind': 'reading', 'eventId': str(i), 'receipt': {'sourceId': 'fixture-paper' if i % 2 else 'second-paper', 'planId': 'plan-001', 'chunkId': 'chunk-003'}} for i in range(83)]
        host.state['run'] = {'runId': 'synthetic', 'status': 'running', 'activity': [], 'approvals': []}
        host.changed()
    def consume():
        conn.request('GET', '/reader/events'); response = conn.getresponse()
        while not done.is_set():
            line = response.fp.readline()
            if not line: break
            if line.startswith(b'data: '):
                body = json.loads(line[6:]); value = body.get('value', body)
                ready.set()
                for message in value.get('conversation', value.get('messages', [])):
                    if message['messageId'] == 'stream': received.append((len(message['content']), time.perf_counter()))
    consumer = threading.Thread(target=consume, daemon=True); consumer.start(); assert ready.wait(15)
    backend = CodexBackend(workspace)
    def apply():
        while True:
            item = events.get()
            if item is None: return
            i, timestamp = item
            start = time.perf_counter()
            backend._translate({'method': 'item/agentMessage/delta', 'params': {'itemId': 'stream', 'delta': chr(0x4e00+i)}})
            event = backend.events.get()
            with host.lock:
                lock_wait.append(time.perf_counter()-start)
                host._notification(event['method'], event['params'])
            applied.append(time.perf_counter()); waiting.append(applied[-1]-start)
    worker = threading.Thread(target=apply, daemon=True); worker.start()
    start = time.perf_counter()
    for i in range(count):
        target = start + i * .005
        time.sleep(max(0, target-time.perf_counter()))
        now = time.perf_counter(); arrived.append(now); events.put((i, now)); backlog.append(events.qsize())
    events.put(None); worker.join(60); assert not worker.is_alive()
    deadline = time.monotonic()+20
    while (not received or received[-1][0] != count) and time.monotonic() < deadline: time.sleep(.01)
    assert received and received[-1][0] == count
    assert host.state['conversation'][-1]['content'] == ''.join(chr(0x4e00+i) for i in range(count))
    with host.lock:
        host.state['run']['status'] = 'completed'; host.changed()
    assert host.store.get('session')['conversation'][-1]['content'] == ''.join(chr(0x4e00+i) for i in range(count))
    result = {'session_bytes': len(json.dumps(host.state, ensure_ascii=False).encode()), 'fragments': count, 'cadence_ms': 5, 'reference_delay_ms': delay*1000,
              'first_applied_ms': (applied[0]-arrived[0])*1000, 'first_sse_ms': (received[0][1]-arrived[0])*1000,
              'last_apply_lag_ms': (applied[-1]-arrived[-1])*1000, 'last_sse_lag_ms': (received[-1][1]-arrived[-1])*1000,
              'first_send_ms': (sent[0][1]-arrived[0])*1000,
              'last_send_lag_ms': (sent[-1][1]-arrived[-1])*1000, 'max_lock_wait_ms': max(lock_wait)*1000,
              'max_backlog': max(backlog), 'max_notification_ms': max(waiting)*1000,
              'full_snapshots': len(snapshots), 'snapshot_seconds': list(snapshots), 'exact_output': True}
    done.set(); server.shutdown(); server.server_close(); host.close(); fixture.tearDown()
    print(json.dumps(result))
    return result

if __name__ == '__main__': run()
