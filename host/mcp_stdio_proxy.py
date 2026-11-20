"""Forward newline-delimited MCP JSON-RPC to this turn's loopback ToolBridge."""
import json
import sys
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener


def main(url):
    address = urlsplit(url)
    if address.scheme != 'http' or address.hostname != '127.0.0.1' or not address.port:
        raise ValueError('FOCUS MCP bridge must be a loopback HTTP endpoint.')
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    client = build_opener(ProxyHandler({}))
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            print(json.dumps({'jsonrpc': '2.0', 'id': None,
                              'error': {'code': -32700, 'message': 'Invalid JSON'}}), flush=True)
            continue
        request = Request(url, data=line.encode('utf-8'), headers={
            'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
        })
        try:
            with client.open(request, timeout=3600) as response:
                if 'id' in message:
                    print(response.read().decode('utf-8'), flush=True)
        except (URLError, TimeoutError):
            if 'id' in message:
                print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'error': {
                    'code': -32603, 'message': 'FOCUS MCP bridge is unavailable.'}}), flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
