"""Recoverable Source clearing across Core notes and Host discussion storage."""
import copy

from .core_bridge import SourceLibrary, WorkspaceError


def scrub(state, source_id, *, reset_reading=False):
    state = copy.deepcopy(state)
    def references(value):
        if isinstance(value, dict):
            return value.get('sourceId') == source_id or value.get('source_id') == source_id or any(references(v) for v in value.values())
        return isinstance(value, list) and any(references(v) for v in value)
    removed = {m['messageId'] for m in state.get('conversation', []) if references(m)}
    state['conversation'] = [m for m in state.get('conversation', []) if m['messageId'] not in removed]
    state['timeline'] = [e for e in state.get('timeline', []) if e.get('messageId') not in removed and (not reset_reading or not references(e))]
    if reset_reading and (state.get('discussionSourceId') == source_id or ((state.get('readingMarker') or [{}])[0] or {}).get('sourceId') == source_id):
        state.update(displayReading=False, readingMarker=None)
    state['readingViews'] = {k: v for k, v in state.get('readingViews', {}).items() if not v or v[0] != source_id}
    state['discussions'] = {k: v for k, v in state.get('discussions', {}).items() if not references(v)}
    state.get('latestDiscussion', {}).pop(source_id, None)
    for key, value in state.get('requests', {}).items():
        if references(value):
            state['requests'][key] = {'cleared': True, 'sourceId': source_id}
    for key in ('noteFeedback', 'noteOperation', 'run'):
        if references(state.get(key)):
            state[key] = None
    # Legacy native contexts may contain more than one Source. Never resume them.
    state['threadId'] = None
    state['resumeBackend'] = None
    return state


class SourceClear:
    def __init__(self, store, notes):
        self.store, self.notes = store, notes

    def recover(self):
        operations = self.store.get('sourceClears') or {}
        for request_id, operation in operations.items():
            if operation['status'] == 'pending':
                if operation.get('resetReading'):
                    self.reset_reading(operation['sourceId'], request_id)
                self.notes.clear(operation['sourceId'], request_id=request_id)
                self.store.clear_discussions(operation['sourceId'], request_id, reset_reading=operation.get('resetReading', False))

    def reset_reading(self, source_id, request_id):
        from core.reading_application import _LOCK
        from core.reading_workspace import _read_document, _write_document, _read_chunk_records
        with _LOCK:
            path = self.notes.workspace / 'state.json'
            state = _read_document(path)
            if request_id in state.get('source_resets', {}):
                return
            selected = state['sources'][source_id]
            plan_id = selected.get('current_plan_id')
            chunks = _read_chunk_records(self.notes.workspace / 'sources' / source_id / 'reading' / 'plans' / plan_id / 'chunks.jsonl') if plan_id else []
            selected.update(current_chunk_id=chunks[0]['chunk_id'] if chunks else None,
                            reading_started=False, reading_pass=int(selected.get('reading_pass', 1)) + 1)
            removed = {k for k, v in state.get('reading_progress', {}).items() if v['source_id'] == source_id}
            state['progress_requests'] = {k: v for k, v in state.get('progress_requests', {}).items() if v.get('input', {}).get('progress_id') not in removed}
            state['reading_progress'] = {k: v for k, v in state.get('reading_progress', {}).items() if v['source_id'] != source_id}
            # Old receipts may replay a stale result but can never mutate this new pass.
            state['reading_revision'] = int(state.get('reading_revision', 0)) + 1
            state.setdefault('source_resets', {})[request_id] = source_id
            _write_document(path, state)

    def execute(self, source_id, payload, *, busy):
        self.notes._check_request(payload.get('requestId'))
        if payload.get('confirmed') is not True:
            raise WorkspaceError('clear_confirmation_required', '清除不可撤销，请确认删除范围。')
        SourceLibrary(self.notes.workspace).get(source_id)
        operations = self.store.get('sourceClears') or {}
        request_id = payload['requestId']
        prior = operations.get(request_id)
        if prior and (prior['sourceId'] != source_id or prior.get('resetReading', False) != payload.get('resetReading', False)):
            raise WorkspaceError('clear_request_conflict', '清除请求已用于另一篇材料。')
        if prior and prior['status'] == 'completed':
            return prior
        if busy:
            raise WorkspaceError('source_busy', '该材料有活动任务，请等待任务结束后再清除。')
        operations[request_id] = {'sourceId': source_id, 'status': 'pending', 'resetReading': payload.get('resetReading', False)}
        self.store.put('sourceClears', operations)
        try:
            self.recover()
        except Exception as exc:
            raise WorkspaceError('clear_incomplete', '清除尚未完成；请重试清除或重启以完成恢复。') from exc
        return self.store.get('sourceClears')[request_id]
