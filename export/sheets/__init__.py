"""Sheet modules, and their registration with the workbook builder.

Adding a sheet in a later phase means writing one module with a ``build(wb,
model)`` function and adding one ``register_sheet`` call here - nothing in
``export/workbook.py`` or in any existing sheet module changes.

``display_order`` is the tab position; ``build_order`` is when the builder
runs, which only matters when a sheet references another sheet's *rows*
(defined names are resolved by Excel and need no ordering).

Gaps are left deliberately:

=====  ============================================================
55     **Tax** (Phase 2, ``engine/tax``): section 48E / 45Y
       eligibility and phase-down, FEOC / material assistance cost
       ratio, domestic content adder, MACRS and bonus depreciation,
       the 50% ITC basis reduction.
75     **Structures** (Phase 3): partnership flip, T-flip, preferred
       equity, direct transfer under section 6418, sale-leaseback,
       and the ranked cost-of-capital comparison.
=====  ============================================================

A Tax sheet will want ``build_order`` around 35 - after Operations, so it can
reference the CFADS and depreciation rows, and before Waterfall, so the
waterfall can take a tax line from it.
"""

from __future__ import annotations

from export.sheets import (
    construction,
    debt,
    inputs,
    notes,
    operations,
    returns,
    summary,
    waterfall,
)
from export.workbook import register_sheet

__all__ = ["register_default_sheets"]


def register_default_sheets() -> None:
    """Register the Phase 4 sheet set. Idempotent - safe to call repeatedly."""
    register_sheet(
        summary.SHEET_NAME,
        summary.build,
        display_order=10,
        build_order=70,
        description="One-page front sheet: key outputs, binding constraint, "
        "sources and uses, credit tests.",
        replace=True,
    )
    register_sheet(
        inputs.SHEET_NAME,
        inputs.build,
        display_order=20,
        build_order=10,
        description="Every driver as a named, blue, editable cell.",
        replace=True,
    )
    register_sheet(
        construction.SHEET_NAME,
        construction.build,
        display_order=30,
        build_order=40,
        description="Monthly drawdown, IDC, fees, funding requirement.",
        replace=True,
    )
    register_sheet(
        operations.SHEET_NAME,
        operations.build,
        display_order=40,
        build_order=20,
        description="Revenue, opex, EBITDA, tax and CFADS by period.",
        replace=True,
    )
    register_sheet(
        debt.SHEET_NAME,
        debt.build,
        display_order=50,
        build_order=30,
        description="Sizing tests, sculpt, amortisation schedule, coverage.",
        replace=True,
    )
    register_sheet(
        waterfall.SHEET_NAME,
        waterfall.build,
        display_order=70,
        build_order=50,
        description="Cash waterfall from CFADS to distributions.",
        replace=True,
    )
    register_sheet(
        returns.SHEET_NAME,
        returns.build,
        display_order=90,
        build_order=60,
        description="Equity cashflows, IRR / XIRR / NPV / payback, cost of "
        "capital.",
        replace=True,
    )
    register_sheet(
        notes.SHEET_NAME,
        notes.build,
        display_order=100,
        build_order=80,
        description="Methodology, conventions, solver-derived cells, sources, "
        "disclaimer.",
        replace=True,
    )


register_default_sheets()
