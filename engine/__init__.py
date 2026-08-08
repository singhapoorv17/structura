"""Structura core engine - energy project-finance structuring.

Phase 1 scope (SPEC.md §6.1): the debt-sizing / sculpting / waterfall spine.
Pure Python, no web dependencies, no Excel, no tax structures.

Typical use::

    from engine import ProjectInputs, DebtTerms, run_model

    solution, waterfall, returns = run_model(ProjectInputs(), DebtTerms())
    print(solution.sizing.summary())

Modules
-------
``models``       inputs and outputs (frozen dataclasses)
``defaults``     market benchmarks, each with a source and a verified-on date
``cashflow``     revenue -> opex -> tax -> CFADS
``debt``         sculpting, amortisation styles, DSCR/LLCR/PLCR, sizing tests
``circularity``  the IDC <-> debt <-> fees <-> DSRA fixed point
``waterfall``    the cash waterfall, with cash conservation asserted
``metrics``      IRR / XIRR / NPV / payback / effective cost of capital
"""

from __future__ import annotations

from engine import cashflow, circularity, debt, defaults, metrics, waterfall
from engine.circularity import FundingSolution, solve_funding
from engine.metrics import compute_returns
from engine.models import (
    AmortizationStyle,
    CashflowResult,
    ConstraintTest,
    ConstructionResult,
    DebtResult,
    DebtTerms,
    ProductionCase,
    ProjectInputs,
    ReturnsResult,
    SizingConstraint,
    SizingResult,
    TaxTreatment,
    Technology,
    WaterfallResult,
)
from engine.waterfall import run_waterfall

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AmortizationStyle",
    "CashflowResult",
    "ConstraintTest",
    "ConstructionResult",
    "DebtResult",
    "DebtTerms",
    "FundingSolution",
    "ProductionCase",
    "ProjectInputs",
    "ReturnsResult",
    "SizingConstraint",
    "SizingResult",
    "TaxTreatment",
    "Technology",
    "WaterfallResult",
    "cashflow",
    "circularity",
    "compute_returns",
    "debt",
    "defaults",
    "metrics",
    "run_model",
    "run_waterfall",
    "solve_funding",
    "waterfall",
]


def run_model(
    project: ProjectInputs,
    terms: DebtTerms,
    *,
    lockup_dscr: float | None = None,
    discount_rate: float = 0.10,
) -> tuple[FundingSolution, WaterfallResult, ReturnsResult]:
    """End-to-end Phase 1 run: cashflow -> funding solve -> waterfall -> returns.

    The convenience entry point the API layer will call. Everything it does is
    available piecewise from the individual modules; nothing is hidden here.
    """
    solution = solve_funding(project, terms)
    result = run_waterfall(
        solution.cashflow.cfads,
        solution.sizing.debt,
        dsra_target=solution.sizing.dsra_target,
        dsra_initial=solution.construction.dsra_initial,
        cash_sweep_pct=terms.cash_sweep_pct,
        lockup_dscr=lockup_dscr,
        covenant_dscr=terms.covenant_dscr,
    )
    returns = compute_returns(
        solution.construction,
        result,
        solution.sizing.debt,
        discount_rate=discount_rate,
        periods_per_year=project.periods_per_year,
        cod_date=project.cod_date,
        tax_rate=project.tax_rate,
    )
    return solution, result, returns
