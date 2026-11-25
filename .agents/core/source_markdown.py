"""Canonical Markdown syntax used to describe and validate source blocks."""
import re
from bisect import bisect_right
from typing import NamedTuple

from .workspace_errors import WorkspaceError


MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\(([^)]+)\)")
MARKDOWN_IMAGE_DETAIL_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)]+)\)")
_REFERENCE_DEFINITION = re.compile(r'^ {0,3}\[(?!\^)([^\]\n]+)\]:[ \t]*(?:\n[ \t]*)?[^\s][^\n]*'
                                   r'(?:\n[ \t]+(?:"[^"\n]*"|\'[^\'\n]*\'|\([^()\n]*\))[ \t]*(?=\n|$))?', re.M)
_IMAGE = re.compile(r'(?<!\\)!\[(?P<alt>[^\]\n]*)\]'
                    r'(?:(?P<target>\((?:[^()\n]|\([^()\n]*\))*\))|\[(?P<label>[^\]\n]*)\])?')


def source_lines(markdown):
    # The canonical Markdown reader uses LF. Other Unicode separators remain text.
    return markdown.removesuffix('\n').split('\n') if markdown else []


def document_language(markdown):
    """Classify the document’s prose independently of parser/OCR settings."""
    prose = []
    cursor = 0
    for start, end in sorted(verbatim_ranges(markdown)):
        prose.append(markdown[cursor:start])
        cursor = max(cursor, end)
    prose.append(markdown[cursor:])
    markdown = re.sub(r'\]\([^\n)]+\)|https?://\S+|\$[^\n$]+\$', '', ' '.join(prose))
    han = len(re.findall(r'[\u3400-\u9fff\U00020000-\U000323af]', markdown))
    letters = sum(character.isalpha() for character in markdown)
    if han and han * 4 >= letters:
        return 'zh'
    if han >= 12 and han * 12 >= letters:
        return 'mixed'
    return 'en'


def has_readable_text(markdown, start, end):
    """Count image alt and surrounding text, skipping image and reference storage syntax."""
    def label_key(label):
        return ' '.join(label.casefold().split())

    verbatim = verbatim_ranges(markdown)
    definitions = [match for match in _REFERENCE_DEFINITION.finditer(markdown)
                   if not any(left <= match.start() < right for left, right in verbatim)]
    labels = {label_key(match[1]) for match in definitions}
    first_line = markdown.rfind('\n', 0, start) + 1
    last_line = markdown.find('\n', end)
    metadata = [(match.start(), match.end(), None) for match in definitions
                if match.end() > start and match.start() < end]
    for image in _IMAGE.finditer(markdown, first_line, last_line if last_line >= 0 else len(markdown)):
        if image['target'] is None and label_key(image['label'] or image['alt']) not in labels:
            continue
        if any(left <= image.start() < right for left, right in verbatim):
            continue
        metadata.append((image.start(), image.end(), image.span('alt')))
    cursor = start
    for left, right, readable in sorted(metadata):
        if right <= cursor or left >= end:
            continue
        if markdown[cursor:left].strip():
            return True
        if readable is not None:
            alt_start, alt_end = readable
            if markdown[max(cursor, alt_start):min(end, alt_end)].strip():
                return True
        cursor = right
    return cursor < end and bool(markdown[cursor:end].strip())


def looks_like_caption(value: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:figure|fig\.?|table|algorithm|scheme|图|表|算法)\s*[-.:：]?[\s\d一二三四五六七八九十]+",
            value,
            flags=re.IGNORECASE,
        )
    )


_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
_ATX_HEADING = re.compile(r'^ {0,3}(#{1,6})[ \t]+(.+?)\s*$')
_SETEXT_UNDERLINE = re.compile(r'^ {0,3}(=+|-+)[ \t]*$')
_PARAGRAPH_BOUNDARY = re.compile(r'^ {0,3}(?:>|[-*+][ \t]|\d+[.)][ \t]|<|!\[|\[[^\]]+\]:|(?:\*[ \t]*){3,}$|(?:_[ \t]*){3,}$)')


