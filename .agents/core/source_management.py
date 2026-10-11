"""Shared Source detail validation and forward recovery."""
import re
from .source_library import SourceLibrary


class SourceManagement:
    def __init__(self, workspace, store):
        self.workspace, self.store = workspace, store

    def recover_edits(self):
        operations = self.store.get('sourceEdits') or {}
        library = SourceLibrary(self.workspace)
        changed = False
        for operation in operations.values():
            if operation['status'] != 'pending':
                continue
            source_id = operation['sourceId']
            library.rename_source(source_id, operation['title'], display_title=operation.get('displayTitle'))
            for topic in library.topics():
                wanted = topic['topicId'] in operation['topicIds']
                attached = source_id in topic['sourceIds']
                if wanted and not attached:
                    library.attach(source_id, existing_topic_id=topic['topicId'])
                elif attached and not wanted:
                    library.detach(topic['topicId'], source_id)
            operation['status'] = 'completed'
            changed = True
        if changed:
            self.store.put('sourceEdits', operations)

    def save_details(self, source_id, payload):
        request_id = payload.get('requestId')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9-]{8,80}', request_id):
            raise ValueError('保存需要唯一请求身份。')
        title, ids = payload.get('title'), payload.get('topicIds')
        display_title = payload.get('displayTitle', title)
        library = SourceLibrary(self.workspace)
        library.get(source_id)
        if not isinstance(title, str) or not title.strip() or len(title) > 1000:
            raise ValueError('来源标题无效。')
        if not isinstance(display_title, str) or not display_title.strip() or len(display_title.strip()) > 1000:
            raise ValueError('知识库显示标题无效。')
        known = {t['topicId'] for t in library.topics()}
        if not isinstance(ids, list) or any(i not in known for i in ids):
            raise ValueError('所属专题已改变，请刷新后保存。')
        operations = self.store.get('sourceEdits') or {}
        binding = {'sourceId': source_id, 'title': title.strip(), 'displayTitle': display_title.strip(), 'topicIds': sorted(set(ids))}
        prior = operations.get(request_id)
        if prior and any(
            prior.get(k, prior.get('title') if k == 'displayTitle' else None) != v
            for k, v in binding.items()
        ):
            raise ValueError('请求身份已用于另一项修改。')
        operations.setdefault(request_id, {**binding, 'status': 'pending'})
        self.store.put('sourceEdits', operations)
        self.recover_edits()
        return self.store.get('sourceEdits')[request_id]


from .workspace_lifecycle import guard_workspace_class
SourceManagement = guard_workspace_class(SourceManagement)
