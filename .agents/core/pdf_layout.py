"""Version-bound MinerU regions projected onto the published Markdown."""
import bisect
import hashlib
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

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
        return ''.join(_text(child.get('content')) for child in value if isinstance(child, dict))
    return ''


def _fragments(block, compact):
    children = block.get('content')
    if block.get('type') in {'table', 'image', 'chart', 'list', 'code', 'index'} and isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                yield from _fragments(child, compact)
    else:
        text = _text(children)
        if text and ''.join(text.split()) in compact:
            yield text
        elif isinstance(children, list):
            # Styling and links may insert Markdown between adjacent inline spans.
            for child in children:
                if isinstance(child, dict):
                    yield from _fragments(child, compact)
        elif block.get('type') == 'table_body':
            # Continued tables can share one HTML wrapper in the Markdown.
            yield from re.findall(r'<tr\b[^>]*>.*?</tr>', text, re.I | re.S)


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
            box = block.get('bbox')
            if not (isinstance(box, list) and len(box) == 4 and all(type(v) in (float, int) for v in box)
                    and 0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
                box = None
            for fragment in _fragments(block, compact):
                needle = ''.join(fragment.split())
                if not needle:
                    continue
                at = compact.find(needle)
                if at >= 0:
                    unique = compact.find(needle, at + 1) < 0
                    candidates.append((page['page_idx'], block['index'], box, needle, at if unique else None))

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
    for (page, index, box, needle, at), limit in zip(candidates, reversed(upper)):
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
        result.append({'blockId': f'{page}-{index}', 'page': page + 1, 'bbox': box,
                       'sourceLines': [bisect.bisect_right(starts, start), bisect.bisect_right(starts, stop - 1)],
                       'offsets': [start, stop]})
    return result


def layout(bundle: Path, *, persist=False):
    pdf = bundle / 'source.pdf'
    middle = bundle / 'mineru' / 'middle_json.json'
    content = bundle / 'content.md'
    pdf_hash = file_digest(pdf)
    identity = ':'.join(('1', pdf_hash, file_digest(content), file_digest(middle) if middle.is_file() else 'none'))
    version = hashlib.sha256(identity.encode()).hexdigest()
    saved = bundle / 'source-layout.json'
    if saved.is_file():
        index = _saved_index(saved, saved.stat().st_ctime_ns)
        if isinstance(index, dict) and index.get('version') == version and isinstance(index.get('blocks'), list):
            return index
    blocks = _blocks(content, middle, version) if middle.is_file() else []
    index = {'version': version, 'pdfHash': pdf_hash, 'blocks': blocks}
    if persist:
        _write_document(saved, index)
    return index


@lru_cache(maxsize=16)
def _saved_index(path, timestamp):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError):
        return None


@lru_cache(maxsize=16)
def _blocks(content, middle, version):
    data = _saved_index(middle, middle.stat().st_ctime_ns)
    if not isinstance(data, dict) or not isinstance(data.get('pages'), list):
        return []
    return align(content.read_text(encoding='utf-8'), data['pages'])
