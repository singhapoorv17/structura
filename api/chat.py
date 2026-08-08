"""POST /api/chat — One chat turn against a deal. Every turn is a model operation or a refusal.

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

from lib_api.http import (  # noqa: E402
    log,
    method_not_allowed,
    preflight,
    read_json_body,
    serve_json,
)
from lib_api.analyse import run_chat  # noqa: E402

ROUTE = "/api/chat"


class handler(BaseHTTPRequestHandler):
    server_version = "structura"
    sys_version = ""

    def do_OPTIONS(self):  # noqa: N802
        preflight(self)

    def do_GET(self):  # noqa: N802
        method_not_allowed(self, "POST")

    def do_POST(self):  # noqa: N802
        serve_json(self, ROUTE, lambda: run_chat(read_json_body(self)))

    def log_message(self, fmt, *args):
        log("http.access", route=ROUTE, detail=fmt % args)
