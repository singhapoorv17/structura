"""Domestic content and energy community adders.

The headline behaviour is the **2026 boundary**: the domestic content threshold
escalated to 50% for 2026, and the test is a cliff. 49% gets nothing; 50% gets
the whole adder.
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.tax import (
    AdderType,
    Confidence,
    CreditType,
    ForeignEntityFlags,
    TaxProject,
    Technology,
    compute_tax,
    domestic_content_adder,
    domestic_content_threshold,
    energy_community_adder,
    evaluate_adders,
)

CAPEX = 100_000_000.0
CLEAN_SUPPLY_CHAIN = ForeignEntityFlags(received_material_assistance_from_pfe=False)


def project(pis: date, **kw: object) -> TaxProject:
    params: dict[str, object] = dict(
        technology=Technology.STORAGE,
        capacity_mw=100.0,
        capex=CAPEX,
        placed_in_service_date=pis,
        begin_construction_date=date(pis.year - 1, 1, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        foreign_entity_flags=CLEAN_SUPPLY_CHAIN,
    )
    params.update(kw)
    return TaxProject(**params)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Threshold schedule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2023, 0.40),
        (2024, 0.40),
        (2025, 0.45),
        (2026, 0.50),
        (2027, 0.55),
        (2032, 0.55),
    ],
)
def test_domestic_content_threshold_schedule(year: int, expected: float) -> None:
    assert domestic_content_threshold(year) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# The 2026 boundary - the test the brief calls out explicitly
# ---------------------------------------------------------------------------


def test_domestic_content_49_percent_in_2026_is_denied() -> None:
    result = domestic_content_adder(project(date(2026, 6, 1), domestic_content_pct=0.49))

    assert not result.granted
    assert result.itc_percentage_points == 0.0
    assert result.threshold == pytest.approx(0.50)
    assert "falls short" in result.reason


def test_domestic_content_50_percent_in_2026_is_granted() -> None:
    result = domestic_content_adder(project(date(2026, 6, 1), domestic_content_pct=0.50))

    assert result.granted
    assert result.itc_percentage_points == pytest.approx(0.10)
    assert result.threshold == pytest.approx(0.50)


def test_the_boundary_moves_the_whole_credit_by_ten_points() -> None:
    """End-to-end: 49% vs 50% in 2026 is a $10m swing on a $100m project."""
    denied = compute_tax(project(date(2026, 6, 1), domestic_content_pct=0.49)).credit
    granted = compute_tax(project(date(2026, 6, 1), domestic_content_pct=0.50)).credit

    assert denied.final_rate == pytest.approx(0.30)
    assert granted.final_rate == pytest.approx(0.40)
    assert granted.credit_amount - denied.credit_amount == pytest.approx(0.10 * CAPEX)


def test_the_same_50_percent_project_would_have_qualified_in_2025() -> None:
    """The escalation is what bites, not the project - worth showing a user."""
    in_2025 = domestic_content_adder(
        project(date(2025, 6, 1), domestic_content_pct=0.49)
    )
    in_2026 = domestic_content_adder(
        project(date(2026, 6, 1), domestic_content_pct=0.49)
    )

    assert in_2025.granted
    assert not in_2026.granted


# ---------------------------------------------------------------------------
# Adder amounts follow the PWA 5x multiplier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pwa", "expected_points"), [(True, 0.10), (False, 0.02)]
)
def test_adder_points_scale_with_pwa(pwa: bool, expected_points: float) -> None:
    result = domestic_content_adder(
        project(date(2026, 6, 1), domestic_content_pct=0.80, is_pwa_compliant=pwa)
    )
    assert result.itc_percentage_points == pytest.approx(expected_points)


def test_ptc_adder_is_a_ten_percent_uplift_not_percentage_points() -> None:
    result = domestic_content_adder(
        project(
            date(2026, 6, 1),
            domestic_content_pct=0.80,
            credit_type=CreditType.PTC,
        )
    )
    assert result.granted
    assert result.itc_percentage_points == 0.0
    assert result.ptc_multiplier == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Energy community - declared simplification
# ---------------------------------------------------------------------------


def test_energy_community_adder_is_granted_on_assertion_and_flagged_provisional() -> None:
    result = energy_community_adder(
        project(
            date(2026, 6, 1),
            energy_community=True,
            energy_community_category="coal_closure",
        )
    )

    assert result.granted
    assert result.itc_percentage_points == pytest.approx(0.10)
    assert result.confidence is Confidence.PROVISIONAL
    assert "does not run the census-tract" in result.reason


def test_energy_community_not_asserted_is_denied() -> None:
    result = energy_community_adder(project(date(2026, 6, 1)))
    assert not result.granted
    assert result.itc_percentage_points == 0.0


def test_unrecognised_energy_community_category_is_flagged_in_the_reason() -> None:
    result = energy_community_adder(
        project(
            date(2026, 6, 1),
            energy_community=True,
            energy_community_category="vibes",
        )
    )
    assert result.granted
    assert "not one of" in result.reason


# ---------------------------------------------------------------------------
# Stacking, and the Notice 2025-08 honest gap
# ---------------------------------------------------------------------------


def test_both_adders_stack_to_fifty_percent() -> None:
    credit = compute_tax(
        project(
            date(2026, 6, 1),
            domestic_content_pct=0.55,
            energy_community=True,
            energy_community_category="brownfield",
        )
    ).credit

    assert credit.final_rate == pytest.approx(0.50)
    assert {a.adder for a in credit.adders} == {
        AdderType.DOMESTIC_CONTENT,
        AdderType.ENERGY_COMMUNITY,
    }
    assert all(a.granted for a in credit.adders)


def test_notice_2025_08_safe_harbor_election_refuses_to_guess() -> None:
    """The elective safe-harbor cost percentages are not shipped.

    Structura raises rather than inventing an assigned cost percentage. That is
    the required behaviour: fabricated precision is a failure state.
    """
    with pytest.raises(NotImplementedError, match="Notice 2025-08"):
        evaluate_adders(
            project(date(2026, 6, 1), domestic_content_safe_harbor_elected=True)
        )
