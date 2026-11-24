"""Canonical Markdown lines and block bounds shared by the source tools."""
from .pdf_layout import layout
from .source_ir_document import load_source_ir, project_source_blocks, project_source_sections
from .source_markdown import MarkdownBlocks, has_readable_text, source_lines
from .source_provenance import SOURCE_ORIGINALS
from .workspace_errors import WorkspaceError


class SourceBlocks(MarkdownBlocks):
    def __init__(self, bundle, markdown=None, *, pdf=None):
        if markdown is None:
            markdown = (bundle / 'content.md').read_text(encoding='utf-8', errors='replace')
        ir = None
        if bundle is not None:
            ir = load_source_ir(bundle, markdown)
            if (bundle / SOURCE_ORIGINALS['paper_pdf']).is_file():
                pdf = layout(bundle, markdown=markdown, source_ir=ir)
        self.pdf = pdf
        self.sections = project_source_sections(ir) if ir is not None else None
        super().__init__(markdown, pdf=pdf, blocks=project_source_blocks(ir) if ir else None)

    def block_ids_at(self, start, stop):
        if start >= stop:
            return []
        return list(dict.fromkeys(block['block_id'] for block in self.blocks
                                  if block['offsets'][0] < stop and start < block['offsets'][1]))

    def chunk_block_ids(self, start, end):
        return self.block_ids_at(self.starts[start - 1], self.starts[end] - 1)

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

    def has_readable_text(self, start, end):
        return has_readable_text(self.markdown, start, end)

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
