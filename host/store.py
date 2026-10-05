"""Workspace discussions and business receipts; separate from Reading Records."""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self, directory: Path, workspace: Path, *, clock=time.time):
        from core.workspace_lifecycle import current_workspace_lease
        self.lease = current_workspace_lease(workspace)
        self.clock = clock
        self.machine_state = {}
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(directory / 'host.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        from core.workspace_lifecycle import inspect_workspace
        identity = inspect_workspace(workspace)['workspaceId']
        bound = self.get('workspaceId')
        if bound is not None and bound != identity:
            self.db.close()
            raise ValueError('Discussion data belongs to a different workspace')
        self.put('workspaceId', identity)
        self.state = self.get('session') or {'threadId': None, 'conversation': [], 'run': None, 'requests': {}}
        self.state.setdefault('sessionId', uuid.uuid4().hex)
        self.state.setdefault('displayReading', True)
        self.state.setdefault('timeline', [])
        self.state.setdefault('resumeBackend', None)
        # Native sessions are machine-local and never resumed from a backup.
        self.state['threadId'] = None
        self.state['resumeBackend'] = None
        self.save()
        run = self.state['run']
        if run and run['status'] in ('running', 'stopping', 'approval'):
            run.update(status='interrupted', error='后台已重启；上次任务已中断，请检查已落盘的更改后再发送。', approvals=[])
            run['terminalAt'] = self.clock()
            if run.get('progress'):
                run['progress']['finishedAt'] = int(time.time() * 1000)
            self.save()
        if run and run.get('runId') and run['status'] not in ('running', 'stopping', 'approval'):
            key = 'execution:' + run['runId']
            if self.get(key) is None:
                self.put(key, {'run': run})

    def get(self, key):
        if key.startswith('runtimeCleanup:'):
            return self.machine_state.get(key)
        with self.lock:
            row = self.db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def put(self, key, value):
        self.lease.require_current()
        if key.startswith('runtimeCleanup:'):
            self.machine_state[key] = value
            return
        def portable(item):
            if isinstance(item, dict):
                return {k: None if k in ('threadId', 'resumeBackend') else portable(v) for k, v in item.items()}
            if isinstance(item, list):
                return [portable(v) for v in item]
            return item
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (?, ?)', (key, json.dumps(portable(value), ensure_ascii=False)))

    def save(self):
        self.put('session', self.state)

    def clear_discussions(self, source_id, request_id, *, reset_reading=False):
        self.lease.require_current()
        from .source_clear import scrub
        with self.lock, self.db:
            self.db.execute('PRAGMA secure_delete=ON')
            current = scrub(self.state, source_id, reset_reading=reset_reading)
            for key, raw in self.db.execute("SELECT key, value FROM state WHERE key LIKE 'session:%' OR key LIKE 'execution:%'").fetchall():
                self.db.execute('UPDATE state SET value=? WHERE key=?',
                    (json.dumps(scrub(json.loads(raw), source_id, reset_reading=reset_reading), ensure_ascii=False), key))
            self.db.execute('UPDATE state SET value=? WHERE key=?', (json.dumps(current, ensure_ascii=False), 'session'))
            operations = self.get('sourceClears')
            operations[request_id]['status'] = 'completed'
            self.db.execute('UPDATE state SET value=? WHERE key=?', (json.dumps(operations), 'sourceClears'))
        self.state = current
        self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')

    def expire_logs(self):
        self.lease.require_current()
        """Only Host-owned diagnostics expire; history and receipts never do."""
        now = self.clock()
        with self.lock, self.db:
            self.db.execute('PRAGMA secure_delete=ON')
            for key, raw in self.db.execute("SELECT key, value FROM state WHERE key='session' OR key LIKE 'session:%' OR key LIKE 'execution:%'").fetchall():
                state = json.loads(raw)
                run = state.get('run')
                if not run or run['status'] in ('running', 'stopping', 'approval'):
                    continue
                terminal = run.get('terminalAt')
                if terminal is None:
                    # Legacy terminal runs have milliseconds in their progress receipt.
                    terminal = (run.get('progress') or {}).get('finishedAt')
                    run['terminalAt'] = terminal / 1000 if terminal is not None else now
                    terminal = run['terminalAt']
                if now >= terminal + 7 * 86400:
                    run['activity'] = []
                    run['approvals'] = []
                    run['error'] = None
                    run['logsExpired'] = True
                encoded = json.dumps(state, ensure_ascii=False)
                if encoded != raw:
                    self.db.execute('UPDATE state SET value=? WHERE key=?', (encoded, key))
                    if key == 'session':
                        self.state = state

    def runtime_cleanup(self):
        with self.lock:
            return list(self.machine_state.values())

    def close(self):
        self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.db.close()
