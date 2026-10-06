"""One machine preference and one active Workspace; no unbound business state."""
import json
import os
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from .configuration import UserSettings
from .backend_setup import BackendSetup
from .core_bridge import WorkspaceError
from .service import HostService
from core.workspace_lifecycle import create_workspace, inspect_workspace


class WorkspaceBinding:
    def __init__(self, settings_path):
        self.settings = UserSettings(settings_path)
        self.path = self.settings.path

    def read(self):
        if not self.path.exists():
            return None
        value = self.settings.document().get('workspace')
        if value is None:
            return None
        if not isinstance(value, dict) or not isinstance(value.get('path'), str) or not isinstance(value.get('workspaceId'), str):
            raise ValueError('已保存的工作区位置无效，请修正本机设置文件。')
        return value

    def save(self, value):
        document = self.settings.document()
        configuration = value.get('configuration')
        if configuration:
            document = self.settings.configured_document(configuration)
        document['workspace'] = {k: v for k, v in value.items() if k != 'configuration'}
        self.settings.write(document)


class Workbench:
    def __init__(self, *, settings_path=None, workspace=None, service_factory=HostService, **options):
        self.settings = UserSettings(settings_path)
        self.binding = WorkspaceBinding(self.settings.path)
        self.lock = threading.RLock()
        self.host = None
        self.generation = uuid.uuid4().hex
        self.setup = BackendSetup()
        self.error = None
        self.service_factory, self.options = service_factory, options
        try:
            self.saved_workspace = self.binding.read()
        except (ValueError, OSError) as exc:
            self.saved_workspace = None
            self.error = str(exc)
        if workspace is not None:
            # Explicit local CLI selection uses the same format/open boundary.
            self.bind({'mode': 'import', 'path': str(workspace)})
        elif self.saved_workspace:
            try:
                path = Path(self.saved_workspace['path'])
                manifest = inspect_workspace(path)
                if manifest['workspaceId'] != self.saved_workspace['workspaceId']:
                    raise WorkspaceError('workspace_identity_changed', '此位置的工作区身份已改变，请重新定位或明确导入。')
                self.host = self._open(path)
            except (OSError, ValueError, WorkspaceError) as exc:
                self.error = str(exc)

    def _open(self, path):
        return self.service_factory(path, None, settings_path=self.settings.path, **self.options)

    def status(self):
        with self.lock:
            workspace = None
            if self.host:
                workspace = {**self.host.lease.manifest, 'path': str(self.host.workspace),
                             'instanceId': self.host.lease.instance_id}
            return {'bound': self.host is not None, 'workspace': workspace, 'generation': self.generation,
                    'savedWorkspace': self.saved_workspace, 'error': self.error,
                    'operationId': (self.saved_workspace or {}).get('operationId'),
                    'busy': bool(self.host and self.host._configuration_busy())}

    def require_instance(self, instance):
        if not self.host or instance != self.host.lease.instance_id:
            raise WorkspaceError('workspace_instance_changed', '工作区已更换，请重新载入；旧草稿未提交。')
        self.host.lease.require_current()
        return self.host

    @contextmanager
    def operation(self, instance):
        # Switching shares admission order with every HTTP business operation.
        with self.lock:
            yield self.require_instance(instance)

    def bind(self, payload, *, expected_generation=None):
        with self.lock:
            if expected_generation is not None and expected_generation != self.generation:
                raise WorkspaceError('workspace_instance_changed', '工作区已更换，请重新载入；旧草稿未提交。')
            if self.host and self.host._configuration_busy():
                raise WorkspaceError('workspace_busy', '任务或批次运行中，请停止并等待后更换工作区。')
            mode = payload.get('mode')
            text = payload.get('path')
            if not isinstance(text, str) or not text.strip():
                raise ValueError('请输入运行 FOCUS 这台电脑上的目录。')
            path = Path(text.strip()).expanduser().resolve()
            if mode == 'create':
                name = payload.get('name', 'knowledge-base')
                if (not isinstance(name, str) or not name.strip() or name in ('.', '..')
                        or any(c in name for c in '/\\<>:"|?*') or name.rstrip(' .') != name):
                    raise ValueError('工作区名称无效，请使用单个目录名。')
                if not path.is_dir():
                    raise ValueError('请选择已存在的父目录。')
                path = path / name
                create_workspace(path)
            elif mode in ('import', 'relocate'):
                manifest = inspect_workspace(path)
                if mode == 'relocate' and (not self.saved_workspace or
                        manifest['workspaceId'] != self.saved_workspace['workspaceId']):
                    raise WorkspaceError('workspace_identity_changed', '重新定位必须选择原工作区；其他库请使用导入。')
            else:
                raise ValueError('请选择导入或新建工作区。')
            if self.host and path == self.host.workspace:
                return self.status()
            original_document = self.settings.document()
            target = self._open(path)
            old = self.host
            saved = False
            try:
                target.snapshot()
                selection = {'path': str(path), 'workspaceId': target.lease.manifest['workspaceId'],
                             'operationId': payload.get('requestId') or uuid.uuid4().hex}
                if payload.get('configuration'):
                    from .configuration import normalize
                    target._apply_configuration(normalize(payload['configuration']))
                    selection['configuration'] = payload['configuration']
                self.binding.save(selection)
                saved = True
                if old:
                    old.close()
            except BaseException:
                if saved:
                    self.settings.write(original_document)
                    if old and not old.lease.handle.closed:
                        old.shutting_down = False
                        old.retention_stop.clear()
                        if not old.retention_worker.is_alive():
                            old.retention_worker = threading.Thread(target=old._retain_logs, daemon=True)
                            old.retention_worker.start()
                target.close()
                raise
            self.host = target
            selection.pop('configuration', None)
            self.saved_workspace, self.error = selection, None
            self.generation = uuid.uuid4().hex
            return self.status()

    def configuration_status(self):
        with self.lock:
            return self.host.configuration_status() if self.host else self.settings.projection()

    def backend_setup(self, action, payload):
        with self.lock:
            host = self.host
        if host:
            return host.backend_setup(action, payload)
        try:
            return self.setup.operate(action, payload)
        except Exception:
            return {'backend': payload.get('backend'), 'runtimePath': None, 'status': 'failed',
                    'message': '后端设置操作失败，请检查认证和网络后重试。'}

    def choose_directory(self):
        from host.directory_picker import choose_directory
        return choose_directory()

    def close(self):
        with self.lock:
            self.setup.close()
            if self.host:
                self.host.close()
