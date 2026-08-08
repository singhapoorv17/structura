"""The sizing tests and the binding-constraint reporter.

Each scenario is constructed so that exactly one test is meant to bind, and the
assertion is that the engine names that one. Practitioners care about *which*
test binds, so getting the attribution right matters as much as
getting the quantum right.
"""

from __future__ import annotations

import pytest

from engine.debt import present_value, size_facility
from engine.models import AmortizationStyle, DebtTerms, SizingConstraint
from tests.conftest import CENT

RATE = 0.06
LIFE = 25
CFADS = tuple(10_000_000.0 for _ in range(LIFE))


def terms(**overrides) -> DebtTerms:
    base = dict(
        target_dscr=1.30,
        tenor_years=18.0,
        interest_rate=RATE,
        amortization=AmortizationStyle.SCULPTED,
        max_gearing=0.75,
        tail_years=2.0,
        dsra_months=6.0,
    )
    base.update(overrides)
    return DebtTerms(**base)


# ---------------------------------------------------------------------------
# DSCR-bound
# ---------------------------------------------------------------------------


def test_dscr_binds_when_project_cost_is_generous() -> None:
    """A large capex base leaves the gearing cap slack, so DSCR sets the debt."""
    result = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=1_000_000_000.0)
    assert result.binding_constraint is SizingConstraint.DSCR
    assert result.min_dscr == pytest.approx(1.30, abs=1e-12)
    assert result.test(SizingConstraint.GEARING).passes
    assert "DSCR-bound" in result.summary()
    assert "gearing would have allowed 75.0%" in result.summary()


def test_dscr_quantum_equals_the_annuity_pv_of_the_sculpted_service() -> None:
    result = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=1_000_000_000.0)
    service = tuple(10_000_000.0 / 1.30 for _ in range(18))
    assert result.debt_size == pytest.approx(present_value(service, RATE), abs=CENT)


# ---------------------------------------------------------------------------
# Gearing-bound
# ---------------------------------------------------------------------------


def test_gearing_binds_when_project_cost_is_small() -> None:
    """A cheap project with strong CFADS is gearing-bound; DSCR comes out above
    target and the summary says so."""
    result = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=100_000_000.0)
    assert result.binding_constraint is SizingConstraint.GEARING
    assert result.debt_size == pytest.approx(75_000_000.0, abs=CENT)
    assert result.gearing == pytest.approx(0.75, abs=1e-12)
    assert result.min_dscr > 1.30
    assert "GEARING-bound" in result.summary()
    assert "achieved min DSCR" in result.summary()


def test_gearing_bound_deal_still_fully_amortises() -> None:
    result = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=100_000_000.0)
    assert result.debt.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    assert sum(result.debt.principal) == pytest.approx(result.debt_size, abs=CENT)


def test_no_project_cost_means_the_gearing_test_is_skipped() -> None:
    result = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=None)
    assert result.binding_constraint is SizingConstraint.DSCR
    assert result.gearing == 0.0
    assert "not tested" in result.test(SizingConstraint.GEARING).note


# ---------------------------------------------------------------------------
# Tail-bound
# ---------------------------------------------------------------------------


def test_tail_requirement_shortens_the_tenor_and_binds() -> None:
    """A 24-year request against a 25-year life with a 3-year tail must be cut
    to 22 years, and the tail test is the binder."""
    result = size_facility(
        CFADS, terms(tenor_years=24.0, tail_years=3.0), 1, LIFE,
        total_project_cost=1_000_000_000.0,
    )
    assert result.binding_constraint is SizingConstraint.TAIL
    assert result.debt.n_periods == 22
    assert result.tail_years == pytest.approx(3.0)
    assert result.test(SizingConstraint.TAIL).passes
    assert "tenor shortened" in result.test(SizingConstraint.TENOR).note

    service = tuple(10_000_000.0 / 1.30 for _ in range(22))
    assert result.debt_size == pytest.approx(present_value(service, RATE), abs=CENT)


