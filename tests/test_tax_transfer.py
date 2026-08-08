"""§6418 transfer economics and the §70512(h) foreign-entity prohibition."""

from __future__ import annotations

from datetime import date

import pytest

from engine.tax import (
    CreditSection,
    CreditType,
    ForeignEntityFlags,
    ForeignEntityStatus,
    TaxProject,
    Technology,
    compute_tax,
    default_transfer_price,
    evaluate_eligibility,
    is_direct_pay_eligible,
    model_transfer,
)

CAPEX = 100_000_000.0


def storage(**kw: object) -> TaxProject:
    params: dict[str, object] = dict(
        technology=Technology.STORAGE,
        capacity_mw=100.0,
        capex=CAPEX,
        placed_in_service_date=date(2028, 6, 30),
        begin_construction_date=date(2026, 3, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        foreign_entity_flags=ForeignEntityFlags(
            received_material_assistance_from_pfe=False
        ),
    )
    params.update(kw)
    return TaxProject(**params)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The hard gate
# ---------------------------------------------------------------------------


def test_transfer_to_a_specified_foreign_entity_is_blocked() -> None:
    project = storage(
        foreign_entity_flags=ForeignEntityFlags(
            received_material_assistance_from_pfe=False,
            transferee_status=ForeignEntityStatus.SPECIFIED_FOREIGN_ENTITY,
        ),
        taxable_year_begin=date(2026, 1, 1),
    )
    result = compute_tax(project)

    assert result.credit.eligible, "the credit itself is fine - only the sale is barred"
    assert result.transfer is not None
    assert not result.transfer.permitted
    assert result.transfer.net_proceeds == 0.0
    assert "§70512(h) PROHIBITS" in result.transfer.blocked_reason


def test_the_same_transfer_is_permitted_to_a_domestic_buyer() -> None:
    result = compute_tax(storage(taxable_year_begin=date(2026, 1, 1)))

    assert result.transfer is not None
    assert result.transfer.permitted
    assert result.transfer.net_proceeds > 0


def test_the_prohibition_first_bites_for_calendar_year_2026() -> None:
    """Effective for taxable years beginning after 2025-07-04."""
    flags = ForeignEntityFlags(
        received_material_assistance_from_pfe=False,
        transferee_status=ForeignEntityStatus.SPECIFIED_FOREIGN_ENTITY,
    )
    pre = compute_tax(
        storage(foreign_entity_flags=flags, taxable_year_begin=date(2025, 1, 1))
    )
    post = compute_tax(
        storage(foreign_entity_flags=flags, taxable_year_begin=date(2026, 1, 1))
    )

    assert pre.transfer is not None and pre.transfer.permitted
    assert post.transfer is not None and not post.transfer.permitted


# ---------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------


def test_transfer_economics_arithmetic() -> None:
    project = storage()
    credit = evaluate_eligibility(project)
    result = model_transfer(
        project, credit, price_per_dollar=0.92, transaction_cost_pct=0.02
    )

    face = 0.30 * CAPEX
    assert result.credit_face_value == pytest.approx(face)
    assert result.gross_proceeds == pytest.approx(0.92 * face)
    assert result.transaction_costs == pytest.approx(0.02 * face)
    assert result.net_proceeds == pytest.approx(0.90 * face)
    assert result.effective_net_price == pytest.approx(0.90)
    assert result.discount_to_face == pytest.approx(0.10)


def test_default_itc_price_is_the_documented_ninety_cent_benchmark() -> None:
    assert default_transfer_price(CreditType.ITC) == pytest.approx(0.90)


def test_market_context_carries_the_crux_2025_shares() -> None:
    project = storage()
    result = model_transfer(project, evaluate_eligibility(project))

    assert result.market_context["transfer_market_usd_bn_2025"] == pytest.approx(42.0)
    assert result.market_context["ptc_share_direct_transfer"] == pytest.approx(0.90)
    assert result.market_context["itc_share_partnership"] == pytest.approx(0.57)


def test_a_zero_credit_has_nothing_to_transfer() -> None:
    """Wind that missed both the cliff and the backstop."""
    project = TaxProject(
        technology=Technology.WIND,
        capacity_mw=200.0,
        capex=CAPEX,
        placed_in_service_date=date(2029, 6, 30),
        begin_construction_date=date(2026, 8, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        foreign_entity_flags=ForeignEntityFlags(
            received_material_assistance_from_pfe=False
        ),
    )
    result = compute_tax(project)

    assert not result.credit.eligible
    assert result.transfer is not None
    assert not result.transfer.permitted
    assert result.transfer.gross_proceeds == 0.0


def test_price_is_validated() -> None:
    project = storage()
    with pytest.raises(ValueError, match="price_per_dollar"):
        model_transfer(project, evaluate_eligibility(project), price_per_dollar=1.4)


def test_transfer_can_be_skipped_for_a_partnership_run() -> None:
    assert compute_tax(storage(), include_transfer=False).transfer is None


# ---------------------------------------------------------------------------
# §6417 direct pay
# ---------------------------------------------------------------------------


def test_applicable_entities_can_elect_direct_pay() -> None:
    eligible, reason = is_direct_pay_eligible(
        "rural_electric_cooperative", CreditSection.SEC_48E
    )
    assert eligible
    assert "§6417(d)(1)(A)" in reason


def test_a_taxable_entity_cannot_direct_pay_a_48e_credit() -> None:
    eligible, reason = is_direct_pay_eligible("corporation", CreditSection.SEC_48E)
    assert not eligible
    assert "§6418 transfer" in reason


def test_a_taxable_entity_can_direct_pay_45x() -> None:
    eligible, _ = is_direct_pay_eligible("corporation", CreditSection.SEC_45X)
    assert eligible
