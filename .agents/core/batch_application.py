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
        self.stop_flags = {}
        with self.lock:
            batches = self._read()
            for batch in batches.values():
                batch.setdefault('workIds', list(batch['itemIds']))
                batch.setdefault('excluded', [])
                batch.setdefault('requests', {})
                batch.setdefault('executionId', batch['requestId'])
                batch.setdefault('resuming', False)
                batch.setdefault('resubmission', None)
                if batch['status'] == 'running':
                    batch['status'] = 'paused'
                    batch['error'] = {'error_id': 'batch_interrupted', 'message': '处理已中断，请明确继续。'}
            if batches:
                _write_document(self.path, batches)

    def _read(self):
        return _read_document(self.path, {})

    def create(self, item_ids, *, request_id, generate_blog=True):
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 100:
            raise WorkspaceError('request_id_invalid', 'A stable batch request identity is required')
        if not isinstance(item_ids, list) or not item_ids or not all(isinstance(i, str) for i in item_ids):
            raise WorkspaceError('batch_items_invalid', 'Select one or more Inbox items')
        item_ids = list(dict.fromkeys(item_ids))
        with self.lock:
            batches = self._read()
            for batch in batches.values():
                if batch['requestId'] == request_id:
                    if batch['itemIds'] != item_ids or batch.get('generateBlog', True) != generate_blog:
                        raise WorkspaceError('request_conflict', 'The confirmed batch is immutable')
                    return self._view(batch)
                if set(batch['itemIds']) & set(item_ids) and batch['status'] in ('confirmed', 'running', 'paused'):
                    if batch['itemIds'] == item_ids:
                        return self._view(batch)
                    raise WorkspaceError('batch_item_busy', '材料已有未完成批次，请返回原批次。')
            items = [self.processing.ingestion.get(i) for i in item_ids]
            if any(i.get('deleted') for i in items):
                raise WorkspaceError('source_deleted', '来源已删除，旧任务不能恢复。')
            if any(i['item_id'] in self.processing.running or i['status'] == 'processing' or
                   (i.get('source_id') and self.processing.blog.status(i['source_id']).get('runStatus') == 'running')
                   for i in items):
                raise WorkspaceError('batch_item_busy', '材料正在处理中，请等待原任务结束。')
            topics = {t['topicId']: t['title'].strip().casefold()
                      for t in SourceLibrary(self.processing.ingestion.workspace).topics()}
            targets = {topics.get(i.get('topic_id')) if i.get('topic_id')
                       else (i.get('topic_title') or '').strip().casefold() for i in items}
            if len(targets) != 1:
                raise WorkspaceError('batch_topic_invalid', '所有材料必须属于同一个有效专题。')
            confirmed = [self.processing.confirm(i, request_id=request_id + ':' + str(n), generate_blog=generate_blog)
                         for n, i in enumerate(item_ids)]
            batch_id = uuid.uuid4().hex
            batch = {'batchId': batch_id, 'requestId': request_id, 'itemIds': item_ids,
                     'topicId': confirmed[0]['topic_id'], 'generateBlog': generate_blog, 'status': 'confirmed',
                     'cursor': 0, 'activeItemId': None, 'error': None, 'itemErrors': {},
                     'workIds': item_ids, 'excluded': [], 'requests': {}, 'executionId': request_id, 'resuming': False, 'resubmission': None}
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
            if item.get('deleted'):
                status = 'deleted'
            elif item_id in batch['excluded']:
                status = 'cancelled'
            elif item_id == batch['activeItemId'] and batch['status'] == 'running':
                status = 'processing'
            elif item['status'] in ('confirmed', 'awaiting_confirmation') and not error:
                status = 'queued'
            elif item['status'] == 'cancelled' or (blog or {}).get('runStatus') == 'cancelled':
                status = 'cancelled'
            elif item['status'] == 'completed' and ((blog or {}).get('runStatus') == 'completed' or not self.processing.wants_blog(item_id)):
                status = 'completed'
            else:
                status = 'partial' if item.get('source_id') else 'failed'
            items.append({'itemId': item_id, 'fileName': item['file_name'], 'sourceId': item.get('source_id'),
                          'status': status, 'ingestionStatus': item['status'], 'blog': blog, 'error': error, 'remoteReference': item.get('remote_reference', False),
                          'resubmitRisk': item.get('resubmit_risk'), 'parserBackend': item.get('parser_backend'),
                          'selectionReason': item.get('selection_reason'), 'parserProgress': item.get('parser_progress')})
        return {k: batch[k] for k in ('batchId', 'topicId', 'status', 'error')} | {
            'items': items, 'executing': batch['batchId'] in self.running}

    def control(self, batch_id, action, *, request_id, item_id=None, risk_choice_id=None, cancel=None):
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 100:
            raise WorkspaceError('request_id_invalid', 'A stable control request is required')
        with self.lock:
            batches = self._read()
            if batch_id not in batches:
                raise WorkspaceError('batch_missing', '批次不存在。')
            batch = batches[batch_id]
            binding = [action, item_id, risk_choice_id]
            if request_id in batch['requests']:
                if batch['requests'][request_id] != binding:
                    raise WorkspaceError('request_conflict', 'Request identity was used by a different action')
                return self._view(batch)
            if action in ('cancel-item', 'remove-item', 'retry-item', 'resubmit-item') and item_id not in batch['itemIds']:
                raise WorkspaceError('batch_item_missing', '材料不属于此批次。')
            current = {i['itemId']: i for i in self._view(batch)['items']}
            if item_id and current[item_id]['status'] == 'deleted':
                raise WorkspaceError('source_deleted', '来源已删除，旧任务不能恢复。')
            if action == 'stop':
                batch['status'] = 'paused'
                batch['error'] = None
            elif action in ('cancel-item', 'remove-item'):
                if action == 'remove-item' and current[item_id]['status'] != 'queued':
                    raise WorkspaceError('batch_item_not_queued', '只能移除尚未执行的排队项。')
                if current[item_id]['status'] == 'completed':
                    raise WorkspaceError('batch_item_complete', '此材料已完成。')
                if item_id not in batch['excluded']:
                    batch['excluded'].append(item_id)
            elif action in ('continue', 'retry-item', 'resubmit-item'):
                if batch_id in self.running or batch['status'] == 'running':
                    raise WorkspaceError('batch_busy', '请等待当前处理停止。')
                if action in ('retry-item', 'resubmit-item'):
                    batch['excluded'] = [i for i in batch['excluded'] if i != item_id]
                    work = [item_id] if current[item_id]['status'] != 'completed' else []
                else:
                    work = [i for i in batch['itemIds'] if i not in batch['excluded'] and current[i]['status'] not in ('completed', 'deleted')]
                if action == 'resubmit-item':
                    self.processing.ingestion.validate_resubmit(item_id, request_id=request_id + ':0', risk_choice_id=risk_choice_id)
                batch['resubmission'] = {'itemId': item_id, 'riskChoiceId': risk_choice_id} if action == 'resubmit-item' else None
                batch.update(workIds=work, cursor=0, activeItemId=None, status='confirmed',
                             error=None, executionId=request_id, resuming=True)
            else:
                raise WorkspaceError('batch_action_invalid', '未知批次操作。')
            batch['requests'][request_id] = binding
            _write_document(self.path, batches)
            # Persist scheduling revocation before revoking Core attempts.
            target = batch['activeItemId'] if action == 'stop' else item_id
            if target and action in ('stop', 'cancel-item', 'remove-item'):
                flag = self.stop_flags.get((batch_id, target))
                if flag:
                    flag.set()
                if cancel:
                    cancel(target)
            return self._view(batch)

    def _submit_blog(self, batch_id, item_id, submit_blog, source_id, **kwargs):
        with self.lock:
            batch = self._read()[batch_id]
            if batch['status'] != 'running' or item_id in batch['excluded']:
                return
            flag = self.stop_flags.get((batch_id, item_id))
            wait = submit_blog(source_id, start_allowed=lambda: flag is not None and not flag.is_set(), **kwargs)
        if wait:
            wait()

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
                    if batch['status'] != 'running':
                        return
                    if should_stop():
                        batch['status'] = 'paused'
                        batch['error'] = {'error_id': 'batch_interrupted', 'message': '处理已中断，请明确继续。'}
                        _write_document(self.path, batches)
                        return
                    if batch['cursor'] == len(batch['workIds']):
                        batch['activeItemId'] = None
                        batch['status'] = 'completed' if all(i['status'] == 'completed' for i in self._view(batch)['items']) else 'partial'
                        _write_document(self.path, batches)
                        return
                    item_id = batch['workIds'][batch['cursor']]
                    if item_id in batch['excluded']:
                        batch['cursor'] += 1
                        _write_document(self.path, batches)
                        continue
                    batch['activeItemId'] = item_id
                    batch['itemErrors'].pop(item_id, None)
                    preparation_error = None
                    flag = threading.Event()
                    self.stop_flags[(batch_id, item_id)] = flag
                    resubmission = batch.get('resubmission')
                    risk = resubmission['riskChoiceId'] if resubmission and resubmission['itemId'] == item_id else None
                    execution_id = batch['executionId'] + ':' + str(batch['cursor'])
                    if batch['resuming'] and not risk:
                        try:
                            self.processing.prepare_resume(item_id, request_id=batch['executionId'] + ':' + str(batch['cursor']))
                        except WorkspaceError as exc:
                            preparation_error = exc
                    _write_document(self.path, batches)
                failure = None
                try:
                    if preparation_error:
                        raise preparation_error
                    self.processing.process(item_id, request_id=execution_id, risk_choice_id=risk,
                        start_allowed=lambda: not flag.is_set(), submit_blog=lambda source_id, **kwargs:
                        self._submit_blog(batch_id, item_id, submit_blog, source_id, **kwargs))
                except Exception as exc:
                    failure = {'error_id': getattr(exc, 'error_id', 'processing_failed'),
                               'message': '处理未完成，请检查服务配置后重试。'}
                with self.lock:
                    batches = self._read()
                    batch = batches[batch_id]
                    if failure:
                        batch['itemErrors'][item_id] = failure
                    batch['cursor'] += 1
                    self.stop_flags.pop((batch_id, item_id), None)
                    batch['activeItemId'] = None
                    current = next(i for i in self._view(batch)['items'] if i['itemId'] == item_id)
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
