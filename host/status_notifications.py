"""Persist dismissal receipts independently of business attempts and assets."""
import hashlib
import json
import re
import uuid


def fingerprint(value):
    def stable(item):
        if isinstance(item, dict):
            return {key: stable(child) for key, child in item.items() if key != 'dismissed'}
        if isinstance(item, list):
            return [stable(child) for child in item]
        return item
    return hashlib.sha256(json.dumps(
        stable(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'),
    ).encode('utf-8')).hexdigest()


class StatusNotifications:
    def __init__(self, store):
        self.store = store
        self.state = store.get('statusNotifications') or {}
        self.dismissed = self.state.get('dismissed', {})
        self.restored = self.state.get('restored', {})
        self.available = {}

    def project(self, kind, identity, value, *, eligible, attempt, original=None, legacy=None, offer=False):
        key = kind + ':' + identity
        dismissed = False
        if eligible:
            token = fingerprint([key, attempt, value['status'], self.restored.get(original)])
            saved = self.dismissed.get(key)
            dismissed = saved == token or (legacy is not None and self.dismissed.get(legacy[0]) == legacy[1])
            if offer and not dismissed:
                self.available[token] = key
        return {**value, 'dismissed': dismissed}

    def restore_original(self, item_id):
        """Invalidate earlier clear requests for the matching original."""
        dismissed = {key: token for key, token in self.dismissed.items()
                     if key not in ('inbox:' + item_id, 'batch-item:' + item_id, 'work:ingestion:' + item_id)}
        self._save(dismissed, {**self.restored, item_id: uuid.uuid4().hex})

    def clear(self, request_id, tokens):
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 160:
            raise ValueError('清空状态需要有效的请求标识。')
        if not isinstance(tokens, list) or any(not isinstance(t, str) or not re.fullmatch(r'[a-f0-9]{64}', t) for t in tokens):
            raise ValueError('清空状态需要任务快照中的可清空提示标识。')
        dismissed = {**self.dismissed, **{self.available[token]: token for token in tokens if token in self.available}}
        if dismissed != self.dismissed or 'requests' in self.state:
            self._save(dismissed, self.restored)
        return dismissed != self.dismissed

    def _save(self, dismissed, restored):
        self.store.put('statusNotifications', {'dismissed': dismissed, 'restored': restored})
