"""POST /api/export — the lender-grade Excel workbook, as raw bytes.

Live formulas, not pasted values, with iterative calculation enabled so the
construction funding circularity resolves natively in Excel.

The 4.5 MB Vercel response body cap is enforced in
``lib_api.service.run_export``: the file is measured on disk and a 413 with a
JSON body is returned rather than a truncated workbook. The sample is ~55 KB.
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib_api.http import (  # noqa: E402
    log,
    method_not_allowed,
    preflight,
    read_json_body,
    serve_binary,
)
from lib_api.service import run_export  # noqa: E402

ROUTE = "/api/export"

XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _produce(request_handler):
    body, filename, warnings = run_export(read_json_body(request_handler))
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
        # Warnings cannot ride in the body of a binary response, so they ride
        # in a header. The contract's rule is that a PLACEHOLDER warning must
        # never be silently swallowed - it does not require a JSON envelope.
        # The full, un-truncated list is always available from /api/compare.
        "X-Structura-Warning-Count": str(len(warnings)),
    }
    if warnings:
        # Header values must be latin-1 and single-line.
        joined = " | ".join(w.replace("\n", " ") for w in warnings)
        headers["X-Structura-Warnings"] = (
            joined.encode("ascii", "replace").decode("ascii")[:1800]
        )
    return body, XLSX_MIME, headers


class handler(BaseHTTPRequestHandler):
    server_version = "structura"
    sys_version = ""

    def do_OPTIONS(self):  # noqa: N802
        preflight(self)

    def do_GET(self):  # noqa: N802
        method_not_allowed(self, "POST")

    def do_POST(self):  # noqa: N802
        serve_binary(self, ROUTE, lambda: _produce(self))

    def log_message(self, fmt, *args):
        log("http.access", route=ROUTE, detail=fmt % args)
