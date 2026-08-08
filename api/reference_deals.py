"""GET /api/reference-deals — the calibrated demo set.

The contract's path is hyphenated; a Python module cannot be. ``vercel.json``
rewrites ``/api/reference-deals`` onto this file, and the underscored path stays
live as an alias.
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib_api.http import log, method_not_allowed, preflight, serve_json  # noqa: E402
from lib_api.service import run_reference_deals  # noqa: E402

ROUTE = "/api/reference-deals"


class handler(BaseHTTPRequestHandler):
    server_version = "structura"
    sys_version = ""

    def do_OPTIONS(self):  # noqa: N802
        preflight(self)

    def do_POST(self):  # noqa: N802
        method_not_allowed(self, "GET")

    def do_GET(self):  # noqa: N802
        serve_json(self, ROUTE, run_reference_deals)

    def log_message(self, fmt, *args):
        log("http.access", route=ROUTE, detail=fmt % args)