def protected_source_ranges(lines: list[str], *, strict: bool = True) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    table_start: int | None = None
    for number, line in enumerate(lines, 1):
        if "|" in line:
            table_start = table_start or number
        elif table_start is not None:
            table = lines[table_start - 1 : number - 1]
            if len(table) >= 2 and any(re.fullmatch(r"\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*", row) for row in table):
                ranges.append((table_start, number - 1))
            table_start = None
    if table_start is not None:
        table = lines[table_start - 1 :]
        if len(table) >= 2 and any(re.fullmatch(r"\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*", row) for row in table):
            ranges.append((table_start, len(lines)))

    ranges.extend(_delimited_source_ranges(lines, strict=strict))
    html_table = None
    for number, line in enumerate(lines, 1):
        if html_table is None and re.match(r'^ {0,3}<table\b', line, re.I):
            html_table = number
        if html_table is not None and re.search(r'</table\s*>', line, re.I):
            ranges.append((html_table, number))
            html_table = None
    for number, line in enumerate(lines, 1):
        if MARKDOWN_IMAGE_RE.search(line):
            if number < len(lines) and looks_like_caption(lines[number]):
                ranges.append((number, number + 1))
            if number > 1 and looks_like_caption(lines[number - 2]):
                ranges.append((number - 1, number))
    return ranges


def _delimited_source_ranges(lines, *, strict):
    ranges = []
    opening: tuple[str, int] | None = None
    for number, line in enumerate(lines, 1):
        marker = line.strip()
        fence = _FENCE.match(line)
        if opening is None:
            if fence:
                opening = (fence[1], number)
            elif marker in {"$$", "\\["}:
                opening = (marker, number)
        else:
            token, start = opening
            if token[0] in {"`", "~"}:
                closes = fence and fence[1].startswith(token) and not fence[2].strip()
            else:
                closes = marker == ("$$" if token == "$$" else "\\]")
            if closes:
                ranges.append((start, number))
                opening = None
    if opening is not None:
        if strict:
            raise WorkspaceError("reading_plan_invalid", "Source Markdown contains an unterminated protected block")
        ranges.append((opening[1], len(lines)))

    return ranges


def verbatim_ranges(markdown):
    """Return code and display math spans where Markdown image and emphasis syntax is literal."""
    lines = source_lines(markdown)
    starts = [0] + [match.end() for match in re.finditer('\n', markdown)]
    ranges = [(starts[first - 1], starts[last - 1] + len(lines[last - 1]))
              for first, last in _delimited_source_ranges(lines, strict=False)]
    ranges.extend(match.span() for match in re.finditer(r'(?<!`)(`+)(?!`)[^\n]+?(?<!`)\1(?!`)', markdown))
    return ranges


class SourceHeading(NamedTuple):
    level: int
    title: str
    last_line: int


def source_headings(lines, protected):
    headings = {}
    paragraph_start = None
    protected_lines = {line for start, end in protected for line in range(start, end + 1)}
    for number, line in enumerate(lines, 1):
        if number in protected_lines or not line.strip() or _PARAGRAPH_BOUNDARY.match(line):
            paragraph_start = None
            continue
        if atx := _ATX_HEADING.match(line):
            headings[number] = SourceHeading(len(atx[1]), atx[2].strip(), number)
            paragraph_start = None
        elif underline := _SETEXT_UNDERLINE.match(line):
            if paragraph_start is not None:
                title = ' '.join(part.strip() for part in lines[paragraph_start - 1:number - 1])
                level = 1 if underline[1].startswith('=') else 2
                headings[paragraph_start] = SourceHeading(level, title, number)
            paragraph_start = None
        elif paragraph_start is None and not line.startswith(('    ', '\t')):
            paragraph_start = number
    return headings


def source_heading_paths(lines, *, identifiers=False, headings=None):
    if headings is None:
        headings = source_headings(lines, protected_source_ranges(lines, strict=False))
    active = {}
    paths = []
    for number in range(1, len(lines) + 1):
        heading = headings.get(number)
        if heading:
            active = {level: value for level, value in active.items() if level < heading.level}
            active[heading.level] = f'section-{number}' if identifiers else heading.title
        paths.append(tuple(active.values()))
    return paths


class MarkdownBlocks:
    """Canonical line, heading and block bounds used for IR and older Bundles."""

    def __init__(self, markdown, *, pdf=None, blocks=None):
        self.markdown = markdown
        self.lines = source_lines(markdown)
        protected = protected_source_ranges(self.lines, strict=False)
        self.headings = source_headings(self.lines, protected)
        self.section_paths = source_heading_paths(self.lines, headings=self.headings)
        self.section_ids = source_heading_paths(self.lines, headings=self.headings, identifiers=True)
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line) + 1)
        self.blocks = blocks if blocks is not None else self._markdown_blocks(protected)
        if blocks is None and pdf is not None:
            self.blocks = self._with_pdf_blocks(pdf['blocks'])

    def _markdown_blocks(self, protected):
        heading_ranges = [(first, heading.last_line) for first, heading in self.headings.items()]
        protected = sorted(protected + heading_ranges)
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
                or MARKDOWN_IMAGE_RE.match(text.lstrip()) is not None)

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

    def line_span(self, start, stop):
        return [bisect_right(self.starts, start), bisect_right(self.starts, max(start, stop - 1))]
