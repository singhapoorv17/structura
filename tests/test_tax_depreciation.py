"""Cost recovery, and the §50(c)(3) 50% ITC basis reduction.

The headline identity, asserted directly because it is the rule most often got
wrong outside the asset class::

    depreciable basis = capex - 0.5 x ITC
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.tax import (
    DepreciationMethod,
    ForeignEntityFlags,
    TaxProject,
    TaxScenario,
    Technology,
    build_schedule,
    compute_tax,
    recovery_percentages,
    reduced_basis,
)

CAPEX = 100_000_000.0
CLEAN_SUPPLY_CHAIN = ForeignEntityFlags(received_material_assistance_from_pfe=False)


# ---------------------------------------------------------------------------
# §50(c)(3)
# ---------------------------------------------------------------------------


def test_itc_basis_reduction_is_half_the_credit() -> None:
    itc = 0.30 * CAPEX
    assert reduced_basis(CAPEX, itc) == pytest.approx(CAPEX - 0.5 * itc)
    assert reduced_basis(CAPEX, itc) == pytest.approx(85_000_000.0)


def test_basis_reduction_flows_through_the_full_engine() -> None:
    """A 30% ITC on a $100m storage project depreciates $85m, not $100m."""
    project = TaxProject(
        technology=Technology.STORAGE,
        capacity_mw=100.0,
        capex=CAPEX,
        placed_in_service_date=date(2028, 6, 30),
        begin_construction_date=date(2026, 3, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        foreign_entity_flags=CLEAN_SUPPLY_CHAIN,
    )
    result = compute_tax(project, TaxScenario(bonus_rate=0.0))

    assert result.credit.credit_amount == pytest.approx(30_000_000.0)
    assert result.depreciation.basis_reduction == pytest.approx(15_000_000.0)
    assert result.depreciation.depreciable_basis == pytest.approx(85_000_000.0)
    assert (
        result.depreciation.original_basis - result.depreciation.basis_reduction
        == pytest.approx(result.depreciation.depreciable_basis)
    )


def test_a_ptc_deal_has_no_basis_reduction() -> None:
    """No investment credit, no §50(c)(3) haircut - PTC deals depreciate more."""
    schedule = build_schedule(CAPEX, itc_amount=0.0)
    assert schedule.depreciable_basis == pytest.approx(CAPEX)


def test_adders_increase_the_credit_and_therefore_shrink_the_basis() -> None:
    """40% ITC -> 20% basis reduction. The adders are not free."""
    schedule = build_schedule(CAPEX, itc_amount=0.40 * CAPEX)
    assert schedule.depreciable_basis == pytest.approx(80_000_000.0)


# ---------------------------------------------------------------------------
# Recovery tables
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", list(DepreciationMethod))
def test_every_recovery_table_sums_to_one(method: DepreciationMethod) -> None:
    assert sum(recovery_percentages(method)) == pytest.approx(1.0)


def test_macrs_5_year_table_matches_pub_946() -> None:
    assert recovery_percentages(DepreciationMethod.MACRS_5) == (
        0.20,
        0.32,
        0.192,
        0.1152,
        0.1152,
        0.0576,
    )


def test_macrs_15_year_table_has_16_periods_under_the_half_year_convention() -> None:
    table = recovery_percentages(DepreciationMethod.MACRS_15)
    assert len(table) == 16
    assert table[0] == pytest.approx(0.05)


@pytest.mark.parametrize(
    ("method", "life"),
    [
        (DepreciationMethod.SL_5, 5),
        (DepreciationMethod.SL_15, 15),
        (DepreciationMethod.SL_20, 20),
        (DepreciationMethod.SL_39, 39),
    ],
)
def test_straight_line_half_year_convention(
    method: DepreciationMethod, life: int
) -> None:
    table = recovery_percentages(method)

    assert len(table) == life + 1
    assert table[0] == pytest.approx(1.0 / (2 * life))
    assert table[-1] == pytest.approx(1.0 / (2 * life))
    assert table[1] == pytest.approx(1.0 / life)


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


def test_macrs_5_schedule_recovers_the_whole_reduced_basis() -> None:
    schedule = build_schedule(CAPEX, itc_amount=0.30 * CAPEX, bonus_rate=0.0)

    assert schedule.total_deductions == pytest.approx(85_000_000.0)
    assert schedule.periods[-1].closing_basis == pytest.approx(0.0, abs=1e-6)
    assert schedule.periods[0].total_deduction == pytest.approx(0.20 * 85_000_000.0)


def test_bonus_is_taken_on_the_reduced_basis_in_year_one() -> None:
    schedule = build_schedule(CAPEX, itc_amount=0.30 * CAPEX, bonus_rate=1.0)

    assert schedule.bonus_deduction == pytest.approx(85_000_000.0)
    assert schedule.periods[0].total_deduction == pytest.approx(85_000_000.0)
    assert schedule.total_deductions == pytest.approx(85_000_000.0)
    assert all(p.total_deduction == pytest.approx(0.0) for p in schedule.periods[1:])


def test_partial_bonus_splits_between_bonus_and_the_recovery_table() -> None:
    schedule = build_schedule(CAPEX, itc_amount=0.30 * CAPEX, bonus_rate=0.60)

    depreciable = 85_000_000.0
    bonus = 0.60 * depreciable
    remaining = depreciable - bonus

    assert schedule.bonus_deduction == pytest.approx(bonus)
    assert schedule.periods[0].total_deduction == pytest.approx(bonus + 0.20 * remaining)
    assert schedule.total_deductions == pytest.approx(depreciable)


def test_periods_are_labelled_from_the_placed_in_service_year() -> None:
    schedule = build_schedule(CAPEX, 0.0, start_year=2028)
    assert schedule.periods[0].year == 2028
    assert schedule.periods[1].year == 2029


def test_basis_rolls_forward_without_gaps() -> None:
    schedule = build_schedule(CAPEX, itc_amount=0.30 * CAPEX, bonus_rate=0.20)

    for prior, current in zip(schedule.periods, schedule.periods[1:]):
        assert current.opening_basis == pytest.approx(prior.closing_basis)


def test_bonus_rate_is_validated() -> None:
    with pytest.raises(ValueError, match="bonus_rate"):
        build_schedule(CAPEX, 0.0, bonus_rate=1.5)
