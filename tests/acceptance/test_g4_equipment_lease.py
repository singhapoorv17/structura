"""G4 — the equipment lease with a third-party residual value guarantee.

The tranche terms used here are the figures reported in the press. They are
**scenario inputs**, not corpus facts: the primary source names the A1 and A2
tranches and discloses no sizes, coupons or guarantee terms. G4.5 asserts that
separation holds in the corpus.
"""

from __future__ import annotations

import pytest

BN = 1e9


@pytest.fixture(scope="module")
def reported_terms():
    """The tranche structure as reported. Supplied by the user, not the corpus."""
    from engine.structures import LeaseTranche

    return (
        LeaseTranche("Class A1", 6.0 * BN, 0.0525, guaranteed=True),
        LeaseTranche("Class A2", 24.0 * BN, 0.0575, guaranteed=True),
        LeaseTranche("Class B", 4.5 * BN, 0.085, guaranteed=False, issue_price=0.985),
    )


@pytest.fixture(scope="module")
def config(reported_terms):
    from engine.structures import EquipmentLeaseConfig

    equity = 0.8 * BN
    return EquipmentLeaseConfig(
        tranches=reported_terms,
        equity=equity,
        asset_cost=sum(t.proceeds for t in reported_terms) + equity,
        lease_term_years=6,
        expected_residual_pct=0.30,
        tax_life_years=5,
        guarantor_name="Broadcom",
        lessee_name="Anthropic",
        equity_target_after_tax_irr=0.15,
    )


@pytest.mark.gate("G4.1")
def test_the_structure_is_registered_and_runs(config):
    from engine.structures import run_equipment_lease
    from engine.structures.models import StructureKey

    assert StructureKey.EQUIPMENT_LEASE.value == "equipment_lease"
    assert "residual value guarantee" in StructureKey.EQUIPMENT_LEASE.label

    result = run_equipment_lease(config)
    assert result.annual_rent > 0.0
    assert result.ledgers


@pytest.mark.gate("G4.2")
def test_supplied_tranche_terms_are_reproduced_and_sources_balance(config):
    from engine.structures import run_equipment_lease

    by_name = {t.name: t for t in config.tranches}
    assert by_name["Class A1"].amount == pytest.approx(6.0 * BN)
    assert by_name["Class A2"].amount == pytest.approx(24.0 * BN)
    assert by_name["Class A2"].issue_price == 1.0, "A2 was reported at par"
    assert by_name["Class B"].amount == pytest.approx(4.5 * BN)
    assert by_name["Class B"].rate == pytest.approx(0.085)
    assert by_name["Class B"].issue_price == pytest.approx(0.985)

    # Notes issued at a discount raise less than par.
    assert config.proceeds < config.debt
    assert config.sources == pytest.approx(config.asset_cost)

    result = run_equipment_lease(config)
    assert not [n for n in result.notes if "do not equal" in n]


@pytest.mark.gate("G4.3")
def test_the_unguaranteed_tranche_absorbs_a_residual_miss_first(config):
    """The guarantee asymmetry is the structure. It has to be visible."""
    from dataclasses import replace

    from engine.structures import run_equipment_lease

    base = run_equipment_lease(config)
    assert base.residual_shortfall == pytest.approx(0.0), (
        "at the underwritten residual there is nothing for the guarantee to do"
    )
    assert base.guarantor_payment == pytest.approx(0.0)

    stressed = run_equipment_lease(replace(config, realised_residual_pct=0.15))
    assert stressed.residual_shortfall > 0.0

    # Class B is exhausted before the guarantor pays anything.
    exposure = stressed.residual_shortfall
    assert stressed.unguaranteed_loss > 0.0
    assert stressed.guarantor_payment > 0.0
    assert stressed.unguaranteed_loss + stressed.guarantor_payment == pytest.approx(
        exposure
    )

    b_ledger = stressed.ledger("Class B")
    a2_ledger = stressed.ledger("Class A2")
    assert b_ledger.total < base.ledger("Class B").total, "Class B took no loss"
    assert a2_ledger.total == pytest.approx(base.ledger("Class A2").total), (
        "a guaranteed tranche was made to bear a residual miss"
    )

    text = stressed.guarantee_asymmetry()
    assert "Broadcom" in text and "unguaranteed" in text


