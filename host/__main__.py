"""python -m host --workspace ./knowledge-base [--backend codex|deepseek]"""
import argparse
import os
import sys
from pathlib import Path

from .backends import DEFAULT_BACKEND, BackendError, backend_names, check_backend
from .workbench import Workbench
from .server import Server



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(os.environ['FOCUS_WORKSPACE']) if os.getenv('FOCUS_WORKSPACE') else None)
    parser.add_argument('--host-data', type=Path, default=None)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--model', default=os.getenv('FOCUS_MODEL'))
    parser.add_argument('--codex-bin', default=os.getenv('FOCUS_CODEX_BIN'))
    parser.add_argument('--network', action='store_true', help='Allow Agent network access (needed for MinerU); default requires approval')
    parser.add_argument('--approval-policy', choices=['on-request', 'untrusted'], default='on-request')
    parser.add_argument('--public-origin', default=os.getenv('FOCUS_PUBLIC_ORIGIN'))
    parser.add_argument('--backend', default=os.getenv('FOCUS_BACKEND'), choices=backend_names(),
                        help='Agent runtime that serves reading turns; UI and Core stay identical')
    parser.add_argument('--check-runtime', action='store_true', help='Verify the selected backend and exit')
    args = parser.parse_args()
    if args.check_runtime:
        args.backend = args.backend or DEFAULT_BACKEND
        backend = check_backend(args.backend, args.codex_bin)
        print(f'{args.backend}: {backend}')
        return
    token = os.getenv('FOCUS_HOST_TOKEN')
    if args.bind not in ('127.0.0.1', 'localhost') and (not token or not args.public_origin):
        raise ValueError('Non-loopback requires FOCUS_HOST_TOKEN and --public-origin; use a trusted private network or HTTPS proxy')
    service = Workbench(workspace=args.workspace, model=args.model, codex_bin=args.codex_bin,
                        backend=args.backend, network=args.network, approval_policy=args.approval_policy)
    server = Server((args.bind, args.port), service, token=token, public_origin=args.public_origin)
    print(f'FOCUS http://{args.bind}:{args.port}', flush=True)
    if not server.local_access and not token:
        print(f'访问口令: {server.token}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        service.close()
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except BackendError as exc:
        # Misconfiguration, not a crash: the hint is the whole message.
        print(f'FOCUS 后端未就绪：{exc}', file=sys.stderr)
        raise SystemExit(2)
