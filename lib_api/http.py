"""BaseHTTPRequestHandler plumbing: bodies, headers, CORS, errors, logging.

Vercel's Python runtime loads each ``api/*.py`` file and looks for a top-level
``handler`` inheriting from ``BaseHTTPRequestHandler`` (or an ASGI/WSGI ``app``).
The class-based form is used here because it needs no third-party dependency —
adding FastAPI to a bundle that already carries scipy and numpy buys nothing and
costs cold-start time.

Nothing in this module knows anything about finance. It exists so the four
endpoint files contain only their own logic.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from typing import Any, Callable, Mapping

from lib_api.errors import ApiError

__all__ = [
    "MAX_REQUEST_BYTES",
    "log",
    "read_json_body",
    "send_json",
    "send_bytes",
    "serve_json",
    "serve_binary",
    "method_not_allowed",
    "preflight",
]

#: A compare request is a few hundred bytes. 256 KB is generous and keeps a
#: hostile client from streaming a gigabyte into a 2 GB function.
MAX_REQUEST_BYTES = 256 * 1024

_JSON = "application/json; charset=utf-8"

_CORS: Mapping[str, str] = {
    # Structura's frontend is same-origin on Vercel, so CORS is not needed in
    # production. It is here so `next dev` on :3000 can call `vercel dev` on
    # :3001, and so the endpoints are usable from a notebook.
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
}


def log(event: str, **fields: Any) -> None:
    """One structured line to stderr. Never to stdout, never to the client."""
    record = {"event": event, **fields}
    try:
        line = json.dumps(record, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        line = json.dumps({"event": event, "log_error": "unserialisable fields"})
    print(line, file=sys.stderr, flush=True)


def read_json_body(rh) -> Any:
    """Decode the request body, or raise a 400 the caller can act on."""
    raw_length = rh.headers.get("Content-Length")
    try:
        length = int(raw_length or 0)
    except (TypeError, ValueError):
        raise ApiError("Content-Length header is not an integer.") from None
    if length < 0:
        raise ApiError("Content-Length header is negative.")
    if length > MAX_REQUEST_BYTES:
        raise ApiError(
            f"Request body is {length} bytes; the limit is {MAX_REQUEST_BYTES}.",
            status=413,
        )
    if length == 0:
        return {}
    raw = rh.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise ApiError("Request body must be UTF-8 encoded JSON.") from None
    except json.JSONDecodeError as exc:
        raise ApiError(f"Request body is not valid JSON: {exc.msg}.") from None


def _write(rh, status: int, body: bytes, content_type: str, extra: Mapping | None):
    rh.send_response(status)
    rh.send_header("Content-Type", content_type)
    rh.send_header("Content-Length", str(len(body)))
    for key, value in _CORS.items():
        rh.send_header(key, value)
    for key, value in (extra or {}).items():
        rh.send_header(key, str(value))
    rh.end_headers()
    rh.wfile.write(body)


def send_json(rh, status: int, payload: Any, extra: Mapping | None = None) -> int:
    """Serialise and write. ``allow_nan=False`` is the last line of defence.

    :func:`lib_api.serialise.sanitise` should already have removed every
    non-finite float. If one survives, this raises rather than emitting the bare
    ``NaN`` token that ``JSON.parse`` rejects.
    """
    body = json.dumps(payload, allow_nan=False, default=str).encode("utf-8")
    _write(rh, status, body, _JSON, extra)
    return len(body)


def send_bytes(
    rh, status: int, body: bytes, content_type: str, extra: Mapping | None = None
) -> int:
    _write(rh, status, body, content_type, extra)
    return len(body)


def preflight(rh) -> None:
    rh.send_response(204)
    for key, value in _CORS.items():
        rh.send_header(key, value)
    rh.send_header("Content-Length", "0")
    rh.end_headers()


def method_not_allowed(rh, allowed: str) -> None:
    send_json(
        rh,
        405,
        {"error": f"Method not allowed. Use {allowed}."},
        {"Allow": f"{allowed}, OPTIONS"},
    )


def _handle_failure(rh, route: str, exc: BaseException, started: float) -> None:
    elapsed = (time.perf_counter() - started) * 1000.0
    if isinstance(exc, ApiError):
        log(
            "request.rejected",
            route=route,
            status=exc.status,
            field=exc.field,
            message=exc.message,
            ms=round(elapsed, 1),
        )
        send_json(rh, exc.status, exc.to_payload())
        return
    # Unexpected. The traceback goes to stderr where an operator can read it;
    # the client gets a sentence and nothing else.
    log(
        "request.failed",
        route=route,
        status=500,
        error_type=type(exc).__name__,
        ms=round(elapsed, 1),
        traceback=traceback.format_exc(),
    )
    send_json(
        rh,
        500,
        {
            "error": "Structura could not complete this run. The failure has "
            "been logged. If it repeats, the inputs are likely outside the "
            "range the engine can solve."
        },
    )


def serve_json(rh, route: str, produce: Callable[[], Any]) -> None:
    """Run ``produce`` and write its dict as JSON, mapping every failure mode."""
    started = time.perf_counter()
    try:
        payload = produce()
    except BaseException as exc:  # noqa: BLE001 - deliberate catch-all boundary
        _handle_failure(rh, route, exc, started)
        return
    try:
        size = send_json(rh, 200, payload)
    except ValueError as exc:  # allow_nan=False tripped
        _handle_failure(rh, route, exc, started)
        return
    log(
        "request.ok",
        route=route,
        status=200,
        bytes=size,
        ms=round((time.perf_counter() - started) * 1000.0, 1),
    )


def serve_binary(
    rh,
    route: str,
    produce: Callable[[], tuple[bytes, str, Mapping]],
) -> None:
    """As :func:`serve_json`, for an endpoint that returns a file."""
    started = time.perf_counter()
    try:
        body, content_type, extra = produce()
    except BaseException as exc:  # noqa: BLE001 - deliberate catch-all boundary
        _handle_failure(rh, route, exc, started)
        return
    size = send_bytes(rh, 200, body, content_type, extra)
    log(
        "request.ok",
        route=route,
        status=200,
        bytes=size,
        ms=round((time.perf_counter() - started) * 1000.0, 1),
    )
