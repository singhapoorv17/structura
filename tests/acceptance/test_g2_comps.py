"""G2 — the comparable-transactions corpus, and the line between fact and band."""

from __future__ import annotations

import datetime as dt

import pytest

MIN_CORPUS = 50
MIN_MATCHES = 3


@pytest.mark.gate("G2.1")
def test_corpus_loads_and_validates():
    from comps.corpus import load

    records = load()
    assert records, "the corpus is empty"
    keys = [r.key for r in records]
    assert len(keys) == len(set(keys)), "duplicate record keys"


#: A source whose date was not captured is allowed to say so, but the escape
#: hatch has to stay narrow or it becomes the default.
MAX_UNDATED_SHARE = 0.45


@pytest.mark.gate("G2.2")
def test_every_stated_cell_has_a_url_and_a_dated_or_explicitly_undated_source():
    from comps.corpus import iter_records

    missing = []
    stated = undated = 0
    for record in iter_records():
        for name, cell in record.provenanced_cells():
            if cell.provenance.value != "stated":
                continue
            stated += 1
            if not cell.source_url:
                missing.append(f"{record.key}.{name}: no source_url")
            if isinstance(cell.source_date, dt.date):
                continue
            if cell.source_date_unknown:
                undated += 1
                continue
            missing.append(f"{record.key}.{name}: no source_date and no explicit unknown")
    assert not missing, "\n".join(missing)

    share = undated / stated if stated else 0.0
    assert share <= MAX_UNDATED_SHARE, (
        f"{undated} of {stated} stated cells carry no captured source date "
        f"({share:.0%}). The ceiling is {MAX_UNDATED_SHARE:.0%} — capture "
        "publication dates during ingest rather than deferring them."
    )


@pytest.mark.gate("G2.3")
def test_no_stored_string_exceeds_its_cap():
    from comps.corpus import iter_records
    from comps.schema import LENGTH_CAPS

    overlong = []
    for record in iter_records():
        for field, value in record.flat_strings():
            cap = LENGTH_CAPS.get(field, LENGTH_CAPS["_default"])
            if len(value) > cap:
                overlong.append(f"{record.key}.{field}: {len(value)} > {cap}")
    assert not overlong, "\n".join(overlong)


@pytest.mark.gate("G2.4")
def test_corpus_reaches_working_size():
    from comps.corpus import load

    records = load()
    assert len(records) >= MIN_CORPUS, (
        f"corpus holds {len(records)} verified transactions, target {MIN_CORPUS}. "
        "Records are added by ingest with a confirmed source URL each; a record "
        "without one does not load."
    )


@pytest.mark.gate("G2.5")
def test_matcher_returns_comps_for_every_canonical_spec(canonical_specs):
    from comps.matcher import match
    from comps.schema import Technology

    thin = []
    for spec in canonical_specs:
        result = match(
            technology=Technology(spec["asset_type"]),
            contract_kind=spec["contract"]["kind"],
            state=spec["state"],
        )
        if len(result.matches) < MIN_MATCHES:
            thin.append(f"{spec['key']}: {len(result.matches)} comps")
            continue
        family = Technology(spec["asset_type"]).family
        for m in result.matches:
            assert m.record.technology.family == family, (
                f"{spec['key']}: matched {m.record.key} across technology families"
            )
    assert not thin, "specs with too few comps:\n" + "\n".join(thin)


@pytest.mark.gate("G2.6")
def test_deal_facts_and_market_bands_stay_in_separate_panels():
    from comps.corpus import iter_records
    from comps.matcher import match
    from comps.schema import MarketBand, Technology

    # A deal record may not hold a benchmark-provenance cell at all.
    for record in iter_records():
        for name, cell in record.provenanced_cells():
            assert cell.provenance.value in {"stated", "not_disclosed"}, (
                f"{record.key}.{name} is {cell.provenance.value}; a transaction "
                "may only hold what its sources stated"
            )

    result = match(technology=Technology.SOLAR)
    wire = result.to_dict()
    assert set(wire) >= {"deals", "market_bands", "coverage_statement"}
    for deal in wire["deals"]:
        assert "low" not in deal and "high" not in deal
    assert all(isinstance(b, MarketBand) for b in result.market_bands)


@pytest.mark.gate("G2.6")
def test_every_market_band_is_cited_and_dated():
    from comps.bands import BANDS

    for band in BANDS:
        assert band.source and band.source_url, f"{band.key} is uncited"
        assert isinstance(band.source_date, dt.date), f"{band.key} has no date"
        assert band.low <= band.high


@pytest.mark.gate("G2.7")
def test_restatements_name_the_primary_source_they_echo():
    from comps.corpus import iter_records

    unlabelled = []
    for record in iter_records():
        assert record.primary_source, f"{record.key} names no primary source"
        for name, cell in record.provenanced_cells():
            if cell.is_restatement and not cell.echo_of:
                unlabelled.append(f"{record.key}.{name}")
    assert not unlabelled, ", ".join(unlabelled)


@pytest.mark.gate("G2.8")
def test_pre_obbba_comps_are_flagged_and_ranked_below_current_ones():
    """A 2019 tax equity deal is not a comp for a 2026 project.

    OBBBA changed eligibility, transfer pricing and begin-construction rules.
    Older transactions stay in the corpus because the structure is still
    instructive, but they must say so and must not out-rank current deals.
    """
    from comps.matcher import OBBBA_ENACTED, match
    from comps.schema import Technology

    result = match(technology=Technology.WIND)
    assert result.matches, "no wind comps to test vintage against"

    for m in result.matches:
        if m.vintage is not None and m.vintage < OBBBA_ENACTED:
            assert m.vintage_warning, f"{m.record.key} is pre-OBBBA and unflagged"
            assert "OBBBA" in m.vintage_warning

    years = [m.vintage for m in result.matches]
    current = [i for i, y in enumerate(years) if y and y >= OBBBA_ENACTED]
    stale = [i for i, y in enumerate(years) if y and y < OBBBA_ENACTED]
    if current and stale:
        assert max(current) < min(stale), (
            f"a pre-OBBBA comp out-ranked a current one: {years}"
        )

    if any(m.vintage_warning for m in result.matches):
        assert "OBBBA" in result.coverage_statement