def test_tail_within_the_requested_tenor_does_not_bind() -> None:
    result = size_facility(
        CFADS, terms(tenor_years=18.0, tail_years=3.0), 1, LIFE,
        total_project_cost=1_000_000_000.0,
    )
    assert result.binding_constraint is SizingConstraint.DSCR
    assert result.tail_years == pytest.approx(7.0)


def test_tail_longer_than_project_life_is_rejected() -> None:
    with pytest.raises(ValueError, match="tail is longer than the project life"):
        size_facility(CFADS, terms(tail_years=30.0), 1, LIFE)


# ---------------------------------------------------------------------------
# LLCR / PLCR bound
# ---------------------------------------------------------------------------


def test_llcr_floor_binds_when_set_above_the_target_dscr() -> None:
    """For a flat sculpt LLCR equals the target DSCR, so an LLCR floor above
    the target must bind and cut the debt in exactly that proportion."""
    result = size_facility(
        CFADS, terms(min_llcr=1.60), 1, LIFE, total_project_cost=1_000_000_000.0
    )
    assert result.binding_constraint is SizingConstraint.LLCR
    assert result.llcr == pytest.approx(1.60, abs=1e-9)

    unconstrained = size_facility(
        CFADS, terms(), 1, LIFE, total_project_cost=1_000_000_000.0
    )
    assert result.debt_size == pytest.approx(
        unconstrained.debt_size * 1.30 / 1.60, abs=CENT
    )
    assert result.min_dscr == pytest.approx(1.60, rel=1e-9)


def test_llcr_floor_below_the_target_does_not_bind() -> None:
    result = size_facility(
        CFADS, terms(min_llcr=1.10), 1, LIFE, total_project_cost=1_000_000_000.0
    )
    assert result.binding_constraint is SizingConstraint.DSCR
    assert result.test(SizingConstraint.LLCR).passes


def test_plcr_floor_binds_when_set_high_enough() -> None:
    result = size_facility(
        CFADS, terms(min_plcr=2.00), 1, LIFE, total_project_cost=1_000_000_000.0
    )
    assert result.binding_constraint is SizingConstraint.PLCR
    assert result.plcr == pytest.approx(2.00, abs=1e-9)
    assert result.plcr > result.llcr  # tail value always lifts PLCR above LLCR


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_every_constraint_is_reported_even_when_not_binding() -> None:
    result = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=500_000_000.0)
    reported = {t.constraint for t in result.tests}
    assert reported == set(SizingConstraint)
    assert sum(1 for t in result.tests if t.binds) == 1


def test_tie_break_prefers_dscr_when_two_tests_permit_the_same_quantum() -> None:
    """A deal simultaneously at its DSCR and gearing limit is described by
    practitioners as DSCR-bound; the reporter follows that convention."""
    dscr_only = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=None)
    exact_cost = dscr_only.debt_size / 0.75
    result = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=exact_cost)
    assert result.binding_constraint is SizingConstraint.DSCR
    assert result.gearing == pytest.approx(0.75, abs=1e-9)


def test_semiannual_periods_produce_twice_as_many_debt_periods() -> None:
    semi_cfads = tuple(5_000_000.0 for _ in range(LIFE * 2))
    result = size_facility(
        semi_cfads, terms(), 2, LIFE * 2, total_project_cost=1_000_000_000.0
    )
    assert result.debt.n_periods == 36
    assert result.debt.rate_per_period == pytest.approx(RATE / 2)
    # Semi-annual service at half the annual rate raises slightly more debt
    # than the annual equivalent, because principal repays sooner.
    annual = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=1e9)
    assert result.debt_size > annual.debt_size


def test_zero_cfads_raises_rather_than_returning_zero_debt() -> None:
    with pytest.raises(ValueError):
        size_facility(
            tuple(0.0 for _ in range(LIFE)), terms(), 1, LIFE,
            total_project_cost=100_000_000.0,
        )


def test_weighted_average_life_is_shorter_than_the_tenor() -> None:
    result = size_facility(CFADS, terms(), 1, LIFE, total_project_cost=1e9)
    assert 0 < result.debt.average_life_years < 18.0
