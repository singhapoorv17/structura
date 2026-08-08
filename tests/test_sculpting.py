"""Golden cases for debt sculpting and the amortisation alternatives.

Every number asserted here was computed by hand (40-digit Decimal arithmetic,
outside the engine) from the closed-form annuity mathematics. If the engine
disagrees with these, the engine is wrong.
"""

from __future__ import annotations

import pytest

from engine.debt import (
    build_schedule,
    effective_grace_periods,
    sculpted_debt_size,
    service_for_debt_size,
    size_debt_service,
)
from engine.models import AmortizationStyle
from tests.conftest import CENT, annuity_factor_reference

FLAT_CFADS = tuple(10_000_000.0 for _ in range(10))
RATE = 0.06


# ---------------------------------------------------------------------------
# GOLDEN (a) - flat CFADS, constant target DSCR
# ---------------------------------------------------------------------------


def test_flat_cfads_sculpt_matches_annuity_to_the_cent() -> None:
    """Flat CFADS at a flat target: debt service is CFADS/DSCR in every period
    and the quantum is exactly the annuity PV of that service.

    Hand-computed: DS = 10,000,000 / 1.25 = 8,000,000 every year.
    Annuity factor at 6% for 10 years = 7.360087051414697...
    Debt = 8,000,000 x 7.360087051414697 = 58,880,696.41131757...
    """
    targets = tuple(1.25 for _ in range(10))
    debt_size, service = sculpted_debt_size(FLAT_CFADS, targets, RATE)

    assert debt_size == pytest.approx(58_880_696.4113176, abs=CENT)
    for ds in service:
        assert ds == pytest.approx(8_000_000.0, abs=CENT)

    # Independent re-derivation of the annuity factor.
    assert debt_size == pytest.approx(
        8_000_000.0 * annuity_factor_reference(RATE, 10), abs=CENT
    )


def test_flat_cfads_schedule_amortises_exactly_and_holds_dscr() -> None:
    targets = tuple(1.25 for _ in range(10))
    debt_size, service = sculpted_debt_size(FLAT_CFADS, targets, RATE)
    schedule = build_schedule(
        debt_size, service, FLAT_CFADS, targets, RATE, 1, AmortizationStyle.SCULPTED
    )

    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    assert sum(schedule.principal) == pytest.approx(debt_size, abs=CENT)
    for d in schedule.dscr:
        assert d == pytest.approx(1.25, abs=1e-12)
    # Interest + principal reconciles to service in every period.
    for i in range(10):
        assert schedule.interest[i] + schedule.principal[i] == pytest.approx(
            schedule.debt_service[i], abs=CENT
        )
    # First period interest is exactly rate x debt.
    assert schedule.interest[0] == pytest.approx(debt_size * RATE, abs=CENT)


# ---------------------------------------------------------------------------
# GOLDEN (b) - level payment against the standard annuity formula
# ---------------------------------------------------------------------------


def test_level_payment_matches_standard_annuity_formula() -> None:
    """Level payment is set by the tightest period, then PV'd as an annuity.

    CFADS rises 10m, 11m, ... 19m; target 1.30x. The binding period is the
    first: A = 10,000,000 / 1.3 = 7,692,307.6923...
    Debt = A x 7.360087051414697 = 56,616,054.24165151...
    Cross-check: the mortgage payment formula D x r / (1 - (1+r)^-n) must
    return A again.
    """
    cfads = tuple(10_000_000.0 + 1_000_000.0 * i for i in range(10))
    targets = tuple(1.30 for _ in range(10))
    debt_size, service = size_debt_service(
        cfads, targets, RATE, AmortizationStyle.LEVEL
    )

    assert debt_size == pytest.approx(56_616_054.2416515, abs=CENT)
    assert all(s == pytest.approx(7_692_307.6923077, abs=CENT) for s in service)

    payment = debt_size * RATE / (1.0 - (1.0 + RATE) ** -10)
    assert payment == pytest.approx(service[0], abs=CENT)

    schedule = build_schedule(
        debt_size, service, cfads, targets, RATE, 1, AmortizationStyle.LEVEL
    )
    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    assert schedule.min_dscr == pytest.approx(1.30, abs=1e-12)
    # Later periods are over-covered: that unused coverage is exactly what
    # sculpting monetises.
    assert schedule.dscr[-1] > 2.4


