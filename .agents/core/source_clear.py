"""Recoverable Source clearing across Core notes and Host discussion storage."""
import copy
import uuid

from .source_library import SourceLibrary
from .reading_workspace import WorkspaceError


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
    state.get('failedChatRuns', {}).pop(source_id, None)
    for key, value in state.get('requests', {}).items():
        if references(value):
            state['requests'][key] = {'cleared': True, 'sourceId': source_id}
    for key in ('noteFeedback', 'noteOperation', 'highlightOperation', 'run'):
        if references(state.get(key)):
            state[key] = None
    # Legacy native contexts may contain more than one Source. Never resume them.
    state['threadId'] = None
    state['resumeBackend'] = None
    return state


def archive_for_reset(state, source_id, current_source):
    from . import discussions

    state = copy.deepcopy(state)
    if source_id not in state.get('latestDiscussion', {}) and any(
            message.get('sourceId') == source_id and not message.get('discussionId')
            for message in state['conversation']):
        discussions.select(state, source_id)
    discussions.select(state, source_id, new=True)
    state.get('failedChatRuns', {}).pop(source_id, None)
    state['timeline'] = [entry for entry in state.get('timeline', [])
                         if (entry.get('receipt') or {}).get('sourceId') != source_id]
    state['readingViews'] = {k: v for k, v in state.get('readingViews', {}).items() if not v or v[0] != source_id}
    for key, value in state.get('requests', {}).items():
        if isinstance(value, dict) and (value.get('discussion') or value).get('sourceId') == source_id:
            state['requests'][key] = {'cleared': True, 'sourceId': source_id}
    for key in ('noteFeedback', 'noteOperation', 'highlightOperation', 'run'):
        if (state.get(key) or {}).get('sourceId') == source_id:
            state[key] = None
    if (state.get('discussionSourceId') or current_source) == source_id:
        state.update(sessionId=uuid.uuid4().hex, threadId=None, resumeBackend=None,
                     discussionSourceId=source_id, displayReading=True, readingMarker=None)
    return state


class SourceClear:
    def __init__(self, store, notes, reading):
        self.store, self.notes, self.reading = store, notes, reading

    def recover(self):
        operations = self.store.get('sourceClears') or {}
        for request_id, operation in operations.items():
            if operation['status'] == 'pending':
                source_id = operation['sourceId']
                if operation.get('restartReading'):
                    current = self.reading.restart_after_clear(source_id, request_id)
                    self.notes.clear(source_id, request_id=request_id, local_only=True)
                    self.store.archive_for_reading_reset(source_id, request_id, current)
                else:
                    if operation.get('resetReading'):
                        self.reading.rewind_after_clear(source_id, request_id)
                    self.notes.clear(source_id, request_id=request_id)
                    self.store.clear_discussions(source_id, request_id, reset_reading=operation.get('resetReading', False))

    def execute(self, source_id, payload, *, busy, restart_reading=False):
        self.notes._check_request(payload.get('requestId'))
        if payload.get('confirmed') is not True:
            raise WorkspaceError('clear_confirmation_required', '清除不可撤销，请确认删除范围。')
        SourceLibrary(self.notes.workspace).get(source_id)
        operations = self.store.get('sourceClears') or {}
        request_id = payload['requestId']
        prior = operations.get(request_id)
        if prior and (prior['sourceId'] != source_id or prior.get('resetReading', False) != payload.get('resetReading', False)
                      or prior.get('restartReading', False) != restart_reading):
            raise WorkspaceError('clear_request_conflict', '清除请求已用于另一篇材料。')
        if prior and prior['status'] == 'completed':
            return prior
        if busy and not prior:
            raise WorkspaceError('source_busy', '该材料有活动任务，请等待任务结束后再清除。')
        operations[request_id] = {'sourceId': source_id, 'status': 'pending', 'resetReading': payload.get('resetReading', False)}
        if restart_reading:
            operations[request_id]['restartReading'] = True
        self.store.put('sourceClears', operations)
        try:
            self.recover()
        except Exception as exc:
            raise WorkspaceError('clear_incomplete', '清除尚未完成；请重试清除或重启以完成恢复。') from exc
        return self.store.get('sourceClears')[request_id]
