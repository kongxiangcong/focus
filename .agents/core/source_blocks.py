"""Canonical Markdown lines and block bounds shared by the source tools."""
from bisect import bisect_right

from .reading_workspace import (
    MARKDOWN_IMAGE_DETAIL_RE,
    MARKDOWN_IMAGE_RE,
    WorkspaceError,
    _protected_source_ranges,
    _source_heading_paths,
)


def source_lines(markdown):
    # The canonical Markdown reader uses LF. Other Unicode separators remain text.
    return markdown.removesuffix('\n').split('\n') if markdown else []


class SourceBlocks:
    def __init__(self, bundle, markdown=None):
        if markdown is None:
            markdown = (bundle / 'content.md').read_text(encoding='utf-8', errors='replace')
        self.markdown = markdown
        self.lines = source_lines(markdown)
        self.section_paths = _source_heading_paths(self.lines)
        self.section_ids = _source_heading_paths(self.lines, identifiers=True)
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line) + 1)
        self.blocks = self._markdown_blocks()
        self.pdf = None
        if (bundle / 'source.pdf').is_file():
            from .pdf_layout import layout
            self.pdf = layout(bundle)
            self.blocks = self._with_pdf_blocks(self.pdf['blocks'])

    def _markdown_blocks(self):
        protected = sorted(_protected_source_ranges(self.lines, strict=False))
        groups = []
        for first, last in protected:
            if groups and first <= groups[-1][1]:
                groups[-1][1] = max(groups[-1][1], last)
            else:
                groups.append([first, last])
        protected = dict(groups)
        blocks = []
        first = 1
        while first <= len(self.lines):
            if not self.lines[first - 1].strip() and first not in protected:
                first += 1
                continue
            last = protected.get(first, first)
            if first not in protected and not self._starts_object(first):
                while last < len(self.lines) and last + 1 not in protected and not self._starts_object(last + 1):
                    last += 1
            blocks.append({'block_id': f'md-{first}', 'source_lines': [first, last],
                           'offsets': [self.starts[first - 1], self.starts[last] - 1]})
            first = last + 1
        return blocks

    def _starts_object(self, line):
        text = self.lines[line - 1]
        return (not text.strip() or self.section_ids[line - 1][-1:] == (f'section-{line}',)
                or (MARKDOWN_IMAGE_RE.match(text.lstrip()) is not None))

    def _with_pdf_blocks(self, fragments):
        fragments = iter(sorted(fragments, key=lambda fragment: fragment['offsets']))
        pending = next(fragments, None)
        result = []
        for block in self.blocks:
            start, end = block['offsets']
            while pending and pending['offsets'][1] <= start:
                pending = next(fragments, None)
            aligned = []
            while pending and pending['offsets'][0] < end:
                first, last = pending['offsets']
                key = pending['blockId']
                if aligned and aligned[-1]['block_id'] == key:
                    aligned[-1]['offsets'][1] = min(last, end)
                else:
                    aligned.append({'block_id': key, 'page': pending['page'],
                                    'offsets': [max(first, start), min(last, end)]})
                if last > end:
                    break
                pending = next(fragments, None)
            if not aligned:
                result.append(block)
                continue
            # Keep Markdown syntax around a fragment on a line owned by one
            # object. When two objects share a line, keep their exact bounds.
            cursor = start
            spans = [self.line_span(*part['offsets']) for part in aligned]
            for index, part in enumerate(aligned):
                first, last = spans[index]
                if index == 0 or spans[index - 1][1] < first:
                    part['offsets'][0] = self.starts[first - 1]
                if index == len(aligned) - 1 or last < spans[index + 1][0]:
                    part['offsets'][1] = self.starts[last] - 1
                left, right = part['offsets']
                if self.markdown[cursor:left].strip():
                    result.append({**block, 'offsets': [cursor, left]})
                result.append(part)
                cursor = right
            if self.markdown[cursor:end].strip():
                result.append({**block, 'offsets': [cursor, end]})
        return result

    def selected_blocks(self, block_ids):
        if not isinstance(block_ids, list) or not block_ids or any(not isinstance(key, str) for key in block_ids):
            raise WorkspaceError('source_range_invalid', 'block_ids must be a nonempty list of block IDs')
        selected = set(block_ids)
        blocks = [block for block in self.blocks if block['block_id'] in selected]
        if {block['block_id'] for block in blocks} != selected:
            raise WorkspaceError('source_range_invalid', 'Unknown block ID in this Source Bundle')
        return blocks

    def line_range(self, start, end, block_ids, *, limit):
        if start is None and end is None and block_ids is not None:
            return 1, len(self.lines)
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(self.lines):
            raise WorkspaceError('source_range_invalid', 'Source range is invalid')
        if limit is not None and end - start + 1 > limit:
            raise WorkspaceError('source_range_invalid', f'Read at most {limit} lines')
        return start, end

    def text(self, first, last):
        return '\n'.join(self.lines[first - 1:last])

    def line_span(self, start, stop):
        return [bisect_right(self.starts, start), bisect_right(self.starts, max(start, stop - 1))]

    def has_readable_text(self, start, end):
        """An image target is storage metadata. Only its alt text is readable."""
        first_line = self.markdown.rfind('\n', 0, start) + 1
        last_line = self.markdown.find('\n', end)
        relevant = self.markdown[first_line:] if last_line < 0 else self.markdown[first_line:last_line]
        cursor = start - first_line
        stop = end - first_line
        for image in MARKDOWN_IMAGE_DETAIL_RE.finditer(relevant):
            if image.end() <= cursor or image.start() >= stop:
                continue
            if relevant[cursor:image.start()].strip():
                return True
            alt_start, alt_end = image.span(1)
            if max(cursor, alt_start) < min(stop, alt_end) and relevant[max(cursor, alt_start):min(stop, alt_end)].strip():
                return True
            cursor = image.end()
        return cursor < stop and bool(relevant[cursor:stop].strip())

    def headers(self, first, last):
        headers = {}
        for block in self.blocks:
            start, end = self.line_span(*block['offsets'])
            if start > last or end < first:
                continue
            key = block['block_id']
            page = block.get('page')
            if key in headers:
                start = min(start, headers[key]['source_lines'][0])
                end = max(end, headers[key]['source_lines'][1])
            page_header = f' | p.{page}' if page is not None else ''
            headers[key] = {'block_id': key, 'page': page, 'source_lines': [start, end],
                            'header': f'[{key}{page_header} | L{start}-{end}]'}
        return list(headers.values())

    def ranges(self, start, end, block_ids, *, limit):
        start, end = self.line_range(start, end, block_ids, limit=limit)
        lower, upper = self.starts[start - 1], self.starts[end] - 1
        if block_ids is None:
            return [[lower, upper]]
        ranges = []
        for block in self.selected_blocks(block_ids):
            first, last = block['offsets']
            first, last = max(lower, first), min(upper, last)
            if first >= last:
                continue
            if ranges and not self.markdown[ranges[-1][1]:first].strip():
                ranges[-1][1] = max(ranges[-1][1], last)
            else:
                ranges.append([first, last])
        if not ranges:
            raise WorkspaceError('source_range_invalid', 'No selected blocks in the requested Source range')
        if limit is not None and sum(self.markdown[first:last].count('\n') + 1 for first, last in ranges) > limit:
            raise WorkspaceError('source_range_invalid', f'Read at most {limit} lines')
        return ranges
