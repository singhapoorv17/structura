"""The operating model: revenue, escalation, degradation, opex and tax."""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.cashflow import assert_cfads_identity, build_cashflow, flat_cashflow
from engine.models import ProductionCase, ProjectInputs, TaxTreatment
from tests.conftest import CENT


def test_flat_project_produces_flat_cfads(flat_project: ProjectInputs) -> None:
    """1,000,000 MWh at $50 = $50m revenue, less $10m opex = $40m EBITDA."""
    result = build_cashflow(flat_project)
    assert result.n_periods == 25
    assert all(r == pytest.approx(50_000_000.0, abs=CENT) for r in result.revenue)
    assert all(o == pytest.approx(10_000_000.0, abs=CENT) for o in result.opex)
    assert all(c == pytest.approx(40_000_000.0, abs=CENT) for c in result.cfads)
    assert result.tax_treatment is TaxTreatment.NONE
    assert_cfads_identity(result)


def test_escalation_and_degradation_compound_annually(
    flat_project: ProjectInputs
) -> None:
    """Year-n revenue = P x (1-d)^(n-1) x p x (1+e)^(n-1)."""
    project = replace(
        flat_project, degradation=0.005, contracted_escalation=0.02,
        opex_escalation=0.025,
    )
    result = build_cashflow(project)
    for year in (1, 5, 10, 25):
        expected_revenue = (
            1_000_000.0 * 0.995 ** (year - 1) * 50.0 * 1.02 ** (year - 1)
        )
        assert result.revenue[year - 1] == pytest.approx(expected_revenue, abs=CENT)
        assert result.opex[year - 1] == pytest.approx(
            10_000_000.0 * 1.025 ** (year - 1), abs=CENT
        )


def test_contract_expiry_switches_volume_to_merchant(
    flat_project: ProjectInputs
) -> None:
    project = replace(
        flat_project, contract_years=10.0, merchant_price=30.0,
        contracted_price=50.0, contracted_share=1.0,
    )
    result = build_cashflow(project)
    assert result.contracted_revenue[9] == pytest.approx(50_000_000.0, abs=CENT)
    assert result.merchant_revenue[9] == pytest.approx(0.0, abs=CENT)
    assert result.contracted_revenue[10] == pytest.approx(0.0, abs=CENT)
    assert result.merchant_revenue[10] == pytest.approx(30_000_000.0, abs=CENT)


def test_partial_contracted_share_splits_every_period(
    flat_project: ProjectInputs
) -> None:
    project = replace(
        flat_project, contracted_share=0.7, merchant_price=30.0,
        contract_years=25.0,
    )
    result = build_cashflow(project)
    assert result.contracted_revenue[0] == pytest.approx(35_000_000.0, abs=CENT)
    assert result.merchant_revenue[0] == pytest.approx(9_000_000.0, abs=CENT)
    assert result.merchant_share == pytest.approx(9.0 / 44.0, rel=1e-9)


def test_semiannual_periods_split_the_year_evenly(
    flat_project: ProjectInputs
) -> None:
    project = replace(flat_project, periods_per_year=2)
    result = build_cashflow(project)
    assert result.n_periods == 50
    assert result.revenue[0] == pytest.approx(25_000_000.0, abs=CENT)
    assert result.revenue[1] == pytest.approx(25_000_000.0, abs=CENT)
    # Both halves of operating year 1 carry the same price and degradation.
    annual = build_cashflow(flat_project)
    assert sum(result.revenue) == pytest.approx(sum(annual.revenue), abs=CENT)
    assert sum(result.cfads) == pytest.approx(sum(annual.cfads), abs=CENT)


def test_production_case_selection(flat_project: ProjectInputs) -> None:
    project = replace(
        flat_project, production_p90=900_000.0, production_p99=800_000.0,
        production_case=ProductionCase.P90,
    )
    assert build_cashflow(project).revenue[0] == pytest.approx(45_000_000.0, abs=CENT)
    project = replace(project, production_case=ProductionCase.P99)
    assert build_cashflow(project).revenue[0] == pytest.approx(40_000_000.0, abs=CENT)


def test_missing_exceedance_case_is_an_error(flat_project: ProjectInputs) -> None:
    project = replace(flat_project, production_case=ProductionCase.P90)
    with pytest.raises(ValueError, match="production_p90"):
        build_cashflow(project)


