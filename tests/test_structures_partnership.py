"""§704(b) capital accounts, DRO caps, outside basis, suspended losses.

The properties asserted here are the ones SAM provably does not have
and are therefore the ones the product is staked on. Every golden number below
is computed longhand in the docstring of the test that uses it, so a reviewer
can check the engine against arithmetic rather than against the engine.
"""

from __future__ import annotations

import pytest

from engine.structures.defaults import CAPITAL_ACCOUNT_TOLERANCE
from engine.structures.partnership import (
    PartnerRole,
    PartnerTerms,
    PeriodInputs,
    SharingRatios,
    assert_capital_account_integrity,
    run_partnership,
)

TOL = 1e-6

SPONSOR = "sponsor"
TAX_EQUITY = "tax_equity"


def _partners(
    *, te_dro: float = 0.0, sponsor_unlimited: bool = True
) -> tuple[PartnerTerms, ...]:
    return (
        PartnerTerms(
            name=SPONSOR,
            role=PartnerRole.SPONSOR,
            tax_rate=0.21,
            unlimited_dro=sponsor_unlimited,
            dro_cap=0.0 if sponsor_unlimited else 1_000.0,
            bears_residual_allocations=True,
        ),
        PartnerTerms(
            name=TAX_EQUITY,
            role=PartnerRole.TAX_EQUITY,
            tax_rate=0.21,
            dro_cap=te_dro,
        ),
    )


def _ratios(te: float = 0.99, cash_te: float = 0.5) -> SharingRatios:
    return SharingRatios(
        income={TAX_EQUITY: te, SPONSOR: 1.0 - te},
        loss={TAX_EQUITY: te, SPONSOR: 1.0 - te},
        credit={TAX_EQUITY: te, SPONSOR: 1.0 - te},
        cash={TAX_EQUITY: cash_te, SPONSOR: 1.0 - cash_te},
    )


def _golden_periods() -> tuple[PeriodInputs, ...]:
    """The hand-checked golden case. All figures in whole units.

    Year 1: sponsor contributes 40, tax equity 60. A 50 credit arises, carrying
    a 25 §50(c)(3) basis reduction. Book and taxable loss are both (100). No
    debt, so partnership minimum gain is zero and the investor's capital-account
    floor is exactly zero.

    Years 2 and 3: income of 30 then 40, no cash distributed.
    """
    return (
        PeriodInputs(
            period=0,
            year=2027,
            book_income=-100.0,
            taxable_income=-100.0,
            credit=50.0,
            itc_basis_reduction=25.0,
            cash_available=0.0,
            contributions={SPONSOR: 40.0, TAX_EQUITY: 60.0},
            nonrecourse_liability=0.0,
            book_basis=0.0,
        ),
        PeriodInputs(period=1, year=2028, book_income=30.0, taxable_income=30.0),
        PeriodInputs(period=2, year=2029, book_income=40.0, taxable_income=40.0),
    )


# ---------------------------------------------------------------------------
# Golden arithmetic
# ---------------------------------------------------------------------------


