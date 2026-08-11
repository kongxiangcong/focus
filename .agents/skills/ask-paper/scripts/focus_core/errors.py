from __future__ import annotations


class FocusError(Exception):
    """A stable, user-actionable workflow failure."""

    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "ok": False,
            "error": self.code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result
