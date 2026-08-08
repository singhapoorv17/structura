"""One exception type, one JSON error shape.

``400 {"error": "message", "field": "capex"}`` for validation,
``500 {"error": "..."}`` otherwise, and **never a stack trace**.
Everything that is a caller's fault raises :class:`ApiError`; everything else
escapes to the handler, which logs the traceback to stderr and returns an
opaque 500.
"""

from __future__ import annotations

__all__ = ["ApiError"]


class ApiError(Exception):
    """A client-visible failure with a status, a message and an optional field."""

    __slots__ = ("message", "status", "field", "extra")

    def __init__(
        self,
        message: str,
        *,
        status: int = 400,
        field: str | None = None,
        extra: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.field = field
        self.extra = extra or {}

    def to_payload(self) -> dict:
        payload: dict = {"error": self.message}
        if self.field is not None:
            payload["field"] = self.field
        payload.update(self.extra)
        return payload
