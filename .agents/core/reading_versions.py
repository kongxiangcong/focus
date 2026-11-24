"""Reading Version selection, committed backup recovery, and browsing bookmarks."""
from contextlib import closing
import hashlib
import shutil
import sqlite3
import uuid

from .reading_workspace import (
    WorkspaceError, _identifier, _read_chunk_records, _read_document,
    _read_reading_record, _source_bundle_at_version, _validate_parser_bundle,
    _write_document,
)
from .source_blocks import source_lines
from .source_provenance import bundle_fingerprint


def selected_version(state, source_id):
    return state.get('sources', {}).get(source_id, {}).get('reading_version', 1)


def version_metadata(state, source_id, reading_version=None):
    if reading_version is None:
        reading_version = selected_version(state, source_id)
    return state.get('reading_versions', {}).get(source_id, {}).get(str(reading_version), {})


def version_cursor(state, source_id, reading_version):
    if selected_version(state, source_id) == reading_version:
        return state['sources'][source_id]
    return version_metadata(state, source_id, reading_version).get('cursor', {})


def pending_reset(state, source_id, reading_version):
    resets = state.get('pending_reading_resets', {})
    request_id = resets.get(source_id)
    receipt = state.get('reading_version_resets', {}).get(request_id)
    if receipt and receipt['readingVersion'] == reading_version:
        return request_id
    if request_id and not receipt and selected_version(state, source_id) == reading_version:
        return request_id
    return version_metadata(state, source_id, reading_version).get('pending_reset')


def version_directory(root, reading_version):
    return root / 'reading' / 'versions' / str(reading_version)


def version_reading_directory(root, state, source_id, reading_version=None):
    if reading_version is None:
        reading_version = selected_version(state, source_id)
    if version_metadata(state, source_id, reading_version).get('storage') == 'versioned':
        return version_directory(root, reading_version)
    return root / 'reading'


def _asset_hashes(root):
    hashes = {}
    for path in sorted(root.rglob('*')):
        if path.is_file() and path != root / 'backup.json':
            with path.open('rb') as asset:
                hashes[path.relative_to(root).as_posix()] = hashlib.file_digest(asset, 'sha256').hexdigest()
    return hashes


