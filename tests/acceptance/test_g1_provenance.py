"""G1 — every number that reaches a reader carries its lineage.

Imports sit inside the test bodies on purpose: a missing module must fail the
gate it belongs to, not blank the whole phase out of the scorecard.
"""

from __future__ import annotations

import datetime as dt

import pytest


@pytest.mark.gate("G1.1")
def test_every_benchmark_carries_a_source_and_a_date():
    from engine import defaults

    benchmarks = defaults.benchmark_registry()
    assert benchmarks, "the benchmark registry is empty"
    for name, bm in benchmarks.items():
        assert bm.source and bm.source.strip(), f"{name} has no source"
        assert isinstance(bm.verified_on, dt.date), f"{name} has no verified_on date"


@pytest.mark.gate("G1.2")
def test_provenance_classes_are_exactly_the_four():
    from engine.provenance import Provenance

    assert {p.value for p in Provenance} == {
        "stated",
        "benchmark",
        "assumed",
        "not_disclosed",
    }


@pytest.mark.gate("G1.2")
def test_stated_requires_a_url_and_a_date():
    from engine.provenance import stated

    with pytest.raises(ValueError):
        stated(1.0, source="somewhere", source_url=None, source_date=dt.date(2026, 1, 1))
    with pytest.raises(ValueError):
        stated(1.0, source="somewhere", source_url="https://x", source_date=None)

    ok = stated(
        1.0,
        source="Example",
        source_url="https://example.com",
        source_date=dt.date(2026, 1, 1),
    )
    assert ok.provenance.value == "stated"


@pytest.mark.gate("G1.3")
def test_a_bare_number_cannot_reach_the_wire():
    from engine.provenance import UnbadgedNumber, to_wire, assumed

    with pytest.raises(UnbadgedNumber):
        to_wire({"sponsor_irr": 0.124})

    with pytest.raises(UnbadgedNumber):
        to_wire({"tranches": [{"size": 6_000_000_000}]})

    wire = to_wire({"sponsor_irr": assumed(0.124, note="tool default")})
    assert wire["sponsor_irr"]["value"] == pytest.approx(0.124)


@pytest.mark.gate("G1.4")
def test_not_disclosed_serialises_explicitly():
    from engine.provenance import not_disclosed, to_wire

    wire = to_wire({"tenor_years": not_disclosed("the release did not state a tenor")})
    field = wire["tenor_years"]
    assert field["provenance"] == "not_disclosed"
    assert field["value"] is None
    assert field["reason"]
    # It must not be mistakable for a real zero or a missing key.
    assert field["value"] != 0
    assert "value" in field


@pytest.mark.gate("G1.5")
def test_a_published_range_survives_to_the_wire():
    from engine import defaults
    from engine.provenance import to_wire

    ranged = [
        bm for bm in defaults.benchmark_registry().values() if bm.low != bm.high
    ]
    assert ranged, "no benchmark exposes a range; the sources publish several"
    for bm in ranged:
        field = to_wire({"x": bm.provenanced()})["x"]
        assert field["low"] is not None and field["high"] is not None
        assert field["low"] < field["high"]


@pytest.mark.gate("G1.6")
def test_confidence_header_counts_every_provenanced_leaf():
    from engine.provenance import (
        assumed,
        benchmark_value,
        confidence_header,
        not_disclosed,
        stated,
    )

    payload = {
        "a": stated(
            1.0,
            source="S",
            source_url="https://example.com",
            source_date=dt.date(2026, 1, 1),
        ),
        "b": [assumed(2.0), assumed(3.0)],
        "c": {"d": not_disclosed("not in the release")},
        "e": benchmark_value(
            4.0,
            source="Norton Rose Fulbright, Cost of Capital: 2026 Outlook",
            source_date=dt.date(2026, 1, 29),
            low=3.5,
            high=4.5,
        ),
    }
    header = confidence_header(payload)
    assert header == {
        "stated": 1,
        "benchmark": 1,
        "assumed": 2,
        "not_disclosed": 1,
        "total": 5,
    }
