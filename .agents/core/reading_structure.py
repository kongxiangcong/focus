"""Source-anchored plan structure, separate from verbatim chunk headings."""
import json
from .reading_workspace import WorkspaceError


def validate_structure(value, chunks):
    def invalid(message):
        raise WorkspaceError('reading_plan_invalid', 'Article structure: ' + message)

    if not isinstance(value, dict) or set(value) != {'nodes', 'chunk_nodes'}:
        invalid('expected nodes and chunk_nodes')
    nodes, bindings = value['nodes'], value['chunk_nodes']
    if not isinstance(nodes, list) or not nodes or not isinstance(bindings, list) or len(bindings) != len(chunks):
        invalid('every chunk needs one node')
    known, sibling_ends = {}, {}
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {'id', 'parent_id', 'title', 'description', 'source_lines'}:
            invalid('invalid node fields')
        key, parent = node['id'], node['parent_id']
        if not isinstance(key, str) or not key or key in known or (parent is not None and (not isinstance(parent, str) or parent not in known)):
            invalid('unique ids and parents before children required')
        if not isinstance(node['title'], str) or not node['title'].strip() or len(node['title']) > 32:
            invalid('title must be 1-32 characters')
        if not isinstance(node['description'], str) or not node['description'].strip() or len(node['description']) > 160:
            invalid('description must be 1-160 characters')
        span = node['source_lines']
        if not isinstance(span, list) or len(span) != 2 or any(type(n) is not int for n in span):
            invalid('invalid source anchor')
        start, end = span
        if start < 1 or end < start or end > chunks[-1]['source_lines'][1]:
            invalid('source anchor outside readable source')
        if parent is not None:
            a, b = known[parent]['source_lines']
            if start < a or end > b:
                invalid('child outside parent')
        if start <= sibling_ends.get(parent, 0):
            invalid('siblings must follow source order without overlap')
        sibling_ends[parent] = end
        known[key] = node
    used = set()
    for chunk, key in zip(chunks, bindings):
        if not isinstance(key, str) or key not in known:
            invalid('unknown chunk node')
        start, end = known[key]['source_lines']
        a, b = chunk['source_lines']
        if a < start or b > end:
            invalid('chunk outside assigned node')
        while key is not None:
            used.add(key)
            key = known[key]['parent_id']
    if used != set(known):
        invalid('nodes must contain reading content')
    return value


def legacy_structure(chunks):
    """Read-only fallback; no invented explanations or asset migration."""
    nodes, bindings, active = [], [], []
    for chunk in chunks:
        path = chunk['section_path'] or ['正文']
        common = 0
        while common < min(len(active), len(path)) and active[common]['title'] == path[common]:
            common += 1
        active = active[:common]
        for title in path[common:]:
            node = {'id': f'section-{len(nodes)+1:03d}', 'parent_id': active[-1]['id'] if active else None,
                    'title': title, 'description': '', 'source_lines': list(chunk['source_lines'])}
            nodes.append(node)
            active.append(node)
        for node in active:
            node['source_lines'][1] = chunk['source_lines'][1]
        bindings.append(active[-1]['id'])
    return {'nodes': nodes, 'chunk_nodes': bindings}


def read_structure(root, chunks):
    path = root / 'structure.json'
    if not path.is_file():
        return legacy_structure(chunks)
    return validate_structure(json.loads(path.read_text(encoding='utf-8')), chunks)