@pytest.mark.gate("G4.4")
def test_the_lessee_pays_rent_and_carries_no_debt_schedule(config):
    from engine.structures import run_equipment_lease

    result = run_equipment_lease(config)
    lessee = result.ledger("Anthropic")
    assert "rent, not debt service" in lessee.role

    # Every lessee flow is an equal outflow. No principal, no interest split,
    # no balance to carry.
    payments = [c for c in lessee.cashflow if c != 0.0]
    assert payments, "the lessee pays nothing"
    assert all(p < 0 for p in payments)
    assert len(set(round(p, 6) for p in payments)) == 1, "rent is not level"
    assert lessee.cashflow[0] == 0.0, "the lessee funds nothing at closing"
    assert not hasattr(result, "lessee_debt_schedule")


@pytest.mark.gate("G4.5")
def test_the_corpus_entry_discloses_only_what_the_release_stated():
    """The engine may model a hypothesis. The corpus records only facts."""
    from comps.corpus import by_key

    record = by_key("broadcom-ai-xpv-2026")
    assert "apollo.com" in record.primary_source.lower() or "Apollo" in (
        record.primary_source
    )

    for tranche in record.tranches:
        for field, cell in tranche.cells():
            assert cell.provenance.value == "not_disclosed", (
                f"{field} claims to be {cell.provenance.value}; the release "
                "states no tranche economics"
            )
            assert "does not state" in cell.reason

    assert record.credit_route.provenance.value == "not_disclosed", (
        "guarantee terms are not in the release"
    )
    assert record.total_quantum.provenance.value == "stated", (
        "the $35bn headline is in the release and should be stated"
    )


@pytest.mark.gate("G4.6")
def test_every_party_has_a_ledger_and_the_ledgers_reconcile(config):
    from dataclasses import replace

    from engine.defaults import CASH_TOLERANCE
    from engine.structures import run_equipment_lease

    for scenario in (config, replace(config, realised_residual_pct=0.15)):
        result = run_equipment_lease(scenario)
        parties = {entry.party for entry in result.ledgers}
        assert {"Anthropic", "Broadcom", "SPV equity", "Class A1", "Class A2", "Class B"} <= parties

        for period, net in enumerate(result.reconciliation()):
            assert abs(net) < 1e-3, (
                f"period {period} does not reconcile: {net:,.2f} of cash "
                "appears from nowhere"
            )
        assert CASH_TOLERANCE > 0


@pytest.mark.gate("G4.7")
def test_a_data_centre_gets_a_structure_that_actually_computes():
    """A hyperscale campus was being handed a renewable tax-equity structure.

    Every data centre came back with preferred equity partnership as the only
    option and every quantitative cell not meaningful, because the engine
    cannot size a renewable structure without a tax project. A securitised
    lease is what these are actually financed with.
    """
    import datetime as dt

    from compare import build_comparison
    from compare.table import NotMeaningful
    from intake import ContractSpec, DealSpec, resolve

    today = dt.date(2026, 8, 8)
    resolution = resolve(
        DealSpec(
            asset_type="DATA_CENTRE",
            size={"it_mw": 250.0},
            state="VA",
            contract=ContractSpec("HYPERSCALE_LEASE", 15),
            cod="2028-09",
        ),
        today=today,
    )
    table = build_comparison(resolution, today=today)

    keys = {s.value for s in table.structures}
    assert "securitised_lease" in keys
    assert "preferred_equity" not in keys, (
        "a renewable tax-equity structure is still being offered for a campus"
    )

    populated = [
        row
        for row in table.quantitative
        if not isinstance(row.values["securitised_lease"], NotMeaningful)
    ]
    assert len(populated) >= 3, "the structure produces no numbers"


@pytest.mark.gate("G4.7")
def test_the_lease_structures_produce_party_ledgers():
    """Both lease structures carry every counterparty, so both must report them."""
    from lib_api.analyse import run_analyse

    for asset, size, expect in (
        ("AI_COMPUTE", {"mw": 1000.0}, "equipment_lease"),
        ("DATA_CENTRE", {"it_mw": 250.0}, "securitised_lease"),
    ):
        payload = run_analyse(
            {
                "asset_type": asset,
                "size": size,
                "state": "TX",
                "contract": {"kind": "HYPERSCALE_LEASE", "tenor_years": 15},
                "cod": "2028-01",
            }
        )
        parties = payload["parties"]
        assert expect in parties, f"{asset} produced no party ledgers"
        view = parties[expect]
        assert not view["conservation"], view["conservation"]
        assert len(view["ledgers"]) >= 4
        for ledger in view["ledgers"]:
            metrics = ledger["metrics"]
            assert metrics["irr"] is not None or metrics["not_meaningful_reason"]
