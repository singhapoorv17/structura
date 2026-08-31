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
    # Capex itself comes from construction-cost data. The comparable
    # financings are carried alongside as a cross-check, and it is that cell
    # which has to name them.
    assert resolution.inputs["capex"].provenance.value == "benchmark"
    assert resolution.comps_used, "no comparable transactions were cited"

    cross = resolution.inputs["capex_comps_crosscheck"]
    assert cross.provenance.value == "benchmark"
    for name in resolution.comps_used:
        assert name in cross.source, f"{name} is not named in the cross-check"
    assert "not used to build the model" in cross.note


@pytest.mark.gate("G3.4")
def test_resolution_is_fast_enough_to_feel_immediate(canonical_specs):
    from intake import DealSpec, resolve

    start = time.perf_counter()
    for spec in canonical_specs:
        resolve(DealSpec.from_dict(spec))
    elapsed = time.perf_counter() - start
    assert elapsed < MAX_SECONDS, f"{elapsed:.1f}s for {len(canonical_specs)} specs"


@pytest.mark.gate("G3.5")
@pytest.mark.parametrize(
    "asset,size,contract,expect_range",
    [
        ("SOLAR", {"mwac": 300.0}, "PPA", (61.40, 64.49)),
        ("WIND", {"mw": 300.0}, "HEDGE", (79.40, 83.79)),
        ("STORAGE", {"mw": 150.0, "mwh": 600.0}, "TOLLING", None),
    ],
)
def test_contract_pricing_comes_from_a_cited_band(asset, size, contract, expect_range):
    """Contract price was the largest unsourced input in the model.

    It is now a cited band for every technology where a free source publishes
    one. This gate exists so it cannot quietly revert to a tool default: an
    assumed price drives every downstream number and looks identical on screen
    to a sourced one but for its badge.
    """
    from intake import ContractSpec, DealSpec, resolve

    resolution = resolve(
        DealSpec(
            asset_type=asset,
            size=size,
            state="TX",
            contract=ContractSpec(contract, 15),
            cod="2028-06",
        )
    )
    cell = resolution.inputs["contracted_price"]
    assert cell.provenance.value == "benchmark", (
        f"{asset} contract price is {cell.provenance.value}, not a cited band"
    )
    assert cell.source and cell.source_url and cell.source_date
    assert cell.low is not None and cell.high is not None and cell.low < cell.high

    if expect_range:
        assert (cell.low, cell.value) == (expect_range[0], expect_range[0]) or (
            cell.high,
            cell.value,
        ) == (expect_range[1], expect_range[1])


@pytest.mark.gate("G3.5")
def test_a_supplied_price_overrides_the_band():
    from intake import ContractSpec, DealSpec, resolve

    resolution = resolve(
        DealSpec(
            asset_type="SOLAR",
            size={"mwac": 300.0},
            state="TX",
            contract=ContractSpec("PPA", 20, price=48.0),
            cod="2028-06",
        )
    )
    cell = resolution.inputs["contracted_price"]
    assert cell.provenance.value == "stated"
    assert cell.value == 48.0


@pytest.mark.gate("G3.5")
def test_a_band_that_restates_names_its_originator():
    """A restated figure has to point back to whoever produced it."""
    from comps.bands import BANDS

    for band in BANDS:
        if "leveltenenergy" in band.source_url or "reporting the" in band.source:
            assert band.restates, f"{band.key} restates without naming a source"
        assert band.point_estimate >= band.low
        assert band.point_estimate <= band.high


@pytest.mark.gate("G3.5")
def test_resolved_revenue_is_in_a_plausible_range(canonical_spec):
    """A revenue yield outside this range means an input is wrong somewhere.

    Not a market claim — a smoke test. Contracted infrastructure does not
    return 2% or 40% of capital cost in year-one revenue, and when this fires
    it has always been a defaulting bug rather than an unusual deal.
    """
    from intake import DealSpec, resolve

    resolution = resolve(DealSpec.from_dict(canonical_spec))
    price = resolution.inputs.get("contracted_price")
    production = resolution.inputs.get("production_p50")
    capex = resolution.inputs.get("capex")
    if not (price and production and capex) or not capex.value:
        pytest.skip("this technology does not resolve a revenue line")

    yield_pct = (price.value * production.value) / capex.value
    assert 0.04 <= yield_pct <= 0.35, (
        f"{canonical_spec['key']}: year-one revenue is {yield_pct:.1%} of "
        f"capital cost (${price.value:,.2f}/MWh on {production.value:,.0f} MWh "
        f"against ${capex.value / 1e6:,.0f}m)"
    )


