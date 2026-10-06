"""Persist dismissal receipts without modifying business attempts or assets."""
import hashlib
import json

TERMINAL_STATUSES = frozenset({
    'completed', 'ready', 'failed', 'error', 'interrupted', 'cancelled', 'deleted',
    'bundle_changed', 'commit_conflict', 'retry_waiting', 'topic_attachment_pending',
    'partial', 'paused',
})


def fingerprint(value):
    def stable(item):
        if isinstance(item, dict):
            return {key: stable(child) for key, child in item.items() if key != 'dismissed'}
        if isinstance(item, list):
            return [stable(child) for child in item]
        return item
    return hashlib.sha256(json.dumps(
        stable(value),
        sort_keys=True, ensure_ascii=False, separators=(',', ':'),
    ).encode('utf-8')).hexdigest()


def clearable(value):
    if value.get('executing') or value.get('status') not in TERMINAL_STATUSES:
        return False
    return not any(item.get('status') in ('queued', 'processing', 'running', 'confirmed') for item in value.get('items', []))


def receipt(kind, value):
    if kind == 'work':
        return fingerprint({'status': value['status'], 'notificationId': value['notificationId']})
    return fingerprint(value)


class StatusNotifications:
    def __init__(self, store):
        self.store = store

    def project(self, kind, identity, value):
        state = self.store.get('statusNotifications') or {}
        dismissed = clearable(value) and state.get('dismissed', {}).get(kind + ':' + identity) == receipt(kind, value)
        return {**value, 'dismissed': dismissed}

    def clear(self, entries, request_id):
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 160:
            raise ValueError('清空状态需要有效的请求标识。')
        previous = self.store.get('statusNotifications') or {}
        if request_id in previous.get('requests', []):
            return
        dismissed = dict(previous.get('dismissed', {}))
        for kind, identity, value in entries:
            if clearable(value):
                dismissed[kind + ':' + identity] = receipt(kind, value)
        self.store.put('statusNotifications', {
            'dismissed': dismissed, 'requests': [*previous.get('requests', []), request_id],
        })
