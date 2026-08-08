"""Serve the api/*.py functions locally.

Vercel loads each file in api/ and looks for a top-level ``handler``. This does
the same thing on one port so the frontend can be exercised end to end without
the Vercel CLI. It imports the real handler classes — there is no second
implementation to drift.

Run:  python scripts/devapi.py [port]
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

API = ROOT / "api"


def load_handlers() -> dict[str, type]:
    out: dict[str, type] = {}
    for path in sorted(API.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"api_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handler = getattr(module, "handler", None)
        if handler is not None:
            out[f"/api/{path.stem}"] = handler
            out[f"/api/{path.stem.replace('_', '-')}"] = handler
    return out


HANDLERS = load_handlers()


class Router(BaseHTTPRequestHandler):
    server_version = "structura-dev"
    sys_version = ""

    def _dispatch(self, verb: str) -> None:
        route = self.path.split("?")[0].rstrip("/")
        target = HANDLERS.get(route)
        if target is None:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"error":"no such route"}')
            return
        # Rebind this connection onto the real handler class and run its verb.
        self.__class__ = target
        getattr(self, f"do_{verb}")()

    def do_GET(self):  # noqa: N802
        self._dispatch("GET")

    def do_POST(self):  # noqa: N802
        self._dispatch("POST")

    def do_OPTIONS(self):  # noqa: N802
        self._dispatch("OPTIONS")

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[devapi] {fmt % args}\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3112
    print(f"routes: {sorted(set(HANDLERS))}", file=sys.stderr)
    ThreadingHTTPServer(("127.0.0.1", port), Router).serve_forever()
