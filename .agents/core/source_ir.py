"""Build and serialize the ordered, source-anchored Parser Bundle representation."""
import html
import json
import re
from collections import Counter

from .article_blog import bundle_fingerprint
from .pdf_layout import (
    _box,
    _pdf_pages,
    archive_layout,
    file_digest,
    layout_fingerprint,
    quote_fingerprint,
    text_fingerprint,
)
from .reading_workspace import MARKDOWN_IMAGE_RE, _replace_text, _write_document
from .source_blocks import SourceBlocks
from .workspace_lifecycle import require_write


IR_VERSION = 1
IR_FILE = 'source-ir.json'
ORIGINALS = {'paper_pdf': 'source.pdf', 'article_html': 'source.html', 'article_markdown': 'source.md'}


class IRSerializer:
    @staticmethod
    def markdown(ir):
        blocks = ''.join(block['separator_before'] + block['markdown'] for block in ir['blocks'])
        return blocks + ir['trailing_separator']


def _block_kind(markdown, is_heading):
    text = markdown.lstrip()
    if is_heading:
        return 'heading'
    if MARKDOWN_IMAGE_RE.search(text):
        return 'image'
    if text.startswith(('$$', '\\[')):
        return 'equation'
    if text.startswith(('```', '~~~')):
        return 'code'
    if re.match(r'<table\b', text, re.I) or re.search(r'^\s*\|?[\s:\-]+\|[\s:\-]+', text, re.M):
        return 'table'
    if re.match(r'(?:[-*+] |\d+[.)] )', text):
        return 'list'
    return 'paragraph'


def _plain_text(markdown, kind):
    if kind == 'code':
        rows = markdown.split('\n')
        if re.fullmatch(r'\s*(?:`{3,}|~{3,})\s*', rows[-1]):
            rows.pop()
        return ' '.join(' '.join(rows[1:]).split())
    text = re.sub(r'^ {0,3}(?:#{1,6}\s+|>\s*)', '', markdown, flags=re.M)
    text = re.sub(r'!?\[([^\[\]]*)\]\((?:[^()]|\([^()]*\))*\)', r'\1', text)
    text = re.sub(r'(\*\*\*|___|\*\*|__|\*|_|~~|`+|\$\$|\$)(?=\S)([^\n]+?)(?<=\S)\1', r'\2', text)
    if kind == 'table':
        text = re.sub(r'</?(?:table|thead|tbody|tfoot|tr|th|td)\b[^>]*>', ' ', text, flags=re.I)
    if kind == 'equation':
        text = text.removeprefix('$$').removesuffix('$$').removeprefix('\\[').removesuffix('\\]')
    return ' '.join(html.unescape(text).split())


def _pdf_anchor(fragments, start, end):
    regions = []
    for fragment in fragments:
        left, right = fragment['offsets']
        if left >= end or right <= start:
            continue
        regions.append({'page_index': fragment['page'] - 1, 'bboxes': fragment['bboxes'],
                        'raw_block_ref': fragment['blockId'],
                        'char_span': {'start': max(start, left), 'end': min(end, right)}})
    if not regions:
        return None
    first = regions[0]['page_index']
    has_boxes = any(region['bboxes'] for region in regions)
    return {'page_index': first, 'page_number': first + 1, 'regions': regions,
            'coord_space': 'normalized_top_left' if has_boxes else None,
            'confidence': 'exact_ir' if has_boxes else 'page'}


