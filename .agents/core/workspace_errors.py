"""Canonical exception for Core operations on a Reading Workspace."""


class WorkspaceError(RuntimeError):
    def __init__(self, error_id: str, message: str):
        super().__init__(message)
        self.error_id = error_id
