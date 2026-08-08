"""POST /api/compare — one project through all five 2026 structures, ranked.

Vercel Python function. The runtime loads this file and looks for the top-level
``handler`` class; the route is the file path, so this is ``/api/compare``.

All logic lives in ``lib_api`` so it can be tested without a server. This file
is only the HTTP boundary.
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler

# The bundle preserves the project layout, so the repository root - which holds
# `engine/`, `export/` and `lib_api/` - is one directory up. Vercel does not
# guarantee it is on sys.path, so put it there explicitly.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib_api.http import (  # noqa: E402
    log,
    method_not_allowed,
    preflight,
    read_json_body,
    serve_json,
)
from lib_api.service import run_compare  # noqa: E402

ROUTE = "/api/compare"


class handler(BaseHTTPRequestHandler):
    server_version = "structura"
    sys_version = ""

    def do_OPTIONS(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        preflight(self)

    def do_GET(self):  # noqa: N802
        method_not_allowed(self, "POST")

    def do_POST(self):  # noqa: N802
        serve_json(self, ROUTE, lambda: run_compare(read_json_body(self)))

    def log_message(self, fmt, *args):  # noqa: D102 - silence the default log
        log("http.access", route=ROUTE, detail=fmt % args)
