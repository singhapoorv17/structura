"""Property tests: invariants that must hold for every input combination.

These are swept across a grid of CFADS shapes, rates, targets, tenors, grace
periods and amortisation styles. Golden cases prove the engine is right in one
place; property tests prove it does not break anywhere else.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine import run_model
from engine.circularity import solve_funding
from engine.debt import (
    build_schedule,
    dsra_targets,
    llcr,
    plcr,
    size_debt_service,
    size_facility,
)
from engine.models import (
    AmortizationStyle,
    DebtTerms,
    ProjectInputs,
    SizingConstraint,
)
from engine.waterfall import assert_cash_conservation, run_waterfall
from tests.conftest import CENT

TOL = 1e-9

CFADS_SHAPES: dict[str, tuple[float, ...]] = {
    "flat": tuple(10_000_000.0 for _ in range(20)),
    "rising": tuple(8_000_000.0 * 1.03**i for i in range(20)),
    "declining": tuple(14_000_000.0 * 0.97**i for i in range(20)),
    "humped": tuple(
        10_000_000.0 * (1.0 + 0.4 * (1 - abs(i - 9) / 9)) for i in range(20)
    ),
    "step_down": tuple(
        (12_000_000.0 if i < 12 else 7_000_000.0) for i in range(20)
    ),
    "lumpy": tuple(
        10_000_000.0 * (1.0 + 0.25 * ((-1) ** i)) for i in range(20)
    ),
}

RATES = (0.0, 0.03, 0.06, 0.095)
TARGETS = (1.05, 1.25, 1.45, 2.00)
STYLES = tuple(AmortizationStyle)
GRACE = (0, 1, 3)


@pytest.mark.parametrize("shape", list(CFADS_SHAPES))
@pytest.mark.parametrize("rate", RATES)
@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("grace", GRACE)
def test_schedule_invariants(
    shape: str, rate: float, target: float, style: AmortizationStyle, grace: int
) -> None:
    """Four invariants, on every combination.

    1. Debt service never exceeds CFADS / target - the coverage the deal was
       sized to is never breached.
    2. The achieved DSCR never dips below target.
    3. The facility amortises to exactly zero by maturity.
    4. Principal repaid sums to the debt drawn.
    """
    cfads = CFADS_SHAPES[shape]
    n = len(cfads)
    targets = tuple(target for _ in range(n))
    size, service = size_debt_service(cfads, targets, rate, style, grace)
    schedule = build_schedule(
        size, service, cfads, targets, rate, 1, style, grace
    )

    for i in range(n):
        assert schedule.debt_service[i] <= cfads[i] / target + CENT
        assert schedule.dscr[i] >= target - TOL

    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    assert sum(schedule.principal) == pytest.approx(size, abs=CENT)
    assert all(p >= -CENT for p in schedule.principal)
    assert all(b >= -CENT for b in schedule.closing_balance)
    # Principal is deferred through the grace period.
    for i in range(grace):
        assert schedule.principal[i] == pytest.approx(0.0, abs=CENT)


@pytest.mark.parametrize("shape", list(CFADS_SHAPES))
@pytest.mark.parametrize("rate", (0.03, 0.06, 0.095))
def test_higher_target_dscr_always_raises_less_debt(shape: str, rate: float) -> None:
    cfads = CFADS_SHAPES[shape]
    sizes = []
    for target in TARGETS:
        targets = tuple(target for _ in range(len(cfads)))
        sizes.append(
            size_debt_service(cfads, targets, rate, AmortizationStyle.SCULPTED)[0]
        )
    assert sizes == sorted(sizes, reverse=True)


@pytest.mark.parametrize("shape", list(CFADS_SHAPES))
def test_higher_interest_rate_always_raises_less_debt(shape: str) -> None:
    cfads = CFADS_SHAPES[shape]
    targets = tuple(1.30 for _ in range(len(cfads)))
    sizes = [
        size_debt_service(cfads, targets, r, AmortizationStyle.SCULPTED)[0]
        for r in RATES
    ]
    assert sizes == sorted(sizes, reverse=True)


@pytest.mark.parametrize("shape", list(CFADS_SHAPES))
@pytest.mark.parametrize("rate", (0.03, 0.06))
def test_sculpting_dominates_the_other_styles(shape: str, rate: float) -> None:
    """Sculpting raises at least as much debt as either fixed alternative.

    Note the ranking between level payment and fixed principal is NOT
    universal: against a declining CFADS profile a declining service schedule
    tracks the cash better, so fixed principal wins. Only sculpting's
    dominance is a theorem.
    """
    cfads = CFADS_SHAPES[shape]
    targets = tuple(1.30 for _ in range(len(cfads)))
    sculpted = size_debt_service(cfads, targets, rate, AmortizationStyle.SCULPTED)[0]
    level = size_debt_service(cfads, targets, rate, AmortizationStyle.LEVEL)[0]
    fixed = size_debt_service(
        cfads, targets, rate, AmortizationStyle.FIXED_PRINCIPAL
    )[0]
    assert sculpted >= level - CENT
    assert sculpted >= fixed - CENT


@pytest.mark.parametrize("shape", ("flat", "rising"))
def test_level_beats_fixed_principal_on_non_declining_cfads(shape: str) -> None:
    cfads = CFADS_SHAPES[shape]
    targets = tuple(1.30 for _ in range(len(cfads)))
    level = size_debt_service(cfads, targets, 0.06, AmortizationStyle.LEVEL)[0]
    fixed = size_debt_service(
        cfads, targets, 0.06, AmortizationStyle.FIXED_PRINCIPAL
    )[0]
    assert level > fixed


@pytest.mark.parametrize("shape", ("declining", "step_down"))
def test_fixed_principal_beats_level_on_declining_cfads(shape: str) -> None:
    """The reversal, asserted explicitly so nobody 'fixes' it back."""
    cfads = CFADS_SHAPES[shape]
    targets = tuple(1.30 for _ in range(len(cfads)))
    level = size_debt_service(cfads, targets, 0.06, AmortizationStyle.LEVEL)[0]
    fixed = size_debt_service(
        cfads, targets, 0.06, AmortizationStyle.FIXED_PRINCIPAL
    )[0]
    assert fixed > level


@pytest.mark.parametrize("shape", list(CFADS_SHAPES))
@pytest.mark.parametrize("rate", (0.03, 0.06, 0.095))
def test_plcr_never_below_llcr(shape: str, rate: float) -> None:
    """The tail can only add value; PLCR >= LLCR is a mathematical certainty."""
    cfads = CFADS_SHAPES[shape]
    targets = tuple(1.30 for _ in range(15))
    size, _ = size_debt_service(
        cfads[:15], targets, rate, AmortizationStyle.SCULPTED
    )
    assert plcr(cfads, size, rate) >= llcr(cfads[:15], size, rate) - TOL


@pytest.mark.parametrize("shape", list(CFADS_SHAPES))
@pytest.mark.parametrize("sweep", (0.0, 0.25, 0.5, 1.0))
def test_waterfall_conserves_cash_and_repays_the_loan(
    shape: str, sweep: float
) -> None:
    cfads = CFADS_SHAPES[shape]
    targets = tuple(1.30 for _ in range(15))
    size, service = size_debt_service(
        cfads[:15], targets, 0.06, AmortizationStyle.SCULPTED
    )
    schedule = build_schedule(
        size, service, cfads[:15], targets, 0.06, 1, AmortizationStyle.SCULPTED
    )
    result = run_waterfall(
        cfads, schedule,
        dsra_target=dsra_targets(schedule.debt_service, 6.0, 1),
        cash_sweep_pct=sweep,
    )
    assert_cash_conservation(result)
    assert result.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    assert not result.in_default
    assert sum(result.principal_scheduled) + sum(result.sweep_prepayment) == (
        pytest.approx(size, abs=CENT)
    )
    assert all(d >= 0.0 for d in result.distributions)
    assert all(b >= -CENT for b in result.dsra_closing)


@pytest.mark.parametrize("gearing", (0.50, 0.65, 0.75))
@pytest.mark.parametrize("target", (1.15, 1.30, 1.60))
def test_full_model_respects_every_reported_constraint(
    flat_project: ProjectInputs, gearing: float, target: float
) -> None:
    terms = DebtTerms(
        target_dscr=target, tenor_years=18.0, interest_rate=0.06,
        max_gearing=gearing, tail_years=2.0, dsra_months=6.0,
    )
    solution, waterfall, _ = run_model(flat_project, terms)
    sizing = solution.sizing

    assert sizing.min_dscr >= target - TOL
    assert sizing.gearing <= gearing + TOL
    assert sizing.tail_years >= terms.tail_years - TOL
    assert exactly_one_binds(sizing.tests)
    assert all(t.passes for t in sizing.tests)
    assert_cash_conservation(waterfall)
    assert solution.construction.converged


def exactly_one_binds(tests) -> bool:
    return sum(1 for t in tests if t.binds) == 1


@pytest.mark.parametrize("months", (0, 6, 18, 36))
def test_construction_length_never_breaks_the_funding_identity(
    flat_project: ProjectInputs, months: int
) -> None:
    project = replace(flat_project, construction_months=months)
    terms = DebtTerms(target_dscr=1.20, max_gearing=0.70, interest_rate=0.06)
    solution = solve_funding(project, terms)
    c = solution.construction
    assert c.total_project_cost == pytest.approx(
        c.capex + c.upfront_fee + c.commitment_fee + c.idc + c.dsra_initial, abs=CENT
    )
    assert c.debt_at_cod + c.equity_at_cod == pytest.approx(
        c.total_project_cost, abs=CENT
    )
    assert c.equity_at_cod >= -CENT


@pytest.mark.parametrize("ppy", (1, 2))
def test_model_runs_at_both_frequencies(
    flat_project: ProjectInputs, ppy: int
) -> None:
    project = replace(flat_project, periods_per_year=ppy)
    terms = DebtTerms(target_dscr=1.30, tenor_years=18.0, interest_rate=0.06)
    solution, waterfall, returns = run_model(project, terms)
    assert solution.sizing.debt.n_periods == 18 * ppy
    assert waterfall.n_periods == 25 * ppy
    assert_cash_conservation(waterfall)
    assert returns.equity_irr_post_tax is not None


def test_gearing_cap_is_never_exceeded_across_a_sweep(
    flat_project: ProjectInputs
) -> None:
    for gearing in (0.40, 0.55, 0.70, 0.80):
        terms = DebtTerms(
            target_dscr=1.10, max_gearing=gearing, interest_rate=0.06,
            tenor_years=18.0,
        )
        solution = solve_funding(flat_project, terms)
        assert solution.construction.gearing <= gearing + 1e-9
        assert solution.sizing.binding_constraint is SizingConstraint.GEARING


def test_time_varying_targets_are_respected_period_by_period() -> None:
    cfads = CFADS_SHAPES["humped"]
    targets = tuple(1.20 + 0.02 * i for i in range(len(cfads)))
    size, service = size_debt_service(
        cfads, targets, 0.06, AmortizationStyle.SCULPTED
    )
    schedule = build_schedule(
        size, service, cfads, targets, 0.06, 1, AmortizationStyle.SCULPTED
    )
    for achieved, target in zip(schedule.dscr, targets):
        assert achieved == pytest.approx(target, abs=1e-9)


def test_sizing_result_summary_always_names_the_binding_test(
    flat_project: ProjectInputs
) -> None:
    for target, gearing in ((1.10, 0.60), (1.80, 0.90), (1.30, 0.75)):
        terms = DebtTerms(
            target_dscr=target, max_gearing=gearing, interest_rate=0.06,
            tenor_years=18.0,
        )
        solution = solve_funding(flat_project, terms)
        summary = solution.sizing.summary()
        assert solution.sizing.binding_constraint.value.upper() in summary
        assert "$" in summary


def test_all_shapes_size_without_error_under_the_full_solver(
    flat_project: ProjectInputs
) -> None:
    """A smoke sweep: no CFADS shape may crash the circularity solver."""
    terms = DebtTerms(target_dscr=1.30, interest_rate=0.06, tenor_years=15.0)
    for price in (35.0, 50.0, 75.0, 120.0):
        project = replace(flat_project, contracted_price=price)
        solution = solve_funding(project, terms)
        assert solution.debt_size > 0
        assert solution.construction.converged
        assert size_facility(
            solution.cashflow.cfads, terms, 1, 25,
            total_project_cost=solution.construction.total_project_cost,
        ).debt_size == pytest.approx(solution.debt_size, abs=1.0)
