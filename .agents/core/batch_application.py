"""A frozen, serial list of Inbox items using the existing processing workflow."""
from __future__ import annotations

import threading
import uuid

from .reading_workspace import WorkspaceError, _read_document, _write_document
from .source_library import SourceLibrary


SERVICE_ERRORS = frozenset({
    'authentication_required', 'authentication_failed', 'service_unavailable',
    'quota_exceeded', 'rate_limit_exceeded',
})


class BatchApplication:
    def __init__(self, processing):
        self.processing = processing
        self.path = processing.ingestion.workspace / 'ingestion' / 'batches.json'
        self.lock = threading.RLock()
        self.running = set()
        with self.lock:
            batches = self._read()
            for batch in batches.values():
                if batch['status'] == 'running':
                    batch['status'] = 'paused'
                    batch['error'] = {'error_id': 'batch_interrupted', 'message': '处理已中断，请明确继续。'}
            if batches:
                _write_document(self.path, batches)

    def _read(self):
        return _read_document(self.path, {})

    def create(self, item_ids, *, request_id):
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 100:
            raise WorkspaceError('request_id_invalid', 'A stable batch request identity is required')
        if not isinstance(item_ids, list) or not item_ids or not all(isinstance(i, str) for i in item_ids):
            raise WorkspaceError('batch_items_invalid', 'Select one or more Inbox items')
        item_ids = list(dict.fromkeys(item_ids))
        with self.lock:
            batches = self._read()
            for batch in batches.values():
                if batch['requestId'] == request_id:
                    if batch['itemIds'] != item_ids:
                        raise WorkspaceError('request_conflict', 'The confirmed batch is immutable')
                    return self._view(batch)
                if set(batch['itemIds']) & set(item_ids) and batch['status'] in ('confirmed', 'running', 'paused'):
                    if batch['itemIds'] == item_ids:
                        return self._view(batch)
                    raise WorkspaceError('batch_item_busy', '材料已有未完成批次，请返回原批次。')
            items = [self.processing.ingestion.get(i) for i in item_ids]
            if any(i['item_id'] in self.processing.running or i['status'] == 'processing' or
                   (i.get('source_id') and self.processing.blog.status(i['source_id']).get('runStatus') == 'running')
                   for i in items):
                raise WorkspaceError('batch_item_busy', '材料正在处理中，请等待原任务结束。')
            topics = {t['topicId']: t['title'].strip().casefold()
                      for t in SourceLibrary(self.processing.ingestion.workspace).topics()}
            targets = {topics.get(i.get('topic_id')) if i.get('topic_id')
                       else (i.get('topic_title') or '').strip().casefold() for i in items}
            if len(targets) != 1 or not next(iter(targets)):
                raise WorkspaceError('batch_topic_invalid', '所有材料必须属于同一个有效专题。')
            confirmed = [self.processing.confirm(i, request_id=request_id + ':' + str(n))
                         for n, i in enumerate(item_ids)]
            batch_id = uuid.uuid4().hex
            batch = {'batchId': batch_id, 'requestId': request_id, 'itemIds': item_ids,
                     'topicId': confirmed[0]['topic_id'], 'status': 'confirmed',
                     'cursor': 0, 'activeItemId': None, 'error': None, 'itemErrors': {}}
            batches[batch_id] = batch
            _write_document(self.path, batches)
            return self._view(batch)

    def list(self):
        with self.lock:
            return [self._view(b) for b in self._read().values()]

    def owns(self, item_id):
        with self.lock:
            return any(item_id in b['itemIds'] and b['status'] in ('confirmed', 'running', 'paused')
                       for b in self._read().values())

    def _view(self, batch):
        items = []
        for index, item_id in enumerate(batch['itemIds']):
            item = self.processing.ingestion.get(item_id)
            blog = self.processing.blog.status(item['source_id']) if item.get('source_id') else None
            error = item.get('topic_error') or item.get('error') or (blog or {}).get('error') or batch['itemErrors'].get(item_id)
            if item_id == batch['activeItemId'] and batch['status'] == 'running':
                status = 'processing'
            elif index >= batch['cursor']:
                status = 'queued'
            elif item['status'] == 'cancelled' or (blog or {}).get('runStatus') == 'cancelled':
                status = 'cancelled'
            elif item['status'] == 'completed' and (blog or {}).get('runStatus') == 'completed':
                status = 'completed'
            else:
                status = 'partial' if item.get('source_id') else 'failed'
            items.append({'itemId': item_id, 'fileName': item['file_name'], 'sourceId': item.get('source_id'),
                          'status': status, 'ingestionStatus': item['status'], 'blog': blog, 'error': error})
        return {k: batch[k] for k in ('batchId', 'topicId', 'status', 'error')} | {'items': items}

    def run(self, batch_id, *, submit_blog, should_stop=lambda: False):
        with self.lock:
            batches = self._read()
            batch = batches[batch_id]
            if batch_id in self.running or batch['status'] != 'confirmed':
                return
            self.running.add(batch_id)
            batch['status'] = 'running'
            _write_document(self.path, batches)
        try:
            while True:
                with self.lock:
                    batches = self._read()
                    batch = batches[batch_id]
                    if should_stop():
                        batch['status'] = 'paused'
                        batch['error'] = {'error_id': 'batch_interrupted', 'message': '处理已中断，请明确继续。'}
                        _write_document(self.path, batches)
                        return
                    if batch['cursor'] == len(batch['itemIds']):
                        batch['activeItemId'] = None
                        batch['status'] = 'completed' if all(i['status'] == 'completed' for i in self._view(batch)['items']) else 'partial'
                        _write_document(self.path, batches)
                        return
                    item_id = batch['itemIds'][batch['cursor']]
                    batch['activeItemId'] = item_id
                    _write_document(self.path, batches)
                failure = None
                try:
                    self.processing.process(item_id, submit_blog=submit_blog)
                except Exception as exc:
                    failure = {'error_id': getattr(exc, 'error_id', 'processing_failed'),
                               'message': '处理未完成，请检查服务配置后重试。'}
                with self.lock:
                    batches = self._read()
                    batch = batches[batch_id]
                    if failure:
                        batch['itemErrors'][item_id] = failure
                    batch['cursor'] += 1
                    batch['activeItemId'] = None
                    current = self._view(batch)['items'][batch['cursor'] - 1]
                    error = current['error']
                    if error and error['error_id'] in SERVICE_ERRORS:
                        batch['status'] = 'paused'
                        batch['error'] = error
                    _write_document(self.path, batches)
                    if batch['status'] == 'paused':
                        return
        finally:
            with self.lock:
                self.running.discard(batch_id)
