"""The translated Source Document and its canonical Markdown locations."""
from bisect import bisect_right
from itertools import zip_longest
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


class TranslationIssue(WorkspaceError):
    def __init__(self, category, message, segment=None, **details):
        self.issue = {"category": category, **details}
        if segment:
            first, last = segment["sourceLines"]
            self.issue.update(segment_id=segment["id"], source_lines=[first, last])
            message = f"原文第 {first}–{last} 行：{message}"
        super().__init__("translation_invalid", message)


class SourceTranslation:
    def __init__(self, root, bundle, source_id, bundle_version, reading_version, *, source=None):
        self.bundle = bundle
        self.source = source if source is not None else SourceBlocks(bundle)
        self.source_id = source_id
        self.bundle_version = bundle_version
        self.reading_version = reading_version
        self.path = root / 'reading' / 'translations' / f'{reading_version}.json'
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
        projection = self.project(segments, start, end)
        return projection[0] if projection is not None else None

    def project(self, segments, start, end):
        """Return the Chunk translation and each segment's offset within it."""
        pieces = []
        offsets = {}
        cursor = start
        length = 0
        for segment in segments:
            first, last = segment['sourceOffsets']
            if last <= start:
                continue
            if first >= end:
                break
            # A new Plan can divide an existing translated segment. Keep its
            # whole text in every intersecting Chunk, with its original mapping.
            separator = self.source.markdown[cursor:first]
            if separator.strip():
                return None
            length += len(separator)
            offsets[segment['id']] = length
            pieces.extend([separator, segment['text']])
            length += len(segment['text'])
            cursor = last
        if not pieces or self.source.markdown[cursor:end].strip():
            return None
        text = ''.join(pieces)
        leading = len(text) - len(text.lstrip())
        return text.strip(), {segment_id: offset - leading for segment_id, offset in offsets.items()}

    def add_candidates(self, segments, candidates):
        if not isinstance(candidates, list) or len(candidates) != len(segments):
            actual = len(candidates) if isinstance(candidates, list) else None
            raise TranslationIssue("batch_shape", f"须返回含 {len(segments)} 个译段的数组。",
                                   expected=len(segments), actual=actual)
        for segment, candidate in zip(segments, candidates):
            if not isinstance(candidate, dict) or candidate.get("id") != segment["id"]:
                raise TranslationIssue("segment_order", f"此处应返回译段 {segment['id']}。", segment,
                                       expected=segment["id"], actual=candidate.get("id") if isinstance(candidate, dict) else None)
            if not isinstance(candidate.get("text"), str) or not candidate["text"].strip():
                raise TranslationIssue("empty_text", "译文不能为空。", segment)
            original = self.source.markdown[slice(*segment["sourceOffsets"])]
            text = candidate["text"].strip()
            heading = re.match(r'^#{1,6}[ \t]+', original)
            if heading and not re.match(re.escape(heading.group().rstrip()) + r'[ \t]+', text):
                raise TranslationIssue('heading_level', '译段必须保留原文标题层级。', segment, expected=heading.group().strip())
            self.validate_markup(original, text, segment)
        for segment, candidate in zip(segments, candidates):
            segment['text'] = candidate['text'].strip()

    @staticmethod
    def validate_markup(original, text, segment=None):
        def protected(markdown):
            return (MARKDOWN_IMAGE_RE.findall(markdown),
                    re.findall(r'(?<!\\)(?:\$[^$\n]+\$|\\\([^\n]+?\\\))', markdown),
                    [markdown[start:end] for start, end in verbatim_ranges(markdown)])

        categories = (("image", "图片链接"), ("inline_math", "行内公式"), ("verbatim", "原样保留的内容"))
        for (category, label), expected, actual in zip(categories, protected(original), protected(text)):
            for index, (left, right) in enumerate(zip_longest(expected, actual)):
                if left != right:
                    raise TranslationIssue(category, f"第 {index + 1} 项{label}不匹配，"
                                           f"期望 {(left or '无')[:100]}，实际 {(right or '无')[:100]}。",
                                           segment, index=index, expected=left, actual=right)
