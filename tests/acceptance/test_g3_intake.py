"""G3 — six fields in, a complete and badged model out."""

from __future__ import annotations

import datetime as dt
import time

import pytest

MAX_SECONDS = 60.0


@pytest.mark.gate("G3.1")
def test_six_fields_produce_a_complete_model(canonical_spec):
    from intake import DealSpec, resolve

    resolution = resolve(DealSpec.from_dict(canonical_spec))
    assert not resolution.unresolved(), (
        f"{canonical_spec['key']} left these unresolved: "
        + ", ".join(resolution.unresolved())
    )
    for required in ("asset_type", "construction_months", "project_life_years"):
        assert required in resolution.inputs, f"{required} was not resolved"


@pytest.mark.gate("G3.2")
def test_an_off_market_premise_is_flagged_before_the_model_runs():
    """A 15-year physical PPA in ERCOT is unusual and the tool should say so."""
    from intake import ContractSpec, DealSpec, resolve

    spec = DealSpec(
        asset_type="SOLAR_PLUS_STORAGE",
        size={"mwac": 430.0, "mwh": 340.0},
        state="TX",
        contract=ContractSpec(kind="PPA", tenor_years=15),
        cod="2028-06",
    )
    advisories = resolve(spec).advisories
    hedge = next((a for a in advisories if a.id == "ercot-hedge-market"), None)
    assert hedge is not None, "the ERCOT hedge premise was not flagged"
    assert hedge.source and hedge.source_url, "the advisory cites no source"
    assert "hedge" in hedge.message.lower()

    # The same project outside ERCOT should not trip it.
    elsewhere = resolve(
        DealSpec(
            asset_type="SOLAR_PLUS_STORAGE",
            size={"mwac": 430.0, "mwh": 340.0},
            state="NM",
            contract=ContractSpec(kind="PPA", tenor_years=15),
            cod="2028-06",
        )
    )
    assert not any(a.id == "ercot-hedge-market" for a in elsewhere.advisories)


@pytest.mark.gate("G3.2")
def test_the_begin_construction_cliff_blocks_a_new_wind_or_solar_project():
    """After 4 July 2026 a new solar project cannot reach the credit.

    This is the check most likely to change what a user does, so it is a
    blocking advisory rather than a note, and it must not fire for storage.
    """
    from intake import ContractSpec, DealSpec, resolve

    after = dt.date(2026, 8, 8)
    solar = resolve(
        DealSpec(
            asset_type="SOLAR",
            size={"mwac": 200.0},
            state="NM",
            contract=ContractSpec(kind="PPA", tenor_years=20),
            cod="2029-01",
        ),
        today=after,
    )
    cliff = next(
        (a for a in solar.advisories if a.id == "begin-construction-cliff"), None
    )
    assert cliff is not None and cliff.severity == "blocking"
    assert cliff.source_url

    storage = resolve(
        DealSpec(
            asset_type="STORAGE",
            size={"mw": 150.0, "mwh": 300.0},
            state="CA",
            contract=ContractSpec(kind="TOLLING", tenor_years=15),
            cod="2029-01",
        ),
        today=after,
    )
    assert not any(a.severity == "blocking" for a in storage.advisories), (
        "storage keeps §48E to 2033 and must not trip the wind and solar cliff"
    )


@pytest.mark.gate("G3.3")
def test_every_resolved_input_is_badged_and_counted(canonical_spec):
    from intake import DealSpec, resolve

    resolution = resolve(DealSpec.from_dict(canonical_spec))
    header = resolution.confidence

    assert header["total"] == len(resolution.inputs)
    assert header["total"] == sum(
        header[k] for k in ("stated", "benchmark", "assumed", "not_disclosed")
    )
    assert header["assumed"] >= 1, "a model with nothing assumed is overclaiming"

    for name, cell in resolution.inputs.items():
        assert cell.provenance.value in {
            "stated",
            "benchmark",
            "assumed",
        }, f"{name} carries {cell.provenance.value}"
        if cell.provenance.value == "benchmark":
            assert cell.source, f"{name} is a benchmark with no source"
        if cell.provenance.value == "assumed":
            assert cell.note, f"{name} is assumed and does not say what it is"


@pytest.mark.gate("G3.3")
def test_a_comps_derived_default_names_the_transactions_behind_it():
    from intake import ContractSpec, DealSpec, resolve

    resolution = resolve(
        DealSpec(
            asset_type="SOLAR_PLUS_STORAGE",
            size={"mwac": 430.0, "mwh": 340.0},
            state="TX",
            contract=ContractSpec(kind="PPA", tenor_years=15),
            cod="2028-06",
        )
    )
    capex = resolution.inputs["capex"]
    assert capex.provenance.value == "benchmark"
    assert resolution.comps_used, "no comparable transactions were cited"
    for name in resolution.comps_used:
        assert name in capex.source, f"{name} is not named in the capex source"
    assert "financing totals rather than construction budgets" in capex.note


@pytest.mark.gate("G3.4")
def test_resolution_is_fast_enough_to_feel_immediate(canonical_specs):
    from intake import DealSpec, resolve

    start = time.perf_counter()
    for spec in canonical_specs:
        resolve(DealSpec.from_dict(spec))
    elapsed = time.perf_counter() - start
    assert elapsed < MAX_SECONDS, f"{elapsed:.1f}s for {len(canonical_specs)} specs"
