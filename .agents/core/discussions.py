"""FOCUS discussion identities and model context over the durable Host history."""
import uuid


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
            # Upgrade existing FOCUS-visible messages, never native Runtime logs.
            for message in state['conversation']:
                if message.get('sourceId') == source_id and not message.get('discussionId'):
                    message['discussionId'] = discussion_id
    latest[source_id] = discussion_id
    return discussion_id


def context(state, discussion_id, summarize):
    messages = [m for m in state['conversation'] if m.get('discussionId') == discussion_id]
    # Keep visible history intact. Summarize new older messages together with
    # the cumulative summary, never silently slice away an uncovered prefix.
    recent, size = [], 0
    for message in reversed(messages):
        if recent and (len(recent) >= 12 or size + len(message['content']) > 60000):
            break
        recent.insert(0, message)
        size += len(message['content'])
    early = messages[:len(messages)-len(recent)]
    metadata = state['discussions'][discussion_id]
    through = metadata.get('summaryThrough')
    start = next((i + 1 for i, m in enumerate(early) if m['messageId'] == through), 0)
    pending = early[start:]
    while pending:
        batch, size = [], 0
        while pending and (not batch or size + len(pending[0]['content']) <= 30000):
            message = pending.pop(0)
            batch.append({'role': message['role'], 'content': message['content']})
            size += len(message['content'])
            through = message['messageId']
        summary = summarize(metadata.get('summary', ''), batch)
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 12000:
            raise ValueError('讨论摘要无效，未更新历史上下文。')
        metadata.update(summary=summary, summaryThrough=through)
    return {'earlierSummary': metadata.get('summary', ''),
            'recentMessages': [{'role': m['role'], 'content': m['content']} for m in recent]}