def build_source_ir(bundle, markdown, *, source_kind, html_spans=()):
    """Build v1 with 1-based inclusive lines and half-open Markdown character bounds.

    Converted HTML spans are in Markdown order with selectors for the archived DOM.
    Separators preserve Markdown whitespace between the authored blocks.
    """
    markdown = markdown.replace('\r\n', '\n').replace('\r', '\n')
    pdf = archive_layout(bundle, markdown) if source_kind == 'paper_pdf' else None
    source = SourceBlocks(None, markdown, pdf=pdf)
    fragments = sorted(pdf['blocks'], key=lambda item: item['offsets']) if pdf else []
    blocks, sections = [], {}
    counts = Counter()
    cursor = fragment_index = html_index = 0
    for block in source.blocks:
        start, end = block['offsets']
        first, last = source.line_span(start, end)
        base_id = block['block_id']
        counts[base_id] += 1
        block_id = base_id if counts[base_id] == 1 else f'{base_id}/{counts[base_id]}'
        section_ids = source.section_ids[first - 1]
        section_path = source.section_paths[first - 1]
        while fragment_index < len(fragments) and fragments[fragment_index]['offsets'][1] <= start:
            fragment_index += 1
        fragment_end = fragment_index
        while fragment_end < len(fragments) and fragments[fragment_end]['offsets'][0] < end:
            fragment_end += 1
        while html_index < len(html_spans) and html_spans[html_index][1] <= start:
            html_index += 1
        html_end = html_index
        while html_end < len(html_spans) and html_spans[html_end][0] < end:
            html_end += 1
        selectors = list(dict.fromkeys(selector for _, _, selector in html_spans[html_index:html_end]))
        for depth, section_id in enumerate(section_ids):
            if section_id not in sections:
                heading_line = int(section_id.removeprefix('section-'))
                heading = source.lines[heading_line - 1]
                sections[section_id] = {
                    'section_id': section_id, 'parent_id': section_ids[depth - 1] if depth else None,
                    'level': len(heading) - len(heading.lstrip('#')), 'title': section_path[depth],
                    'source_lines': [heading_line, last], 'block_ids': [],
                }
            sections[section_id]['source_lines'][1] = last
            sections[section_id]['block_ids'].append(block_id)
        text = markdown[start:end]
        kind = _block_kind(text, section_ids[-1:] == (f'section-{first}',))
        blocks.append({
            'block_id': block_id, 'order': len(blocks) + 1, 'kind': kind,
            'section_id': section_ids[-1] if section_ids else None, 'section_path': list(section_path),
            'markdown': text, 'separator_before': markdown[cursor:start],
            'plain_text': _plain_text(text, kind), 'quote_hash': quote_fingerprint(text),
            'anchors': {
                'markdown': {'source_lines': [first, last], 'char_span': {'start': start, 'end': end}},
                'pdf': _pdf_anchor(fragments[fragment_index:fragment_end], start, end),
                'html': {'parser': 'lxml', 'selectors': selectors} if selectors else None,
            },
        })
        cursor = end
    pages = [
        {'page_index': page['page'] - 1, 'page_number': page['page'], 'unit': 'pt',
         **{key: page[key] for key in ('width', 'height', 'rotation') if key in page}}
        for page in pdf['pages']
    ] if pdf else []
    ir = {
        'ir_version': IR_VERSION, 'source_kind': source_kind,
        'source_version': file_digest(bundle / ORIGINALS[source_kind]),
        'layout_version': None, 'coord_standard': 'normalized_top_left_v1' if pdf else None,
        'pages': pages, 'sections': list(sections.values()), 'blocks': blocks,
        'trailing_separator': markdown[cursor:],
    }
    ir['bundle_version'] = bundle_fingerprint(bundle, markdown=IRSerializer.markdown(ir).encode('utf-8'))
    if pdf:
        ir['layout_version'] = project_pdf_layout(bundle, ir, markdown)['version']
    return ir


def publish_source_ir(bundle, ir):
    """Materialize canonical Markdown and its IR in the unregistered candidate."""
    content = bundle / 'content.md'
    require_write(content)
    _replace_text(content, IRSerializer.markdown(ir), newline="\n")
    _write_document(bundle / IR_FILE, ir)


def publish_pdf_source_ir(bundle):
    content = bundle / 'content.md'
    markdown = content.read_bytes().decode('utf-8')
    ir = load_source_ir(bundle, markdown)
    if ir is None or ir['source_kind'] != 'paper_pdf':
        publish_source_ir(bundle, build_source_ir(bundle, markdown, source_kind='paper_pdf'))


