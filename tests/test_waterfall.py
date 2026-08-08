"""The cash waterfall: conservation, reserves, sweeps and lock-ups.

Cash conservation is asserted inside ``run_waterfall`` itself, so every test in
this file exercises it implicitly. The explicit tests here check that the
*order* of payments is right, not just that the arithmetic balances.
"""

from __future__ import annotations

import pytest

from engine.debt import build_schedule, dsra_targets, sculpted_debt_size
from engine.models import AmortizationStyle, DebtTerms, ProjectInputs
from engine.waterfall import assert_cash_conservation, run_waterfall
from tests.conftest import CENT

RATE = 0.06
TENOR = 10
LIFE = 15
CFADS = tuple(10_000_000.0 for _ in range(LIFE))
TARGETS = tuple(1.25 for _ in range(TENOR))


def build_debt(cfads=CFADS, targets=TARGETS, rate=RATE):
    size, service = sculpted_debt_size(cfads[: len(targets)], targets, rate)
    return build_schedule(
        size, service, cfads[: len(targets)], targets, rate, 1,
        AmortizationStyle.SCULPTED,
    )


def test_cash_is_conserved_in_every_period() -> None:
    debt = build_debt()
    reserves = dsra_targets(debt.debt_service, 6.0, 1)
    result = run_waterfall(CFADS, debt, dsra_target=reserves)
    assert_cash_conservation(result)
    for i in range(result.n_periods):
        assert result.sources(i) == pytest.approx(result.uses(i), abs=CENT)


def test_debt_service_is_paid_before_reserves_and_distributions() -> None:
    debt = build_debt()
    reserves = dsra_targets(debt.debt_service, 6.0, 1)
    result = run_waterfall(CFADS, debt, dsra_target=reserves)

    for i in range(TENOR):
        assert result.interest[i] == pytest.approx(debt.interest[i], abs=CENT)
        assert result.principal_scheduled[i] == pytest.approx(
            debt.principal[i], abs=CENT
        )
        assert result.dscr[i] == pytest.approx(1.25, abs=1e-9)
    assert result.closing_balance[TENOR - 1] == pytest.approx(0.0, abs=CENT)
    assert not result.in_default


def test_dsra_is_funded_at_cod_and_released_at_maturity() -> None:
    debt = build_debt()
    reserves = dsra_targets(debt.debt_service, 6.0, 1)
    result = run_waterfall(CFADS, debt, dsra_target=reserves)

    assert result.dsra_opening[0] == pytest.approx(reserves[0], abs=CENT)
    for i in range(TENOR - 1):
        assert result.dsra_closing[i] == pytest.approx(reserves[i + 1], abs=CENT)
    # Fully released once the debt is gone, and that cash reaches equity.
    assert result.dsra_closing[TENOR - 1] == pytest.approx(0.0, abs=CENT)
    assert result.distributions[TENOR - 1] > result.distributions[TENOR - 2]


def test_dsra_is_drawn_to_cure_a_debt_service_shortfall() -> None:
    """A one-off CFADS collapse is absorbed by the reserve, not by a default."""
    stressed = list(CFADS)
    stressed[4] = 4_000_000.0
    debt = build_debt()
    reserves = dsra_targets(debt.debt_service, 12.0, 1)
    result = run_waterfall(tuple(stressed), debt, dsra_target=reserves)

    assert result.dsra_release[4] > 0
    assert result.interest[4] + result.principal_scheduled[4] == pytest.approx(
        debt.interest[4] + debt.principal[4], abs=CENT
    )
    assert result.debt_service_shortfall[4] == pytest.approx(0.0, abs=CENT)
    assert result.dscr[4] < 1.0  # the covenant is still breached
    assert_cash_conservation(result)


def test_shortfall_beyond_the_reserve_is_reported_not_hidden() -> None:
    stressed = list(CFADS)
    stressed[4] = 0.0
    debt = build_debt()
    reserves = dsra_targets(debt.debt_service, 6.0, 1)
    result = run_waterfall(tuple(stressed), debt, dsra_target=reserves)

    assert result.debt_service_shortfall[4] > 0
    assert result.in_default
    assert_cash_conservation(result)


def test_cash_sweep_prepays_debt_and_shortens_the_loan() -> None:
    """A 100% sweep on a deal with surplus cash repays the loan early."""
    debt = build_debt()
    reserves = dsra_targets(debt.debt_service, 6.0, 1)
    no_sweep = run_waterfall(CFADS, debt, dsra_target=reserves, cash_sweep_pct=0.0)
    swept = run_waterfall(CFADS, debt, dsra_target=reserves, cash_sweep_pct=1.0)

    assert sum(swept.sweep_prepayment) > 0
    assert swept.closing_balance[3] < no_sweep.closing_balance[3]
    # Total principal repaid is unchanged - the sweep moves it earlier only.
    assert sum(swept.principal_scheduled) + sum(swept.sweep_prepayment) == (
        pytest.approx(debt.debt_size, abs=CENT)
    )
    # Interest paid falls, because the balance is retired sooner.
    assert sum(swept.interest) < sum(no_sweep.interest)
    assert_cash_conservation(swept)


