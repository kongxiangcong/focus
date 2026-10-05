"""Portable format and OS-owned, per-open write authority.

The lock file is only a rendezvous point. Its contents never confer ownership.
"""
import json
import os
import uuid
import functools
import sqlite3
import shutil
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .reading_workspace import WorkspaceError, _write_document

FORMAT_VERSION = 1
MANIFEST = 'focus-workspace.json'
_leases = {}
_operation_lease = ContextVar('focus_operation_lease', default=None)


def require_write(path):
    lease = _operation_lease.get()
    if lease is not None:
        lease.require_current()


def writer_authorized(workspace, writer_id, owner):
    lease = _leases.get(Path(workspace).resolve())
    if lease:
        lease.require_current()
        return writer_id == lease.instance_id
    return owner in (None, writer_id)


def current_workspace_lease(path):
    lease = _leases.get(Path(path).resolve())
    if lease is None:
        raise WorkspaceError('workspace_not_open', '请通过 FOCUS 工作区打开入口取得写入资格。')
    lease.require_current()
    return lease


def guard_workspace_class(cls):
    """Bind Core operations to the open instance, including late continuations."""
    original_init = cls.__init__

    @functools.wraps(original_init)
    def initialize(self, workspace, *args, **kwargs):
        owner = workspace
        if hasattr(owner, 'processing'):
            owner = owner.processing
        if hasattr(owner, 'ingestion'):
            owner = owner.ingestion
        path = Path(getattr(owner, 'workspace', owner)).resolve()
        self._workspace_lease = _leases.get(path)
        if (path / MANIFEST).exists() and self._workspace_lease is None:
            raise WorkspaceError('workspace_not_open', '请通过 FOCUS 工作区打开入口取得写入资格。')
        original_init(self, workspace, *args, **kwargs)

    cls.__init__ = initialize
    for name, method in list(vars(cls).items()):
        if name.startswith('_') or not callable(method) or isinstance(method, (staticmethod, classmethod)):
            continue

        def guarded(self, *args, __method=method, **kwargs):
            lease = self._workspace_lease
            if lease:
                lease.require_current()
            elif hasattr(self, 'workspace') and (Path(self.workspace) / MANIFEST).exists():
                raise WorkspaceError('workspace_instance_expired', '请重新打开工作区后操作。')
            token = _operation_lease.set(lease)
            try:
                return __method(self, *args, **kwargs)
            finally:
                _operation_lease.reset(token)

        setattr(cls, name, functools.wraps(method)(guarded))
    return cls


