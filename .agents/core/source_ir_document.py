"""Read the versioned Source IR document and project its canonical block bounds."""
import json

from .source_provenance import SOURCE_ORIGINALS, bundle_fingerprint, file_digest


IR_VERSION = 1
IR_FILE = 'source-ir.json'
ORIGINALS = {'paper_pdf': 'source.pdf', 'article_html': 'source.html', 'article_markdown': 'source.md'}


class IRSerializer:
    @staticmethod
    def markdown(ir):
        blocks = ''.join(block['separator_before'] + block['markdown'] for block in ir['blocks'])
        return blocks + ir['trailing_separator']


def load_source_ir(bundle, markdown):
    try:
        ir = json.loads((bundle / IR_FILE).read_text(encoding='utf-8'))
        if type(ir['ir_version']) is not int or ir['ir_version'] != IR_VERSION or ir['source_kind'] not in SOURCE_ORIGINALS:
            return None
        if IRSerializer.markdown(ir) != markdown or ir['trailing_separator'].strip():
            return None
        original = bundle / SOURCE_ORIGINALS[ir['source_kind']]
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


def project_source_sections(ir):
    sections = ir.get('sections')
    if not isinstance(sections, list):
        return None
    headings = {block['block_id']: block for block in ir['blocks'] if block.get('kind') == 'heading'}
    result, seen = [], {None}
    previous = 0
    for section in sections:
        try:
            key, parent = section['section_id'], section['parent_id']
            first, last = section['source_lines']
            level, title, start = section['level'], section['title'], section['block_ids'][0]
            heading = headings[start]
            if (not isinstance(key, str) or not key or key in seen or parent not in seen
                    or not isinstance(title, str) or not title or type(level) is not int or not 1 <= level <= 6
                    or type(first) is not int or type(last) is not int or not previous < first <= last
                    or heading.get('section_id') != key or heading['anchors']['markdown']['source_lines'][0] != first):
                return None
        except (TypeError, ValueError, KeyError, IndexError):
            return None
        result.append({'id': key, 'parentId': parent, 'level': level, 'title': title,
                       'sourceLines': [first, last], 'startBlockId': start})
        seen.add(key)
        previous = first
    return result if len(result) == len(headings) else None
