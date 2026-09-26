"""Confirmed ingestion and blog scope shared by hosts, backed by Core assets."""
from __future__ import annotations

import threading

from .ingestion import _component_config
from .reading_workspace import WorkspaceError, _read_document, _write_document
from .source_library import SourceLibrary


class ProcessingApplication:
    def __init__(self, ingestion, blog):
        self.ingestion = ingestion
        self.blog = blog
        self.path = ingestion.workspace / 'ingestion' / 'processing.json'
        self.lock = threading.RLock()
        self.running = set()

    def authorized(self, item_id):
        return item_id in _read_document(self.path, {})

    def confirm(self, item_id, *, request_id):
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 160:
            raise WorkspaceError('request_id_invalid', 'A stable request identity is required')
        with self.lock:
            scopes = _read_document(self.path, {})
            item = self.ingestion.get(item_id)
            if any(key != item_id and value['request_id'] == request_id for key, value in scopes.items()):
                raise WorkspaceError('request_conflict', 'Request identity belongs to another original')
            existing = scopes.get(item_id)
            if existing:
                if existing['fingerprint'] != item['fingerprint'] or existing['topic_id'] != item['topic_id']:
                    raise WorkspaceError('confirmation_required', 'The confirmed original or Topic has changed')
                return item
            library = SourceLibrary(self.ingestion.workspace)
            if item.get('topic_id'):
                topic = next((entry for entry in library.topics() if entry['topicId'] == item['topic_id']), None)
                if topic is None:
                    raise WorkspaceError('topic_missing', 'Select an existing Topic')
            else:
                topic = library.create_topic(item.get('topic_title'))
            self.ingestion.update_staged(item_id, topic_id=topic['topicId'], topic_title=None)
            item = self.ingestion.confirm(item_id, services=item['services'],
                                          purpose='register source and generate blog', scope='ingestion')
            scopes[item_id] = {
                'request_id': request_id, 'fingerprint': item['fingerprint'],
                'topic_id': topic['topicId'], 'services': item['services'],
                'blog_config': _component_config(self.blog.runtime),
                'scope': ['ingestion', 'reading_blog', 'conditional_value_analysis', 'html'],
            }
            _write_document(self.path, scopes)
            return item

    def process(self, item_id, *, submit_blog=None):
        with self.lock:
            scope = _read_document(self.path, {}).get(item_id)
            if not scope:
                raise WorkspaceError('confirmation_required', 'Confirm processing first')
            if item_id in self.running:
                return self.ingestion.get(item_id)
            item = self.ingestion.get(item_id)
            if scope['fingerprint'] != item['fingerprint'] or scope['blog_config'] != _component_config(self.blog.runtime):
                raise WorkspaceError('confirmation_required', 'The confirmed input or model service has changed')
            self.running.add(item_id)
        try:
            if item['status'] != 'completed':
                item = self.ingestion.process(item_id, request_id=scope['request_id'])
            if item['status'] == 'completed':
                (submit_blog or self.blog.generate)(item['source_id'], request_id=scope['request_id'] + ':blog',
                                                    authorized_by='ingestion_confirmation')
            return item
        finally:
            with self.lock:
                self.running.discard(item_id)
