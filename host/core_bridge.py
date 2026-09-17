"""Browser-safe projection and bounded Core tools; no chat in the Workspace."""
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents'))
from core.reading_workspace import (WorkspaceCore, WorkspaceError, _identifier, _read_chunk_records,
    _read_reading_record, _chunk_presentation, _validate_parser_bundle)
from core.source_library import SourceLibrary

ACTIONS = {
    'state': ('get_reading_state', {}),
    'current': ('get_current_chunk', {}),
    'map': ('map_reading_plan', {'source_id': 'string', 'draft': 'object|null', 'scope': 'string|null'}),
    'switch': ('switch_source', {'source_id': 'string'}),
    'topic': ('select_topic', {'topic_id': 'string'}),
    'search': ('search_source', {'query': 'string', 'limit': 'integer'}),
    'read_range': ('read_source_range', {'start': 'integer', 'end': 'integer', 'source_id': 'string|null'}),
    'append_note': ('append_note', {'expected_plan_id': 'string', 'expected_chunk_id': 'string',
                                   'kind': 'thought|emphasis|question|clarification', 'origin': 'user|dialogue',
                                   'content': 'string', 'anchor': 'object|null'}),
    'list_notes': ('list_notes', {'plan_id': 'string', 'chunk_id': 'string', 'limit': 'integer'}),
    'translate': ('retranslate_current_chunk', {'expected_plan_id': 'string', 'expected_chunk_id': 'string', 'translation': 'string'}),
    'continue': ('continue_reading', {'expected_plan_id': 'string', 'expected_chunk_id': 'string', 'pending_notes': 'array'}),
    'topic_search': ('search_topic', {'topic_id': 'string', 'query': 'string', 'limit': 'integer'}),
    'topic_range': ('read_topic_range', {'topic_id': 'string', 'source_id': 'string', 'start': 'integer', 'end': 'integer'}),
    'topic_notes': ('topic_notes', {'topic_id': 'string'}),
    'synthesize_topic': ('synthesize_topic', {'topic_id': 'string', 'draft': 'object'}),
}
TOOL = {
    'type': 'function',
    'name': 'focus',
    'description': 'FOCUS Core is the only authority for reading assets. Arguments is a JSON object encoded as a string. '
                   'catalog lists sources/topics. Other action argument fields: ' + json.dumps({k: v[1] for k, v in ACTIONS.items()}) +
                   '. map: call draft=null first; only supply a draft if reading_plan_input_missing. '
                   'continue requires the current source_id too; the Host requests explicit user confirmation if not already authorized. '
                   'Never edit Cursor, plans or records with shell/patch. Use parser skills for new sources.',
    'inputSchema': {'type': 'object', 'properties': {
        'action': {'type': 'string', 'enum': ['catalog', *ACTIONS]},
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
        if action in ('search', 'topic_search', 'list_notes'):
            args['limit'] = min(max(int(args.get('limit', 5)), 1), 20)
        if action in ('read_range', 'topic_range') and args['end'] - args['start'] > 500:
            raise ValueError('Read at most 501 lines per request')
        if action == 'continue':
            self.check_receipt({'sourceId': args.pop('source_id'), 'planId': args['expected_plan_id'], 'chunkId': args['expected_chunk_id']})
        method, fields = ACTIONS[action]
        if set(args) - set(fields):
            raise ValueError('Unexpected Core arguments')
        if action == 'map':
            args.setdefault('draft', None)
        return getattr(self.core, method)(**args)

    def window(self):
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

    def project_chunk(self, c):
        return {'sourceId': c['source_id'], 'planId': c['plan_id'], 'chunkId': c['chunk_id'],
                'index': c['index'], 'total': c['total'], 'sectionPath': c['section_path'],
                'sourceLines': c['source_lines'], 'sourceMarkdown': c['source_text'], 'translation': c['translation'],
                'images': [{'src': '/reader/assets/' + quote(c['source_id'], safe='') + '/' +
                            quote(str(Path(i['path']).relative_to(self.workspace / 'sources' / c['source_id'] / 'parser-bundle')).replace('\\', '/'), safe='/'),
                            'caption': i['caption']} for i in c['images']],
                'relevantGlossary': c['relevant_glossary'], 'presentationStatus': c['status'].replace('_', '-')}

    def reference(self, receipt):
        source, plan, chunk_id = (_identifier(receipt[k], k) for k in ('sourceId', 'planId', 'chunkId'))
        SourceLibrary(self.workspace).get(source)
        bundle = self.workspace / 'sources' / source / 'parser-bundle'
        root = bundle.parent / 'reading' / 'plans' / plan
        metadata = _validate_parser_bundle(bundle)
        chunks = _read_chunk_records(root / 'chunks.jsonl')
        chunk = next((c for c in chunks if c['chunk_id'] == chunk_id), None)
        if chunk is None:
            raise ValueError('引用段落不存在')
        record = _read_reading_record(root / 'records' / f'{chunk_id}.json', chunk_id)
        item = _chunk_presentation(bundle, root, source_id=source, plan_id=plan,
                                  chunk=chunk, reading_record=record, total=len(chunks))
        item['status'] = 'source_ready' if metadata['language'] == 'zh' else 'presented' if record['translation'] else 'translation_required'
        return self.project_chunk(item)
