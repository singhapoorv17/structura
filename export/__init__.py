"""Structura Excel export - the lender-grade workbook with live formulas.

SPEC.md §6.5 and §4.2: the exported model carries **live formulas, not pasted
values**, or the "lender-grade" claim is false. Change the DSCR input cell and
every dependent figure recalculates - including the debt quantum, because the
sculpt, the sizing tests and the construction funding circularity are all
written as Excel formulas.

Usage::

    from engine import ProjectInputs, DebtTerms, run_model
    from export import build_workbook

    project, terms = ProjectInputs(), DebtTerms()
    build_workbook(project, terms, run_model(project, terms), "deal.xlsx")

Modules
-------
``api``        the single public entry point, :func:`build_workbook`
``workbook``   calculation properties, cell helpers, the sheet registry
``styles``     the blue-input / black-formula / green-link banker convention
``model``      the bundle of engine objects each sheet builder receives
``sheets``     one module per worksheet, self-registering
"""

from __future__ import annotations

from export.api import build_bundle, build_workbook
from export.model import DISCLAIMER, ModelBundle
from export.workbook import (
    ITERATE_COUNT,
    ITERATE_DELTA,
    SheetSpec,
    WorkbookBuilder,
    register_sheet,
    registered_sheets,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "DISCLAIMER",
    "ITERATE_COUNT",
    "ITERATE_DELTA",
    "ModelBundle",
    "SheetSpec",
    "WorkbookBuilder",
    "build_bundle",
    "build_workbook",
    "register_sheet",
    "registered_sheets",
]
