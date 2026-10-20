#!/usr/bin/env python3
"""Validate this skill's limited packaging profile, assets and specified contrast pairs."""
from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import unquote
from build_starters import ROOT, outputs
from check_offline import inspect_text


def luminance(color: str) -> float:
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        raise ValueError(f'Contrast checker accepts opaque #RRGGBB only: {color}')
    rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    return sum(a*b for a, b in zip(linear, [.2126, .7152, .0722]))


def contrast(a: str, b: str) -> float:
    x, y = sorted([luminance(a), luminance(b)])
    return (y+.05)/(x+.05)


def validate() -> tuple[list[str], dict[str, float]]:
    errors = []
    text = (ROOT/'SKILL.md').read_text(encoding='utf-8')
    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
        errors.append('SKILL.md missing frontmatter delimiters.')
        return errors, {}
    front = text.split('---', 2)[1]
    name = re.search(r'^name:\s*(\S+)\s*$', front, re.M)
    description = re.search(r'^description:\s*(.+)$', front, re.M)
    if not name or name.group(1) != ROOT.name or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name.group(1)):
        errors.append('Name must match skill folder and kebab-case profile.')
    if not description or not 1 <= len(description.group(1)) <= 1024:
        errors.append('Description missing or exceeds 1024 characters.')
    if len(text.splitlines()) > 500:
        errors.append('SKILL.md exceeds 500-line disclosure budget.')
    if 'disable-model-invocation: true' not in front:
        errors.append('Explicit-only extension missing.')
    metadata = (ROOT/'agents/openai.yaml').read_text(encoding='utf-8')
    if 'allow_implicit_invocation: false' not in metadata or '$editorial-ui' not in metadata:
        errors.append('Codex explicit-invocation metadata missing.')
    # This is intentionally NOT a general YAML or official skill-schema validator.
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if '://' in target or target.startswith('#'):
            continue
        path = (ROOT/unquote(target.split('#')[0])).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.exists():
            errors.append(f'Missing/outside local reference: {target}')
    for path in ROOT.rglob('*'):
        if path.suffix.lower() in {'.ttf', '.otf', '.woff', '.woff2', '.mp3', '.wav'}:
            errors.append(f'Forbidden bundled binary asset: {path.relative_to(ROOT)}')
    for path, generated in outputs().items():
        if not path.exists() or path.read_text(encoding='utf-8') != generated:
            errors.append(f'Stale generated asset: {path.relative_to(ROOT)}')
        if path.suffix == '.html' and path.exists():
            for finding in inspect_text(path.read_text(encoding='utf-8')).findings:
                errors.append(f'{path.name}: {finding.kind}: {finding.detail}')
    data = json.loads((ROOT/'assets/design-tokens.json').read_text(encoding='utf-8'))
    pairs = {}
    for mode, values in data['themes'].items():
        for foreground, background, minimum in data['contrast_pairs']:
            ratio = contrast(values[foreground], values[background])
            label = f'{mode}:{foreground}/{background}'
            pairs[label] = round(ratio, 3)
            if ratio < minimum:
                errors.append(f'{label}: {ratio:.3f}:1 below {minimum}:1')
    return errors, pairs


def main() -> int:
    try:
        errors, pairs = validate()
        record = {'status': 'FAIL' if errors else 'PASS', 'errors': errors, 'contrast_pairs': pairs,
                  'scope': 'bundle-profile and specified opaque token pairs; not official conformance or full accessibility audit'}
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'ERROR: {exc}')
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