def test_golden_capital_accounts_first_three_periods() -> None:
    """Every line of the golden case, computed by hand.

    **Year 1.**
    Contributions put the sponsor at 40 and the investor at 60. The credit of
    50 is shared 99/1, so the §50(c)(3) basis reduction of 25 is charged 24.75
    to the investor and 0.25 to the sponsor (Treas. Reg.
    §1.704-1(b)(2)(iv)(j) treats it as an item of loss). That leaves capital
    accounts of 39.75 and 35.25.

    The 100 book loss would go 99 / 1 on the stated ratio. The investor has no
    DRO and no minimum gain, so its floor is zero and its capacity is exactly
    35.25. It takes 35.25 and the remaining 63.75 **reallocates to the
    sponsor**, which therefore absorbs 1 + 63.75 = 64.75. Allocations still sum
    to 100.

    Closing capital: sponsor 39.75 - 64.75 = **(25.00)**; investor **0.00**.

    Outside basis: the sponsor has 40 - 0.25 = 39.75 available against a 64.75
    loss, so **39.75 is allowed and 25.00 is suspended** under §704(d). The
    investor has 60 - 24.75 = 35.25 against a 35.25 loss: fully allowed, basis
    to zero, nothing suspended.

    **Year 2.** Income 30 goes 29.7 / 0.3. The sponsor's 0.3 of basis frees
    0.30 of suspended loss, leaving **24.70**.

    **Year 3.** Income 40 goes 39.6 / 0.4, freeing another 0.40 and leaving
    **24.30**.
    """
    result = run_partnership(
        _partners(), _golden_periods(), tuple(_ratios() for _ in range(3))
    )

    y1 = result.periods[0]
    sponsor, te = y1.partner(SPONSOR), y1.partner(TAX_EQUITY)

    assert te.credit_allocated == pytest.approx(49.5, abs=TOL)
    assert sponsor.credit_allocated == pytest.approx(0.5, abs=TOL)
    assert te.itc_basis_reduction_share == pytest.approx(24.75, abs=TOL)
    assert sponsor.itc_basis_reduction_share == pytest.approx(0.25, abs=TOL)

    assert te.book_allocation_base == pytest.approx(-99.0, abs=TOL)
    assert te.book_allocation == pytest.approx(-35.25, abs=TOL)
    assert te.book_reallocation == pytest.approx(63.75, abs=TOL)
    assert sponsor.book_allocation == pytest.approx(-64.75, abs=TOL)
    assert sponsor.book_allocation + te.book_allocation == pytest.approx(
        -100.0, abs=TOL
    )

    assert sponsor.capital_closing == pytest.approx(-25.0, abs=TOL)
    assert te.capital_closing == pytest.approx(0.0, abs=TOL)
    assert te.capital_floor == pytest.approx(0.0, abs=TOL)

    assert sponsor.taxable_loss_allowed == pytest.approx(39.75, abs=TOL)
    assert sponsor.taxable_loss_suspended == pytest.approx(25.0, abs=TOL)
    assert sponsor.outside_basis_closing == pytest.approx(0.0, abs=TOL)
    assert te.taxable_loss_allowed == pytest.approx(35.25, abs=TOL)
    assert te.suspended_loss_closing == pytest.approx(0.0, abs=TOL)

    y2 = result.periods[1]
    assert y2.partner(TAX_EQUITY).book_allocation == pytest.approx(29.7, abs=TOL)
    assert y2.partner(SPONSOR).book_allocation == pytest.approx(0.3, abs=TOL)
    assert y2.partner(SPONSOR).suspended_loss_freed == pytest.approx(0.3, abs=TOL)
    assert y2.partner(SPONSOR).suspended_loss_closing == pytest.approx(24.7, abs=TOL)
    assert y2.partner(TAX_EQUITY).capital_closing == pytest.approx(29.7, abs=TOL)
    assert y2.partner(SPONSOR).capital_closing == pytest.approx(-24.7, abs=TOL)

    y3 = result.periods[2]
    assert y3.partner(SPONSOR).suspended_loss_freed == pytest.approx(0.4, abs=TOL)
    assert y3.partner(SPONSOR).suspended_loss_closing == pytest.approx(24.3, abs=TOL)
    assert y3.partner(TAX_EQUITY).capital_closing == pytest.approx(69.3, abs=TOL)
    assert y3.partner(SPONSOR).capital_closing == pytest.approx(-24.3, abs=TOL)


def test_suspended_loss_carryforward_is_explicit_and_monotone_until_freed() -> None:
    """The §704(d) carryforward balance, asserted period by period."""
    result = run_partnership(
        _partners(), _golden_periods(), tuple(_ratios() for _ in range(3))
    )
    assert result.suspended_losses(SPONSOR) == pytest.approx(
        (25.0, 24.7, 24.3), abs=TOL
    )
    assert result.suspended_losses(TAX_EQUITY) == pytest.approx(
        (0.0, 0.0, 0.0), abs=TOL
    )