class ReadingVersions:
    def __init__(self, reading, notes):
        self.reading = reading
        self.notes = notes
        self.state_path = reading.workspace / 'state.json'

    def receipts(self):
        return _read_document(self.state_path).get('reading_version_resets', {})

    def list(self, source_id):
        from .reading_application import _LOCK

        self.reading._root(source_id)
        with _LOCK:
            state = _read_document(self.state_path)
            selected = selected_version(state, source_id)
            versions = state.get('reading_versions', {}).get(source_id, {})
            return [
                {'readingVersion': version, 'selected': version == selected,
                 'ready': self._ready(state, source_id, version),
                 'backedUpAt': versions.get(str(version), {}).get('backed_up_at')}
                for version in sorted({selected, *map(int, versions)})
            ]

    def _ready(self, state, source_id, reading_version):
        cursor = version_cursor(state, source_id, reading_version)
        plan = cursor.get('current_plan_id')
        try:
            if plan:
                return self.reading._plan_ready(source_id, plan, reading_version=reading_version)
            run = self.reading.status(source_id, reading_version=reading_version)
        except (OSError, WorkspaceError):
            return False
        return bool(not cursor.get('reading_started') and run and run['ready'])

    def switch(self, source_id, reading_version):
        from .reading_application import _LOCK

        self.check_version(reading_version)
        self.reading._root(source_id)
        with _LOCK:
            state = _read_document(self.state_path)
            current = selected_version(state, source_id)
            if current == reading_version:
                return
            versions = state.get('reading_versions', {}).get(source_id, {})
            if str(reading_version) not in versions:
                raise WorkspaceError('reading_version_missing', '找不到此阅读轮次。')
            if not self._ready(state, source_id, reading_version):
                raise WorkspaceError('reading_not_ready', '此轮阅读尚未就绪。')
            incoming = dict(version_cursor(state, source_id, reading_version))
            if not incoming.get('current_plan_id'):
                plan = self.reading.status(source_id, reading_version=reading_version)['plan_id']
                chunks = _read_chunk_records(self.reading._root(source_id) / 'reading' / 'plans' / plan / 'chunks.jsonl')
                incoming.update(current_plan_id=plan, current_chunk_id=chunks[0]['chunk_id'], reading_started=False)
            versions[str(current)]['cursor'] = state['sources'][source_id]
            state['sources'][source_id] = {**incoming, 'reading_version': reading_version}
            state['current_source_id'] = source_id
            state['reading_revision'] = state.get('reading_revision', 0) + 1
            state['reading_version_switch'] = {'sourceId': source_id, 'readingVersion': reading_version,
                                               'readingRevision': state['reading_revision']}
            _write_document(self.state_path, state)

    def reset(self, source_id, request_id, *, expected, discussion_id, capture, clock):
        """Publish the verified backup and next round in a single Core commit."""
        from .reading_application import _LOCK

        root = self.reading._root(source_id)
        with _LOCK:
            state = _read_document(self.state_path)
            current = selected_version(state, source_id)
            cursor = state['sources'][source_id]
            if expected is not None and expected != current:
                raise WorkspaceError('reading_version_changed', '阅读轮次已改变，请刷新后重试。')
            versions = state.setdefault('reading_versions', {}).setdefault(source_id, {})
            following = max([current, *map(int, versions)]) + 1
            bound = versions.get(str(current), {})
            old_plan = cursor.get('current_plan_id')
            run = self.reading._read(source_id) or {}
            if old_plan is None and run.get('status') == 'ready' and self.reading._plan_ready(source_id, run['plan_id']):
                old_plan = run['plan_id']
            plan_ids = sorted({*bound.get('plan_ids', []), *run.get('ready_plans', {}), *([old_plan] if old_plan else [])})
            plan_root = root / 'reading' / 'plans'
            provenance = plan_root / old_plan / 'provenance.json' if old_plan else None
            bundle = (bound.get('bundle_version') or
                      (_read_document(provenance).get('bundle') if provenance and provenance.is_file() else None) or
                      self.reading._bundle_version(source_id))
            parser_bundle = _source_bundle_at_version(root, bundle)

            token = uuid.uuid4().hex
            backup_root = version_directory(root, current) / 'backups'
            staging = backup_root / token
            next_notes = version_directory(root, following) / 'notes.sqlite3'
            try:
                staging.mkdir(parents=True)
                shutil.copytree(parser_bundle, staging / 'parser-bundle')
                for plan_id in plan_ids:
                    plan_id = _identifier(plan_id, 'plan_id')
                    shutil.copytree(plan_root / plan_id, staging / 'plans' / plan_id)
                for path, name in (
                    (root / 'reading' / 'translations' / f'{current}.json', 'translation.json'),
                    (version_reading_directory(root, state, source_id) / 'opening-v2.json', 'opening-v2.json'),
                ):
                    if path.is_file():
                        shutil.copy2(path, staging / name)

                # Capture the note and highlight projections from the same WAL snapshot.
                annotations = self.notes.backup_round(source_id, bundle, staging / 'notes.sqlite3', next_notes)
                snapshot = capture(old_plan, bundle)
                backed_up_at = int(clock() * 1000)
                snapshot.update(annotations, sourceId=source_id, readingVersion=current, bundleVersion=bundle,
                                cursor=dict(cursor), planId=old_plan, bookmark=self._bookmark_at(state, source_id, current, bundle),
                                backedUpAt=backed_up_at)
                manifest_path = staging / 'backup.json'
                _write_document(manifest_path, {'snapshot': snapshot, 'files': _asset_hashes(staging)})
                manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                self._read_backup(staging, source_id, current, bundle, backed_up_at, manifest_hash)

                versions[str(current)] = {**bound, 'bundle_version': bundle, 'discussion_id': discussion_id,
                                          'cursor': dict(cursor), 'plan_ids': plan_ids, 'backup': token,
                                          'backed_up_at': backed_up_at, 'backup_sha256': manifest_hash}
                if run.get('status') == 'running':
                    versions[str(current)]['revoked_preparation'] = run['run_id']
                versions[str(following)] = {'storage': 'versioned', 'bundle_version': self.reading._bundle_version(source_id),
                                            'discussion_id': uuid.uuid4().hex, 'plan_ids': [], 'pending_reset': request_id}
                for entry in state.get('reading_progress', {}).values():
                    if entry['source_id'] == source_id:
                        entry.setdefault('reading_version', current)
                state['sources'][source_id] = dict(current_plan_id=None, current_chunk_id=None, reading_started=False,
                                                   reading_pass=1, reading_version=following)
                state['reading_revision'] = state.get('reading_revision', 0) + 1
                receipt = {'sourceId': source_id, 'status': 'completed', 'resetReading': True, 'restartReading': True,
                           'priorReadingVersion': current, 'readingVersion': following, 'backedUpAt': backed_up_at}
                state.setdefault('reading_version_resets', {})[request_id] = receipt
                _write_document(self.state_path, state)
            except Exception as exc:
                # If an error was reported after the atomic replacement, the receipt
                # still owns the staged assets and will be reconciled by Host.
                receipt = self.receipts().get(request_id)
                if not receipt:
                    shutil.rmtree(staging, ignore_errors=True)
                    raise WorkspaceError('clear_incomplete', '阅读备份未完成，请重试重新阅读。') from exc
            for backup in backup_root.iterdir():
                if backup != staging:
                    shutil.rmtree(backup, ignore_errors=True)
            return receipt

    @staticmethod
    def _read_backup(root, source_id, reading_version, bundle, backed_up_at, manifest_hash):
        path = root / 'backup.json'
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest_hash:
            raise ValueError('Reading backup manifest has changed')
        manifest = _read_document(path)
        data = manifest['snapshot']
        if (data['sourceId'], data['readingVersion'], data['bundleVersion'], data['backedUpAt']) != (
                source_id, reading_version, bundle, backed_up_at):
            raise ValueError('Reading backup identity is invalid')
        if _asset_hashes(root) != manifest['files']:
            raise ValueError('Reading backup assets are incomplete')
        parser = root / 'parser-bundle'
        _validate_parser_bundle(parser)
        if (bundle_fingerprint(parser) != bundle or
                (parser / 'content.md').read_text(encoding='utf-8') != data['document']['markdown']):
            raise ValueError('Reading backup Parser Bundle is invalid')
        plan_id = data['planId']
        if plan_id:
            plan = root / 'plans' / _identifier(plan_id, 'plan_id')
            chunks = _read_chunk_records(plan / 'chunks.jsonl')
            chunk_ids = [chunk['chunk_id'] for chunk in chunks]
            if data['cursor'].get('current_chunk_id') not in (None, *chunk_ids):
                raise ValueError('Reading backup Cursor is invalid')
            data['chunks'] = [{**chunk, 'record': _read_reading_record(plan / 'records' / f'{chunk_id}.json', chunk_id)}
                              for chunk, chunk_id in zip(chunks, chunk_ids)]
        else:
            data['chunks'] = []
        database = root / 'notes.sqlite3'
        with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('Reading backup annotations are unreadable')
        return data

    def recover(self, source_id, reading_version):
        self.reading._root(source_id)
        self.check_version(reading_version)
        metadata = version_metadata(_read_document(self.state_path), source_id, reading_version)
        if 'backup' not in metadata:
            raise WorkspaceError('reading_backup_missing', '此轮阅读没有可恢复的备份。')
        try:
            root = version_directory(self.reading._root(source_id), reading_version) / 'backups' / metadata['backup']
            return self._read_backup(root, source_id, reading_version, metadata['bundle_version'], metadata['backed_up_at'],
                                     metadata['backup_sha256'])
        except (OSError, ValueError, KeyError, sqlite3.Error, WorkspaceError) as exc:
            raise WorkspaceError('reading_backup_invalid', '此轮阅读备份无法读取。') from exc

    @staticmethod
    def check_version(value):
        if type(value) is not int or value < 1:
            raise WorkspaceError('reading_version_invalid', '阅读轮次无效。')

    @staticmethod
    def _bookmark_at(state, source_id, reading_version, bundle):
        saved = state.get('reading_view_bookmarks', {}).get(source_id, {}).get(str(reading_version))
        return saved if saved and saved['bundleVersion'] == bundle else None

    def bookmark(self, source_id, reading_version=None, payload=None):
        from .reading_application import _LOCK

        root = self.reading._root(source_id)
        with _LOCK:
            state = _read_document(self.state_path)
            if reading_version is None:
                reading_version = selected_version(state, source_id)
            self.check_version(reading_version)
            metadata = version_metadata(state, source_id, reading_version)
            if reading_version != selected_version(state, source_id) and not metadata:
                raise WorkspaceError('reading_version_missing', '找不到此阅读轮次。')
            bundle = metadata.get('bundle_version') or self.reading._bundle_version(source_id)
            if payload is None:
                return self._bookmark_at(state, source_id, reading_version, bundle)
            if (set(payload) - {'readingVersion', 'bundleVersion', 'line', 'offset', 'sourceOffset', 'fraction'}
                    or payload['readingVersion'] != reading_version or payload['bundleVersion'] != bundle):
                raise WorkspaceError('reading_bookmark_changed', '阅读位置的原文已改变，请刷新后重试。')
            line, offset = payload.get('line'), payload.get('offset', 0)
            source_offset, fraction = payload.get('sourceOffset', 0), payload.get('fraction', 0)
            parser = _source_bundle_at_version(root, bundle)
            markdown = (parser / 'content.md').read_text(encoding='utf-8')
            if (type(line) is not int or not 1 <= line <= len(source_lines(markdown))
                    or type(offset) not in (int, float) or not -100000 <= offset <= 100000
                    or type(source_offset) is not int or not 0 <= source_offset < len(markdown)
                    or type(fraction) not in (int, float) or not 0 <= fraction <= 1):
                raise WorkspaceError('reading_bookmark_invalid', '阅读书签无效。')
            bookmarks = state.setdefault('reading_view_bookmarks', {}).setdefault(source_id, {})
            if bookmarks.get(str(reading_version)) != payload:
                bookmarks[str(reading_version)] = payload
                _write_document(self.state_path, state)
            return payload
