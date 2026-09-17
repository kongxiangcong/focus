"""Local Markdown registration and metadata CLI shared by the Host agent and skills."""
import argparse
import uuid
import json
import re
import shutil
import tempfile
from pathlib import Path

from .source_library import SourceLibrary
from .reading_workspace import _validate_parser_bundle, _write_document


def import_markdown(workspace, original, *, title=None, short_name=None, language='zh', topic=None, uploader=None):
    original = Path(original)
    raw = original.read_bytes()
    content = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    if not content.strip():
        raise ValueError('Markdown 内容为空。')
    library = SourceLibrary(Path(workspace))
    existing = library.find_original(original, source_kind='article_markdown')
    if existing:
        sid = existing['source_id']
        if topic:
            library.attach(sid, topic_title=topic)
        if uploader and not existing.get('uploader'):
            library.describe(sid, uploader=uploader)
        return {'ok': True, 'source_id': sid, 'reused': True}
    heading = re.search(r'^#\s+(.+)$', content, re.M)
    title = title or (heading.group(1).strip() if heading else original.stem)
    staging = Path(tempfile.mkdtemp(prefix='.markdown-', dir=workspace))
    try:
        shutil.copyfile(original, staging / 'source.md')
        (staging / 'content.md').write_text(content, encoding='utf-8')
        (staging / 'images').mkdir()
        _write_document(staging / 'metadata.json', {'source_kind': 'article_markdown',
            'parser': 'markdown-import', 'language': language, 'task_id': 'local-' + uuid.uuid4().hex})
        _write_document(staging / 'validation.json', {'ok': True, 'warnings': []})
        _validate_parser_bundle(staging)
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
