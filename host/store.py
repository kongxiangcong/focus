"""Host-owned durable conversation; never stored in Reading Records."""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self, directory: Path, workspace: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(directory / 'host.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        bound = self.get('workspace')
        if bound is not None and bound != str(workspace):
            raise ValueError('Host data directory belongs to a different workspace')
        self.put('workspace', str(workspace))
        self.state = self.get('session') or {'threadId': None, 'conversation': [], 'run': None, 'requests': {}}
        self.state.setdefault('sessionId', uuid.uuid4().hex)
        self.state.setdefault('displayReading', True)
        self.state.setdefault('timeline', [])
        self.state.setdefault('resumeBackend', None)
        self.save()
        run = self.state['run']
        if run and run['status'] in ('running', 'stopping', 'approval'):
            run.update(status='interrupted', error='后台已重启；上次任务已中断，请检查已落盘的更改后再发送。', approvals=[])
            if run.get('progress'):
                run['progress']['finishedAt'] = int(time.time() * 1000)
            self.save()

    def get(self, key):
        with self.lock:
            row = self.db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else None

    def put(self, key, value):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (?, ?)', (key, json.dumps(value, ensure_ascii=False)))

    def save(self):
        self.put('session', self.state)

    def close(self):
        self.db.close()