def test_fixed_principal_binds_in_the_first_period() -> None:
    """Fixed principal front-loads service, so period 1 always binds.

    D x (1/10 + 0.06) = 8,000,000  ->  D = 50,000,000 exactly.
    """
    targets = tuple(1.25 for _ in range(10))
    debt_size, service = size_debt_service(
        FLAT_CFADS, targets, RATE, AmortizationStyle.FIXED_PRINCIPAL
    )
    assert debt_size == pytest.approx(50_000_000.0, abs=CENT)

    schedule = build_schedule(
        debt_size, service, FLAT_CFADS, targets, RATE, 1,
        AmortizationStyle.FIXED_PRINCIPAL,
    )
    for p in schedule.principal:
        assert p == pytest.approx(5_000_000.0, abs=CENT)
    assert schedule.dscr[0] == pytest.approx(1.25, abs=1e-12)
    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)


def test_sculpting_raises_the_most_debt_of_the_three_styles() -> None:
    """Sculpted >= level >= fixed principal off identical CFADS.

    This ordering is the reason sculpting is market standard, and it must hold
    for any CFADS profile.
    """
    cfads = tuple(10_000_000.0 + 400_000.0 * i for i in range(15))
    targets = tuple(1.35 for _ in range(15))
    sizes = {
        style: size_debt_service(cfads, targets, RATE, style)[0]
        for style in AmortizationStyle
    }
    assert sizes[AmortizationStyle.SCULPTED] > sizes[AmortizationStyle.LEVEL]
    assert sizes[AmortizationStyle.LEVEL] > sizes[AmortizationStyle.FIXED_PRINCIPAL]


# ---------------------------------------------------------------------------
# GOLDEN (d) - time-varying DSCR target
# ---------------------------------------------------------------------------


def test_time_varying_dscr_target() -> None:
    """A contracted-then-merchant deal: 1.20x for 5 years, 1.50x thereafter.

    DS = 8,333,333.333... for years 1-5 and 6,666,666.666... for years 6-10.
    PV at 6% = 56,087,853.3187075...
    """
    targets = tuple([1.20] * 5 + [1.50] * 5)
    debt_size, service = sculpted_debt_size(FLAT_CFADS, targets, RATE)

    assert debt_size == pytest.approx(56_087_853.3187075, abs=CENT)
    assert service[0] == pytest.approx(10_000_000.0 / 1.20, abs=CENT)
    assert service[5] == pytest.approx(10_000_000.0 / 1.50, abs=CENT)

    schedule = build_schedule(
        debt_size, service, FLAT_CFADS, targets, RATE, 1, AmortizationStyle.SCULPTED
    )
    for achieved, target in zip(schedule.dscr, targets):
        assert achieved == pytest.approx(target, abs=1e-12)
    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    # Debt service steps DOWN when the target steps UP - the signature of a
    # deal sculpted to a merchant tail.
    assert schedule.debt_service[5] < schedule.debt_service[4]


# ---------------------------------------------------------------------------
# Grace periods
# ---------------------------------------------------------------------------


def test_grace_period_is_interest_only_and_defers_amortisation() -> None:
    """Two years of grace: interest only, then a sculpt over the remaining 8.

    Debt = PV over periods 3..10 of 8,000,000 discounted back to the end of
    period 2 = 8,000,000 x annuity(6%, 8) = 49,673,752.68...
    """
    targets = tuple(1.25 for _ in range(10))
    debt_size, service = sculpted_debt_size(
        FLAT_CFADS, targets, RATE, grace_periods=2
    )

    expected = 8_000_000.0 * annuity_factor_reference(RATE, 8)
    assert debt_size == pytest.approx(expected, abs=CENT)
    assert service[0] == pytest.approx(debt_size * RATE, abs=CENT)
    assert service[1] == pytest.approx(debt_size * RATE, abs=CENT)
    assert service[2] == pytest.approx(8_000_000.0, abs=CENT)

    schedule = build_schedule(
        debt_size, service, FLAT_CFADS, targets, RATE, 1,
        AmortizationStyle.SCULPTED, grace_periods=2,
    )
    assert schedule.principal[0] == pytest.approx(0.0, abs=CENT)
    assert schedule.principal[1] == pytest.approx(0.0, abs=CENT)
    assert schedule.opening_balance[2] == pytest.approx(debt_size, abs=CENT)
    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    # Grace raises less debt than no grace: two years of principal are lost
    # from the front while interest still has to be covered.
    no_grace, _ = sculpted_debt_size(FLAT_CFADS, targets, RATE)
    assert debt_size < no_grace


