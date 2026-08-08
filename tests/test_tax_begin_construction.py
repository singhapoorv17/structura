"""Begin construction, and the *Oregon Environmental Council* litigation fork.

The headline test is :func:`test_litigation_toggle_flips_eligibility_for_a_wind_
project`: the same wind project is eligible under current law (Notice 2025-42
vacated, 5% cost safe harbor restored) and **loses the credit entirely** if the
notice is reinstated on appeal. That is a modelled legal risk no incumbent
exposes.
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.tax import (
    BeginConstructionMethod,
    EligibilityPath,
    ForeignEntityFlags,
    Notice202542Status,
    TaxProject,
    TaxScenario,
    Technology,
    assess_begin_construction,
    compute_tax,
    continuity_deadline,
    notice_2025_42_applies,
)

CAPEX = 200_000_000.0
CLEAN_SUPPLY_CHAIN = ForeignEntityFlags(received_material_assistance_from_pfe=False)

VACATED = TaxScenario(notice_2025_42_status=Notice202542Status.VACATED)
REINSTATED = TaxScenario(
    notice_2025_42_status=Notice202542Status.REINSTATED_ON_APPEAL
)


def wind(**kw: object) -> TaxProject:
    """A 200 MW wind project relying on the 5% cost safe harbor."""
    params: dict[str, object] = dict(
        technology=Technology.WIND,
        capacity_mw=200.0,
        capex=CAPEX,
        placed_in_service_date=date(2029, 6, 30),
        begin_construction_date=date(2026, 6, 1),
        begin_construction_method=BeginConstructionMethod.FIVE_PERCENT_SAFE_HARBOR,
        cost_incurred_pct_at_boc=0.055,
        is_pwa_compliant=True,
        foreign_entity_flags=CLEAN_SUPPLY_CHAIN,
    )
    params.update(kw)
    return TaxProject(**params)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ⚖️ The litigation fork
# ---------------------------------------------------------------------------


def test_current_law_default_is_vacated() -> None:
    """As of 2026-08-06 the notice is vacated - that is the default scenario."""
    assert TaxScenario().notice_2025_42_status is Notice202542Status.VACATED


def test_litigation_toggle_flips_eligibility_for_a_wind_project() -> None:
    project = wind()

    under_current_law = compute_tax(project, VACATED)
    under_appeal_outcome = compute_tax(project, REINSTATED)

    # Current law: the 5% safe harbor is restored, so BOC is established in time.
    assert under_current_law.begin_construction.established
    assert under_current_law.credit.eligible
    assert (
        under_current_law.credit.path is EligibilityPath.WIND_SOLAR_BEGIN_CONSTRUCTION
    )
    assert under_current_law.credit.credit_amount == pytest.approx(0.30 * CAPEX)

    # Appeal outcome: the safe harbor is gone, this project never began
    # construction, and PIS in 2029 is past the 2027-12-31 backstop.
    assert not under_appeal_outcome.begin_construction.method_available
    assert not under_appeal_outcome.begin_construction.established
    assert not under_appeal_outcome.credit.eligible
    assert under_appeal_outcome.credit.credit_amount == 0.0
    assert under_appeal_outcome.credit.path is EligibilityPath.NONE


def test_physical_work_test_survives_the_appeal_outcome() -> None:
    """Notice 2025-42 removed only the 5% safe harbor, not the other route."""
    project = wind(
        begin_construction_method=BeginConstructionMethod.PHYSICAL_WORK_TEST,
        physical_work_commenced=True,
        physical_work_description="Turbine foundations excavated on site.",
    )

    assert compute_tax(project, VACATED).credit.eligible
    assert compute_tax(project, REINSTATED).credit.eligible


def test_notice_2025_42_does_not_reach_small_wind_and_solar() -> None:
    """The notice applied only above 1.5 MW nameplate."""
    small = wind(capacity_mw=1.5)
    large = wind(capacity_mw=1.6)

    assert not notice_2025_42_applies(small, REINSTATED)[0]
    assert notice_2025_42_applies(large, REINSTATED)[0]


def test_notice_2025_42_does_not_reach_storage() -> None:
    project = wind(technology=Technology.STORAGE)
    applies, reason = notice_2025_42_applies(project, REINSTATED)

    assert not applies
    assert "only wind and solar" in reason


def test_vacatur_reason_names_the_case() -> None:
    _, reason = notice_2025_42_applies(wind(), VACATED)
    assert "Oregon Environmental Council" in reason
    assert "2026-06-06" in reason


# ---------------------------------------------------------------------------
# The two methods
# ---------------------------------------------------------------------------


def test_five_percent_safe_harbor_boundary() -> None:
    just_under = assess_begin_construction(wind(cost_incurred_pct_at_boc=0.0499), VACATED)
    exactly_at = assess_begin_construction(wind(cost_incurred_pct_at_boc=0.05), VACATED)

    assert not just_under.established
    assert exactly_at.established


def test_physical_work_test_requires_an_assertion() -> None:
    project = wind(
        begin_construction_method=BeginConstructionMethod.PHYSICAL_WORK_TEST,
        physical_work_commenced=False,
    )
    result = assess_begin_construction(project, VACATED)

    assert not result.established
    assert "No physical work" in result.steps[1].detail


def test_physical_work_description_is_carried_into_the_audit_trail() -> None:
    project = wind(
        begin_construction_method=BeginConstructionMethod.PHYSICAL_WORK_TEST,
        physical_work_commenced=True,
        physical_work_description="Custom transformer under binding contract.",
    )
    result = assess_begin_construction(project, VACATED)

    assert "Custom transformer" in result.steps[1].detail


def test_no_begin_construction_date_means_not_established() -> None:
    result = assess_begin_construction(wind(begin_construction_date=None), VACATED)

    assert not result.established
    assert result.continuity_deadline is None


# ---------------------------------------------------------------------------
# Four-year continuity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("boc", "expected"),
    [
        (date(2026, 1, 1), date(2030, 12, 31)),
        (date(2026, 12, 31), date(2030, 12, 31)),
        (date(2030, 6, 1), date(2034, 12, 31)),
    ],
)
def test_continuity_deadline_is_end_of_the_fourth_following_calendar_year(
    boc: date, expected: date
) -> None:
    assert continuity_deadline(boc) == expected


def test_continuity_miss_unwinds_an_otherwise_valid_begin_construction() -> None:
    result = assess_begin_construction(
        wind(placed_in_service_date=date(2031, 1, 1)), VACATED
    )

    assert not result.continuity_satisfied
    assert not result.established
    assert "continuity window closes" in result.reason
