#!/usr/bin/env python3
"""Conservative static self-contained-HTML preflight. Not a security/network proof."""
from __future__ import annotations
import argparse
import json
import re
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from pathlib import Path

@dataclass(frozen=True)
class Finding:
    line: int
    kind: str
    detail: str


def inline_resource(value: str) -> bool:
    value = value.strip().lower()
    return not value or value.startswith(('#', 'data:', 'blob:'))


def check_css(text: str, line: int = 1) -> list[Finding]:
    found = []
    clean = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    for match in re.finditer(r'url\(\s*([\'"]?)(.*?)\1\s*\)', clean, re.I | re.S):
        value = match.group(2).strip()
        if not inline_resource(value):
            found.append(Finding(line + clean[:match.start()].count('\n'), 'css-resource', value[:180]))
    for match in re.finditer(r'@import\b', clean, re.I):
        found.append(Finding(line + clean[:match.start()].count('\n'), 'css-import', 'CSS import requires review; inline the stylesheet.'))
    if re.search(r'@font-face\b', clean, re.I):
        found.append(Finding(line, 'embedded-font', 'Use system font stacks; do not package font data.'))
    return found


def check_script(text: str, line: int = 1) -> list[Finding]:
    # Heuristic by design: flags recognizable APIs even when the address is constructed.
    patterns = {
        'network-api': r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|WebTransport|sendBeacon|RTCPeerConnection)\s*\(',
        'module-import': r'\bimport\s*(?:\(|[\'"]|[^;\n]*\bfrom\b)',
        'worker': r'\b(?:Worker|SharedWorker)\s*\(',
        'service-worker': r'\bserviceWorker\s*\.\s*register\s*\(',
        'dynamic-code': r'\b(?:eval|Function)\s*\(',
        'dynamic-resource': r'\.\s*(?:src|srcset|poster)\s*=\s*[\'"](?!data:|blob:|#)',
        'dynamic-attribute': r'\bsetAttribute\s*\(\s*[\'"](?:src|srcset|poster)[\'"]',
    }
    result = []
    for kind, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            result.append(Finding(line + text[:match.start()].count('\n'), kind, match.group(0)[:180]))
    return result


class Inspector(HTMLParser):
    def __init__(self, depth: int = 0):
        super().__init__(convert_charrefs=True)
        self.depth = depth
        self.findings: list[Finding] = []
        self.links = 0
        self.current: str | None = None
        self.current_line = 1
        self.parts: list[str] = []
        self.script_type = ''

    def issue(self, kind: str, detail: str) -> None:
        self.findings.append(Finding(self.getpos()[0], kind, detail[:200]))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {k.lower(): (v or '') for k, v in attrs}
        for key, value in attributes.items():
            if key.startswith('on'):
                self.findings.extend(check_script(value, self.getpos()[0]))
            if key == 'style':
                self.findings.extend(check_css(value, self.getpos()[0]))
        # Automatic resource loads. Anchor navigation is recorded but is not an auto-load.
        automatic = {'src', 'poster', 'data', 'background', 'manifest'}
        for key in automatic:
            if key in attributes and (key != 'data' or tag == 'object'):
                if not inline_resource(attributes.get(key, '')):
                    self.issue('html-resource', f'<{tag}> {key}={attributes[key]}')
        if 'srcset' in attributes:
            # Conservative: even mixed data-URL srcsets require manual review.
            self.issue('srcset-review', 'Inline image srcsets are not parsed; use a single embedded src or review explicitly.')
        for key in ['href', 'xlink:href']:
            if key not in attributes:
                continue
            value = attributes[key]
            if tag == 'a':
                if re.match(r'javascript:', value, re.I):
                    self.issue('javascript-url', value)
                elif value and not inline_resource(value):
                    self.links += 1
            elif not inline_resource(value):
                self.issue('html-resource', f'<{tag}> {key}={value}')
        if tag == 'base':
            self.issue('base-url', 'A base URL can turn relative paths into network resources.')
        if tag in {'form', 'button', 'input'}:
            for key in ['action', 'formaction']:
                if key in attributes and attributes[key] and not attributes[key].startswith('#'):
                    self.issue('form-action', attributes[key])
        if 'ping' in attributes:
            self.issue('link-ping', attributes['ping'])
        if tag == 'meta' and attributes.get('http-equiv', '').lower() == 'refresh':
            self.issue('meta-refresh', attributes.get('content', ''))
        if 'srcdoc' in attributes:
            if self.depth >= 4:
                self.issue('nested-srcdoc', 'Nested srcdoc depth exceeded; manual review required.')
            else:
                child = inspect_text(attributes['srcdoc'], depth=self.depth+1)
                self.findings.extend(Finding(self.getpos()[0], 'srcdoc-'+i.kind, i.detail) for i in child.findings)
        if tag in {'script', 'style'}:
            self.current = tag
            self.current_line = self.getpos()[0]
            self.parts = []
            self.script_type = attributes.get('type', '').lower()

    def handle_data(self, data: str) -> None:
        if self.current:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self.current:
            return
        text = ''.join(self.parts)
        if tag == 'style':
            self.findings.extend(check_css(text, self.current_line))
        elif self.script_type not in {'application/json', 'application/ld+json'}:
            self.findings.extend(check_script(text, self.current_line))
        self.current = None
        self.parts = []


def inspect_text(text: str, depth: int = 0) -> Inspector:
    inspector = Inspector(depth)
    inspector.feed(text)
    inspector.close()
    return inspector


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('html', type=Path)
    parser.add_argument('--json', action='store_true', help='Machine-readable output.')
    args = parser.parse_args()
    try:
        result = inspect_text(args.html.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'ERROR: {exc}')
        return 2
    record = {'file': str(args.html), 'status': 'FAIL' if result.findings else 'PASS',
              'scope': 'static-preflight-only', 'user_navigation_links': result.links,
              'findings': [asdict(i) for i in result.findings]}
    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(f"{record['status']}: {args.html.name}; {len(result.findings)} findings; {result.links} user-activated links.")
        for item in result.findings:
            print(f'  line {item.line}: {item.kind}: {item.detail}')
        print('Scope: static heuristic only. Also test file:// behavior in a fresh network-blocked browser.')
    return 1 if result.findings else 0

if __name__ == '__main__':
    raise SystemExit(main())
