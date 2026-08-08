"""Direct transfer, preferred equity and sale-leaseback.

The three structures that do not turn on a flip point. Between them they cover
43% of ITC gross value and more than 90% of PTC value in 2025 (Crux)
- so a model that treats them as afterthoughts to the flip has the market
upside down.
"""

from __future__ import annotations

from datetime import date

import pytest

from engine import DebtTerms, ProjectInputs
from engine.tax import (
    ForeignEntityFlags,
    ForeignEntityStatus,
    MacrInputs,
    MacrMethod,
    TaxProject,
    TaxScenario,
)
from engine.tax import Technology as TaxTechnology
from engine.structures import (
    PreferredConfig,
    SaleLeasebackConfig,
    SponsorTaxProfile,
    StructureKey,
    TransferConfig,
    build_context,
    run_preferred,
    run_sale_leaseback,
    run_transfer,
)
from engine.structures.defaults import (
    SALE_LEASEBACK_ITC_WINDOW_MONTHS,
    TRUE_LEASE_MAX_TERM_PCT_OF_USEFUL_LIFE,
)
from engine.structures.preferred import PREFERRED, preferred_cash_schedule
from engine.structures.sale_leaseback import solve_level_rent

TOL = 1e-6


def storage_project() -> ProjectInputs:
    return ProjectInputs(
        name="Monetisation test - storage",
        capex=200_000_000.0,
        opex_year1=5_000_000.0,
        production_p50=400_000.0,
        contracted_price=70.0,
        contract_years=25.0,
        project_life_years=25.0,
    )


