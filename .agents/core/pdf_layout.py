"""Version-bound MinerU regions projected onto the published Markdown."""
import bisect
import hashlib
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .mineru import mineru_artifact_name
from .reading_workspace import _write_document


@lru_cache(maxsize=256)
def _digest(path, identity):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_digest(path):
    stat = path.stat()
    return _digest(path, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_ctime_ns))


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ''.join(_text(child) for child in value)
    if isinstance(value, dict):
        return _text(value.get('content'))
    return ''


def _fragments(block, compact):
    children = block.get('content')
    if block.get('type') in _OBJECT_TYPES and isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                yield from _fragments(child, compact)
    else:
        text = _text(children)
        if text and ''.join(text.split()) in compact:
            yield text
        elif block.get('type') == 'table_body':
            # Continued tables can share one HTML wrapper in the Markdown.
            yield from re.findall(r'<tr\b[^>]*>.*?</tr>', text, re.I | re.S)
        elif isinstance(children, list):
            # Styling and links may insert Markdown between adjacent inline spans.
            for child in children:
                if isinstance(child, dict):
                    yield from _fragments(child, compact)


def align(markdown, pages):
    """Accept unique literal fragments; resolve repeats only with unique ordered neighbours."""
    chars = [m.start() for m in re.finditer(r'\S', markdown)]
    compact = ''.join(markdown[i] for i in chars)
    starts = [0] + [m.end() for m in re.finditer('\n', markdown)]
    candidates = []
    for page in pages:
        if not isinstance(page, dict) or type(page.get('page_idx')) is not int or page['page_idx'] < 0:
            continue
        if not isinstance(page.get('blocks'), list):
            continue
        for block in page['blocks']:
            if not isinstance(block, dict) or type(block.get('index')) is not int:
                continue
            boxes = _boxes(block, 'normalized_top_left', (1, 1), 0)
            for fragment in _fragments(block, compact):
                needle = ''.join(fragment.split())
                if not needle:
                    continue
                at = compact.find(needle)
                if at >= 0:
                    unique = compact.find(needle, at + 1) < 0
                    candidates.append((page['page_idx'], block['index'], boxes, needle, at if unique else None))

    result = []
    counts = Counter(entry[3] for entry in candidates)
    end = len(compact)
    upper = []
    for _, _, _, _, at in reversed(candidates):
        upper.append(end)
        if at is not None:
            end = at
    visits = Counter()
    repeated_positions = {}
    lower = 0
    for (page, index, boxes, needle, at), limit in zip(candidates, reversed(upper)):
        if counts[needle] > 1:
            if needle not in repeated_positions:
                positions = [match.start() for match in re.finditer(re.escape(needle), compact)]
                repeated_positions[needle] = positions if len(positions) == counts[needle] else []
            positions = repeated_positions[needle]
            ordinal = visits[needle]
            visits[needle] += 1
            if not positions or not lower <= positions[ordinal] <= limit - len(needle):
                continue
            at = positions[ordinal]
        if at is None:
            at = compact.find(needle, lower, limit)
            if at < 0 or compact.find(needle, at + 1, limit) >= 0:
                continue
        lower = at + len(needle)
        start, stop = chars[at], chars[lower - 1] + 1
        result.append({'blockId': f'{page}-{index}', 'page': page + 1, 'bbox': boxes[0] if boxes else None, 'bboxes': boxes,
                       'sourceLines': [bisect.bisect_right(starts, start), bisect.bisect_right(starts, stop - 1)],
                       'offsets': [start, stop]})
    return result


# Bump when the source IR and its PDF anchor semantics change.
IR_SCHEMA_VERSION = 1
_ARTIFACTS_BY_PRIORITY = ('middle_json.json', 'content_list.json', 'content_list_v2.json', 'structured_content.json')
_OBJECT_TYPES = ('image', 'table', 'chart', 'code', 'algorithm', 'list', 'index')
_UNROTATED_SPACES = ('normalized_unrotated_top_left', 'page_unrotated_top_left')
_TEXT_FIELDS = (
    'text', 'title_content', 'paragraph_content', 'math_content', 'equation_content',
    'image_caption', 'table_caption', 'chart_caption', 'code_caption', 'algorithm_caption',
    'table_body', 'table_content', 'html', 'content', 'code_body', 'code_content', 'algorithm_content', 'list_items',
    'image_footnote', 'table_footnote', 'chart_footnote', 'code_footnote', 'algorithm_footnote',
    'page_header_content', 'page_footer_content', 'page_footnote_content', 'page_aside_text_content',
    'page_number_content',
)


def _number(value):
    return type(value) in (int, float) and -math.inf < value < math.inf


def _dimensions(values):
    if isinstance(values, (tuple, list)) and len(values) == 2 and all(_number(v) and v > 0 for v in values):
        return tuple(values)
    return None


