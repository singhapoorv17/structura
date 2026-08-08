"""Shared fixtures and helpers for the engine test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.models import (  # noqa: E402
    AmortizationStyle,
    DebtTerms,
    ProjectInputs,
    Technology,
)

#: Tolerance for "to the cent" golden comparisons on eight- and nine-figure
#: currency amounts. 0.01 on 1e8 is 1e-10 relative - far tighter than any
#: modelling convention, and only achievable because the sculpting identity is
#: closed-form rather than iterative.
CENT = 0.01


def annuity_factor_reference(rate: float, n: int) -> float:
    """Independent annuity factor, written out longhand for the golden tests.

    Deliberately not imported from the engine: a golden test that checks the
    engine against the engine checks nothing.
    """
    total = 0.0
    for t in range(1, n + 1):
        total += 1.0 / (1.0 + rate) ** t
    return total


@pytest.fixture
def flat_project() -> ProjectInputs:
    """A hand-checkable project: no escalation, no degradation, flat CFADS.

    Production 1,000,000 MWh at $50/MWh flat gives $50m of revenue; $10m of
    flat opex gives $40m of EBITDA and, with tax off, $40m of CFADS every year
    for 20 years.
    """
    return ProjectInputs(
        name="Flat test project",
        technology=Technology.STORAGE,
        capacity_mw=100.0,
        capex=300_000_000.0,
        construction_months=12,
        opex_year1=10_000_000.0,
        opex_escalation=0.0,
        production_p50=1_000_000.0,
        degradation=0.0,
        contracted_price=50.0,
        contracted_share=1.0,
        contracted_escalation=0.0,
        contract_years=25.0,
        merchant_price=0.0,
        merchant_escalation=0.0,
        project_life_years=25.0,
        periods_per_year=1,
    )


@pytest.fixture
def base_terms() -> DebtTerms:
    return DebtTerms(
        target_dscr=1.30,
        tenor_years=18.0,
        interest_rate=0.06,
        upfront_fee=0.0125,
        commitment_fee=0.005,
        amortization=AmortizationStyle.SCULPTED,
        max_gearing=0.75,
        tail_years=2.0,
        dsra_months=6.0,
        cash_sweep_pct=0.0,
    )