def inspect_workspace(path):
    path = Path(path).resolve()
    try:
        value = json.loads((path / MANIFEST).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise WorkspaceError('workspace_format_invalid', '请选择新格式 FOCUS 工作区；空目录请使用新建。') from exc
    if (not isinstance(value, dict) or value.get('formatVersion') != FORMAT_VERSION
            or value.get('minimumReader') != FORMAT_VERSION or value.get('minimumWriter') != FORMAT_VERSION):
        raise WorkspaceError('workspace_format_unsupported', '此工作区格式不兼容当前 FOCUS。')
    try:
        uuid.UUID(value['workspaceId'])
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise WorkspaceError('workspace_format_invalid', '工作区身份已损坏。') from exc
    return value


@contextmanager
def _inspection_database(database):
    # A crash can leave the schema and latest receipts in WAL. Inspect a private
    # copy so SQLite may recover it without creating SHM or changing the original.
    with tempfile.TemporaryDirectory(prefix='focus-inspect-') as directory:
        copied = Path(directory) / database.name
        shutil.copyfile(database, copied)
        wal = database.with_name(database.name + '-wal')
        if wal.exists():
            shutil.copyfile(wal, copied.with_name(copied.name + '-wal'))
        connection = sqlite3.connect(copied)
        try:
            yield connection
        finally:
            connection.close()


def validate_workspace_data(path):
    """Read-only admission before locks, database initialization or recovery."""
    path = Path(path).resolve()
    inspect_workspace(path)
    try:
        cleanup_roots = []
        state_path = path / 'state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding='utf-8'))
            if not isinstance(state, dict) or not isinstance(state.get('sources'), dict):
                raise ValueError('Invalid reading state')
            tombstones = state.get('deleted_sources', {})
            if not isinstance(tombstones, dict):
                raise ValueError('Invalid deletion receipts')
            from .source_library import deletion_cleanup_target
            for source_id, tombstone in tombstones.items():
                if not isinstance(tombstone, dict) or not isinstance(tombstone.get('cleanup_paths', []), list):
                    raise ValueError('Invalid deletion receipt')
                for relative in tombstone.get('cleanup_paths', []):
                    if not isinstance(relative, str):
                        raise ValueError('Invalid deletion path')
                    target = deletion_cleanup_target(path, source_id, relative)
                    cleanup_roots.append(target)
        # These files belong to FOCUS, including candidate and recovery receipts.
        for candidate in path.rglob('*'):
            if any(candidate.is_relative_to(root) for root in cleanup_roots):
                continue
            if not candidate.is_file() or candidate.suffix not in ('.json', '.jsonl', '.yaml'):
                continue
            raw = candidate.read_text(encoding='utf-8')
            values = [json.loads(line) for line in raw.splitlines() if line.strip()] if candidate.suffix == '.jsonl' else [json.loads(raw)]
            relative = candidate.relative_to(path)
            business = 'parser-bundle' not in relative.parts and 'mineru' not in relative.parts
            if business and any(not isinstance(value, dict) for value in values):
                raise ValueError('Expected a business document')
            if candidate == path / 'state.json' and not isinstance(values[0].get('sources'), dict):
                raise ValueError('Invalid reading state')
            if candidate == path / 'state.json':
                from .reading_workspace import _current_source_state
                if values[0].get('current_source_id') is not None:
                    _current_source_state(path)
                if not isinstance(values[0].get('deleted_sources', {}), dict):
                    raise ValueError('Invalid deletion receipts')
            if candidate.name == 'source.yaml' and candidate.parent.parent == path / 'sources' and not candidate.parent.name.endswith('.staging'):
                from .source_library import SourceLibrary
                SourceLibrary._validate_source(values[0], candidate.parent.name)
        for database in path.rglob('notes.sqlite3'):
            if any(database.is_relative_to(root) for root in cleanup_roots):
                continue
            with _inspection_database(database) as connection:
                if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('Damaged notes store')
        database = path / 'discussions/host.sqlite3'
        if database.exists():
            with _inspection_database(database) as connection:
                if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('Damaged discussion store')
                for key, raw in connection.execute('SELECT key, value FROM state'):
                    value = json.loads(raw)
                    if key == 'workspaceId' and value != inspect_workspace(path)['workspaceId']:
                        raise ValueError('Discussion identity mismatch')
                    if key == 'session':
                        if (not isinstance(value, dict) or not isinstance(value.get('conversation'), list)
                                or 'run' not in value or not isinstance(value.get('requests'), dict)):
                            raise ValueError('Invalid discussion state')
                        run = value['run']
                        if run is not None and (not isinstance(run, dict) or not isinstance(run.get('status'), str)):
                            raise ValueError('Invalid execution receipt')
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise WorkspaceError('workspace_data_invalid', '工作区业务数据损坏；请保留原目录并选择有效备份。') from exc


def create_workspace(path):
    path = Path(path).resolve()
    if path.exists() and any(path.iterdir()):
        raise WorkspaceError('workspace_exists', '目标已有文件；已有工作区请导入，不会覆盖。')
    path.mkdir(parents=True, exist_ok=True)
    value = {'workspaceId': str(uuid.uuid4()), 'formatVersion': FORMAT_VERSION,
             'minimumReader': FORMAT_VERSION, 'minimumWriter': FORMAT_VERSION}
    try:
        with (path / MANIFEST).open('x', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError as exc:
        raise WorkspaceError('workspace_exists', '目标已被创建，请使用导入。') from exc
    return value


class WorkspaceLease:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.manifest = inspect_workspace(self.path)
        existing_lock = (self.path / '.focus.lock').exists()
        if not existing_lock:
            validate_workspace_data(self.path)
        self.instance_id = uuid.uuid4().hex
        self.handle = (self.path / '.focus.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.handle.seek(0, 2)
                if self.handle.tell() == 0:
                    self.handle.write(b'0')
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise WorkspaceError('workspace_busy', '工作区正由另一 FOCUS 进程使用；请先退出。') from exc
        try:
            validate_workspace_data(self.path)
        except BaseException:
            self.close()
            raise
        _leases[self.path] = self

    def require_current(self):
        if self.handle.closed or _leases.get(self.path) is not self:
            raise WorkspaceError('workspace_instance_expired', '工作区已关闭，请重新载入。')

    def close(self):
        if not self.handle.closed:
            if os.name == 'nt':
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            self.handle.close()
            if _leases.get(self.path) is self:
                del _leases[self.path]


def open_command_workspace(path):
    """CLI lifetime: managed workspaces use the same OS writer boundary."""
    path = Path(path).resolve()
    inspect_workspace(path)
    existing = _leases.get(path)
    if existing:
        existing.require_current()
        return None
    return WorkspaceLease(path)