def test_pre_debt_tax_ignores_interest(flat_project: ProjectInputs) -> None:
    """Taxable income = EBITDA - depreciation. Capex 300m over 20 years = 15m.

    Taxable = 40m - 15m = 25m, tax at 21% = 5.25m, CFADS = 34.75m.
    """
    project = replace(
        flat_project, tax_treatment=TaxTreatment.PRE_DEBT, tax_rate=0.21,
        depreciation_years=20.0,
    )
    result = build_cashflow(project, interest=tuple(5_000_000.0 for _ in range(25)))
    assert result.cash_tax[0] == pytest.approx(5_250_000.0, abs=CENT)
    assert result.cfads[0] == pytest.approx(34_750_000.0, abs=CENT)


def test_full_tax_deducts_interest(flat_project: ProjectInputs) -> None:
    """Taxable = 40m - 15m - 5m interest = 20m, tax = 4.2m, CFADS = 35.8m."""
    project = replace(
        flat_project, tax_treatment=TaxTreatment.FULL, tax_rate=0.21,
        depreciation_years=20.0,
    )
    result = build_cashflow(project, interest=tuple(5_000_000.0 for _ in range(25)))
    assert result.cash_tax[0] == pytest.approx(4_200_000.0, abs=CENT)
    assert result.cfads[0] == pytest.approx(35_800_000.0, abs=CENT)


def test_depreciation_stops_after_the_depreciable_life(
    flat_project: ProjectInputs
) -> None:
    project = replace(
        flat_project, tax_treatment=TaxTreatment.PRE_DEBT, tax_rate=0.21,
        depreciation_years=5.0,
    )
    result = build_cashflow(project)
    assert result.depreciation[4] == pytest.approx(60_000_000.0, abs=CENT)
    assert result.depreciation[5] == pytest.approx(0.0, abs=CENT)
    assert sum(result.depreciation) == pytest.approx(flat_project.capex, abs=CENT)


def test_losses_carry_forward_and_shelter_later_income(
    flat_project: ProjectInputs
) -> None:
    """Heavy early depreciation should produce zero tax, then a sheltered year.

    Capex 300m over 5 years = 60m of depreciation against 40m of EBITDA: a 20m
    loss each year for five years, carried forward. Tax stays at zero until the
    accumulated 100m of losses is used up.
    """
    project = replace(
        flat_project, tax_treatment=TaxTreatment.PRE_DEBT, tax_rate=0.21,
        depreciation_years=5.0,
    )
    result = build_cashflow(project)
    assert all(t == 0.0 for t in result.cash_tax[:5])
    # Years 6-10 absorb the 100m carryforward at 40m a year: 2.5 years of it.
    assert result.cash_tax[5] == pytest.approx(0.0, abs=CENT)
    assert result.cash_tax[7] == pytest.approx(0.5 * 40_000_000.0 * 0.21, abs=CENT)
    assert result.cash_tax[8] == pytest.approx(40_000_000.0 * 0.21, abs=CENT)


def test_zero_tax_rate_is_a_no_op(flat_project: ProjectInputs) -> None:
    project = replace(
        flat_project, tax_treatment=TaxTreatment.FULL, tax_rate=0.0
    )
    result = build_cashflow(project)
    assert all(t == 0.0 for t in result.cash_tax)


def test_flat_cashflow_helper() -> None:
    result = flat_cashflow(1_000_000.0, 5)
    assert result.cfads == tuple(1_000_000.0 for _ in range(5))
    assert_cfads_identity(result)


def test_input_validation() -> None:
    with pytest.raises(ValueError, match="periods_per_year"):
        ProjectInputs(periods_per_year=3)
    with pytest.raises(ValueError, match="contracted_share"):
        ProjectInputs(contracted_share=1.5)
    with pytest.raises(ValueError, match="degradation"):
        ProjectInputs(degradation=-0.1)
    with pytest.raises(ValueError, match="capex_curve"):
        ProjectInputs(construction_months=12, capex_curve=(1.0, 1.0))
    with pytest.raises(ValueError, match="project_life_years"):
        ProjectInputs(project_life_years=0.0)


def test_capex_curve_is_normalised(flat_project: ProjectInputs) -> None:
    project = replace(
        flat_project, construction_months=3, capex_curve=(1.0, 2.0, 1.0)
    )
    weights = project.normalised_capex_curve()
    assert sum(weights) == pytest.approx(1.0)
    assert weights == pytest.approx((0.25, 0.5, 0.25))
    assert flat_project.normalised_capex_curve() == pytest.approx(
        tuple(1 / 12 for _ in range(12))
    )