def _box(box, size, rotation):
    if not isinstance(box, (tuple, list)) or len(box) != 4 or not all(_number(v) for v in box):
        return None
    width, height = size
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        return None
    x0, x1, y0, y1 = x0 / width, x1 / width, y0 / height, y1 / height
    if rotation == 90:
        return (1 - y1, x0, 1 - y0, x1)
    if rotation == 180:
        return (1 - x1, 1 - y1, 1 - x0, 1 - y0)
    if rotation == 270:
        return (y0, 1 - x1, y1, 1 - x0)
    return (x0, y0, x1, y1)


def _boxes(block, space, page_size, rotation, original_size=None):
    if page_size and original_size:
        original_width, original_height = original_size
        if space in _UNROTATED_SPACES and rotation in (90, 270):
            original_width, original_height = original_height, original_width
        if not math.isclose(page_size[0] / page_size[1], original_width / original_height, rel_tol=0.01):
            return []
    if space in ('normalized_top_left', 'normalized_unrotated_top_left'):
        size = (1, 1)
    elif space == 'normalized_1000_top_left':
        size = (1000, 1000)
    elif space in ('page_top_left', 'page_unrotated_top_left'):
        size = page_size
    else:
        return []
    if not size or (space in _UNROTATED_SPACES and rotation is None):
        return []
    rotate = rotation if space in _UNROTATED_SPACES else 0
    raw = block.get('bboxes', [block.get('bbox')])
    if not isinstance(raw, list):
        return []
    if space == 'normalized_1000_top_left' and not all(
            isinstance(box, list) and all(type(value) is int for value in box) for box in raw):
        return []
    boxes = [_box(box, size, rotate) for box in raw]
    return [list(box) for box in dict.fromkeys(boxes)] if all(boxes) else []


def _legacy_block(block):
    children = block.get('blocks')
    if isinstance(children, list):
        return {**block, 'content': [_legacy_block(child) for child in children if isinstance(child, dict)]}
    lines = block.get('lines')
    if isinstance(lines, list):
        spans = []
        for line in lines:
            if isinstance(line, dict) and isinstance(line.get('spans'), list):
                spans.extend({**span, 'content': span.get('html') or span.get('content')}
                             for span in line['spans'] if isinstance(span, dict))
        return {**block, 'content': spans}
    return block


def _list_block(block):
    content = block.get('content')
    fields = content if isinstance(content, dict) else block
    fragments = []
    for name in _TEXT_FIELDS:
        if name == 'content' and not isinstance(content, dict):
            continue
        value = fields.get(name)
        if name == 'list_items' and isinstance(value, list):
            fragments.extend({'type': 'text', 'content': item.get('item_content') if isinstance(item, dict) else item}
                             for item in value)
        elif value:
            is_body = name in ('table_body', 'table_content') or (name == 'html' and block.get('type') == 'table')
            fragments.append({'type': 'table_body' if is_body else 'text', 'content': value})
    return {**block, 'type': 'list', 'content': fragments} if fragments else block


def _middle_pages(payload):
    specification = payload.get('extensions', {})
    layout = specification.get('docvortex_layout') if isinstance(specification, dict) else None
    sizes = {}
    if isinstance(layout, dict) and layout.get('version') == 1 and isinstance(layout.get('pages'), list):
        for page in layout['pages']:
            if isinstance(page, dict) and type(page.get('page_idx')) is int:
                sizes[page['page_idx']] = _dimensions((page.get('width_pt'), page.get('height_pt')))
    if isinstance(payload.get('pages'), list):
        # The saved local protocol uses fractions on the visual page.
        schema = payload.get('schema')
        known = schema is None or (schema == 'docvortex.middle' and payload.get('schema_version') == '2.0')
        for page in payload['pages']:
            if isinstance(page, dict) and type(page.get('page_idx')) is int:
                yield (page, payload.get('coordinate_space', 'normalized_top_left' if known else None),
                       sizes.get(page['page_idx']))
    elif isinstance(payload.get('pdf_info'), list):
        # The legacy PDF middle artifact shares its page_size basis with para_blocks.
        for page in payload['pdf_info']:
            if not isinstance(page, dict) or not isinstance(page.get('para_blocks'), list):
                continue
            blocks = [_legacy_block(block) for block in page['para_blocks'] if isinstance(block, dict)]
            yield {**page, 'blocks': blocks}, payload.get('coordinate_space', 'page_top_left'), None


def _list_pages(name, payload, page_count):
    if name == 'content_list.json':
        by_page = {}
        for block in payload:
            if isinstance(block, dict) and type(block.get('page_idx')) is int:
                by_page.setdefault(block['page_idx'], []).append(block)
        groups = sorted(by_page.items())
    else:
        # V2 numbering is by outer array position; a sliced export cannot prove its first page.
        if page_count != len(payload) or not all(isinstance(page, list) for page in payload):
            return
        groups = enumerate(payload)
    for index, blocks in groups:
        yield {'page_idx': index, 'blocks': [_list_block(block) for block in blocks if isinstance(block, dict)]}, \
            'normalized_1000_top_left', None


