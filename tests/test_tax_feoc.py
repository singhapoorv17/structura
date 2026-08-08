"""FEOC / Material Assistance Cost Ratio, and §70512(h).

The behaviour that matters: a MACR failure **kills the credit**. It is not a
warning, a flag, or a haircut. These tests pin that, plus the pass/fail boundary
at the one threshold the verified rulebook actually carries (solar eligible
components, CY2026, 50%).
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.tax import (
    BeginConstructionMethod,
    ComponentCost,
    CreditSection,
    ForeignEntityFlags,
    ForeignEntityStatus,
    MacrInputs,
    MacrMethod,
    TaxProject,
    Technology,
    assess_feoc,
    compute_macr,
    compute_tax,
    macr_threshold,
    transfer_to_foreign_entity_prohibited,
)

CAPEX = 100_000_000.0


def solar(pis: date, macr: MacrInputs | None, **kw: object) -> TaxProject:
    """A solar project that is otherwise fully eligible, so FEOC is isolated."""
    params: dict[str, object] = dict(
        technology=Technology.SOLAR,
        capacity_mw=100.0,
        capex=CAPEX,
        placed_in_service_date=pis,
        begin_construction_date=date(2026, 3, 1),
        begin_construction_method=BeginConstructionMethod.FIVE_PERCENT_SAFE_HARBOR,
        cost_incurred_pct_at_boc=0.06,
        is_pwa_compliant=True,
        macr_inputs=macr,
    )
    params.update(kw)
    return TaxProject(**params)  # type: ignore[arg-type]


def asserted(ratio: float) -> MacrInputs:
    return MacrInputs(method=MacrMethod.USER_ASSERTED, asserted_ratio=ratio)


# ---------------------------------------------------------------------------
# Threshold lookup, and honesty about it
# ---------------------------------------------------------------------------


def test_solar_cy2026_threshold_is_the_one_verified_cell() -> None:
    threshold = macr_threshold(Technology.SOLAR, 2026)

    assert threshold.value == pytest.approx(0.50)
    assert not threshold.is_placeholder


@pytest.mark.parametrize(
    ("technology", "year"),
    [
        (Technology.SOLAR, 2027),
        (Technology.WIND, 2026),
        (Technology.STORAGE, 2026),
        (Technology.GEOTHERMAL, 2028),
    ],
)
def test_every_other_threshold_declares_itself_a_placeholder(
    technology: Technology, year: int
) -> None:
    threshold = macr_threshold(technology, year)

    assert threshold.is_placeholder
    assert "PLACEHOLDER" in threshold.note


# ---------------------------------------------------------------------------
# The pass/fail boundary
# ---------------------------------------------------------------------------


def test_macr_just_below_the_threshold_fails() -> None:
    result = assess_feoc(solar(date(2026, 12, 1), asserted(0.4999)))

    assert result.applies
    assert not result.passes
    assert result.threshold == pytest.approx(0.50)
    assert "DENIED" in result.reason


def test_macr_exactly_at_the_threshold_passes() -> None:
    result = assess_feoc(solar(date(2026, 12, 1), asserted(0.50)))

    assert result.passes
    assert result.macr == pytest.approx(0.50)


def test_macr_failure_kills_credit_eligibility_it_is_not_a_warning() -> None:
    """The single most important FEOC behaviour in the engine."""
    failing = compute_tax(solar(date(2026, 12, 1), asserted(0.45)))
    passing = compute_tax(solar(date(2026, 12, 1), asserted(0.55)))

    assert not failing.credit.eligible
    assert failing.credit.credit_amount == 0.0
    assert failing.credit.final_rate == 0.0
    assert "MACR" in failing.credit.disqualification_reason

    assert passing.credit.eligible
    assert passing.credit.credit_amount == pytest.approx(0.30 * CAPEX)


def test_feoc_does_not_apply_before_2026() -> None:
    result = assess_feoc(solar(date(2025, 12, 31), None))

    assert not result.applies
    assert result.passes


def test_material_assistance_representation_short_circuits_the_test() -> None:
    project = solar(
        date(2026, 12, 1),
        None,
        foreign_entity_flags=ForeignEntityFlags(
            received_material_assistance_from_pfe=False
        ),
    )
    result = assess_feoc(project)

    assert result.applies
    assert result.passes
    assert result.macr == pytest.approx(1.0)


def test_missing_macr_evidence_fails_closed() -> None:
    """No evidence for a project that admits PFE assistance = credit denied."""
    result = assess_feoc(solar(date(2026, 12, 1), None))

    assert result.applies
    assert not result.passes
    assert result.macr is None


# ---------------------------------------------------------------------------
# MACR computation methods (Notice 2026-15)
# ---------------------------------------------------------------------------


def test_supplier_certification_build_up() -> None:
    inputs = MacrInputs(
        method=MacrMethod.SUPPLIER_CERTIFICATION,
        components=(
            ComponentCost("modules", 60_000_000, 20_000_000, True),
            ComponentCost("trackers", 25_000_000, 0, True),
            ComponentCost("inverters", 15_000_000, 5_000_000, True),
        ),
    )
    ratio, basis = compute_macr(inputs)

    # 100m total, 25m PFE-attributable -> 75%.
    assert ratio == pytest.approx(0.75)
    assert "3 components" in basis


def test_uncertified_components_are_treated_as_fully_pfe_attributable() -> None:
    """Conservative by design - it is the diligence default a buyer insists on."""
    inputs = MacrInputs(
        method=MacrMethod.SUPPLIER_CERTIFICATION,
        components=(
            ComponentCost("modules", 60_000_000, 0.0, True),
            ComponentCost("inverters", 40_000_000, 0.0, False),
        ),
    )
    ratio, basis = compute_macr(inputs)

    assert ratio == pytest.approx(0.60)
    assert "without a supplier certification" in basis


def test_interim_safe_harbor_satisfies_the_test() -> None:
    ratio, basis = compute_macr(MacrInputs(method=MacrMethod.INTERIM_SAFE_HARBOR))

    assert ratio == pytest.approx(1.0)
    assert "Interim safe harbor" in basis


def test_doe_default_cost_tables_are_not_shipped_and_say_so() -> None:
    with pytest.raises(NotImplementedError, match="default cost tables"):
        compute_macr(MacrInputs(method=MacrMethod.DEFAULT_COST_TABLE))


def test_user_asserted_ratio_requires_a_ratio() -> None:
    with pytest.raises(ValueError, match="asserted_ratio"):
        MacrInputs(method=MacrMethod.USER_ASSERTED)


def test_component_cost_validates_its_own_arithmetic() -> None:
    with pytest.raises(ValueError, match="pfe_attributable_cost"):
        ComponentCost("modules", 100.0, 150.0)


# ---------------------------------------------------------------------------
# §70512(h) - the transfer prohibition (the rule itself; see test_tax_transfer)
# ---------------------------------------------------------------------------


def test_section_70512h_blocks_a_specified_foreign_entity() -> None:
    prohibited, reason = transfer_to_foreign_entity_prohibited(
        CreditSection.SEC_48E,
        ForeignEntityStatus.SPECIFIED_FOREIGN_ENTITY,
        date(2026, 1, 1),
    )

    assert prohibited
    assert "§7701(a)(51)(B)" in reason


def test_section_70512h_does_not_reach_a_pre_effective_taxable_year() -> None:
    prohibited, _ = transfer_to_foreign_entity_prohibited(
        CreditSection.SEC_48E,
        ForeignEntityStatus.SPECIFIED_FOREIGN_ENTITY,
        date(2025, 1, 1),
    )
    assert not prohibited


def test_section_70512h_does_not_reach_a_foreign_influenced_entity() -> None:
    """A different §7701(a)(51) limb, and the transfer ban does not name it."""
    prohibited, reason = transfer_to_foreign_entity_prohibited(
        CreditSection.SEC_48E,
        ForeignEntityStatus.FOREIGN_INFLUENCED_ENTITY,
        date(2026, 1, 1),
    )
    assert not prohibited
    assert "not a specified foreign entity" in reason


@pytest.mark.parametrize(
    "section",
    [
        CreditSection.SEC_45Q,
        CreditSection.SEC_45X,
        CreditSection.SEC_45Y,
        CreditSection.SEC_45Z,
        CreditSection.SEC_48E,
    ],
)
def test_all_five_named_credits_are_covered(section: CreditSection) -> None:
    prohibited, _ = transfer_to_foreign_entity_prohibited(
        section, ForeignEntityStatus.SPECIFIED_FOREIGN_ENTITY, date(2026, 1, 1)
    )
    assert prohibited
