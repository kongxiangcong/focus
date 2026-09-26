"""Read-only public GitHub retrieval, without arbitrary URLs or local paths."""
import base64
import json
import re
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


TOOL = {'name': 'implementation_lookup',
        'description': 'Search public GitHub repositories or read a repository text file. No execution or writes. Verify official ownership using Source evidence.',
        'inputSchema': {'type': 'object', 'properties': {
            'action': {'type': 'string', 'enum': ['search', 'read']},
            'query': {'type': 'string'}, 'repository': {'type': 'string'}, 'path': {'type': 'string'}},
            'required': ['action'], 'additionalProperties': False}}


class ImplementationSearch:
    def __init__(self):
        self.evidence = []

    def call(self, name, arguments):
        if name != TOOL['name'] or not isinstance(arguments, dict):
            raise ValueError('Unsupported tool')
        action = arguments.get('action')
        if action == 'search':
            query = arguments.get('query', '')
            if not isinstance(query, str) or not 1 <= len(query) <= 160:
                raise ValueError('Invalid query')
            route = 'search/repositories?' + urlencode({'q': query, 'per_page': 5})
        elif action == 'read':
            repository, path = arguments.get('repository', ''), arguments.get('path', '')
            if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
                raise ValueError('Invalid repository')
            if not isinstance(path, str) or not path or len(path) > 300 or any(
                    part in ('', '.', '..') for part in path.split('/')) or '\\' in path:
                raise ValueError('Invalid repository path')
            route = 'repos/' + repository + '/contents/' + quote(path, safe='/')
        else:
            raise ValueError('Unsupported action')
        url = 'https://api.github.com/' + route
        with urlopen(Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'FOCUS'}), timeout=20) as response:
            raw = response.read(300001)
        if len(raw) > 300000:
            raise ValueError('Repository response too large')
        data = json.loads(raw)
        if action == 'search':
            result = {'repositories': [{key: item.get(key) for key in ('full_name', 'description', 'html_url')}
                                        for item in data.get('items', [])[:5]]}
        elif data.get('type') == 'file' and data.get('encoding') == 'base64':
            result = {'repository': repository, 'path': path, 'url': data['html_url'],
                      'text': base64.b64decode(data['content'], validate=False).decode('utf-8')[:30000]}
        else:
            raise ValueError('A text file is required')
        self.evidence.append({'action': action, 'url': url})
        return result
