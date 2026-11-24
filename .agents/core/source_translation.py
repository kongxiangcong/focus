"""The translated Source Document and its canonical Markdown locations."""
from bisect import bisect_right
import re

from .reading_workspace import WorkspaceError, _read_document, _write_document
from .source_blocks import SourceBlocks
from .source_markdown import MARKDOWN_IMAGE_RE, verbatim_ranges


def _segment(source, blocks, start, end, *, original=False, coarse=False):
    ids = list(dict.fromkeys(block['block_id'] for block in blocks if block['offsets'][0] < end))
    return {
        'id': f'md-{start}-{end}',
        'blockIds': ids,
        'sourceLines': source.line_span(start, end),
        'sourceOffsets': [start, end],
        'granularity': 'source' if original else 'group' if coarse else 'block',
    }


class SourceTranslation:
    def __init__(self, bundle, source_id, bundle_version, reading_version, *, source=None):
        self.source = source if source is not None else SourceBlocks(bundle)
        self.source_id = source_id
        self.bundle_version = bundle_version
        self.reading_version = reading_version
        self.path = bundle.parent / 'reading' / 'translations' / f'{reading_version}.json'
        self.ends = [block['offsets'][1] for block in self.source.blocks]

    def result(self, status, segments=()):
        return {'status': status, 'bundleVersion': self.bundle_version,
                'readingVersion': self.reading_version, 'segments': list(segments)}

    def load(self):
        if not self.path.is_file():
            return None
        try:
            value = _read_document(self.path)
        except WorkspaceError:
            return None
        if (value.get('sourceId') != self.source_id or value.get('status') != 'ready'
                or value.get('bundleVersion') != self.bundle_version
                or value.get('readingVersion') != self.reading_version
                or not self._valid(value.get('segments'))):
            return None
        return value

    def _covering_blocks(self, start, end):
        left = bisect_right(self.ends, start)
        for index in range(left, len(self.source.blocks)):
            block = self.source.blocks[index]
            if block['offsets'][0] >= end:
                break
            yield block

    def _valid(self, segments):
        if not isinstance(segments, list):
            return False
        cursor = 0
        for segment in segments:
            if not isinstance(segment, dict):
                return False
            bounds = segment.get('sourceOffsets')
            text = segment.get('text')
            granularity = segment.get('granularity')
            if (not isinstance(bounds, list) or len(bounds) != 2 or any(type(n) is not int for n in bounds)
                    or not isinstance(text, str) or not text.strip()
                    or granularity not in ('block', 'group', 'source')):
                return False
            start, end = bounds
            if not (cursor <= start < end <= len(self.source.markdown)) or self.source.markdown[cursor:start].strip():
                return False
            blocks = list(self._covering_blocks(start, end))
            if granularity == 'block' and (len(blocks) != 1 or blocks[0]['offsets'] != bounds):
                return False
            expected = _segment(self.source, blocks, start, end,
                                original=granularity == 'source', coarse=granularity == 'group')
            if any(segment.get(key) != value for key, value in expected.items()):
                return False
            if granularity == 'source' and self.source.markdown[start:end] != text:
                return False
            cursor = end
        return not self.source.markdown[cursor:].strip()

    def save(self, segments, *, run_id):
        if not self._valid(segments):
            raise WorkspaceError('translation_invalid', '译文及映射须覆盖有序、可验证的整篇原文范围。')
        value = {'sourceId': self.source_id, 'preparationId': run_id, **self.result('ready', segments)}
        _write_document(self.path, value)
        return value

    def interval(self, lines):
        start, end = lines
        return self.source.starts[start - 1], self.source.starts[end] - 1

    def segments(self, start, end, *, translated=None, original=False):
        source = self.source
        blocks = self._covering_blocks(start, end)
        if translated is not None:
            return [{**_segment(source, blocks, start, end, coarse=True), 'text': translated}]
        result = []
        for block in blocks:
            first, last = block['offsets']
            low, high = max(first, start), min(last, end)
            text = source.markdown[low:high]
            if not text.strip():
                continue
            preserve = original or text.lstrip().startswith(('~~~', '```', '$$', '\\[', '|', '<table'))
            result.append({**_segment(source, [block], low, high, original=preserve,
                                      coarse=(low != first or high != last)),
                           'text': text if preserve else None})
        return result

    def render(self, segments, start, end):
        pieces = []
        cursor = start
        for segment in segments:
            first, last = segment['sourceOffsets']
            if last <= start:
                continue
            if first >= end:
                break
            if first < start or last > end:
                return None
            separator = self.source.markdown[cursor:first]
            if separator.strip():
                return None
            pieces.extend([separator, segment['text']])
            cursor = last
        if not pieces or self.source.markdown[cursor:end].strip():
            return None
        return ''.join(pieces).strip()

    def add_candidates(self, segments, candidates):
        expected = [(segment, self.source.markdown[slice(*segment['sourceOffsets'])]) for segment in segments]
        if (not isinstance(candidates, list) or len(candidates) != len(expected)
                or any(not isinstance(candidate, dict) or candidate.get('id') != segment['id']
                       or not isinstance(candidate.get('text'), str) or not candidate['text'].strip()
                       for (segment, _), candidate in zip(expected, candidates))):
            raise WorkspaceError('translation_invalid', '译段须按原文顺序返回每个指定范围的标识和译文。')
        for (segment, original), candidate in zip(expected, candidates):
            text = candidate['text'].strip()
            heading = re.match(r'^#{1,6}[ \t]+', original)
            if heading and not re.match(re.escape(heading.group().rstrip()) + r'[ \t]+', text):
                raise WorkspaceError('translation_invalid', '译段必须保留原文标题层级。')
            self.validate_markup(original, text)
            segment['text'] = text

    @staticmethod
    def validate_markup(original, text):
        def protected(markdown):
            return (MARKDOWN_IMAGE_RE.findall(markdown),
                    re.findall(r'(?<!\\)(?:\$[^$\n]+\$|\\\([^\n]+?\\\))', markdown),
                    [markdown[start:end] for start, end in verbatim_ranges(markdown)])

        if protected(original) != protected(text):
            raise WorkspaceError('translation_invalid', '译段必须保留原文的公式、代码和图片链接。')
