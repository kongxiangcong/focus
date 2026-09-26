"""Reading progress lives beside navigation requests in the authoritative state file.

Navigation enqueues a fact in the same atomic state write as its Cursor change.
Later generation can enrich that fact, but cannot move the Cursor.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from .reading_workspace import WorkspaceError, _read_document, _write_document, validate_source_id


def enqueue(state: dict, *, request_id: str, operation: str, source_id: str,
            bundle: str, plan_id: str, chunk_id: str, reading_pass: int) -> None:
    state.setdefault('reading_progress', {})[request_id] = {
        'progress_id': request_id, 'trigger_request_id': request_id,
        'source_id': source_id, 'bundle': bundle, 'plan_id': plan_id,
        'chunk_id': chunk_id, 'reading_pass': reading_pass,
        'operation': operation, 'status': 'pending', 'revision': 1,
        'fact': '已读本段', 'topic': None, 'user_understanding': None,
        'deleted': False, 'attempt': None, 'error': None,
    }


class ReadingProgress:
    """Core write boundary for one progress entry per committed navigation."""

    def __init__(self, workspace: Path):
        self.path = Path(workspace).resolve() / 'state.json'

    def _state(self):
        return _read_document(self.path)

    def get(self, progress_id: str) -> dict:
        from .reading_application import _LOCK
        with _LOCK:
            entry = self._state().get('reading_progress', {}).get(progress_id)
            if entry is None:
                raise WorkspaceError('progress_missing', 'Reading progress does not exist')
            return dict(entry)

    def list(self, source_id: str, plan_id: str | None = None) -> list[dict]:
        from .reading_application import _LOCK
        source_id = validate_source_id(source_id)
        with _LOCK:
            return [dict(entry) for entry in self._state().get('reading_progress', {}).values()
                    if entry['source_id'] == source_id and (plan_id is None or entry['plan_id'] == plan_id)]

    def interrupt_running(self) -> None:
        from .reading_application import _LOCK
        with _LOCK:
            if not self.path.is_file():
                return
            state = self._state()
            changed = False
            for entry in state.get('reading_progress', {}).values():
                if entry['status'] == 'generating':
                    entry.update(status='interrupted', attempt=None, error='生成中断，可补记')
                    changed = True
            if changed:
                _write_document(self.path, state)

    def begin(self, progress_id: str, *, request_id: str) -> dict:
        from .reading_application import _LOCK
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9-]{8,80}', request_id):
            raise WorkspaceError('progress_request_invalid', 'Unique request ID required')
        with _LOCK:
            state = self._state()
            entry = state.get('reading_progress', {}).get(progress_id)
            if entry is None:
                raise WorkspaceError('progress_missing', 'Reading progress does not exist')
            requests = state.setdefault('progress_requests', {})
            previous = requests.get(request_id)
            payload = {'operation': 'generate', 'progress_id': progress_id}
            if previous:
                if previous['input'] != payload:
                    raise WorkspaceError('progress_request_reused', 'Request ID has different progress input')
                return {**entry, 'replayed': True}
            if entry['deleted'] or entry['status'] not in ('pending', 'failed', 'interrupted'):
                raise WorkspaceError('progress_not_pending', 'This progress entry cannot be generated')
            entry.update(status='generating', attempt=uuid.uuid4().hex, error=None)
            requests[request_id] = {'input': payload, 'result': {'progress_id': progress_id,
                'attempt': entry['attempt']}}
            _write_document(self.path, state)
            return dict(entry)

    def finish(self, progress_id: str, *, attempt: str, expected_revision: int,
               topic: str | None, user_understanding: str | None, error: str | None = None) -> dict:
        from .reading_application import _LOCK
        with _LOCK:
            state = self._state()
            entry = state.get('reading_progress', {}).get(progress_id)
            if (entry is None or entry['status'] != 'generating' or entry['attempt'] != attempt
                    or entry['revision'] != expected_revision or entry['deleted']):
                raise WorkspaceError('progress_stale', 'Progress candidate is stale')
            if error is None:
                if any(value is not None and (not isinstance(value, str) or len(value) > 500)
                       for value in (topic, user_understanding)):
                    raise WorkspaceError('progress_invalid', 'Progress summary is invalid')
                entry.update(status='saved', topic=topic, user_understanding=user_understanding,
                             error=None, attempt=None)
            else:
                entry.update(status='failed', error='生成失败，可补记', attempt=None)
            _write_document(self.path, state)
            return dict(entry)

    def cancel(self, progress_id: str, *, attempt: str) -> dict:
        from .reading_application import _LOCK
        with _LOCK:
            state = self._state()
            entry = state.get('reading_progress', {}).get(progress_id)
            if entry is None or entry['attempt'] != attempt or entry['status'] != 'generating':
                raise WorkspaceError('progress_stale', 'Progress attempt is stale')
            entry.update(status='interrupted', attempt=None, error='生成已停止，可补记')
            _write_document(self.path, state)
            return dict(entry)

    def change(self, progress_id: str, *, operation: str, expected_revision: int,
               request_id: str, content: str | None = None) -> dict:
        from .reading_application import _LOCK
        if operation not in ('edit', 'delete') or not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9-]{8,80}', request_id):
            raise WorkspaceError('progress_request_invalid', 'Invalid progress change')
        if operation == 'edit' and (not isinstance(content, str) or not content.strip() or len(content) > 1000):
            raise WorkspaceError('progress_invalid', 'Progress correction is required')
        payload = {'operation': operation, 'progress_id': progress_id,
                   'expected_revision': expected_revision, 'content': content}
        with _LOCK:
            state = self._state()
            entry = state.get('reading_progress', {}).get(progress_id)
            if entry is None:
                raise WorkspaceError('progress_missing', 'Reading progress does not exist')
            requests = state.setdefault('progress_requests', {})
            previous = requests.get(request_id)
            if previous:
                if previous['input'] != payload:
                    raise WorkspaceError('progress_request_reused', 'Request ID has different progress input')
                return dict(previous['result'])
            if type(expected_revision) is not int or entry['revision'] != expected_revision or entry['deleted']:
                result = {'status': 'conflict', 'current': dict(entry), 'attempted_content': content}
            else:
                entry['revision'] += 1
                entry['attempt'] = None
                if operation == 'delete':
                    entry.update(deleted=True, status='deleted')
                else:
                    entry.update(topic=content.strip(), user_understanding=None, status='saved', error=None)
                result = {'status': 'changed', 'entry': dict(entry)}
            requests[request_id] = {'input': payload, 'result': result}
            _write_document(self.path, state)
            return result


class ProgressApplication:
    """Enrich a committed read fact without owning navigation or raw chat."""

    def __init__(self, core: ReadingProgress, runtime):
        self.core, self.runtime = core, runtime

    def process(self, progress_id: str, *, request_id: str, discussion: list[dict]) -> dict:
        entry = self.core.begin(progress_id, request_id=request_id)
        attempt, revision = entry['attempt'], entry['revision']
        if entry.get('replayed') or entry['status'] != 'generating' or attempt is None:
            return entry
        try:
            scoped = [m for m in discussion if m.get('sourceId') == entry['source_id']
                      and m.get('chunkId') == entry['chunk_id']
                      and m.get('readingPass') == entry['reading_pass']
                      and m.get('role') in ('user', 'assistant') and isinstance(m.get('content'), str)]
            # A user turn without an answer is not a completed discussion.
            if not any(m['role'] == 'assistant' and m['content'].strip() for m in scoped):
                return self.core.finish(progress_id, attempt=attempt, expected_revision=revision,
                                        topic=None, user_understanding=None)
            explicit = [m['content'].strip()[:300] for m in scoped if m['role'] == 'user' and
                        not re.search(r'[吗？?]', m['content']) and
                        re.search(r'我(?:现在)?(?:理解|明白|懂)(?:了|的是|：|:)|I (?:understand|realize)', m['content'], re.I)]
            candidate = self.runtime.progress(source_id=entry['source_id'], chunk_id=entry['chunk_id'],
                discussion=[{'role': m['role'], 'content': m['content'][:500]} for m in scoped[-8:]])
            topic = candidate.get('topic') if isinstance(candidate, dict) else None
            if topic is not None and (not isinstance(topic, str) or not topic.strip()):
                raise ValueError('Invalid progress topic')
            return self.core.finish(progress_id, attempt=attempt, expected_revision=revision,
                                    topic=topic, user_understanding=explicit[-1] if explicit else None)
        except Exception:
            try:
                return self.core.finish(progress_id, attempt=attempt, expected_revision=revision,
                                        topic=None, user_understanding=None, error='generation_failed')
            except WorkspaceError:
                return self.core.get(progress_id)
