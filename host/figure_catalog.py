"""Read-only figure projection; does not reparse or mutate a Parser Bundle."""
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from core.reading_workspace import MARKDOWN_IMAGE_DETAIL_RE, _split_image_target

CAPTION = re.compile(r'^\s*(?:图|fig(?:ure)?\.?|table|tab\.?|表|equation|formula|公式)\s*[-.:：]?\s*\d+', re.I)
NECESSARY = re.compile(r'^\s*(?:table|tab\.?|表|equation|formula|公式)(?:\s*[-.:：]?\s*\d+|\s*$)', re.I)


class HtmlFigures(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.figures = []
        self.caption = None
        self.figure_start = 0
        self.protected = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'figure':
            self.figure_start = len(self.figures)
        if tag == 'figcaption':
            self.caption = []
        if tag == 'img':
            src = attrs.get('src', '')
            if any(t in ('table', 'pre', 'code', 'math') or protected for t, protected in self.stack) or \
                    attrs.get('role') == 'math' or re.search(r'\b(?:equation|math)\b', attrs.get('class', '')) or \
                    re.match(r'^(?:equation|formula|公式)(?:\s|$)', attrs.get('alt', ''), re.I):
                self.protected.add(src)
            else:
                self.figures.append((self.getpos(), src, attrs.get('alt', '')))
        if tag not in ('img', 'br', 'hr', 'input', 'meta', 'link', 'source', 'wbr'):
            self.stack.append((tag, attrs.get('role') == 'math' or bool(re.search(r'\b(?:equation|math)\b', attrs.get('class', '')))))

    def handle_endtag(self, tag):
        if tag == 'figcaption' and self.caption is not None:
            caption = ''.join(self.caption).strip()
            for i in range(self.figure_start, len(self.figures)):
                pos, src, _ = self.figures[i]
                self.figures[i] = (pos, src, caption)
            self.caption = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.caption is not None:
            self.caption.append(data)


def source_figures(bundle: Path, markdown: str):
    """Ordered local images, including raw HTML; formulas/tables stay in the text."""
    lines = markdown.splitlines()
    html = HtmlFigures()
    # Ignore literal HTML/images in fenced code and Markdown tables.
    filtered = []
    fenced = False
    candidates = []
    for index, line in enumerate(lines):
        if re.match(r'^\s*(```|~~~)', line):
            fenced = not fenced
        table = line.lstrip().startswith('|') or index + 1 < len(lines) and bool(re.match(r'^\s*\|?\s*:?-{3,}', lines[index + 1]))
        filtered.append('' if fenced or table else line)
        if fenced or table:
            continue
        for match in MARKDOWN_IMAGE_DETAIL_RE.finditer(line):
            src = _split_image_target(match.group(2))
            caption = match.group(1).strip()
            if NECESSARY.match(caption):
                continue
            following = index + 1
            while following < len(lines) and not lines[following].strip():
                following += 1
            if following < len(lines) and CAPTION.match(lines[following]):
                caption_lines = []
                while following < len(lines) and lines[following].strip() and not MARKDOWN_IMAGE_DETAIL_RE.search(lines[following]) and not lines[following].startswith('#'):
                    caption_lines.append(lines[following]); following += 1
                caption = '\n'.join(caption_lines).strip()
            candidates.append(((index + 1, match.start()), src, caption))
    html.feed('\n'.join(filtered))
    candidates.extend(html.figures)
    protected_paths = {(bundle / unquote(urlsplit(src.replace('\\', '/')).path)).resolve() for src in html.protected}
    seen = set()
    for _, src, caption in sorted(candidates):
        if NECESSARY.match(caption):
            continue
        parsed = urlsplit(src.replace('\\', '/'))
        if parsed.scheme or parsed.netloc:
            continue
        path = (bundle / unquote(parsed.path)).resolve()
        if not path.is_relative_to(bundle.resolve()) or not path.is_file() or path in seen or path in protected_paths or 'equations' in path.parts:
            continue
        seen.add(path)
        yield {'path': str(path), 'caption': caption}
