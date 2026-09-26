"""Browser-safe projection and bounded Core tools; no chat in the Workspace."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents'))
from core.reading_workspace import (WorkspaceCore, WorkspaceError, validate_source_id, _identifier, _read_chunk_records,
    _read_reading_record, _chunk_presentation, _validate_parser_bundle, _needs_translation)
from core.source_library import SourceLibrary
from core.source_notes import SourceNotes
from core.discussion_application import DiscussionApplication

ACTIONS = {
    'search': ('search_source', {'query': 'string', 'limit': 'integer', 'source_id': 'string|null', 'bundle_version': 'string|null'}),
    'read_range': ('read_source_range', {'start': 'integer', 'end': 'integer', 'source_id': 'string|null', 'bundle_version': 'string|null'}),
    'topic_search': ('search_topic', {'topic_id': 'string', 'query': 'string', 'limit': 'integer'}),
    'topic_range': ('read_topic_range', {'topic_id': 'string', 'source_id': 'string', 'start': 'integer', 'end': 'integer'}),
    'topic_notes': ('topic_notes', {'topic_id': 'string'}),
}
TOOL = {
    'type': 'function',
    'name': 'focus',
    'description': 'Source evidence and Source Note candidates. source_note is accepted only in a Host-bound discussion '
                   'with explicit user save intent; Host/Core owns validation and persistence. Reading preparation and navigation use ReaderHost operations. '
                   'Arguments is a JSON object encoded as a string. Fields: ' + json.dumps({k: ACTIONS[k][1] for k in
                       ('search', 'read_range', 'topic_search', 'topic_range', 'topic_notes')}) +
                   ' source_note fields: {content:string, kind:example|conclusion|question|thought|concept, '
                   'origin:user|dialogue, evidence_role:source_claim|explanation|unresolved_question, '
                   'anchor?:{sourceId:string,bundle:string,sourceLines:[start,end],quote?:string}}. '
                   'source_claim requires an anchor matching the bound scope. Use search/read_range to verify exact lines first. '
                   'Do not include request IDs or intent fields; the Host supplies them. Only a saved tool result proves success.',
    'inputSchema': {'type': 'object', 'properties': {
        'action': {'type': 'string', 'enum': ['catalog', 'search', 'read_range', 'topic_search', 'topic_range', 'topic_notes', 'source_note']},
        'arguments': {'type': 'string'}}, 'required': ['action', 'arguments'], 'additionalProperties': False},
}


class CoreBridge:
    def __init__(self, workspace):
        self.workspace = workspace
        self.core = WorkspaceCore(workspace)

    def catalog(self):
        library = SourceLibrary(self.workspace)
        sources = [library.get(p.parent.name) for p in sorted((self.workspace / 'sources').glob('*/source.yaml'))]
        topics = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((self.workspace / 'topics').glob('*/topic.yaml'))]
        return {'sources': [{'sourceId': s['source_id'], 'title': s['title']} for s in sources],
                'topics': [{'topicId': t['topic_id'], 'title': t['title']} for t in topics]}

    def check_receipt(self, receipt):
        state = self.core.get_reading_state()
        if receipt != {'sourceId': state['source_id'], 'planId': state['plan_id'], 'chunkId': state['chunk_id']}:
            raise WorkspaceError('cursor_changed', '阅读位置已改变，请刷新后重试。')

    def tool(self, action, arguments):
        args = json.loads(arguments)
        if not isinstance(args, dict):
            raise ValueError('arguments must encode an object')
        if action == 'catalog':
            return self.catalog()
        if action not in ACTIONS:
            raise ValueError('Unsupported FOCUS operation')
        if action in ('search', 'topic_search'):
            args['limit'] = min(max(int(args.get('limit', 5)), 1), 20)
        if action in ('read_range', 'topic_range') and args['end'] - args['start'] > 500:
            raise ValueError('Read at most 501 lines per request')
        method, fields = ACTIONS[action]
        if set(args) - set(fields):
            raise ValueError('Unexpected Core arguments')
        return getattr(self.core, method)(**args)

    def window(self):
        state_path = self.workspace / 'state.json'
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding='utf-8'))
            source_id = state.get('current_source_id')
            selected = state.get('sources', {}).get(source_id, {}) if source_id else {}
            plan_id = selected.get('current_plan_id')
            if source_id and plan_id:
                provenance = self.workspace / 'sources' / source_id / 'reading' / 'plans' / plan_id / 'provenance.json'
                if provenance.is_file():
                    from core.article_blog import bundle_fingerprint
                    expected = json.loads(provenance.read_text(encoding='utf-8')).get('bundle')
                    current = bundle_fingerprint(self.workspace / 'sources' / source_id / 'parser-bundle')
                    if expected != current:
                        source = SourceLibrary(self.workspace).get(source_id)
                        return {'status': 'empty', 'source': {'sourceId': source_id,
                            'title': source['title'], 'topicId': None}, 'current': None,
                            'history': [], 'conversation': [],
                            'readingRevision': int(state.get('reading_revision', 0)),
                            'readingUnavailable': '此计划属于旧版原文，请重新准备新计划；旧引用仍可查看。'}
        try:
            result = self.core.reading_window()
        except WorkspaceError as exc:
            # Missing selection/plan is a real empty state; corrupt assets remain errors.
            if exc.error_id not in ('source_missing', 'reading_plan_missing') and not (
                    exc.error_id == 'workspace_object_missing' and not (self.workspace / 'state.json').exists()):
                raise
            return {'status': 'empty', 'source': {'sourceId': '', 'title': '选择论文，开始阅读', 'topicId': None},
                    'current': None, 'history': [], 'conversation': []}
        state = result['state']
        plan_root = self.workspace / 'sources' / result['source']['source_id'] / 'reading/plans' / state['plan_id']
        outline = [{'chunkId': c['chunk_id'], 'index': c['index'], 'sectionPath': c['section_path']}
                   for c in _read_chunk_records(plan_root / 'chunks.jsonl')]
        return {'outline': outline, 'status': 'reading' if result['current'] else 'completed',
                'readingRevision': int(json.loads((self.workspace / 'state.json').read_text(encoding='utf-8')).get('reading_revision', 0)),
                'source': {'sourceId': result['source']['source_id'], 'title': result['source']['title'],
                           'topicId': result['state']['topic_id']},
                'current': self.project_chunk(result['current']) if result['current'] else None,
                'history': [self.project_chunk(c) for c in result['history']], 'conversation': []}

    def image(self, source_id, relative):
        SourceLibrary(self.workspace).get(source_id)
        root = (self.workspace / 'sources' / source_id / 'parser-bundle').resolve()
        if not root.is_relative_to(self.workspace):
            raise ValueError('Image source is outside the Workspace')
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or target.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.gif') or not target.is_file():
            raise ValueError('Invalid image path')
        return target

    def historical_image(self, source_id, bundle_version, relative):
        SourceLibrary(self.workspace).get(source_id)
        if not isinstance(bundle_version, str) or not re.fullmatch(r'[0-9a-f]{64}', bundle_version):
            raise ValueError('Invalid Bundle version')
        root = (self.workspace / 'sources' / source_id / 'reading' / 'bundles' / bundle_version).resolve()
        if not root.is_relative_to(self.workspace) or not root.is_dir():
            raise ValueError('Original Bundle is unavailable')
        from core.article_blog import bundle_fingerprint
        if bundle_fingerprint(root) != bundle_version:
            raise ValueError('Original Bundle is unavailable')
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or target.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.gif') or not target.is_file():
            raise ValueError('Invalid historical image path')
        return target

    def historical_content(self, source_id, bundle_version):
        SourceLibrary(self.workspace).get(source_id)
        if not isinstance(bundle_version, str) or not re.fullmatch(r'[0-9a-f]{64}', bundle_version):
            raise ValueError('Invalid Bundle version')
        root = (self.workspace / 'sources' / source_id / 'reading' / 'bundles' / bundle_version).resolve()
        from core.article_blog import bundle_fingerprint
        if not root.is_relative_to(self.workspace) or not root.is_dir() or bundle_fingerprint(root) != bundle_version:
            raise ValueError('Original Bundle is unavailable')
        target = root / 'content.md'
        if not target.is_file():
            raise ValueError('Original Bundle is unavailable')
        return target

    def source_resource(self, source_id, resource):
        source = SourceLibrary(self.workspace).get(source_id)
        root = (self.workspace / 'sources' / source_id / 'parser-bundle').resolve()
        if resource == 'content':
            target = root / 'content.md'
        elif resource == 'original':
            name = {'paper_pdf': 'source.pdf', 'article_html': 'source.html',
                    'article_markdown': 'source.md'}.get(source['source_kind'])
            if name is None:
                raise ValueError('Unsupported Source original')
            target = root / name
        else:
            raise ValueError('Unknown Source resource')
        target = target.resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError('Source resource is unavailable')
        return target

    def project_chunk(self, c):
        def image_url(image):
            path = Path(image['path']).resolve()
            current = (self.workspace / 'sources' / c['source_id'] / 'parser-bundle').resolve()
            if path.is_relative_to(current):
                return '/reader/assets/' + quote(c['source_id'], safe='') + '/' + quote(str(path.relative_to(current)).replace('\\', '/'), safe='/')
            archived = (self.workspace / 'sources' / c['source_id'] / 'reading' / 'bundles').resolve()
            if path.is_relative_to(archived) and len(path.relative_to(archived).parts) > 1:
                return '/reader/historical-assets/' + quote(c['source_id'], safe='') + '/' + quote(str(path.relative_to(archived)).replace('\\', '/'), safe='/')
            raise ValueError('Image reference is outside a Source Bundle')
        return {'sourceId': c['source_id'], 'planId': c['plan_id'], 'chunkId': c['chunk_id'],
                'index': c['index'], 'total': c['total'], 'sectionPath': c['section_path'],
                'sourceLines': c['source_lines'], 'sourceMarkdown': c['source_text'], 'translation': c['translation'],
                'images': [{'src': image_url(i),
                            'caption': i['caption']} for i in c['images']],
                'relevantGlossary': c['relevant_glossary'], 'presentationStatus': c['status'].replace('_', '-')}

    def reference(self, receipt):
        source = validate_source_id(receipt['sourceId'])
        plan, chunk_id = (_identifier(receipt[k], k) for k in ('planId', 'chunkId'))
        SourceLibrary(self.workspace).get(source)
        source_root = self.workspace / 'sources' / source
        root = source_root / 'reading' / 'plans' / plan
        chunks = _read_chunk_records(root / 'chunks.jsonl')
        chunk = next((c for c in chunks if c['chunk_id'] == chunk_id), None)
        if chunk is None:
            raise ValueError('引用段落不存在')
        provenance_path = root / 'provenance.json'
        current = source_root / 'parser-bundle'
        from core.article_blog import bundle_fingerprint
        if provenance_path.is_file():
            expected_bundle = json.loads(provenance_path.read_text(encoding='utf-8')).get('bundle')
            bundle = current if expected_bundle == bundle_fingerprint(current) else source_root / 'reading' / 'bundles' / str(expected_bundle)
            if not bundle.is_dir() or bundle_fingerprint(bundle) != expected_bundle:
                raise ValueError('原版本引用不可定位')
        else:
            raise ValueError('原版本引用不可定位')
        metadata = _validate_parser_bundle(bundle)
        record = _read_reading_record(root / 'records' / f'{chunk_id}.json', chunk_id)
        item = _chunk_presentation(bundle, root, source_id=source, plan_id=plan,
                                  chunk=chunk, reading_record=record, total=len(chunks))
        item['status'] = 'source_ready' if not _needs_translation(metadata, chunk) else 'presented' if record['translation'] else 'translation_required'
        projected = self.project_chunk(item)
        projected['bundleVersion'] = expected_bundle
        return projected
