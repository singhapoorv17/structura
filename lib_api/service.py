"""The two real operations behind the endpoints: compare, and export.

Kept out of the handler files so they can be unit-tested by calling a function,
with no server, no socket and no Vercel emulation. ``tests/test_api_*.py``
import this module directly.
"""

from __future__ import annotations

import os
import tempfile
import time
from datetime import date
from typing import Any

from engine.structures import compare_structures

from lib_api.build import ALL_DEALS, apply_overrides, deal_keys, resolve_deal
from lib_api.errors import ApiError
from lib_api.serialise import comparison_to_dict, reference_deals_payload
from lib_api.validate import parse_request

__all__ = [
    "MAX_EXPORT_BYTES",
    "run_compare",
    "run_export",
    "run_reference_deals",
    "run_current_law",
]

#: Vercel caps a response body at 4.5 MB. The sample workbook is ~55 KB, so
#: this is a fence rather than a live constraint - but a fence that returns 413
#: with a JSON error beats one that truncates an Excel file into corruption.
MAX_EXPORT_BYTES = 4 * 1024 * 1024


def _prepare(body: Any):
    """Validate, resolve the base deal, apply the overrides. Shared by both."""
    request = parse_request(body, valid_deal_keys=deal_keys())
    deal, deal_warnings = resolve_deal(request.deal_key)
    deal, override_warnings = apply_overrides(deal, request.overrides)
    warnings = [*request.warnings, *deal_warnings, *override_warnings]
    return request, deal, warnings


def run_compare(body: Any) -> dict:
    """POST /api/compare — one project through all five structures."""
    request, deal, warnings = _prepare(body)
    if request.structure is not None:
        warnings.append(
            "api: 'structure' is accepted by /api/export only. /api/compare "
            "always returns all five structures, ranked."
        )

    started = time.perf_counter()
    comparison = compare_structures(
        deal.project,
        deal.debt_terms,
        deal.tax_project,
        deal.configs,
        tax_scenario=deal.tax_scenario,
        sponsor=deal.sponsor,
        discount_rate=deal.discount_rate,
    )
    compute_ms = (time.perf_counter() - started) * 1000.0

    return comparison_to_dict(
        comparison, deal, compute_ms=compute_ms, extra_warnings=warnings
    )


def run_export(body: Any) -> tuple[bytes, str, list[str]]:
    """POST /api/export — the lender-grade workbook, as raw bytes.

    Returns ``(payload, filename, warnings)``. Raises :class:`ApiError` with
    status 413 if the workbook would breach the response body cap.
    """
    # Imported lazily: openpyxl and the sheet registry cost ~200 ms to import
    # and /api/compare must not pay for them.
    from export.api import build_workbook

    request, deal, warnings = _prepare(body)
    if request.structure is not None:
        warnings.append(
            f"api: the workbook is the project-level model (funding, debt "
            f"sizing, waterfall, returns) and is the same for every structure, "
            f"so '{request.structure}' did not change its contents."
        )

    with tempfile.TemporaryDirectory(prefix="structura-export-") as tmp:
        path = os.path.join(tmp, "structura-model.xlsx")
        build_workbook(
            deal.project,
            deal.debt_terms,
            None,
            path,
            discount_rate=deal.discount_rate,
        )
        size = os.path.getsize(path)
        if size > MAX_EXPORT_BYTES:
            raise ApiError(
                f"The generated workbook is {size / 1_048_576:.2f} MB, above "
                f"the {MAX_EXPORT_BYTES / 1_048_576:.0f} MB response cap "
                f"imposed by the 4.5 MB Vercel body limit. Reduce the project "
                f"life or the number of periods.",
                status=413,
                extra={"bytes": size, "limit_bytes": MAX_EXPORT_BYTES},
            )
        with open(path, "rb") as fh:
            payload = fh.read()

    filename = f"structura-{deal.key}-{date.today().isoformat()}.xlsx"
    return payload, filename, warnings


def run_reference_deals() -> dict:
    """GET /api/reference-deals."""
    return reference_deals_payload(ALL_DEALS)


def run_current_law() -> dict:
    """GET /api/current-law."""
    from lib_api.serialise import current_law_payload

    return current_law_payload()
