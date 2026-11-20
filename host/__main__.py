"""Start FOCUS and optionally select a registered Backend for this process."""
import argparse
import os
import sys
from pathlib import Path

from .backends import BackendError
from .configuration import UserSettings, resolve_startup
from .workbench import Workbench
from .server import Server



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(os.environ['FOCUS_WORKSPACE']) if os.getenv('FOCUS_WORKSPACE') else None)
    parser.add_argument('--host-data', type=Path, default=None)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--model', help='Override the selected Backend model (FOCUS_MODEL)')
    parser.add_argument('--backend-bin', help='Override the Backend executable path (FOCUS_BACKEND_BIN)')
    parser.add_argument('--network', action='store_true', help='Allow Agent network access (needed for MinerU); default requires approval')
    parser.add_argument('--approval-policy', choices=['on-request', 'untrusted'], default='on-request')
    parser.add_argument('--public-origin', default=os.getenv('FOCUS_PUBLIC_ORIGIN'))
    parser.add_argument('--backend', help='Select a registered Backend by ID (FOCUS_BACKEND)')
    parser.add_argument('--backends-dir', type=Path, help='Directory containing additional Backend manifests (FOCUS_BACKENDS_DIR)')
    parser.add_argument('--check-runtime', action='store_true', help='List discovered runtimes or check the selected executable without starting it')
    args = parser.parse_args()
    options = {'backend': args.backend, 'backend_bin': args.backend_bin, 'model': args.model}
    if args.check_runtime:
        settings = UserSettings(backends_dir=args.backends_dir)
        startup = resolve_startup(settings, **options)
        for error in settings.registry.errors:
            print(f'{error["file"]}: {error["message"]}', file=sys.stderr)
        if startup:
            if startup.error:
                raise BackendError(startup.error)
            value = startup.configuration
            print(f'{value["backend"]}: {value["runtimePath"]}')
        else:
            for backend in settings.projection()['backends']:
                print(f'{backend["id"]}: {backend["runtimePath"] or backend["unavailableReason"]}')
        return
    token = os.getenv('FOCUS_HOST_TOKEN')
    if args.bind not in ('127.0.0.1', 'localhost') and (not token or not args.public_origin):
        raise ValueError('Non-loopback requires FOCUS_HOST_TOKEN and --public-origin; use a trusted private network or HTTPS proxy')
    service = Workbench(workspace=args.workspace, backends_dir=args.backends_dir, network=args.network,
                        approval_policy=args.approval_policy, **options)
    server = Server((args.bind, args.port), service, token=token, public_origin=args.public_origin)
    print(f'FOCUS http://{args.bind}:{server.server_port}', flush=True)
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