@pytest.mark.gate("G3.6")
def test_every_assumption_says_it_is_unsourced(canonical_spec):
    """An assumption that reads like a fact is worse than a missing number.

    A reader filtering to "show only what is assumed" gets a consistent
    statement rather than a mix of explanations and silences.
    """
    from intake import DealSpec, resolve
    from intake.resolve import UNSOURCED

    resolution = resolve(DealSpec.from_dict(canonical_spec))
    vague = []
    for name, cell in resolution.inputs.items():
        if cell.provenance.value != "assumed":
            continue
        if UNSOURCED not in cell.note:
            vague.append(f"{name}: {cell.note[:70]!r}")
    assert not vague, "assumptions that do not declare themselves:\n" + "\n".join(vague)


@pytest.mark.gate("G3.6")
def test_capacity_factors_match_the_eia_workbook():
    """Read from the file, not from a rendering of it.

    A page-scrape of this table returned 23.6% for wind against the workbook's
    34.2%. The band is pinned here so a future edit has to justify itself.
    """
    from comps.bands import BY_KEY

    solar = BY_KEY["capacity_factor.solar"]
    wind = BY_KEY["capacity_factor.wind"]
    assert solar.point_estimate == pytest.approx(0.244)
    assert wind.point_estimate == pytest.approx(0.342)
    for band in (solar, wind):
        assert "eia.gov" in band.source_url
        assert band.low < band.point_estimate < band.high


@pytest.mark.gate("G3.6")
def test_a_hyperscale_deal_is_not_priced_off_a_colocation_rate():
    """The published colocation rate is for a sub-megawatt requirement.

    CBRE's widely quoted $195.94/kW-month covers a 250-500 kW deployment.
    Applying it to a 250 MW build-to-suit overstates revenue by roughly half
    again, which is the trap this band exists to avoid.
    """
    from comps.bands import BY_KEY
    from intake import ContractSpec, DealSpec, resolve

    band = BY_KEY["lease_price.hyperscale"]
    assert band.high <= 150.0, "the band has drifted into colocation pricing"
    assert "colocation" in band.note.lower()

    resolution = resolve(
        DealSpec(
            asset_type="DATA_CENTRE",
            size={"it_mw": 250.0},
            state="VA",
            contract=ContractSpec("HYPERSCALE_LEASE", 15),
            cod="2028-09",
        )
    )
    rate = resolution.inputs["lease_rate"]
    assert rate.provenance.value == "benchmark"
    assert 100.0 <= rate.value <= 150.0


@pytest.mark.gate("G3.7")
@pytest.mark.parametrize("asset,size", [
    ("SOLAR", {"mwac": 300.0}),
    ("WIND", {"mw": 300.0}),
    ("STORAGE", {"mw": 150.0, "mwh": 600.0}),
])
def test_capex_is_a_construction_cost_not_a_financing_total(asset, size):
    """A financing package is not what the project cost to build.

    Deriving capex from comparable financings overstated it by a fifth or
    more, because a package carries credit monetisation, letters of credit and
    reserves on top of the build. Four of five solar and wind deals came back
    with a negative sponsor NPV as a result, on a technology the US installs
    tens of gigawatts of a year. Construction cost now comes from the EIA's
    installed-generator data, and the financing figure is kept alongside as a
    cross-check so the gap stays visible.
    """
    from intake import ContractSpec, DealSpec, resolve

    resolution = resolve(
        DealSpec(
            asset_type=asset,
            size=size,
            state="TX",
            contract=ContractSpec("PPA", 15),
            cod="2028-06",
        )
    )
    capex = resolution.inputs["capex"]
    assert capex.provenance.value == "benchmark"
    assert "eia.gov" in (capex.source_url or ""), (
        f"{asset} capex is sourced from {capex.source!r}, not construction-cost data"
    )

    mw = size.get("mwac") or size["mw"]
    per_mw = capex.value / mw / 1e6
    assert 0.8 <= per_mw <= 3.0, f"{asset} resolves to ${per_mw:.2f}m/MW"

    cross = resolution.inputs.get("capex_comps_crosscheck")
    if cross is not None:
        assert cross.value >= capex.value * 0.9, (
            "a financing total below construction cost means partial "
            "financings are still leaking into the derivation"
        )
        assert "cross-check" in cross.note


@pytest.mark.gate("G3.7")
def test_a_partial_financing_never_implies_a_project_cost():
    """A tax equity commitment funds one slice of the stack, not the project."""
    from comps.corpus import load
    from comps.matcher import match
    from comps.schema import Technology
    from intake.resolve import _per_mw_from_comps

    tagged = [r for r in load() if "partial-financing" in r.tags]
    assert tagged, "no record is tagged as a partial financing"

    # Greenbacker financed $440m of tax equity against a 500 MW project. Left
    # in, it implied $0.88m/MW; Doral's full package implied $2.09m. A median
    # across the two measures nothing.
    greenbacker = next(r for r in load() if r.key == "greenbacker-cider-2026")
    assert "partial-financing" in greenbacker.tags

    result = match(technology=Technology.SOLAR, limit=8)
    _, cited = _per_mw_from_comps(result)
    for record in load():
        if record.name in cited:
            assert "partial-financing" not in record.tags
            assert "programme-capacity" not in record.tags
