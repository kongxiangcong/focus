"""Forward newline-delimited MCP JSON-RPC to this turn's loopback ToolBridge."""
import json
import sys
import threading
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
    output_lock = threading.Lock()

    def write(value):
        with output_lock:
            print(value, flush=True)

    def forward(line, message):
        request = Request(url, data=line.encode('utf-8'), headers={
            'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
        })
        try:
            with client.open(request, timeout=3600 if 'id' in message else 5) as response:
                if 'id' in message:
                    write(response.read().decode('utf-8'))
        except (URLError, TimeoutError):
            if 'id' in message:
                write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'error': {
                    'code': -32603, 'message': 'FOCUS MCP bridge is unavailable.'}}))

    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError()
        except ValueError:
            write(json.dumps({'jsonrpc': '2.0', 'id': None,
                              'error': {'code': -32700, 'message': 'Invalid JSON'}}))
            continue
        if 'id' in message:
            # Continue reading so MCP cancellation can reach the bridge during approval.
            threading.Thread(target=forward, args=(line, message), daemon=True).start()
        else:
            forward(line, message)


if __name__ == '__main__':
    main(sys.argv[1])
