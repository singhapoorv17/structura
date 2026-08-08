"""Return metrics: IRR, XIRR, NPV, payback and the effective cost of debt."""

from __future__ import annotations

from datetime import date

import pytest

from engine.metrics import (
    annualise,
    effective_cost_of_debt,
    equity_cashflows,
    irr,
    npv,
    payback_period,
    period_dates,
    xirr,
)
from engine.models import DebtTerms, ProjectInputs
from tests.conftest import CENT


def test_irr_of_a_textbook_series() -> None:
    """-100 now, +110 in a year is a 10% IRR, exactly."""
    assert irr((-100.0, 110.0)) == pytest.approx(0.10, abs=1e-12)


def test_irr_of_a_level_annuity_recovers_the_discount_rate() -> None:
    """Investing the annuity PV and receiving the annuity returns the rate."""
    rate = 0.08
    payments = [250.0] * 12
    price = sum(p / (1 + rate) ** (i + 1) for i, p in enumerate(payments))
    assert irr([-price, *payments]) == pytest.approx(rate, abs=1e-9)


def test_irr_returns_none_when_no_sign_change() -> None:
    assert irr((100.0, 200.0)) is None
    assert irr((-100.0, -200.0)) is None
    assert irr(()) is None


def test_npv_convention_puts_index_zero_at_time_zero() -> None:
    assert npv((-100.0, 110.0), 0.10) == pytest.approx(0.0, abs=1e-12)
    assert npv((-100.0, 110.0), 0.0) == pytest.approx(10.0, abs=1e-12)


def test_annualise_compounds_a_periodic_rate() -> None:
    assert annualise(0.03, 2) == pytest.approx(1.03**2 - 1.0, abs=1e-15)
    assert annualise(0.10, 1) == pytest.approx(0.10, abs=1e-15)


def test_payback_interpolates_within_the_period() -> None:
    """-100, then +40 a year: cumulative crosses zero halfway through year 3."""
    assert payback_period((-100.0, 40.0, 40.0, 40.0)) == pytest.approx(2.5, abs=1e-12)
    assert payback_period((-100.0, 40.0)) is None


def test_payback_scales_with_period_frequency() -> None:
    assert payback_period((-100.0, 50.0, 50.0), periods_per_year=2) == pytest.approx(
        1.0, abs=1e-12
    )


def test_xirr_matches_irr_on_evenly_spaced_annual_dates() -> None:
    dates = (date(2027, 1, 1), date(2028, 1, 1), date(2029, 1, 1))
    amounts = (-1000.0, 600.0, 600.0)
    assert xirr(dates, amounts) == pytest.approx(irr(amounts), abs=2e-3)
    assert xirr(dates, (100.0, 200.0, 300.0)) is None
    with pytest.raises(ValueError):
        xirr(dates, (1.0, 2.0))


def test_effective_cost_of_debt_equals_the_coupon_when_there_are_no_fees() -> None:
    from engine.debt import build_schedule, sculpted_debt_size
    from engine.models import AmortizationStyle

    cfads = tuple(10_000_000.0 for _ in range(10))
    targets = tuple(1.25 for _ in range(10))
    size, service = sculpted_debt_size(cfads, targets, 0.06)
    schedule = build_schedule(
        size, service, cfads, targets, 0.06, 1, AmortizationStyle.SCULPTED
    )
    assert effective_cost_of_debt(schedule) == pytest.approx(0.06, abs=1e-9)


def test_fees_push_the_effective_cost_above_the_coupon() -> None:
    from engine.debt import build_schedule, sculpted_debt_size
    from engine.models import AmortizationStyle

    cfads = tuple(10_000_000.0 for _ in range(10))
    targets = tuple(1.25 for _ in range(10))
    size, service = sculpted_debt_size(cfads, targets, 0.06)
    schedule = build_schedule(
        size, service, cfads, targets, 0.06, 1, AmortizationStyle.SCULPTED
    )
    with_fee = effective_cost_of_debt(schedule, upfront_fee=0.0125 * size)
    assert with_fee > 0.06
    assert with_fee == pytest.approx(0.0631, abs=5e-4)


def test_period_dates_start_at_cod() -> None:
    dates = period_dates(date(2027, 1, 1), 3, 1)
    assert len(dates) == 4
    assert dates[0] == date(2027, 1, 1)
    assert (dates[1] - dates[0]).days == 365
    semi = period_dates(date(2027, 1, 1), 2, 2)
    assert (semi[1] - semi[0]).days == 182


def test_end_to_end_returns_are_coherent(
    flat_project: ProjectInputs, base_terms: DebtTerms
) -> None:
    from engine import run_model

    solution, waterfall, returns = run_model(flat_project, base_terms)

    assert returns.equity_investment == pytest.approx(
        solution.construction.equity_at_cod, abs=CENT
    )
    assert returns.equity_cashflows[0] == pytest.approx(
        -returns.equity_investment, abs=CENT
    )
    assert returns.equity_irr_post_tax is not None
    assert 0.0 < returns.equity_irr_post_tax < 1.0
    assert returns.equity_moic > 1.0
    assert returns.payback_years is not None
    # Leverage works: the levered equity IRR beats the unlevered project yield.
    unlevered = irr(
        (-solution.construction.total_project_cost, *solution.cashflow.cfads)
    )
    assert returns.equity_irr_post_tax > unlevered

    # WACC sits between the after-tax cost of debt and the equity return.
    assert returns.after_tax_cost_of_debt is not None
    assert (
        returns.after_tax_cost_of_debt
        < returns.weighted_average_cost_of_capital
        < returns.equity_irr_post_tax
    )
    assert len(returns.dates) == len(waterfall.distributions) + 1


def test_pre_and_post_tax_equity_irr_bracket_each_other(
    flat_project: ProjectInputs, base_terms: DebtTerms
) -> None:
    """Same deal, tax line on and off: the pre-tax IRR must be the higher one."""
    from dataclasses import replace

    from engine.circularity import solve_funding
    from engine.metrics import compute_returns
    from engine.models import TaxTreatment
    from engine.waterfall import run_waterfall

    taxed = replace(flat_project, tax_treatment=TaxTreatment.FULL, tax_rate=0.21)
    solution = solve_funding(taxed, base_terms)

    post = run_waterfall(
        solution.cashflow.cfads, solution.sizing.debt,
        dsra_target=solution.sizing.dsra_target,
        dsra_initial=solution.construction.dsra_initial,
    )
    pre_tax_cfads = tuple(
        c + t for c, t in zip(solution.cashflow.cfads, solution.cashflow.cash_tax)
    )
    pre = run_waterfall(
        pre_tax_cfads, solution.sizing.debt,
        dsra_target=solution.sizing.dsra_target,
        dsra_initial=solution.construction.dsra_initial,
    )
    returns = compute_returns(
        solution.construction, post, solution.sizing.debt,
        waterfall_pre_tax=pre, periods_per_year=1, tax_rate=0.21,
    )
    assert returns.equity_irr_pre_tax > returns.equity_irr_post_tax


def test_equity_cashflows_are_a_single_outflow_then_distributions(
    flat_project: ProjectInputs, base_terms: DebtTerms
) -> None:
    from engine import run_model

    solution, waterfall, _ = run_model(flat_project, base_terms)
    flows = equity_cashflows(solution.construction, waterfall)
    assert flows[0] < 0
    assert all(f >= 0 for f in flows[1:])
    assert len(flows) == waterfall.n_periods + 1
