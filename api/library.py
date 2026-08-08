"""GET /api/library — The comparable-transactions corpus.

Vercel Python function. All logic lives in ``lib_api``; this file is only the
HTTP boundary.
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib_api.http import log, method_not_allowed, preflight, serve_json  # noqa: E402
from lib_api.analyse import run_library  # noqa: E402

ROUTE = "/api/library"


class handler(BaseHTTPRequestHandler):
    server_version = "structura"
    sys_version = ""

    def do_OPTIONS(self):  # noqa: N802
        preflight(self)

    def do_POST(self):  # noqa: N802
        method_not_allowed(self, "GET")

    def do_GET(self):  # noqa: N802
        serve_json(self, ROUTE, run_library)

    def log_message(self, fmt, *args):
        log("http.access", route=ROUTE, detail=fmt % args)