def test_a_loss_disallowed_by_basis_is_freed_when_basis_is_restored() -> None:
    """A partner with no basis suspends its loss and deducts it later.

    Year 1: contributions of 10 each, book/tax loss of 60 shared 50/50, so each
    partner is allocated 30 against 10 of basis. **20 is suspended each.**
    Year 2: income of 50 shared 50/50 restores 25 of basis to each, which frees
    20 of suspended loss and leaves **nil** suspended and 5 of basis.
    """
    partners = (
        PartnerTerms(
            name=SPONSOR,
            role=PartnerRole.SPONSOR,
            tax_rate=0.21,
            unlimited_dro=True,
            bears_residual_allocations=True,
        ),
        PartnerTerms(
            name=TAX_EQUITY,
            role=PartnerRole.TAX_EQUITY,
            tax_rate=0.21,
            unlimited_dro=True,
        ),
    )
    half = SharingRatios(
        income={SPONSOR: 0.5, TAX_EQUITY: 0.5},
        loss={SPONSOR: 0.5, TAX_EQUITY: 0.5},
        credit={SPONSOR: 0.5, TAX_EQUITY: 0.5},
        cash={SPONSOR: 0.5, TAX_EQUITY: 0.5},
    )
    periods = (
        PeriodInputs(
            period=0,
            year=2027,
            book_income=-60.0,
            taxable_income=-60.0,
            contributions={SPONSOR: 10.0, TAX_EQUITY: 10.0},
        ),
        PeriodInputs(period=1, year=2028, book_income=50.0, taxable_income=50.0),
    )
    result = run_partnership(partners, periods, (half, half))

    y1 = result.periods[0].partner(TAX_EQUITY)
    assert y1.taxable_allocation == pytest.approx(-30.0, abs=TOL)
    assert y1.taxable_loss_allowed == pytest.approx(10.0, abs=TOL)
    assert y1.taxable_loss_suspended == pytest.approx(20.0, abs=TOL)
    assert y1.suspended_loss_closing == pytest.approx(20.0, abs=TOL)
    assert y1.outside_basis_closing == pytest.approx(0.0, abs=TOL)

    y2 = result.periods[1].partner(TAX_EQUITY)
    assert y2.suspended_loss_opening == pytest.approx(20.0, abs=TOL)
    assert y2.suspended_loss_freed == pytest.approx(20.0, abs=TOL)
    assert y2.suspended_loss_closing == pytest.approx(0.0, abs=TOL)
    assert y2.outside_basis_closing == pytest.approx(5.0, abs=TOL)


# ---------------------------------------------------------------------------
# The integrity invariant
# ---------------------------------------------------------------------------


def test_capital_account_integrity_holds_in_every_period_not_just_the_last() -> None:
    """Σ capital + Σ distributions - Σ contributions + Σ ITC adjustment
    == cumulative allocations, asserted at the close of every period."""
    periods = (
        PeriodInputs(
            period=0,
            year=2027,
            book_income=-150.0,
            taxable_income=-150.0,
            credit=60.0,
            itc_basis_reduction=30.0,
            cash_available=12.0,
            contributions={SPONSOR: 50.0, TAX_EQUITY: 120.0},
            nonrecourse_liability=160.0,
            book_basis=20.0,
        ),
        PeriodInputs(
            period=1,
            year=2028,
            book_income=14.0,
            taxable_income=14.0,
            cash_available=13.0,
            nonrecourse_liability=150.0,
            book_basis=15.0,
        ),
        PeriodInputs(
            period=2,
            year=2029,
            book_income=15.0,
            taxable_income=15.0,
            cash_available=14.0,
            nonrecourse_liability=138.0,
            book_basis=10.0,
        ),
    )
    result = run_partnership(
        _partners(), periods, tuple(_ratios(cash_te=0.2) for _ in range(3))
    )
    assert_capital_account_integrity(result)  # explicit; also runs inside

    cum_alloc = {SPONSOR: 0.0, TAX_EQUITY: 0.0}
    cum_dist = {SPONSOR: 0.0, TAX_EQUITY: 0.0}
    cum_contrib = {SPONSOR: 0.0, TAX_EQUITY: 0.0}
    cum_itc = {SPONSOR: 0.0, TAX_EQUITY: 0.0}
    for period in result.periods:
        for name in (SPONSOR, TAX_EQUITY):
            row = period.partner(name)
            cum_alloc[name] += row.book_allocation
            cum_dist[name] += row.distributions
            cum_contrib[name] += row.contributions
            cum_itc[name] += row.itc_basis_reduction_share
            assert (
                row.capital_closing
                + cum_dist[name]
                - cum_contrib[name]
                + cum_itc[name]
            ) == pytest.approx(cum_alloc[name], abs=CAPITAL_ACCOUNT_TOLERANCE)


