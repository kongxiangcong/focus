"""Physical originals and content fingerprints that bind Parser Bundle assets."""
import hashlib
from functools import lru_cache
from pathlib import Path


SOURCE_ORIGINALS = {'paper_pdf': 'source.pdf', 'article_html': 'source.html', 'article_markdown': 'source.md'}


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=256)
def _digest(path, identity):
    return file_fingerprint(path)


def file_digest(path):
    stat = path.stat()
    return _digest(path, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))


def bundle_fingerprint(bundle: Path, *, markdown: bytes | None = None) -> str:
    """Fingerprint canonical Markdown and the Bundle images it references."""
    bundle = Path(bundle).resolve()
    digest = hashlib.sha256()
    content = bundle / "content.md"
    if markdown is not None:
        digest.update(markdown)
    elif content.is_file():
        digest.update(content.read_bytes())
    images = bundle / "images"
    if images.is_dir():
        for path in sorted(images.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(images).as_posix().encode("utf-8"))
                digest.update(path.read_bytes())
    return digest.hexdigest()


def text_fingerprint(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def quote_fingerprint(text):
    return 'sha256:' + text_fingerprint(text)
