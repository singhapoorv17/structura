"""The public entry point: turn an engine run into a lender-grade workbook.

One function. Everything else in ``export`` is an implementation detail that a
later phase may extend, but this signature is the contract the API layer and
the CLI depend on::

    from export import build_workbook
    build_workbook(project, terms, engine_result, "deal.xlsx")
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

from engine import run_model
from engine.circularity import FundingSolution
from engine.models import (
    DebtTerms,
    ProjectInputs,
    ReturnsResult,
    WaterfallResult,
)

import export.sheets  # noqa: F401 - importing registers the default sheet set
from export.model import ModelBundle
from export.workbook import WorkbookBuilder, registered_sheets

__all__ = ["build_workbook", "build_bundle", "EngineResult"]

#: What ``engine.run_model`` returns.
EngineResult = tuple[FundingSolution, WaterfallResult, ReturnsResult]


def build_bundle(
    project: ProjectInputs,
    terms: DebtTerms,
    engine_result: EngineResult | ModelBundle | None = None,
    *,
    discount_rate: float = 0.10,
    lockup_dscr: float | None = None,
    generated_on: date | None = None,
) -> ModelBundle:
    """Normalise the caller's engine output into a :class:`ModelBundle`.

    Accepts the tuple ``engine.run_model`` returns, an already-built bundle, or
    ``None`` - in which case the model is run here. Running it here is the
    convenient path for a script; passing the result in is the right path for a
    server that has already computed it and does not want to pay twice.
    """
    if isinstance(engine_result, ModelBundle):
        return engine_result
    if engine_result is None:
        engine_result = run_model(
            project, terms, lockup_dscr=lockup_dscr, discount_rate=discount_rate
        )
    if not isinstance(engine_result, Sequence) or len(engine_result) != 3:
        raise TypeError(
            "engine_result must be the (FundingSolution, WaterfallResult, "
            "ReturnsResult) tuple returned by engine.run_model()"
        )
    solution, waterfall, returns = engine_result
    return ModelBundle(
        project=project,
        terms=terms,
        solution=solution,
        waterfall=waterfall,
        returns=returns,
        discount_rate=discount_rate,
        lockup_dscr=lockup_dscr,
        generated_on=generated_on or date.today(),
    )


def build_workbook(
    project_inputs: ProjectInputs,
    debt_terms: DebtTerms,
    engine_result: EngineResult | ModelBundle | None = None,
    path: str | Path = "structura-model.xlsx",
    *,
    discount_rate: float = 0.10,
    lockup_dscr: float | None = None,
    generated_on: date | None = None,
) -> Path:
    """Write the Structura workbook to ``path`` and return the path.

    The workbook carries **live formulas**, not pasted values. It is written
    with iterative calculation enabled so the construction
    funding circularity resolves natively in Excel, and with
    ``fullCalcOnLoad`` so it calculates on open.

    Parameters
    ----------
    project_inputs, debt_terms:
        The engine inputs. They become the blue cells on the Inputs sheet.
    engine_result:
        Output of ``engine.run_model``. Optional; the model is run here if it
        is omitted.
    path:
        Destination ``.xlsx`` file. Parent directories must already exist.
    discount_rate:
        Annual rate used for the equity NPV.
    lockup_dscr:
        Distribution lock-up level. ``None`` means no lock-up test.
    generated_on:
        Overrides the generation date stamped on the Summary and Notes sheets.
        Supply a fixed date to make the output byte-comparable across runs.

    Returns
    -------
    Path
        The file written.
    """
    model = build_bundle(
        project_inputs,
        debt_terms,
        engine_result,
        discount_rate=discount_rate,
        lockup_dscr=lockup_dscr,
        generated_on=generated_on,
    )

    wb = WorkbookBuilder()
    specs = registered_sheets()
    for spec in sorted(specs, key=lambda s: (s.build_order, s.name)):
        spec.builder(wb, model)
    wb.order_sheets([spec.name for spec in specs])

    destination = Path(path)
    wb.save(destination)
    return destination