def test_sweep_never_prepays_more_than_the_outstanding_balance() -> None:
    debt = build_debt()
    result = run_waterfall(
        CFADS, debt, dsra_target=dsra_targets(debt.debt_service, 6.0, 1),
        cash_sweep_pct=1.0,
    )
    for i in range(result.n_periods):
        assert result.sweep_prepayment[i] <= result.opening_balance[i] + CENT
        assert result.closing_balance[i] >= -CENT


def test_partial_sweep_splits_surplus_with_equity() -> None:
    debt = build_debt()
    reserves = dsra_targets(debt.debt_service, 6.0, 1)
    result = run_waterfall(CFADS, debt, dsra_target=reserves, cash_sweep_pct=0.5)
    for i in range(TENOR):
        cafd = result.cash_available_for_distribution[i]
        remaining = result.opening_balance[i] - result.principal_scheduled[i]
        # Half the surplus goes to prepayment, capped by what is still owed.
        assert result.sweep_prepayment[i] == pytest.approx(
            min(0.5 * cafd, max(remaining, 0.0)), abs=CENT
        )
        assert result.distributions[i] == pytest.approx(
            cafd - result.sweep_prepayment[i], abs=CENT
        )


def test_lockup_blocks_distributions_and_traps_the_cash() -> None:
    """Below the lock-up DSCR nothing reaches equity."""
    stressed = list(CFADS)
    stressed[3] = 6_000_000.0  # DSCR ~0.75x
    debt = build_debt()
    result = run_waterfall(
        tuple(stressed), debt,
        dsra_target=dsra_targets(debt.debt_service, 12.0, 1),
        lockup_dscr=1.10,
    )
    assert result.lockup[3]
    assert result.distributions[3] == pytest.approx(0.0, abs=CENT)
    assert not result.lockup[0]
    assert_cash_conservation(result)


def test_covenant_breach_is_flagged_without_stopping_the_model() -> None:
    stressed = list(CFADS)
    stressed[2] = 9_000_000.0
    debt = build_debt()
    result = run_waterfall(
        tuple(stressed), debt,
        dsra_target=dsra_targets(debt.debt_service, 6.0, 1),
        covenant_dscr=1.20,
    )
    assert result.covenant_breach[2]
    assert not result.covenant_breach[0]


def test_post_maturity_periods_distribute_everything() -> None:
    debt = build_debt()
    result = run_waterfall(
        CFADS, debt, dsra_target=dsra_targets(debt.debt_service, 6.0, 1)
    )
    for i in range(TENOR, LIFE):
        assert result.interest[i] == 0.0
        assert result.principal_scheduled[i] == 0.0
        assert result.distributions[i] == pytest.approx(CFADS[i], abs=CENT)
        assert result.dscr[i] == float("inf")


def test_maintenance_reserve_deposits_and_releases_flow_through() -> None:
    debt = build_debt()
    deposits = tuple(500_000.0 if i < 5 else 0.0 for i in range(LIFE))
    releases = tuple(1_000_000.0 if i == 7 else 0.0 for i in range(LIFE))
    result = run_waterfall(
        CFADS, debt,
        dsra_target=dsra_targets(debt.debt_service, 6.0, 1),
        mra_deposits=deposits, mra_releases=releases,
    )
    assert result.mra_closing[4] == pytest.approx(2_500_000.0, abs=CENT)
    assert result.mra_release[7] == pytest.approx(1_000_000.0, abs=CENT)
    assert result.mra_closing[7] == pytest.approx(1_500_000.0, abs=CENT)
    assert_cash_conservation(result)


def test_subordinated_service_sits_between_the_sweep_and_equity() -> None:
    debt = build_debt()
    sub = tuple(1_000_000.0 for _ in range(LIFE))
    result = run_waterfall(
        CFADS, debt,
        dsra_target=dsra_targets(debt.debt_service, 6.0, 1),
        subordinated_service=sub,
    )
    assert result.subordinated_service[0] == pytest.approx(1_000_000.0, abs=CENT)
    plain = run_waterfall(
        CFADS, debt, dsra_target=dsra_targets(debt.debt_service, 6.0, 1)
    )
    assert result.distributions[0] == pytest.approx(
        plain.distributions[0] - 1_000_000.0, abs=CENT
    )
    assert_cash_conservation(result)


def test_conservation_holds_on_a_full_model_run(
    flat_project: ProjectInputs, base_terms: DebtTerms
) -> None:
    from engine import run_model

    solution, result, _ = run_model(flat_project, base_terms)
    assert_cash_conservation(result)
    assert result.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    assert sum(result.principal_scheduled) + sum(result.sweep_prepayment) == (
        pytest.approx(solution.debt_size, abs=CENT)
    )
