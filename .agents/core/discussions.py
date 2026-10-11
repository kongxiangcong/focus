"""Lossless discussion history projection and transactional incremental compaction.

The persisted Host conversation owns the full transcript. summaryThrough marks
a contiguous prefix; never discard a message when the marker is inconsistent.
"""
import json
import uuid

RECENT_LIMIT = 12
RECENT_CHAR_LIMIT = 60000
MAX_SUMMARY_CHARS = 12000
BATCH_CHAR_LIMIT = 30000


def select(state, source_id, *, discussion_id=None, new=False):
    discussions = state.setdefault('discussions', {})
    latest = state.setdefault('latestDiscussion', {})
    if discussion_id:
        if discussions.get(discussion_id, {}).get('sourceId') != source_id:
            raise ValueError('讨论不属于此 Source。')
    else:
        discussion_id = None if new else latest.get(source_id)
    if not discussion_id:
        discussion_id = uuid.uuid4().hex
        discussions[discussion_id] = {'sourceId': source_id, 'summary': '', 'summaryThrough': None}
        if not new:
            for message in state['conversation']:
                if message.get('sourceId') == source_id and not message.get('discussionId'):
                    message['discussionId'] = discussion_id
    latest[source_id] = discussion_id
    return discussion_id


def plan(state, discussion_id, *, exclude_message_id=None):
    """Snapshot complete uncovered history without modifying the authority."""
    metadata = state['discussions'][discussion_id]
    messages = [message for message in state['conversation']
                if message.get('discussionId') == discussion_id and
                message.get('messageId') != exclude_message_id]
    ids = [message['messageId'] for message in messages]
    if len(ids) != len(set(ids)):
        raise ValueError('讨论消息身份重复；拒绝不完整上下文。')
    through = metadata.get('summaryThrough')
    if through is not None and through not in ids:
        raise ValueError('讨论摘要覆盖标记失效；拒绝跳过旧消息。')
    if through is not None and not metadata.get('summary', '').strip():
        raise ValueError('已有摘要丢失；拒绝跳过已覆盖历史。')
    tail = messages[ids.index(through) + 1:] if through else messages
    recent, size = [], 0
    for message in reversed(tail):
        if recent and (len(recent) >= RECENT_LIMIT or size + len(message['content']) > RECENT_CHAR_LIMIT):
            break
        recent.insert(0, message)
        size += len(message['content'])
    return {'summary': metadata.get('summary', ''), 'summaryThrough': through,
            'pending': tail[:len(tail)-len(recent)], 'recent': recent,
            'sourceId': metadata['sourceId']}


def _projection(summary, messages):
    return {'earlierSummary': summary,
            'recentMessages': [{'role': message['role'], 'content': message['content']}
                               for message in messages]}


def inline_context(snapshot, *, budget):
    """Project all uncovered messages when within the conservative character cap."""
    value = _projection(snapshot['summary'], snapshot['pending'] + snapshot['recent'])
    return value if len(json.dumps(value, ensure_ascii=False)) <= budget else None


def compact_snapshot(snapshot, summarize, *, batch_callback=None):
    """Calculate an update without mutating the persisted summary/cursor."""
    summary = snapshot['summary']
    through = snapshot['summaryThrough']
    pending = list(snapshot['pending'])
    while pending:
        batch, size = [], 0
        while pending and (not batch or size + len(pending[0]['content']) <= BATCH_CHAR_LIMIT):
            message = pending.pop(0)
            batch.append({'role': message['role'], 'content': message['content']})
            size += len(message['content'])
            through = message['messageId']
        if batch_callback:
            batch_callback(size + len(summary))
        summary = summarize(summary, batch)
        if not isinstance(summary, str) or not summary.strip() or len(summary) > MAX_SUMMARY_CHARS:
            raise ValueError('讨论摘要无效，旧历史覆盖标记未推进。')
    return {'summary': summary, 'summaryThrough': through}


def context(state, discussion_id, summarize, *, exclude_message_id=None):
    """Compatibility eager API; persist only after all batches succeed."""
    snapshot = plan(state, discussion_id, exclude_message_id=exclude_message_id)
    update = compact_snapshot(snapshot, summarize)
    state['discussions'][discussion_id].update(update)
    return _projection(update['summary'], snapshot['recent'])