def _archive_geometry(name, payload, pdf_pages):
    if name in ('middle_json.json', 'structured_content.json') and isinstance(payload, dict):
        archive = _middle_pages(payload)
    elif name in ('content_list.json', 'content_list_v2.json') and isinstance(payload, list):
        archive = _list_pages(name, payload, len(pdf_pages))
    else:
        return []
    pages = []
    visited = set()
    for page, default_space, archive_size in archive:
        index = page.get('page_idx')
        if (type(index) is not int or index < 0 or index in visited or (pdf_pages and index >= len(pdf_pages))
                or not isinstance(page.get('blocks'), list)):
            continue
        visited.add(index)
        original = pdf_pages[index] if pdf_pages else {}
        page_size = _dimensions(page.get('page_size')) or archive_size
        original_size = _dimensions((original.get('width'), original.get('height')))
        rotation = original.get('rotation')
        declared_rotation = page.get('rotation', rotation)
        valid_rotation = declared_rotation is None or (type(declared_rotation) is int and
            declared_rotation % 90 == 0 and (rotation is None or declared_rotation % 360 == rotation))
        if valid_rotation and declared_rotation is not None:
            rotation = declared_rotation = declared_rotation % 360
        page_space = page.get('coordinate_space', default_space)
        blocks = []
        seen_indices = set()
        for ordinal, block in enumerate(page['blocks']):
            if not isinstance(block, dict):
                continue
            block_index = block.get('index', ordinal)
            if type(block_index) is not int or block_index < 0 or block_index in seen_indices:
                continue
            seen_indices.add(block_index)
            space = block.get('coordinate_space', page_space)
            boxes = _boxes(block, space, page_size, rotation, original_size) if valid_rotation else []
            children = block.get('content')
            if valid_rotation and 'bboxes' not in block and block.get('type') in _OBJECT_TYPES and isinstance(children, list):
                child_boxes = [_boxes(child, child.get('coordinate_space', space), page_size, rotation, original_size)
                               for child in children if isinstance(child, dict)]
                if child_boxes and all(child_boxes):
                    boxes = [list(box) for box in dict.fromkeys(tuple(box) for item in child_boxes for box in item)]
            blocks.append({**block, 'index': block_index, 'bboxes': boxes})
        pages.append({'page_idx': index, 'page_size': page_size, 'rotation': declared_rotation, 'blocks': blocks})
    return pages


@lru_cache(maxsize=16)
def _pdf_pages(pdf, pdf_hash):
    if pdf.stat().st_size < 64:
        return []
    try:
        with pdf.open('rb') as stream:
            pages = []
            for index, page in enumerate(PdfReader(stream).pages, start=1):
                rotation = page.rotation % 360
                crop, media = page.cropbox, page.mediabox
                # Match PDF.js's visible CropBox/MediaBox intersection.
                width = min(crop.right, media.right) - max(crop.left, media.left)
                height = min(crop.top, media.top) - max(crop.bottom, media.bottom)
                if width <= 0 or height <= 0:
                    width, height = media.width, media.height
                width, height = float(width * page.user_unit), float(height * page.user_unit)
                if rotation in (90, 270):
                    width, height = height, width
                size = _dimensions((width, height))
                geometry = {'width': width, 'height': height, 'rotation': rotation} if size and rotation % 90 == 0 else {}
                pages.append({'page': index, **geometry})
            return pages
    except (PdfReadError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return []


def _archive_paths(bundle):
    artifacts = {}
    for path in sorted((bundle / 'mineru').glob('*.json')):
        name = mineru_artifact_name(path.name)
        if name in _ARTIFACTS_BY_PRIORITY and path.is_file():
            artifacts.setdefault(name, []).append(path)
    for name in _ARTIFACTS_BY_PRIORITY:
        paths = artifacts.get(name, [])
        canonical = bundle / 'mineru' / name
        if canonical in paths:
            yield name, canonical
        elif len(paths) == 1:
            yield name, paths[0]


@lru_cache(maxsize=16)
def _layout(content, markdown_digest, pdf, pdf_hash, artifacts):
    pages = _pdf_pages(pdf, pdf_hash)
    markdown = content.read_text(encoding='utf-8')
    blocks, geometry = [], []
    for name, path, _ in artifacts:
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError):
            continue
        archive = _archive_geometry(name, payload, pages)
        geometry.append([(page['page_idx'], page['page_size'], page['rotation'],
                          [(block['index'], block.get('type'), block['bboxes'])
                           for block in page['blocks']]) for page in archive])
        if not blocks:
            blocks = align(markdown, archive)
    fingerprint = json.dumps([IR_SCHEMA_VERSION, pdf_hash, markdown_digest, pages, geometry, blocks],
                             sort_keys=True, separators=(',', ':'))
    version = hashlib.sha256(fingerprint.encode()).hexdigest()
    return {'version': version, 'pdfHash': pdf_hash, 'pages': pages, 'blocks': blocks}


def layout(bundle: Path, *, persist=False):
    pdf, content = bundle / 'source.pdf', bundle / 'content.md'
    artifacts = tuple((name, path, file_digest(path)) for name, path in _archive_paths(bundle))
    index = _layout(content, file_digest(content), pdf, file_digest(pdf), artifacts)
    if persist:
        _write_document(bundle / 'source-layout.json', index)
    return index
