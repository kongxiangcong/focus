"""Publish synthetic legacy test layouts as v1 fixtures, never user migration."""
import uuid
from host.service import HostService as RealHostService
from host.core_bridge import ROOT
from core.reading_workspace import _write_document
from core.workspace_lifecycle import MANIFEST


def publish_workspace(workspace):
    if not (workspace / MANIFEST).exists() and workspace.exists():
        _write_document(workspace / MANIFEST, {'workspaceId': str(uuid.uuid4()),
            'formatVersion': 1, 'minimumReader': 1, 'minimumWriter': 1})


def HostService(workspace, data, **kwargs):
    publish_workspace(workspace)
    return RealHostService(workspace, data, **kwargs)
