"""Local Markdown registration and metadata CLI shared by the Host agent and skills."""
import argparse
import uuid
import json
import re
import shutil
import tempfile
from pathlib import Path

from .source_library import SourceLibrary, normalize_short_name
from .reading_workspace import WorkspaceError, _validate_parser_bundle, _write_document


def _read_markdown(original):
    raw = original.read_bytes()
    content = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    if not content.strip():
        raise ValueError('Markdown 内容为空。')
    return raw, content


def _write_markdown_candidate(candidate, raw, content, *, language):
    from .source_ir import build_source_ir, publish_source_ir

    candidate.mkdir(parents=True, exist_ok=True)
    (candidate / 'source.md').write_bytes(raw)
    (candidate / 'images').mkdir()
    _write_document(candidate / 'metadata.json', {'source_kind': 'article_markdown',
        'parser': 'markdown-import', 'language': language, 'task_id': 'local-' + uuid.uuid4().hex})
    _write_document(candidate / 'validation.json', {'ok': True, 'warnings': []})
    publish_source_ir(candidate, build_source_ir(candidate, content, source_kind='article_markdown'))
    _validate_parser_bundle(candidate)


def _markdown_title(content, stem):
    heading = re.search(r'^#[ \t]+([^\n]+)$', content, re.M)
    return (heading.group(1).strip() if heading else '') or stem


class LocalMarkdownParser:
    model = 'local-markdown-v1'
    language = 'zh'

    def __init__(self, file_name):
        self.stem = Path(file_name).stem

    def parse(self, source, candidate, *, checkpoint=None):
        from .ingestion import persist_candidate_result

        raw, content = _read_markdown(source)
        title = _markdown_title(content, self.stem)
        short_name = 'Markdown'
        for proposed in (title, self.stem):
            try:
                short_name = normalize_short_name(proposed)
            except WorkspaceError:
                continue
            break
        _write_markdown_candidate(candidate, raw, content, language=self.language)
        result = {'title': title, 'short_name': short_name}
        persist_candidate_result(candidate, result)
        return result


def import_markdown(workspace, original, *, title=None, short_name=None, language='zh', topic=None, uploader=None):
    original = Path(original)
    raw, content = _read_markdown(original)
    library = SourceLibrary(Path(workspace))
    existing = library.find_original(original, source_kind='article_markdown')
    if existing:
        sid = existing['source_id']
        if topic:
            library.attach(sid, topic_title=topic)
        if uploader and not existing.get('uploader'):
            library.describe(sid, uploader=uploader)
        return {'ok': True, 'source_id': sid, 'reused': True}
    title = title or _markdown_title(content, original.stem)
    staging = Path(tempfile.mkdtemp(prefix='.markdown-', dir=workspace))
    try:
        _write_markdown_candidate(staging, raw, content, language=language)
        result = library.register(staging, source_kind='article_markdown', title=title,
            short_name=short_name or title, identity='markdown:' + uuid.uuid4().hex, topic_title=topic)
        if uploader:
            library.describe(result['source_id'], uploader=uploader)
        return result
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    ingest = commands.add_parser('markdown')
    ingest.add_argument('file', type=Path)
    ingest.add_argument('--title')
    ingest.add_argument('--short-name')
    ingest.add_argument('--language', choices=['zh', 'en'], default='zh')
    ingest.add_argument('--topic')
    describe = commands.add_parser('describe')
    describe.add_argument('--source-id', required=True)
    describe.add_argument('--venue')
    describe.add_argument('--published-at')
    started = commands.add_parser('start-reading')
    started.add_argument('--source-id', required=True)
    for command in (ingest, describe, started):
        command.add_argument('--workspace', type=Path, required=True)
    for command in (ingest, describe):
        command.add_argument('--uploader')
    args = parser.parse_args()
    if args.command == 'markdown':
        result = import_markdown(args.workspace, args.file, title=args.title, short_name=args.short_name,
            language=args.language, topic=args.topic, uploader=args.uploader)
    else:
        library = SourceLibrary(args.workspace)
        if args.command == 'describe':
            library.describe(args.source_id, uploader=args.uploader, venue=args.venue, published_at=args.published_at)
        else:
            library.start_reading(args.source_id)
        result = {'ok': True, 'source_id': args.source_id}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