def test_allocations_always_sum_to_one_hundred_percent_of_the_item() -> None:
    periods = (
        PeriodInputs(
            period=0,
            year=2027,
            book_income=-500.0,
            taxable_income=-500.0,
            contributions={SPONSOR: 10.0, TAX_EQUITY: 40.0},
        ),
        PeriodInputs(period=1, year=2028, book_income=-20.0, taxable_income=-20.0),
        PeriodInputs(period=2, year=2029, book_income=60.0, taxable_income=60.0),
    )
    result = run_partnership(_partners(), periods, tuple(_ratios() for _ in range(3)))
    for period in result.periods:
        total = sum(p.book_allocation for p in period.partners)
        assert total == pytest.approx(period.book_income, abs=TOL)


# ---------------------------------------------------------------------------
# DRO cap and reallocation
# ---------------------------------------------------------------------------


def test_dro_cap_is_never_breached_and_the_reallocation_fires() -> None:
    """The investor absorbs loss to exactly its floor and no further."""
    periods = (
        PeriodInputs(
            period=0,
            year=2027,
            book_income=-400.0,
            taxable_income=-400.0,
            contributions={SPONSOR: 100.0, TAX_EQUITY: 100.0},
        ),
    )
    result = run_partnership(_partners(te_dro=0.0), periods, (_ratios(),))
    te = result.periods[0].partner(TAX_EQUITY)
    sponsor = result.periods[0].partner(SPONSOR)

    assert te.book_allocation_base == pytest.approx(-396.0, abs=TOL)
    assert te.book_allocation == pytest.approx(-100.0, abs=TOL)
    assert te.capital_after_allocation == pytest.approx(0.0, abs=TOL)
    assert te.capital_after_allocation >= te.capital_floor - TOL
    assert te.floor_binds is True
    assert sponsor.book_allocation == pytest.approx(-300.0, abs=TOL)
    assert te.book_allocation + sponsor.book_allocation == pytest.approx(
        -400.0, abs=TOL
    )
    assert result.periods[0].reallocations
    event = result.periods[0].reallocations[0]
    assert event.from_partner == TAX_EQUITY
    assert event.to_partner == SPONSOR
    assert event.amount == pytest.approx(296.0, abs=TOL)


def test_a_dro_lets_the_investor_go_negative_by_exactly_the_dro_amount() -> None:
    result = run_partnership(
        _partners(te_dro=50.0),
        (
            PeriodInputs(
                period=0,
                year=2027,
                book_income=-400.0,
                taxable_income=-400.0,
                contributions={SPONSOR: 100.0, TAX_EQUITY: 100.0},
            ),
        ),
        (_ratios(),),
    )
    te = result.periods[0].partner(TAX_EQUITY)
    assert te.capital_floor == pytest.approx(-50.0, abs=TOL)
    assert te.book_allocation == pytest.approx(-150.0, abs=TOL)
    assert te.capital_after_allocation == pytest.approx(-50.0, abs=TOL)