def test_grace_period_interest_cap_binds_when_cfads_is_thin_early() -> None:
    """If early CFADS cannot cover interest-only service, the quantum is capped.

    CFADS is 1,000,000 in year 1 (grace) and 10,000,000 thereafter. At a 1.25x
    target the grace period can service 800,000 of interest, so the facility
    cannot exceed 800,000 / 0.06 = 13,333,333.33.
    """
    cfads = (1_000_000.0,) + tuple(10_000_000.0 for _ in range(9))
    targets = tuple(1.25 for _ in range(10))
    debt_size, service = sculpted_debt_size(cfads, targets, RATE, grace_periods=1)

    assert debt_size == pytest.approx(800_000.0 / RATE, abs=CENT)
    assert service[0] == pytest.approx(800_000.0, abs=CENT)

    schedule = build_schedule(
        debt_size, service, cfads, targets, RATE, 1,
        AmortizationStyle.SCULPTED, grace_periods=1,
    )
    # Grace period sits exactly on target; the amortising periods are
    # over-covered because the profile was scaled down pro rata.
    assert schedule.dscr[0] == pytest.approx(1.25, abs=1e-9)
    assert all(d > 1.25 for d in schedule.dscr[1:])
    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)


def test_steeply_ramping_cfads_gets_an_automatic_interest_only_holiday() -> None:
    """A pure PV sculpt against a steep ramp at a high rate implies principal
    going backwards. No term facility permits that, so the engine lengthens the
    grace period until every period amortises non-negatively.

    CFADS ramps 3% a year off 8,000,000 at a 9.5% coupon and a 1.25x target.
    """
    cfads = tuple(8_000_000.0 * 1.03**i for i in range(20))
    targets = tuple(1.25 for _ in range(20))
    rate = 0.095

    naive_grace = effective_grace_periods(cfads, targets, rate, 0)
    assert naive_grace > 0

    debt_size, service = sculpted_debt_size(cfads, targets, rate)
    schedule = build_schedule(
        debt_size, service, cfads, targets, rate, 1,
        AmortizationStyle.SCULPTED, naive_grace,
    )
    assert all(p >= -CENT for p in schedule.principal)
    assert all(d >= 1.25 - 1e-9 for d in schedule.dscr)
    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    # The forced holiday costs debt capacity versus the unconstrained PV.
    unconstrained_pv = sum(
        (c / 1.25) / (1.0 + rate) ** (i + 1) for i, c in enumerate(cfads)
    )
    assert debt_size < unconstrained_pv


def test_no_holiday_is_imposed_when_the_naive_sculpt_already_works() -> None:
    targets = tuple(1.25 for _ in range(10))
    assert effective_grace_periods(FLAT_CFADS, targets, RATE, 0) == 0
    assert effective_grace_periods(FLAT_CFADS, targets, RATE, 2) == 2


def test_grace_longer_than_tenor_is_rejected() -> None:
    targets = tuple(1.25 for _ in range(10))
    with pytest.raises(ValueError, match="grace period"):
        sculpted_debt_size(FLAT_CFADS, targets, RATE, grace_periods=10)


# ---------------------------------------------------------------------------
# Scaling to a constrained quantum
# ---------------------------------------------------------------------------


def test_service_scales_linearly_below_the_dscr_maximum() -> None:
    """Cutting the debt scales the whole service profile and lifts every DSCR."""
    targets = tuple(1.25 for _ in range(10))
    max_size, _ = sculpted_debt_size(FLAT_CFADS, targets, RATE)
    target_size = max_size * 0.8

    service = service_for_debt_size(
        target_size, FLAT_CFADS, targets, RATE, AmortizationStyle.SCULPTED
    )
    schedule = build_schedule(
        target_size, service, FLAT_CFADS, targets, RATE, 1,
        AmortizationStyle.SCULPTED,
    )
    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
    for d in schedule.dscr:
        assert d == pytest.approx(1.25 / 0.8, rel=1e-12)


def test_requesting_more_than_dscr_supports_is_rejected() -> None:
    targets = tuple(1.25 for _ in range(10))
    max_size, _ = sculpted_debt_size(FLAT_CFADS, targets, RATE)
    with pytest.raises(ValueError, match="exceeds the DSCR-supportable"):
        service_for_debt_size(
            max_size * 1.01, FLAT_CFADS, targets, RATE, AmortizationStyle.SCULPTED
        )


def test_zero_interest_rate_degenerates_to_simple_division() -> None:
    """At r = 0 the annuity factor is just n, which the engine must not divide by."""
    targets = tuple(1.25 for _ in range(10))
    debt_size, service = sculpted_debt_size(FLAT_CFADS, targets, 0.0)
    assert debt_size == pytest.approx(80_000_000.0, abs=CENT)
    schedule = build_schedule(
        debt_size, service, FLAT_CFADS, targets, 0.0, 1, AmortizationStyle.SCULPTED
    )
    assert all(i == 0.0 for i in schedule.interest)
    assert schedule.closing_balance[-1] == pytest.approx(0.0, abs=CENT)
