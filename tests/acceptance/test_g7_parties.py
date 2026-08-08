"""G7 — economics by party, and the ledgers underneath them."""

from __future__ import annotations

import datetime as dt

import pytest

TODAY = dt.date(2026, 8, 8)
BN = 1e9


@pytest.fixture(scope="module")
def flip_result():
    from compare.build import engine_inputs
    from engine.structures import compare_structures
    from intake import ContractSpec, DealSpec, resolve

    resolution = resolve(
        DealSpec(
            asset_type="STORAGE",
            size={"mw": 150.0, "mwh": 600.0},
            state="CA",
            contract=ContractSpec("TOLLING", 15),
            cod="2028-01",
        ),
        today=TODAY,
    )
    project, debt, tax = engine_inputs(resolution)
    ranked = compare_structures(project, debt, tax).ranked
    return next(r.result for r in ranked if r.result.key.value == "partnership_flip")


@pytest.fixture(scope="module")
def lease_result():
    from engine.structures import (
        EquipmentLeaseConfig,
        LeaseTranche,
        run_equipment_lease,
    )

    tranches = (
        LeaseTranche("Class A1", 6.0 * BN, 0.0525, guaranteed=True),
        LeaseTranche("Class A2", 24.0 * BN, 0.0575, guaranteed=True),
        LeaseTranche("Class B", 4.5 * BN, 0.085, guaranteed=False, issue_price=0.985),
    )
    equity = 0.8 * BN
    return run_equipment_lease(
        EquipmentLeaseConfig(
            tranches=tranches,
            equity=equity,
            asset_cost=sum(t.proceeds for t in tranches) + equity,
            lease_term_years=6,
            expected_residual_pct=0.30,
            realised_residual_pct=0.15,
            tax_life_years=5,
        )
    )


@pytest.mark.gate("G7.1")
def test_the_partnership_conserves_cash_and_income_every_period(flip_result):
    from parties import conservation_report

    failures = conservation_report(flip_result)
    assert not failures, "\n".join(failures)


@pytest.mark.gate("G7.1")
def test_the_equipment_lease_reconciles_across_every_party(lease_result):
    for period, net in enumerate(lease_result.reconciliation()):
        assert abs(net) < 1e-3, f"period {period} nets {net:,.2f}"


@pytest.mark.gate("G7.2")
def test_every_party_reports_metrics_or_says_why_not(flip_result):
    from parties import party_view

    view = party_view(flip_result)
    assert view.ledgers, "no party ledgers"
    for ledger in view.ledgers:
        metrics = ledger.metrics(total_capital=view.total_capital)
        if metrics.irr is None:
            assert metrics.not_meaningful_reason.strip(), (
                f"{ledger.party} has no IRR and gives no reason"
            )
        assert metrics.moic is not None or metrics.not_meaningful_reason


@pytest.mark.gate("G7.2")
def test_an_irr_is_refused_on_a_series_that_cannot_support_one():
    """A rate solved on a non-conventional series is a confident wrong number.

    A tax equity investor whose credit arrives in the same period as its
    contribution shows a net inflow at time zero. Solving that returned -21%
    on a position with a 1.16x multiple.
    """
    from parties.ledgers import Ledger

    inflow_first = Ledger(
        party="Test",
        role="test",
        years=(2028, 2029, 2030),
        cashflow=(34.0, 1.0, -2.0),
    )
    metrics = inflow_first.metrics()
    assert metrics.irr is None
    assert "net inflow" in metrics.not_meaningful_reason

    alternating = Ledger(
        party="Test",
        role="test",
        years=(2028, 2029, 2030, 2031),
        cashflow=(-10.0, 30.0, -30.0, 20.0),
    )
    assert alternating.metrics().irr is None
    assert "changes sign" in alternating.metrics().not_meaningful_reason

    conventional = Ledger(
        party="Test",
        role="test",
        years=(2028, 2029, 2030),
        cashflow=(-100.0, 60.0, 60.0),
    )
    assert conventional.metrics().irr is not None


@pytest.mark.gate("G7.2")
def test_the_third_party_ledger_ties_to_the_engines_cost_of_capital(flip_result):
    """Two independent paths to the same number is the check that matters."""
    from parties import party_view

    view = party_view(flip_result)
    ledger = view.ledger("Third-party capital")
    rate = ledger.metrics(total_capital=view.total_capital).irr
    assert rate is not None
    assert rate == pytest.approx(flip_result.effective_cost_of_capital, abs=1e-9)


@pytest.mark.gate("G7.3")
def test_partnership_parties_expose_capital_account_and_outside_basis(flip_result):
    from parties import party_view

    view = party_view(flip_result)
    partners = [l for l in view.ledgers if "partner ledger" in l.party]
    assert partners, "no partner ledgers were produced"
    for ledger in partners:
        assert ledger.capital_account, f"{ledger.party} exposes no capital account"
        assert ledger.outside_basis is not None, f"{ledger.party} exposes no basis"
        assert len(ledger.capital_account) == len(ledger.years)
        assert len(ledger.outside_basis) == len(ledger.years)
        # Outside basis cannot go negative: §704(d) suspends the loss instead.
        assert min(ledger.outside_basis) >= -1e-6, (
            f"{ledger.party} has negative outside basis"
        )


@pytest.mark.gate("G7.4")
def test_every_ledger_names_the_engine_line_behind_it(flip_result):
    from parties import party_view

    view = party_view(flip_result)
    for ledger in view.ledgers:
        assert ledger.trace.strip(), f"{ledger.party} has no trace"

    # A tax equity position is mostly credit and deductions, so the components
    # have to be visible or the total cannot be checked.
    tax_equity = next(l for l in view.ledgers if l.party.startswith("Tax Equity"))
    assert set(tax_equity.components) == {
        "contributions",
        "distributions",
        "credit",
        "tax_effect",
    }
    for period in range(len(tax_equity.years)):
        rebuilt = (
            tax_equity.components["distributions"][period]
            - tax_equity.components["contributions"][period]
            + tax_equity.components["credit"][period]
            + tax_equity.components["tax_effect"][period]
        )
        assert rebuilt == pytest.approx(tax_equity.cashflow[period], abs=1e-6)

    # Capital contributed must be read from the contributions series, not from
    # the netted flow, or the credit hides it.
    assert tax_equity.invested == pytest.approx(
        sum(tax_equity.components["contributions"]), abs=1e-6
    )
    assert tax_equity.invested > 0
