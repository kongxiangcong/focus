"""Additive, version-bound Chinese structure and guide; never writes the cursor."""
import re
import uuid
from .reading_structure import validate_structure, read_structure
from .reading_workspace import _read_document, _write_document, _read_chunk_records, WorkspaceError

VERSION = 'article-overview-v1'


def validate_chinese_structure(value, chunks):
    value = validate_structure(value, chunks)
    for node in value['nodes']:
        if not re.search(r'[\u3400-\u9fff]', node['title']):
            raise WorkspaceError('overview_invalid', '骨架标题须为中文，专名可保留；不能整句使用英文标题。')
    return value


def validate_guide(value):
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceError('overview_invalid', '导读正文不能为空。')
    count = len(re.sub(r'\s', '', value))
    if count > 500 or not re.search(r'[\u3400-\u9fff]', value):
        raise WorkspaceError('overview_invalid', '导读须为中文短段落，正文不超过 500 字；请重新组织，不要截断。')
    return value.strip()


class ArticleOverview:
    def __init__(self, workspace, app):
        self.workspace = workspace
        self.app = app
        self.core = app.core
        self.lease = app.core._workspace_lease

    def target(self, source_id):
        if self.lease:
            self.lease.require_current()
        self.core._root(source_id)
        state = _read_document(self.core.workspace / 'state.json')
        selected = state['sources'][source_id].get('current_plan_id')
        run = self.core.status(source_id)
        # A selected plan always wins over an unactivated replacement candidate.
        plan = selected or (run or {}).get('plan_id')
        if not plan:
            return None
        root = self.core._root(source_id) / 'reading' / 'plans' / plan
        chunks = _read_chunk_records(root / 'chunks.jsonl')
        from .reading_application import _digest
        bundle = self.core._bundle_version(source_id)
        provenance = root / 'provenance.json'
        if provenance.exists() and _read_document(provenance).get('bundle') != bundle:
            raise WorkspaceError('overview_stale_plan', '原文已更新，请先准备并启用新版阅读计划。')
        return root, chunks, {'sourceId': source_id, 'planId': plan, 'bundle': bundle,
                              'chunksRevision': _digest(chunks), 'version': VERSION}

    def status(self, source_id):
        title = self.core._root(source_id) / 'source.yaml'
        result = {'sourceId': source_id, 'title': _read_document(title)['title'], 'status': 'missing'}
        try:
            target = self.target(source_id)
        except WorkspaceError as exc:
            return {**result, 'status': 'stale', 'error': str(exc)}
        if target is None:
            return result
        root, chunks, identity = target
        result.update(identity)
        path = root / 'overview.json'
        if not path.exists():
            return result
        try:
            saved = _read_document(path)
        except WorkspaceError:
            return {**result, 'status': 'failed', 'error': '导读资产无法读取，请重试。'}
        if any(saved.get(k) != v for k, v in identity.items()):
            return {**result, 'status': 'stale', 'error': '原文或阅读计划已变化，请重新准备文章结构。'}
        if saved.get('status') != 'ready':
            return {**result, 'status': saved.get('status', 'failed'), 'error': saved.get('error')}
        try:
            tree = validate_chinese_structure(saved['structure'], chunks)
            guide = validate_guide(saved['guide'])
        except (ValueError, KeyError, WorkspaceError):
            return {**result, 'status': 'failed', 'error': '导读资产校验失败，请重试。'}
        return {**result, 'status': 'ready', 'revision': saved.get('revision'), 'guide': guide,
                'structure': [{'id': n['id'], 'parentId': n['parent_id'], 'title': n['title'],
                               'description': n['description'], 'sourceLines': n['source_lines']} for n in tree['nodes']],
                'chunkNodes': tree['chunk_nodes']}

    def generate(self, source_id, *, stopped=lambda: False, on_progress=lambda: None):
        if self.status(source_id)['status'] == 'ready':
            return
        root, chunks, identity = self.target(source_id)
        path = root / 'overview.json'
        attempt = uuid.uuid4().hex
        run = {**identity, 'revision': attempt, 'status': 'running'}
        if self.lease:
            self.lease.require_current()
        _write_document(path, run)
        on_progress()
        def guard():
            target = self.target(source_id)
            if stopped() or target is None or target[2] != identity or _read_document(path).get('revision') != attempt:
                raise WorkspaceError('overview_changed', '准备已停止或原文版本已变化，请重试。')
        try:
            ranges = self.app._ranges(source_id)
            try:
                tree = validate_chinese_structure(read_structure(root, chunks), chunks)
            except WorkspaceError:
                tree = None
            feedback = None
            for _ in range(0 if tree is not None else 3):
                guard()
                candidate = self.app.runtime.overview_structure(source_id=source_id, ranges=ranges,
                                                               chunks=chunks, feedback=feedback)
                try:
                    tree = validate_chinese_structure(candidate, chunks)
                    break
                except WorkspaceError as exc:
                    feedback = str(exc)
            if tree is None:
                raise WorkspaceError('overview_invalid', feedback)
            guide = None
            feedback = None
            for _ in range(3):
                guard()
                candidate = self.app.runtime.overview_guide(source_id=source_id, ranges=ranges,
                                                          structure=tree, feedback=feedback)
                try:
                    guide = validate_guide(candidate)
                    break
                except WorkspaceError as exc:
                    feedback = str(exc)
            if guide is None:
                raise WorkspaceError('overview_invalid', feedback)
            guard()
            _write_document(path, {**run, 'status': 'ready', 'structure': tree, 'guide': guide,
                                   'runtime': getattr(self.app.runtime, 'provenance', None)})
        except Exception as exc:
            if path.exists() and _read_document(path).get('revision') == attempt:
                _write_document(path, {**run, 'status': 'failed', 'error': str(exc)})
            raise
        finally:
            on_progress()


from .workspace_lifecycle import guard_workspace_class
ArticleOverview = guard_workspace_class(ArticleOverview)
