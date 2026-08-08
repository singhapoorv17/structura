"""``lib_api`` — the shared Python layer behind the ``api/*.py`` Vercel functions.

The Vercel Python runtime turns every file in ``api/`` into its own function, so
nothing shared can live there. This package holds the parts that must be
identical across endpoints:

``errors``      the one exception type that maps cleanly onto an HTTP status
``validate``    request parsing, type checking and the DoS guardrails
``build``       request -> ``ProjectInputs`` / ``DebtTerms`` / ``TaxProject`` / configs
``serialise``   engine objects -> the JSON response shape
``service``     the two real operations: compare, and export
``http``        BaseHTTPRequestHandler plumbing, CORS, structured logging

Nothing in here computes finance. Every number comes from ``engine`` and is
passed through unchanged; the only transformations are enum -> string,
dataclass -> dict, and non-finite float -> ``null`` (with a warning, never a
silent drop).
"""

from __future__ import annotations

__all__ = ["errors", "validate", "build", "serialise", "service", "http"]
