"""GET /api/current-law — the citation registry, rendered for the moat page.

SPEC §4.1: *"Current law is the moat. Every tax rule carries a citation and a
'verified on' date in code. A /current-law page renders them."* This endpoint is
that render feed. It reads ``engine.tax.citations`` directly, so the page cannot
drift from the rules the engine actually applies, and it returns the
unverified/placeholder block separately because honest gaps are a feature
(SPEC §4.3).

``vercel.json`` rewrites the hyphenated contract path onto this file.
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lib_api.http import log, method_not_allowed, preflight, serve_json  # noqa: E402
from lib_api.service import run_current_law  # noqa: E402

ROUTE = "/api/current-law"


class handler(BaseHTTPRequestHandler):
    server_version = "structura"
    sys_version = ""

    def do_OPTIONS(self):  # noqa: N802
        preflight(self)

    def do_POST(self):  # noqa: N802
        method_not_allowed(self, "GET")

    def do_GET(self):  # noqa: N802
        serve_json(self, ROUTE, run_current_law)

    def log_message(self, fmt, *args):
        log("http.access", route=ROUTE, detail=fmt % args)