def test_minimum_gain_acts_as_a_deemed_dro_and_lets_losses_keep_flowing() -> None:
    """§1.704-2(g)(1): a share of minimum gain is a deemed DRO.

    The same 400 loss, but now the partnership carries 300 of nonrecourse debt
    against zero book basis, so partnership minimum gain is 300. The investor's
    99% share of the 300 of nonrecourse deductions gives it a 297 minimum-gain
    share, so its floor drops from 0 to (297) and it can absorb the whole 396
    the ratio gives it — 100 of capital plus 296 of deficit.
    """
    result = run_partnership(
        _partners(te_dro=0.0),
        (
            PeriodInputs(
                period=0,
                year=2027,
                book_income=-400.0,
                taxable_income=-400.0,
                contributions={SPONSOR: 100.0, TAX_EQUITY: 100.0},
                nonrecourse_liability=300.0,
                book_basis=0.0,
            ),
        ),
        (_ratios(),),
    )
    te = result.periods[0].partner(TAX_EQUITY)
    assert result.periods[0].minimum_gain == pytest.approx(300.0, abs=TOL)
    assert te.minimum_gain_share == pytest.approx(297.0, abs=TOL)
    assert te.capital_floor == pytest.approx(-297.0, abs=TOL)
    assert te.book_allocation == pytest.approx(-396.0, abs=TOL)
    assert te.floor_binds is False


def test_reallocation_stops_when_no_partner_has_capacity_and_warns() -> None:
    """With every DRO capped, the residual bearer takes it and says so."""
    partners = (
        PartnerTerms(
            name=SPONSOR,
            role=PartnerRole.SPONSOR,
            tax_rate=0.21,
            dro_cap=10.0,
            unlimited_dro=False,
            bears_residual_allocations=True,
        ),
        PartnerTerms(
            name=TAX_EQUITY, role=PartnerRole.TAX_EQUITY, tax_rate=0.21, dro_cap=0.0
        ),
    )
    result = run_partnership(
        partners,
        (
            PeriodInputs(
                period=0,
                year=2027,
                book_income=-500.0,
                taxable_income=-500.0,
                contributions={SPONSOR: 20.0, TAX_EQUITY: 20.0},
            ),
        ),
        (_ratios(),),
    )
    assert any("residual bearer" in w for w in result.warnings)
    total = sum(p.book_allocation for p in result.periods[0].partners)
    assert total == pytest.approx(-500.0, abs=TOL)


# ---------------------------------------------------------------------------
# Minimum gain chargeback
# ---------------------------------------------------------------------------


def test_minimum_gain_chargeback_fires_on_a_net_decrease() -> None:
    """§1.704-2(f): a net decrease in minimum gain charges income back first.

    Year 1 builds 100 of minimum gain (100 of nonrecourse debt against nil book
    basis), allocated 99 / 1 with the nonrecourse deductions. Year 2 pays the
    debt down to 60, a net decrease of 40, so 40 of the year's income is
    charged back **before** any sharing-ratio allocation, 39.6 to the investor
    and 0.40 to the sponsor.
    """
    periods = (
        PeriodInputs(
            period=0,
            year=2027,
            book_income=-100.0,
            taxable_income=-100.0,
            contributions={SPONSOR: 10.0, TAX_EQUITY: 10.0},
            nonrecourse_liability=100.0,
            book_basis=0.0,
        ),
        PeriodInputs(
            period=1,
            year=2028,
            book_income=80.0,
            taxable_income=80.0,
            nonrecourse_liability=60.0,
            book_basis=0.0,
        ),
    )
    result = run_partnership(_partners(), periods, (_ratios(), _ratios()))

    assert result.periods[0].minimum_gain == pytest.approx(100.0, abs=TOL)
    assert result.periods[0].partner(TAX_EQUITY).minimum_gain_share == pytest.approx(
        99.0, abs=TOL
    )

    y2 = result.periods[1]
    assert y2.minimum_gain == pytest.approx(60.0, abs=TOL)
    assert y2.minimum_gain_net_decrease == pytest.approx(40.0, abs=TOL)
    assert y2.chargeback_required == pytest.approx(40.0, abs=TOL)
    assert y2.chargeback_allocated == pytest.approx(40.0, abs=TOL)
    assert y2.partner(TAX_EQUITY).chargeback_income == pytest.approx(39.6, abs=TOL)
    assert y2.partner(SPONSOR).chargeback_income == pytest.approx(0.4, abs=TOL)
    # The chargeback consumes minimum-gain share.
    assert y2.partner(TAX_EQUITY).minimum_gain_share == pytest.approx(59.4, abs=TOL)
    # And the whole 80 of income is still allocated in full.
    assert sum(p.book_allocation for p in y2.partners) == pytest.approx(80.0, abs=TOL)


