"""Install FOCUS Host dependencies and record stable CLI entry points."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from host.configuration import UserSettings


def discover(settings):
    paths = {}
    for spec in settings.registry.list_specs():
        command = Path(spec.command[0]).expanduser()
        if command.parent != Path('.') and not command.is_absolute():
            command = spec.directory / command
        entry = shutil.which(str(command))
        if entry:
            paths[spec.id] = os.path.abspath(entry)
    document = settings.document()
    previous = document.get('discoveredRuntimes', {})
    for backend in previous.keys() | paths.keys():
        for preference in (document if document.get('backend') == backend else {},
                           document.get('preferences', {}).get(backend, {})):
            if preference.get('runtimePath') and (backend in paths or preference['runtimePath'] == previous.get(backend)):
                preference['runtimePath'] = paths.get(backend)
    document['discoveredRuntimes'] = paths
    settings.write(document)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discover-only', action='store_true', help='Only update local CLI paths')
    args = parser.parse_args()
    settings = UserSettings()
    paths = discover(settings)
    if not args.discover_only:
        root = Path(__file__).resolve().parent
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'host/requirements.txt'], cwd=root, check=True)
        pnpm = shutil.which('pnpm')
        if not pnpm:
            parser.error('请安装 pnpm 后重新运行部署脚本。')
        subprocess.run([pnpm, 'install', '--frozen-lockfile'], cwd=root, check=True)
        subprocess.run([pnpm, 'reader:build'], cwd=root, check=True)
    print(f'本机设置：{settings.path}')
    for backend, path in paths.items():
        print(f'{backend}: {path}')
    if not paths:
        print('未发现 CLI，请安装后重新运行部署脚本。')
    print('启动：python -m host --network\n访问：http://127.0.0.1:8333/')


if __name__ == '__main__':
    main()