def load_source_ir(bundle, markdown):
    try:
        ir = json.loads((bundle / IR_FILE).read_text(encoding='utf-8'))
        if type(ir['ir_version']) is not int or ir['ir_version'] != IR_VERSION or ir['source_kind'] not in ORIGINALS:
            return None
        if IRSerializer.markdown(ir) != markdown or ir['trailing_separator'].strip():
            return None
        original = bundle / ORIGINALS[ir['source_kind']]
        if (ir.get('source_version') != file_digest(original)
                or ir.get('bundle_version') != bundle_fingerprint(bundle, markdown=markdown.encode('utf-8'))):
            return None
        cursor = 0
        line = 1
        seen = set()
        for order, block in enumerate(ir['blocks'], 1):
            cursor += len(block['separator_before'])
            line += block['separator_before'].count('\n')
            anchor = block['anchors']['markdown']
            block_id = block['block_id']
            end = cursor + len(block['markdown'])
            last = line + block['markdown'].count('\n')
            if (not isinstance(block_id, str) or not block_id or block_id in seen or not block['markdown']
                    or block.get('order') != order or block['separator_before'].strip()
                    or anchor['char_span'] != {'start': cursor, 'end': end}
                    or anchor['source_lines'] != [line, last]):
                return None
            seen.add(block_id)
            cursor = end
            line = last
        return ir
    except (FileNotFoundError, ValueError, TypeError, KeyError):
        return None


def project_source_blocks(ir):
    blocks = []
    for block in ir['blocks']:
        anchor = block['anchors']['markdown']
        start, end = (anchor['char_span'][key] for key in ('start', 'end'))
        entry = {'block_id': block['block_id'], 'offsets': [start, end], 'source_lines': anchor['source_lines']}
        pdf = block['anchors'].get('pdf')
        if isinstance(pdf, dict) and type(pdf.get('page_number')) is int:
            entry['page'] = pdf['page_number']
        blocks.append(entry)
    return blocks


def _project_regions(ir, markdown, page_count):
    blocks = []
    for block in ir['blocks']:
        pdf = block['anchors'].get('pdf')
        if not isinstance(pdf, dict) or not isinstance(pdf.get('regions'), list):
            continue
        anchor = block['anchors']['markdown']
        span = anchor['char_span']
        for region in pdf['regions']:
            start, end = (region['char_span'][key] for key in ('start', 'end'))
            index = region['page_index']
            if (type(index) is not int or index < 0 or (page_count and index >= page_count)
                    or not span['start'] <= start < end <= span['end']):
                raise ValueError('Invalid PDF anchor')
            boxes = region['bboxes']
            if pdf.get('coord_space') != 'normalized_top_left' or not all(_box(box, (1, 1), 0) for box in boxes):
                boxes = []
            first = anchor['source_lines'][0] + markdown.count('\n', span['start'], start)
            last = first + markdown.count('\n', start, end)
            blocks.append({'blockId': block['block_id'], 'page': index + 1, 'offsets': [start, end],
                           'sourceLines': [first, last], 'bbox': boxes[0] if boxes else None, 'bboxes': boxes})
    return blocks


def project_pdf_layout(bundle, ir, markdown):
    pdf = bundle / 'source.pdf'
    current = file_digest(pdf)
    pages = _pdf_pages(pdf, current)
    blocks = []
    if current == ir.get('source_version'):
        try:
            blocks = _project_regions(ir, markdown, len(pages))
        except (TypeError, KeyError, ValueError):
            pass
    geometry = [ir.get('pages'), project_source_blocks(ir), blocks]
    version = layout_fingerprint(IR_VERSION, current, text_fingerprint(markdown), pages, geometry)
    return {'version': version, 'pdfHash': current, 'pages': pages, 'blocks': blocks}
