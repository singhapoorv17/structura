"""Golden case (c): LLCR and PLCR against hand-computed present values."""

from __future__ import annotations

import pytest

from engine.debt import (
    dsra_targets,
    llcr,
    llcr_series,
    plcr,
    present_value,
    sculpted_debt_size,
)

# Deliberately tiny so every PV can be written out longhand.
CFADS = (100.0, 200.0, 300.0)
RATE = 0.10
LOAN_PERIODS = 2

# PV of CFADS to loan maturity  = 100/1.1 + 200/1.21           = 256.19834710743802
# PV of CFADS to project end    = above + 300/1.331            = 481.59278737791134
PV_LOAN_LIFE = 256.19834710743802
PV_PROJECT_LIFE = 481.59278737791134
# Sculpted at a 2.0x target: DS = 50, 100 -> D = 50/1.1 + 100/1.21
DEBT = 128.09917355371901


def test_present_value_matches_hand_computation() -> None:
    assert present_value(CFADS[:LOAN_PERIODS], RATE) == pytest.approx(
        PV_LOAN_LIFE, abs=1e-9
    )
    assert present_value(CFADS, RATE) == pytest.approx(PV_PROJECT_LIFE, abs=1e-9)


def test_debt_size_is_half_the_loan_life_pv_at_a_two_times_target() -> None:
    targets = (2.0, 2.0)
    debt_size, service = sculpted_debt_size(CFADS[:LOAN_PERIODS], targets, RATE)
    assert service == pytest.approx((50.0, 100.0), abs=1e-9)
    assert debt_size == pytest.approx(DEBT, abs=1e-9)
    assert debt_size == pytest.approx(PV_LOAN_LIFE / 2.0, abs=1e-9)


def test_llcr_equals_the_constant_target_dscr_when_sculpted() -> None:
    """The identity every project-finance analyst should be able to recite.

    Sculpting to a constant target d makes CFADS_t = d x DS_t in every period,
    so PV(CFADS) = d x PV(DS) = d x D, hence LLCR = d exactly. Any deviation
    means the sculpt is not actually hitting its target.
    """
    assert llcr(CFADS[:LOAN_PERIODS], DEBT, RATE) == pytest.approx(2.0, abs=1e-12)


def test_plcr_hand_computed_and_strictly_above_llcr() -> None:
    """PLCR = 481.59278737791134 / 128.09917355371901 = 3.7595307917888563.

    PLCR exceeds LLCR by exactly the PV of the tail (300/1.331 = 225.3944403)
    divided by the debt - which is what the tail is worth to a lender.
    """
    value = plcr(CFADS, DEBT, RATE)
    assert value == pytest.approx(3.7595307917888563, abs=1e-12)
    assert value > llcr(CFADS[:LOAN_PERIODS], DEBT, RATE)

    tail_value = (300.0 / 1.1**3) / DEBT
    assert value - llcr(CFADS[:LOAN_PERIODS], DEBT, RATE) == pytest.approx(
        tail_value, abs=1e-12
    )


def test_reserves_lift_the_ratio_by_reserves_over_debt() -> None:
    with_reserve = llcr(CFADS[:LOAN_PERIODS], DEBT, RATE, reserves=25.0)
    assert with_reserve == pytest.approx(2.0 + 25.0 / DEBT, abs=1e-12)


def test_llcr_is_infinite_once_the_debt_is_repaid() -> None:
    assert llcr(CFADS, 0.0, RATE) == float("inf")


def test_llcr_series_walks_forward_correctly() -> None:
    """At the end of period 1 the LLCR discounts only period 2's CFADS."""
    balances = (80.0, 0.0)
    series = llcr_series(CFADS, balances, RATE, horizon=LOAN_PERIODS)
    assert series[0] == pytest.approx((200.0 / 1.1) / 80.0, abs=1e-12)
    assert series[1] == float("inf")


def test_llcr_declines_when_cfads_is_back_loaded_against_a_flat_sculpt() -> None:
    """Sanity: a rising CFADS profile sculpted flat leaves LLCR above target."""
    cfads = (100.0, 150.0, 250.0)
    targets = (1.5, 1.5, 1.5)
    debt_size, _ = sculpted_debt_size(cfads, targets, RATE)
    assert llcr(cfads, debt_size, RATE) == pytest.approx(1.5, abs=1e-12)
    assert plcr(cfads, debt_size, RATE) == pytest.approx(1.5, abs=1e-12)


# ---------------------------------------------------------------------------
# DSRA
# ---------------------------------------------------------------------------


def test_six_month_dsra_on_annual_periods_is_half_the_next_payment() -> None:
    service = (100.0, 120.0, 140.0)
    targets = dsra_targets(service, dsra_months=6.0, periods_per_year=1)
    assert len(targets) == 4
    assert targets[0] == pytest.approx(50.0)  # funded at COD off period 1
    assert targets[1] == pytest.approx(60.0)
    assert targets[2] == pytest.approx(70.0)
    assert targets[3] == pytest.approx(0.0)  # released at maturity


def test_twelve_month_dsra_holds_a_full_forward_payment() -> None:
    service = (100.0, 120.0, 140.0)
    targets = dsra_targets(service, dsra_months=12.0, periods_per_year=1)
    assert targets[0] == pytest.approx(100.0)
    assert targets[1] == pytest.approx(120.0)
    assert targets[2] == pytest.approx(140.0)
    assert targets[3] == pytest.approx(0.0)


def test_dsra_spanning_more_than_one_period_consumes_the_next_pro_rata() -> None:
    """18 months of reserve on annual periods = next payment plus half the one after."""
    service = (100.0, 200.0, 300.0)
    targets = dsra_targets(service, dsra_months=18.0, periods_per_year=1)
    assert targets[0] == pytest.approx(100.0 + 0.5 * 200.0)
    assert targets[1] == pytest.approx(200.0 + 0.5 * 300.0)


def test_semiannual_dsra_uses_period_length_correctly() -> None:
    """On semi-annual periods a 6-month reserve is one full period of service."""
    service = (50.0, 60.0, 70.0, 80.0)
    targets = dsra_targets(service, dsra_months=6.0, periods_per_year=2)
    assert targets[0] == pytest.approx(50.0)
    assert targets[1] == pytest.approx(60.0)


def test_backward_looking_dsra_lags_the_forward_variant_into_a_rising_profile() -> None:
    service = (100.0, 200.0, 300.0)
    forward = dsra_targets(service, 12.0, 1, forward_looking=True)
    backward = dsra_targets(service, 12.0, 1, forward_looking=False)
    assert backward[1] < forward[1]
    assert backward[2] < forward[2]


def test_zero_dsra_months_gives_no_reserve() -> None:
    assert dsra_targets((100.0, 200.0), 0.0, 1) == (0.0, 0.0, 0.0)