def storage_tax_project(**overrides: object) -> TaxProject:
    base = dict(
        technology=TaxTechnology.STORAGE,
        capacity_mw=100.0,
        capex=200_000_000.0,
        placed_in_service_date=date(2027, 1, 1),
        begin_construction_date=date(2026, 3, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        macr_inputs=MacrInputs(
            method=MacrMethod.USER_ASSERTED, asserted_ratio=0.80
        ),
    )
    base.update(overrides)
    return TaxProject(**base)  # type: ignore[arg-type]


def make_context(
    *,
    bonus_rate: float = 0.0,
    sponsor: SponsorTaxProfile | None = None,
    tax_project: TaxProject | None = None,
):
    return build_context(
        storage_project(),
        DebtTerms(),
        tax_project or storage_tax_project(),
        tax_scenario=TaxScenario(bonus_rate=bonus_rate),
        sponsor=sponsor or SponsorTaxProfile(),
    )


# ---------------------------------------------------------------------------
# Direct transfer (§6418)
# ---------------------------------------------------------------------------


def test_transfer_proceeds_are_credit_times_price_less_transaction_costs() -> None:
    ctx = make_context()
    face = ctx.economics.itc_amount
    result = run_transfer(
        ctx, TransferConfig(price_per_dollar=0.92, transaction_cost_pct=0.02)
    )
    assert result.feasible
    assert result.detail["gross_proceeds"] == pytest.approx(face * 0.92, abs=1.0)
    assert result.detail["transaction_costs"] == pytest.approx(face * 0.02, abs=1.0)
    assert result.transfer_net_proceeds == pytest.approx(
        face * (0.92 - 0.02), abs=1.0
    )
    assert result.detail["effective_net_price"] == pytest.approx(0.90, abs=1e-9)
    assert result.credit_transferred == pytest.approx(face)
    assert result.credit_retained == 0.0


def test_transfer_proceeds_land_in_the_settlement_year() -> None:
    ctx = make_context()
    early = run_transfer(ctx, TransferConfig(settlement_year_index=0))
    late = run_transfer(ctx, TransferConfig(settlement_year_index=3))
    base = ctx.economics.distributable_cash

    assert early.sponsor_cash_only[1] == pytest.approx(
        base[0] + early.transfer_net_proceeds, abs=1.0
    )
    assert late.sponsor_cash_only[1] == pytest.approx(base[0], abs=1.0)
    assert late.sponsor_cash_only[4] == pytest.approx(
        base[3] + late.transfer_net_proceeds, abs=1.0
    )
    # Front-loading the cash is worth something: the earlier settlement wins.
    assert early.sponsor_after_tax_irr > late.sponsor_after_tax_irr
    assert (
        early.cash_timing.weighted_average_years
        < late.cash_timing.weighted_average_years
    )


def test_transfer_to_a_specified_foreign_entity_is_blocked() -> None:
    """§70512(h), propagated straight out of ``engine.tax``."""
    ctx = make_context(
        tax_project=storage_tax_project(
            foreign_entity_flags=ForeignEntityFlags(
                transferee_status=ForeignEntityStatus.SPECIFIED_FOREIGN_ENTITY,
                received_material_assistance_from_pfe=False,
            ),
            taxable_year_begin=date(2027, 1, 1),
        )
    )
    result = run_transfer(ctx)
    assert result.feasible is False
    assert result.transfer_net_proceeds == 0.0
    assert "specified foreign entity" in result.infeasible_reason.lower()
    assert "transfer_blocked" in {f.code for f in result.risks}


def test_transfer_is_blocked_when_the_macr_gate_fails() -> None:
    ctx = make_context(
        tax_project=storage_tax_project(
            macr_inputs=MacrInputs(
                method=MacrMethod.USER_ASSERTED, asserted_ratio=0.05
            )
        )
    )
    assert ctx.tax.feoc.passes is False
    assert ctx.credit_is_zero
    result = run_transfer(ctx)
    assert result.feasible is False
    assert result.transfer_net_proceeds == 0.0


def test_a_sponsor_that_cannot_use_depreciation_is_told_so() -> None:
    ctx = make_context(sponsor=SponsorTaxProfile(can_use_depreciation=False))
    result = run_transfer(ctx)
    assert "depreciation_stranded" in {f.code for f in result.risks}
    usable = make_context(sponsor=SponsorTaxProfile(can_use_depreciation=True))
    better = run_transfer(usable)
    assert better.sponsor_after_tax_irr > result.sponsor_after_tax_irr


# ---------------------------------------------------------------------------
# Preferred equity
# ---------------------------------------------------------------------------


def test_preferred_cash_schedule_pays_return_before_redemption() -> None:
    """Hand-checked: 100 of preferred at 10%, cash of 5 then 200.

    Year 1: 10 accrues, only 5 of cash, so 5 of return is paid and 5 accrues
    unpaid; nothing is redeemed and the balance is still 100.
    Year 2: the unpaid 5 compounds, so (100 + 5) x 10% = 10.5 accrues on top of
    the 5 carried, giving 15.5 of return. 200 of cash pays that in full and
    redeems the whole 100.
    """
    config = PreferredConfig(
        commitment=100.0,
        preferred_return=0.10,
        cash_priority_share=1.0,
        compound_unpaid_return=True,
    )
    cash, returns, redemptions, balances = preferred_cash_schedule(
        config, 100.0, (5.0, 200.0)
    )
    assert returns[0] == pytest.approx(5.0, abs=TOL)
    assert redemptions[0] == pytest.approx(0.0, abs=TOL)
    assert balances[0] == pytest.approx(100.0, abs=TOL)
    assert returns[1] == pytest.approx(15.5, abs=TOL)
    assert redemptions[1] == pytest.approx(100.0, abs=TOL)
    assert balances[1] == pytest.approx(0.0, abs=TOL)
    assert cash[1] == pytest.approx(115.5, abs=TOL)


def test_preferred_is_redeemed_and_the_sharing_ratio_drops_afterwards() -> None:
    ctx = make_context()
    result = run_preferred(
        ctx, PreferredConfig(commitment=30_000_000.0, preferred_return=0.09)
    )
    assert result.feasible
    assert result.key is StructureKey.PREFERRED_EQUITY
    assert result.detail["preferred_unreturned_final"] == pytest.approx(0.0, abs=1.0)
    redemption_year = int(result.detail["preferred_redemption_year"])
    assert 0 < redemption_year <= ctx.economics.n_years

    partnership = result.partnership
    assert partnership is not None
    # Once the preferred is redeemed the sharing ratio drops to the residual
    # 5%. The *base* allocation is the one to look at: the allocation actually
    # made may be smaller still if the DRO cap bites.
    before = partnership.periods[redemption_year - 1].partner(PREFERRED)
    after = partnership.periods[redemption_year].partner(PREFERRED)
    assert before.book_allocation_base == pytest.approx(
        0.99 * partnership.periods[redemption_year - 1].book_income, abs=1e-3
    )
    assert after.book_allocation_base == pytest.approx(
        0.05 * partnership.periods[redemption_year].book_income, abs=1e-3
    )


def test_preferred_never_redeemed_is_flagged_as_blocking() -> None:
    ctx = make_context()
    result = run_preferred(
        ctx,
        PreferredConfig(
            commitment=400_000_000.0,
            preferred_return=0.15,
            target_term_years=5.0,
        ),
    )
    codes = {f.code for f in result.risks}
    assert "preferred_unredeemed_at_maturity" in codes
    assert result.detail["preferred_unreturned_final"] > 0.0


def test_preferred_capital_accounts_reconcile() -> None:
    ctx = make_context()
    result = run_preferred(ctx, PreferredConfig(commitment=30_000_000.0))
    partnership = result.partnership
    assert partnership is not None
    for period in partnership.periods:
        total = sum(p.book_allocation for p in period.partners)
        assert total == pytest.approx(period.book_income, abs=1e-6)
        for row in period.partners:
            assert row.capital_closing == pytest.approx(
                row.capital_opening
                + row.contributions
                + row.book_allocation
                - row.distributions
                - row.itc_basis_reduction_share,
                abs=1e-6,
            )


def test_a_higher_preferred_return_costs_the_sponsor() -> None:
    ctx = make_context()
    cheap = run_preferred(
        ctx, PreferredConfig(commitment=30_000_000.0, preferred_return=0.07)
    )
    dear = run_preferred(
        ctx, PreferredConfig(commitment=30_000_000.0, preferred_return=0.13)
    )
    assert dear.sponsor_after_tax_irr < cheap.sponsor_after_tax_irr
    assert dear.effective_cost_of_capital > cheap.effective_cost_of_capital


# ---------------------------------------------------------------------------
# Sale-leaseback
# ---------------------------------------------------------------------------


def test_solved_rent_gives_the_lessor_exactly_its_target_yield() -> None:
    from engine.metrics import irr

    rent, solved = solve_level_rent(
        sale_price=100.0,
        term_years=10,
        itc=0.0,
        depreciation=tuple(10.0 for _ in range(10)),
        residual=20.0,
        tax_rate=0.21,
        target_irr=0.07,
    )
    assert solved
    flows = [-100.0]
    for t in range(10):
        flows.append(rent * 0.79 + 0.21 * 10.0)
    flows[-1] += 20.0
    assert irr(tuple(flows)) == pytest.approx(0.07, abs=1e-6)


def test_lease_payments_and_residual_reconcile() -> None:
    ctx = make_context()
    config = SaleLeasebackConfig(lease_term_years=15.0, residual_value_pct=0.20)
    result = run_sale_leaseback(ctx, config)
    assert result.feasible

    rent = result.detail["level_rent"]
    term = int(result.detail["lease_term_years"])
    assert result.detail["total_rent_paid"] == pytest.approx(rent * term, abs=1e-6)
    assert result.detail["residual_value"] == pytest.approx(
        0.20 * result.detail["sale_price"], abs=1e-6
    )

    # The sponsor's cash line is EBITDA less rent, and the residual is paid in
    # the final year of the term when the purchase option is exercised.
    econ = ctx.economics
    for i in range(term):
        expected = econ.ebitda[i] - rent
        if i == term - 1:
            expected -= result.detail["residual_value"]
        assert result.sponsor_cash_only[i + 1] == pytest.approx(expected, abs=1e-6)
    for i in range(term, econ.n_years):
        assert result.sponsor_cash_only[i + 1] == pytest.approx(
            econ.ebitda[i], abs=1e-6
        )


def test_the_sponsor_no_longer_owns_the_tax_attributes() -> None:
    """The defining feature: the lessor is the tax owner."""
    ctx = make_context()
    result = run_sale_leaseback(ctx)
    assert result.credit_retained == 0.0
    assert result.credit_transferred == pytest.approx(ctx.economics.itc_amount)
    assert result.partnership is None
    assert "tax_attributes_transferred" in {f.code for f in result.risks}

    # The sponsor's only tax item is its rent deduction: its taxable income is
    # EBITDA less rent, with no depreciation anywhere in it.
    rent = result.detail["level_rent"]
    term = int(result.detail["lease_term_years"])
    econ = ctx.economics
    tax_effect = result.sponsor_cashflow[1] - result.sponsor_cash_only[1]
    assert tax_effect == pytest.approx(
        -ctx.sponsor.tax_rate * (econ.ebitda[0] - rent), abs=1e-6
    )
    assert term > 0


def test_a_sale_outside_the_three_month_window_loses_the_credit() -> None:
    """§50(d)(4): three months, or the investment credit is gone for everyone."""
    ctx = make_context()
    inside = run_sale_leaseback(
        ctx,
        SaleLeasebackConfig(
            months_after_placed_in_service=SALE_LEASEBACK_ITC_WINDOW_MONTHS
        ),
    )
    outside = run_sale_leaseback(
        ctx,
        SaleLeasebackConfig(
            months_after_placed_in_service=SALE_LEASEBACK_ITC_WINDOW_MONTHS + 1
        ),
    )
    assert inside.detail["itc_to_lessor"] == pytest.approx(ctx.economics.itc_amount)
    assert outside.detail["itc_to_lessor"] == 0.0
    assert "sale_leaseback_outside_itc_window" in {f.code for f in outside.risks}
    # Without the credit the lessor must earn its yield from rent alone.
    assert outside.detail["level_rent"] > inside.detail["level_rent"]


def test_a_lease_running_past_eighty_percent_of_useful_life_fails_the_guideline() -> None:
    ctx = make_context()
    result = run_sale_leaseback(
        ctx,
        SaleLeasebackConfig(
            lease_term_years=24.0, asset_useful_life_years=25.0
        ),
    )
    assert result.detail["true_lease_term_pct_of_useful_life"] > (
        TRUE_LEASE_MAX_TERM_PCT_OF_USEFUL_LIFE
    )
    assert "true_lease_guideline_failure" in {f.code for f in result.risks}


def test_a_residual_below_twenty_percent_fails_the_guideline() -> None:
    ctx = make_context()
    result = run_sale_leaseback(
        ctx,
        SaleLeasebackConfig(lease_term_years=15.0, residual_value_pct=0.10),
    )
    assert "true_lease_guideline_failure" in {f.code for f in result.risks}


def test_placeholder_lease_assumptions_are_disclosed() -> None:
    ctx = make_context()
    result = run_sale_leaseback(ctx)
    assert any("PLACEHOLDER" in w for w in result.warnings)


def test_sponsor_flows_ignore_the_project_debt_after_closing() -> None:
    """Declared simplification: the facility is repaid out of the sale proceeds."""
    ctx = make_context()
    result = run_sale_leaseback(ctx, SaleLeasebackConfig(sale_price=250_000_000.0))
    econ = ctx.economics
    assert result.sponsor_cashflow[0] == pytest.approx(
        250_000_000.0 - econ.equity_at_cod - econ.debt_at_cod, abs=1e-6
    )