def test_chargeback_carries_forward_when_there_is_not_enough_income() -> None:
    periods = (
        PeriodInputs(
            period=0,
            year=2027,
            book_income=-100.0,
            taxable_income=-100.0,
            contributions={SPONSOR: 10.0, TAX_EQUITY: 10.0},
            nonrecourse_liability=100.0,
            book_basis=0.0,
        ),
        PeriodInputs(
            period=1,
            year=2028,
            book_income=5.0,
            taxable_income=5.0,
            nonrecourse_liability=40.0,
            book_basis=0.0,
        ),
    )
    result = run_partnership(_partners(), periods, (_ratios(), _ratios()))
    y2 = result.periods[1]
    assert y2.chargeback_required == pytest.approx(60.0, abs=TOL)
    assert y2.chargeback_allocated == pytest.approx(5.0, abs=TOL)
    assert y2.chargeback_carryforward == pytest.approx(55.0, abs=TOL)


# ---------------------------------------------------------------------------
# Guard rails
# ---------------------------------------------------------------------------


def test_sharing_ratios_that_do_not_sum_to_one_are_rejected() -> None:
    with pytest.raises(ValueError, match="sum to"):
        SharingRatios(
            income={SPONSOR: 0.5, TAX_EQUITY: 0.4},
            loss={SPONSOR: 0.5, TAX_EQUITY: 0.5},
            credit={SPONSOR: 0.5, TAX_EQUITY: 0.5},
            cash={SPONSOR: 0.5, TAX_EQUITY: 0.5},
        )


def test_exactly_one_residual_bearer_is_required() -> None:
    both = (
        PartnerTerms(
            name=SPONSOR,
            role=PartnerRole.SPONSOR,
            tax_rate=0.21,
            bears_residual_allocations=True,
        ),
        PartnerTerms(
            name=TAX_EQUITY,
            role=PartnerRole.TAX_EQUITY,
            tax_rate=0.21,
            bears_residual_allocations=True,
        ),
    )
    with pytest.raises(ValueError, match="exactly one partner"):
        run_partnership(
            both, (PeriodInputs(period=0, year=2027),), (_ratios(),)
        )


def test_outside_basis_never_goes_negative() -> None:
    periods = (
        PeriodInputs(
            period=0,
            year=2027,
            book_income=-900.0,
            taxable_income=-900.0,
            cash_available=30.0,
            contributions={SPONSOR: 10.0, TAX_EQUITY: 10.0},
        ),
    )
    result = run_partnership(_partners(), periods, (_ratios(),))
    for row in result.periods[0].partners:
        assert row.outside_basis_closing >= -TOL


def test_distribution_in_excess_of_basis_is_section_731_gain() -> None:
    periods = (
        PeriodInputs(
            period=0,
            year=2027,
            book_income=0.0,
            taxable_income=0.0,
            cash_available=50.0,
            contributions={SPONSOR: 10.0, TAX_EQUITY: 10.0},
        ),
    )
    result = run_partnership(_partners(), periods, (_ratios(cash_te=0.5),))
    te = result.periods[0].partner(TAX_EQUITY)
    assert te.distributions == pytest.approx(25.0, abs=TOL)
    assert te.excess_distribution_gain == pytest.approx(15.0, abs=TOL)
    assert te.outside_basis_closing == pytest.approx(0.0, abs=TOL)


def test_reruns_are_bit_identical() -> None:
    args = (_partners(), _golden_periods(), tuple(_ratios() for _ in range(3)))
    a = run_partnership(*args)
    b = run_partnership(*args)
    assert a.capital_account(TAX_EQUITY) == b.capital_account(TAX_EQUITY)
    assert a.outside_basis(SPONSOR) == b.outside_basis(SPONSOR)
