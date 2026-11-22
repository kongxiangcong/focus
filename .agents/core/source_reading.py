"""Source-level reading assets and exact evidence; independent of Plan/Cursor."""
from bisect import bisect_right
import hashlib
import re
import time
from pathlib import Path
from .source_notes import SourceNotes, _LOCK
from .source_library import SourceLibrary
from .reading_workspace import WorkspaceError, _read_document, _write_document
from .article_overview import validate_guide
from .source_blocks import SourceBlocks, source_lines




class SourceReading:
    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.notes = SourceNotes(workspace)

    def document(self, source_id):
        with _LOCK:
            version = self.notes.bundle_version(source_id)
            source = SourceLibrary(self.workspace).get(source_id)
            markdown = (self.notes._root(source_id) / 'parser-bundle' / 'content.md').read_text(encoding='utf-8', errors='replace')
            if self.notes.bundle_version(source_id) != version:
                raise WorkspaceError('source_bundle_changed', '原文版本已改变，请重新打开。')
            return {'sourceId': source_id, 'bundleVersion': version, 'title': source['title'],
                    'markdown': markdown, 'lineCount': len(source_lines(markdown)), 'generation': self.notes.generation(source_id)}

    def opening(self, source_id):
        doc = {'bundleVersion': self.notes.bundle_version(source_id)}
        path = self.notes._root(source_id) / 'reading' / 'opening-v2.json'
        saved = _read_document(path) if path.exists() else {}
        if saved.get('bundleVersion') == doc['bundleVersion']:
            return saved
        return {'sourceId': source_id, 'bundleVersion': doc['bundleVersion'], 'status': 'missing'}

    def generate(self, source_id, runtime, *, stopped=lambda: False):
        doc = self.document(source_id)
        generation = self.notes.generation(source_id)
        existing = self.opening(source_id)
        if existing['status'] == 'ready':
            return existing
        value = runtime.opening(source_id=source_id,
            ranges=[{'source_lines': [1, doc['lineCount']], 'source_text': doc['markdown']}])
        if not isinstance(value, dict):
            raise ValueError('导读返回格式无效')
        guide = validate_guide(value.get('guide'))
        nodes = value.get('structure')
        if not isinstance(nodes, list) or not 1 <= len(nodes) <= 30:
            raise ValueError('骨架须包含 1–30 个节点')
        seen = {}
        siblings = {}
        for node in nodes:
            if not isinstance(node, dict) or set(node) != {'id', 'parentId', 'title', 'sourceLines'}:
                raise ValueError('骨架节点格式无效')
            key, parent, title, lines = (node[k] for k in ('id', 'parentId', 'title', 'sourceLines'))
            if not isinstance(key, str) or not key or key in seen or (parent is not None and parent not in seen):
                raise ValueError('骨架层级无效')
            if not isinstance(title, str) or len(title) > 50 or not re.search(r'[\u3400-\u9fff]', title):
                raise ValueError('骨架标题须为简短中文')
            if not isinstance(lines, list) or len(lines) != 2 or any(type(n) is not int for n in lines) or not 1 <= lines[0] <= lines[1] <= doc['lineCount']:
                raise ValueError('骨架原文范围无效')
            if parent and not seen[parent][0] <= lines[0] <= lines[1] <= seen[parent][1]:
                raise ValueError('子节点超出父节点')
            previous = siblings.get(parent)
            if previous is not None and lines[0] <= previous:
                raise ValueError('兄弟节点原文范围须按顺序且不重叠')
            siblings[parent] = lines[1]
            seen[key] = lines
        with _LOCK:
            if stopped() or generation != self.notes.generation(source_id) or self.notes.bundle_version(source_id) != doc['bundleVersion']:
                raise WorkspaceError('source_bundle_changed', '导读生成期间原文或会话已改变')
            result = {k: doc[k] for k in ('sourceId', 'bundleVersion')}
            result.update(status='ready', methodVersion='article-overview-v2', revision=hashlib.sha256(repr(value).encode()).hexdigest(), structure=nodes, guide=guide)
            _write_document(self.notes._root(source_id) / 'reading' / 'opening-v2.json', result)
            return result

    def completion(self, source_id, payload=None):
        with _LOCK:
            path = self.notes._root(source_id) / 'reading' / 'source-completion.json'
            if payload is None and not path.exists():
                return None
            doc = {'sourceId': source_id, 'bundleVersion': self.notes.bundle_version(source_id),
                   'generation': self.notes.generation(source_id)}
            saved = _read_document(path) if path.exists() else None
            if saved and (saved['bundleVersion'] != doc['bundleVersion'] or saved['generation'] != doc['generation']):
                saved = None
            if payload is None:
                return saved
            self.notes._check_request(payload.get('requestId'))
            if payload.get('bundleVersion') != doc['bundleVersion'] or payload.get('generation') != doc['generation']:
                raise WorkspaceError('source_bundle_changed', '阅读现场已改变，请刷新后重试')
            if saved:
                return saved
            result = {k: doc[k] for k in ('sourceId', 'bundleVersion', 'generation')}
            result.update(requestId=payload['requestId'], completedAt=time.time())
            _write_document(path, result)
            return result

    def cite(self, scope, arguments):
        """Only exact, unique quotes in the frozen Source range become citations."""
        with _LOCK:
            if not isinstance(arguments, dict) or set(arguments) - {'start', 'end', 'block_ids', 'quote', 'prefix', 'suffix', 'relation'}:
                raise ValueError('Unexpected citation fields')
            if scope.get('generation', 0) != self.notes.generation(scope['sourceId']):
                raise WorkspaceError('discussion_cleared', '会话已清除')
            doc = self.document(scope['sourceId'])
            if doc['bundleVersion'] != scope['bundle']:
                raise WorkspaceError('source_bundle_changed', '原文版本已改变')
            start, end, quote = (arguments.get(k) for k in ('start', 'end', 'quote'))
            if not isinstance(quote, str) or not quote.strip() or len(quote) > 4000:
                raise ValueError('Exact quote required')
            prefix, suffix = arguments.get('prefix', ''), arguments.get('suffix', '')
            if any(not isinstance(s, str) or len(s) > 128 for s in (prefix, suffix)):
                raise ValueError('Invalid citation context')
            quote, prefix, suffix = (s.replace('\r\n', '\n') for s in (quote, prefix, suffix))
            bundle = self.notes._root(scope['sourceId']) / 'parser-bundle'
            source = SourceBlocks(bundle, doc['markdown'])
            block_ids = arguments.get('block_ids')
            ranges = source.ranges(start, end, block_ids, limit=101)
            first, last = source.line_range(start, end, block_ids, limit=None)
            lower, upper = source.starts[first - 1], source.starts[last] - 1
            positions = []
            for first, last in ranges:
                for match in re.finditer('(?=' + re.escape(quote) + ')', source.markdown[first:last]):
                    at = first + match.start()
                    stop = at + len(quote)
                    if (at - len(prefix) >= lower and stop + len(suffix) <= upper
                            and source.markdown.startswith(prefix, at - len(prefix))
                            and source.markdown.startswith(suffix, stop)):
                        positions.append(at)
            if len(positions) != 1:
                raise ValueError('Quote is missing or ambiguous; narrow the source range or supply exact context')
            at = positions[0]
            stop = at + len(quote)
            if not source.has_readable_text(at, stop):
                raise ValueError('Quote needs readable source text, such as a caption or an image label')
            quote_start = bisect_right(source.starts, at)
            quote_end = quote_start + quote.count('\n')
            prefix = prefix or source.markdown[max(0, at - 128):at]
            suffix = suffix or source.markdown[stop:stop + 128]
            relation = arguments.get('relation', 'supports')
            if relation not in ('supports', 'contradicts', 'context'):
                raise ValueError('Invalid evidence relation')
            # ID is run-bound; the model cannot mint a valid ID by writing a marker.
            identity = repr((scope['requestId'], at, stop, quote, prefix, suffix, relation))
            key = hashlib.sha256(identity.encode()).hexdigest()[:24]
            pdf_anchor = {}
            if source.pdf is not None:
                pages = {}
                for fragment in source.pdf['blocks']:
                    if fragment['offsets'][0] >= stop or fragment['offsets'][1] <= at:
                        continue
                    boxes = pages.setdefault(fragment['page'], [])
                    for box in fragment.get('bboxes', [fragment.get('bbox')]):
                        if box is not None and box not in boxes:
                            boxes.append(box)
                pdf_anchor = {'layoutVersion': source.pdf['version'],
                              'pdfRegions': [{'pageIndex': page - 1, 'pageNumber': page, 'bboxes': boxes,
                                              'granularity': 'block' if boxes else 'page'} for page, boxes in pages.items()]}
            blocks = list(dict.fromkeys(block['block_id'] for block in source.blocks
                                        if block['offsets'][0] < stop and at < block['offsets'][1]))
            sections = list(dict.fromkeys(section for path in source.section_ids[quote_start - 1:quote_end] for section in path))
            return {'blockIds': blocks, **pdf_anchor, 'sectionIds': sections, 'renderGranularity': 'block',
                    'evidenceId': key, 'sourceId': doc['sourceId'], 'bundleVersion': doc['bundleVersion'],
                    'sourceLines': [quote_start, quote_end], 'quote': {'exact': quote, 'prefix': prefix, 'suffix': suffix},
                    'relation': relation, 'marker': '[[e:' + key + ']]'}


from .workspace_lifecycle import guard_workspace_class
SourceReading = guard_workspace_class(SourceReading)
