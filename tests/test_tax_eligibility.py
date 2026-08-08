"""§48E/§45Y eligibility - the headline behaviour of the whole product.

Three cases carry the OBBBA wind/solar bifurcation and are tested explicitly
because getting them wrong is the difference between a 30% credit and nothing:

===========================  ==========  =====================================
Begin construction           PIS         Expected
===========================  ==========  =====================================
2026-07-01 (on time)         2029-06-30  eligible via the BOC path
2026-07-05 (missed by a day) 2027-06-01  eligible via the 2027-12-31 backstop
2026-07-05 (missed by a day) 2028-01-01  **ZERO credit**
===========================  ==========  =====================================
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.tax import (
    BeginConstructionMethod,
    CreditType,
    EligibilityPath,
    ForeignEntityFlags,
    TaxProject,
    TaxScenario,
    Technology,
    compute_tax,
    evaluate_eligibility,
    phase_down_percentage,
    ptc_rate_per_kwh,
)

CAPEX = 100_000_000.0

#: No FEOC exposure, so these tests isolate the eligibility rules.
CLEAN_SUPPLY_CHAIN = ForeignEntityFlags(received_material_assistance_from_pfe=False)


def solar(boc: date, pis: date, **kw: object) -> TaxProject:
    """A 100 MW solar project that has validly begun construction on ``boc``."""
    params: dict[str, object] = dict(
        technology=Technology.SOLAR,
        capacity_mw=100.0,
        capex=CAPEX,
        placed_in_service_date=pis,
        begin_construction_date=boc,
        begin_construction_method=BeginConstructionMethod.FIVE_PERCENT_SAFE_HARBOR,
        cost_incurred_pct_at_boc=0.06,
        is_pwa_compliant=True,
        foreign_entity_flags=CLEAN_SUPPLY_CHAIN,
    )
    params.update(kw)
    return TaxProject(**params)  # type: ignore[arg-type]


def storage(boc: date, pis: date, **kw: object) -> TaxProject:
    params: dict[str, object] = dict(
        technology=Technology.STORAGE,
        capacity_mw=100.0,
        capex=CAPEX,
        placed_in_service_date=pis,
        begin_construction_date=boc,
        begin_construction_method=BeginConstructionMethod.PHYSICAL_WORK_TEST,
        physical_work_commenced=True,
        is_pwa_compliant=True,
        foreign_entity_flags=CLEAN_SUPPLY_CHAIN,
    )
    params.update(kw)
    return TaxProject(**params)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The three headline wind/solar cases (SPEC §2.1)
# ---------------------------------------------------------------------------


def test_solar_began_construction_before_the_cliff_is_eligible() -> None:
    """BOC 2026-07-01 - three days inside the deadline - keeps the full credit."""
    result = compute_tax(solar(date(2026, 7, 1), date(2029, 6, 30)))

    assert result.credit.eligible
    assert result.credit.path is EligibilityPath.WIND_SOLAR_BEGIN_CONSTRUCTION
    assert result.credit.final_rate == pytest.approx(0.30)
    assert result.credit.credit_amount == pytest.approx(0.30 * CAPEX)
    # The four-year continuity window runs to the end of 2030.
    assert result.begin_construction.continuity_deadline == date(2030, 12, 31)
    assert result.begin_construction.continuity_satisfied


def test_solar_missed_cliff_but_placed_in_service_by_2027_uses_the_backstop() -> None:
    """BOC 2026-07-05 - one day late - survives only via the PIS backstop."""
    result = compute_tax(solar(date(2026, 7, 5), date(2027, 6, 1)))

    assert result.credit.eligible
    assert result.credit.path is EligibilityPath.WIND_SOLAR_PIS_BACKSTOP
    assert result.credit.final_rate == pytest.approx(0.30)
    assert "backstop" in result.credit.explanation.lower()


def test_solar_missed_cliff_and_backstop_gets_zero() -> None:
    """BOC 2026-07-05 with PIS 2028-01-01 - one day past both tests - is ZERO.

    Not reduced. Zero. This is the case OBBBA created and no incumbent models.
    """
    result = compute_tax(solar(date(2026, 7, 5), date(2028, 1, 1)))

    assert not result.credit.eligible
    assert result.credit.path is EligibilityPath.NONE
    assert result.credit.final_rate == 0.0
    assert result.credit.credit_amount == 0.0
    assert "NO §48E/§45Y credit" in result.credit.disqualification_reason


def test_wind_follows_the_same_cliff_as_solar() -> None:
    on_time = solar(date(2026, 7, 4), date(2029, 6, 30), technology=Technology.WIND)
    late = solar(date(2026, 7, 5), date(2028, 6, 30), technology=Technology.WIND)

    assert compute_tax(on_time).credit.eligible
    assert not compute_tax(late).credit.eligible


def test_boc_deadline_is_inclusive_of_2026_07_04() -> None:
    """"on or before 2026-07-04" - the boundary date itself qualifies."""
    result = compute_tax(solar(date(2026, 7, 4), date(2029, 6, 30)))
    assert result.credit.path is EligibilityPath.WIND_SOLAR_BEGIN_CONSTRUCTION


def test_pis_backstop_is_inclusive_of_2027_12_31() -> None:
    on_time = compute_tax(solar(date(2026, 8, 1), date(2027, 12, 31)))
    one_day_late = compute_tax(solar(date(2026, 8, 1), date(2028, 1, 1)))

    assert on_time.credit.path is EligibilityPath.WIND_SOLAR_PIS_BACKSTOP
    assert one_day_late.credit.path is EligibilityPath.NONE


def test_continuity_failure_pushes_a_timely_project_onto_the_backstop() -> None:
    """A 2026 BOC with a 2031 PIS blows the four-year continuity window.

    Because the backstop date has also passed, the credit is zero - which is the
    trap for developers who safe-harboured equipment and then let the build slip.
    """
    result = compute_tax(solar(date(2026, 3, 1), date(2031, 6, 30)))

    assert not result.begin_construction.continuity_satisfied
    assert not result.credit.eligible
    assert result.credit.path is EligibilityPath.NONE


# ---------------------------------------------------------------------------
# Storage / geothermal / nuclear / hydro runway and phase-down (SPEC §2.1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("boc_year", "expected_pct"),
    [(2033, 1.00), (2034, 0.75), (2035, 0.50), (2036, 0.00), (2040, 0.00)],
)
def test_storage_phase_down_by_begin_construction_year(
    boc_year: int, expected_pct: float
) -> None:
    assert phase_down_percentage(boc_year) == pytest.approx(expected_pct)

    project = storage(date(boc_year, 6, 1), date(boc_year + 2, 6, 1))
    credit = compute_tax(project).credit

    assert credit.phase_down_pct == pytest.approx(expected_pct)
    assert credit.final_rate == pytest.approx(0.30 * expected_pct)
    assert credit.eligible is (expected_pct > 0.0)


def test_storage_is_not_subject_to_the_wind_solar_cliff() -> None:
    """A storage project beginning construction in 2030 is entirely fine."""
    credit = compute_tax(storage(date(2030, 1, 1), date(2032, 1, 1))).credit

    assert credit.eligible
    assert credit.path is EligibilityPath.NON_WIND_SOLAR_RUNWAY
    assert credit.phase_down_pct == pytest.approx(1.0)


@pytest.mark.parametrize(
    "technology",
    [Technology.STORAGE, Technology.GEOTHERMAL, Technology.NUCLEAR, Technology.HYDRO],
)
def test_all_non_wind_solar_technologies_share_the_runway(
    technology: Technology,
) -> None:
    project = storage(date(2032, 1, 1), date(2034, 1, 1), technology=technology)
    credit = compute_tax(project).credit

    assert credit.path is EligibilityPath.NON_WIND_SOLAR_RUNWAY
    assert credit.final_rate == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# Base rate and the 5x PWA multiplier
# ---------------------------------------------------------------------------


def test_pwa_compliance_is_the_difference_between_30_percent_and_6_percent() -> None:
    compliant = solar(date(2026, 6, 1), date(2029, 6, 30), is_pwa_compliant=True)
    not_compliant = solar(date(2026, 6, 1), date(2029, 6, 30), is_pwa_compliant=False)

    assert compute_tax(compliant).credit.final_rate == pytest.approx(0.30)
    assert compute_tax(not_compliant).credit.final_rate == pytest.approx(0.06)


def test_pwa_multiplier_also_scales_the_adders() -> None:
    """2 percentage points at the base rate, 10 with PWA - the same 5x."""
    with_pwa = solar(
        date(2026, 6, 1),
        date(2026, 12, 1),
        is_pwa_compliant=True,
        domestic_content_pct=0.60,
        energy_community=True,
        energy_community_category="coal_closure",
    )
    without_pwa = with_pwa.with_(is_pwa_compliant=False)

    assert compute_tax(with_pwa).credit.final_rate == pytest.approx(0.30 + 0.10 + 0.10)
    assert compute_tax(without_pwa).credit.final_rate == pytest.approx(
        0.06 + 0.02 + 0.02
    )


# ---------------------------------------------------------------------------
# §45Y production credit
# ---------------------------------------------------------------------------


def test_ptc_rate_refuses_to_guess_an_unsourced_inflation_factor() -> None:
    """Honest gaps beat fabricated precision (SPEC §4, build brief).

    The 0.3 c/kWh base amount and the 5x multiplier are implemented; the annual
    §45Y(c) inflation adjustment factor is not shipped for any year after the
    2022 base year, so quoting a rate raises rather than inventing one.
    """
    assert ptc_rate_per_kwh(2022, is_pwa_compliant=False) == pytest.approx(0.003)
    assert ptc_rate_per_kwh(2022, is_pwa_compliant=True) == pytest.approx(0.015)

    with pytest.raises(NotImplementedError, match="inflation adjustment factor"):
        ptc_rate_per_kwh(2027, is_pwa_compliant=True)


def test_ptc_credit_is_annual_production_times_rate_over_ten_years() -> None:
    project = TaxProject(
        technology=Technology.STORAGE,
        capacity_mw=100.0,
        capex=CAPEX,
        placed_in_service_date=date(2022, 6, 1),
        begin_construction_date=date(2021, 1, 1),
        credit_type=CreditType.PTC,
        annual_production_mwh=300_000.0,
        is_pwa_compliant=True,
        foreign_entity_flags=CLEAN_SUPPLY_CHAIN,
    )
    credit = evaluate_eligibility(project, TaxScenario())

    assert credit.base_rate == pytest.approx(0.015)
    assert credit.annual_credit_amount == pytest.approx(0.015 * 300_000 * 1_000)
    assert credit.credit_amount == pytest.approx(credit.annual_credit_amount * 10)


def test_ptc_adders_are_multiplicative_not_additive() -> None:
    project = TaxProject(
        technology=Technology.STORAGE,
        capacity_mw=100.0,
        capex=CAPEX,
        placed_in_service_date=date(2022, 6, 1),
        begin_construction_date=date(2021, 1, 1),
        credit_type=CreditType.PTC,
        annual_production_mwh=300_000.0,
        is_pwa_compliant=True,
        domestic_content_pct=0.90,
        energy_community=True,
        energy_community_category="brownfield",
        foreign_entity_flags=CLEAN_SUPPLY_CHAIN,
    )
    credit = evaluate_eligibility(project, TaxScenario())

    assert credit.final_rate == pytest.approx(0.015 * 1.20)


# ---------------------------------------------------------------------------
# The result must explain itself (SPEC §4.2, §6.6)
# ---------------------------------------------------------------------------


def test_every_result_carries_an_auditable_explanation_and_citations() -> None:
    result = compute_tax(solar(date(2026, 7, 1), date(2029, 6, 30)))

    assert result.credit.steps, "a credit with no reasoning is not auditable"
    assert "wind-solar-boc-cliff" in result.credit.citation_ids
    assert "base-and-pwa-rate" in result.credit.citation_ids
    assert len(result.credit.explanation.splitlines()) == len(result.credit.steps)


def test_zero_credit_results_still_explain_themselves() -> None:
    result = compute_tax(solar(date(2026, 7, 5), date(2028, 1, 1)))

    assert result.credit.steps
    assert result.credit.disqualification_reason
    assert "wind-solar-pis-backstop" in result.credit.citation_ids
