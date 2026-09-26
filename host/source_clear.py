"""Recoverable Source clearing across Core notes and Host discussion storage."""
import copy

from .core_bridge import SourceLibrary, WorkspaceError


def scrub(state, source_id):
    state = copy.deepcopy(state)
    def references(value):
        if isinstance(value, dict):
            return value.get('sourceId') == source_id or value.get('source_id') == source_id or any(references(v) for v in value.values())
        return isinstance(value, list) and any(references(v) for v in value)
    removed = {m['messageId'] for m in state.get('conversation', []) if references(m)}
    state['conversation'] = [m for m in state.get('conversation', []) if m['messageId'] not in removed]
    state['timeline'] = [e for e in state.get('timeline', []) if e.get('messageId') not in removed]
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
                self.notes.clear(operation['sourceId'], request_id=request_id)
                self.store.clear_discussions(operation['sourceId'], request_id)

    def execute(self, source_id, payload, *, busy):
        self.notes._check_request(payload.get('requestId'))
        if payload.get('confirmed') is not True:
            raise WorkspaceError('clear_confirmation_required', '清除不可撤销，请确认删除范围。')
        SourceLibrary(self.notes.workspace).get(source_id)
        operations = self.store.get('sourceClears') or {}
        request_id = payload['requestId']
        prior = operations.get(request_id)
        if prior and prior['sourceId'] != source_id:
            raise WorkspaceError('clear_request_conflict', '清除请求已用于另一篇材料。')
        if prior and prior['status'] == 'completed':
            return prior
        if busy:
            raise WorkspaceError('source_busy', '该材料有活动任务，请等待任务结束后再清除。')
        operations[request_id] = {'sourceId': source_id, 'status': 'pending'}
        self.store.put('sourceClears', operations)
        try:
            self.recover()
        except Exception as exc:
            raise WorkspaceError('clear_incomplete', '清除尚未完成；请重试清除或重启以完成恢复。') from exc
        return self.store.get('sourceClears')[request_id]
