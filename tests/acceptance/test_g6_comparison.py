"""G6 — the numbers and the qualitative band, side by side."""

from __future__ import annotations

import datetime as dt

import pytest

TODAY = dt.date(2026, 8, 8)


def _table(spec_dict, priority=None):
    from compare import build_comparison
    from intake import DealSpec, resolve
    from recommend import SponsorPriority

    resolution = resolve(DealSpec.from_dict(spec_dict), today=TODAY)
    return build_comparison(
        resolution, priority=priority or SponsorPriority.MAX_IRR, today=TODAY
    )


@pytest.mark.gate("G6.1")
def test_every_quantitative_cell_is_a_number_or_a_stated_reason(canonical_spec):
    from compare.table import NotMeaningful
    from engine.provenance import Provenanced

    table = _table(canonical_spec)
    assert table.structures, f"{canonical_spec['key']}: nothing to compare"
    assert table.quantitative, "no quantitative rows"

    for row in table.quantitative:
        for key in table.structures:
            value = row.values[key.value]
            assert isinstance(value, (Provenanced, NotMeaningful)), (
                f"{row.id}/{key.value} is a bare value"
            )
            if isinstance(value, NotMeaningful):
                assert value.reason.strip(), (
                    f"{row.id}/{key.value} is blank with no reason given"
                )
            else:
                assert value.value is not None


@pytest.mark.gate("G6.1")
def test_the_table_leads_with_a_metric_that_means_something():
    """A column of blank IRRs is worse than leading with NPV and saying why."""
    from compare.table import NotMeaningful

    table = _table(
        {
            "asset_type": "STORAGE",
            "size": {"mw": 150.0, "mwh": 600.0},
            "state": "CA",
            "contract": {"kind": "TOLLING", "tenor_years": 15},
            "cod": "2028-01",
        }
    )
    metric, note = table.headline_metric
    irr = next(r for r in table.quantitative if r.id == "sponsor_after_tax_irr")
    all_blank = all(isinstance(v, NotMeaningful) for v in irr.values.values())

    if all_blank:
        assert metric == "sponsor_npv"
        assert note and "not a usable comparison" in note
        npv = next(r for r in table.quantitative if r.id == "sponsor_npv")
        populated = [v for v in npv.values.values() if not isinstance(v, NotMeaningful)]
        assert populated, "the fallback metric is blank too"
    else:
        assert metric == "sponsor_after_tax_irr"
        assert note == ""


@pytest.mark.gate("G6.2")
def test_every_qualitative_cell_carries_a_rule_id_and_a_reason(canonical_spec):
    table = _table(canonical_spec)
    assert table.qualitative, "no qualitative band"
    for cell in table.qualitative:
        assert cell.rule_id, "a qualitative cell has no rule id"
        assert cell.reason.strip(), f"{cell.rule_id} gives no reason"
        assert 1 <= cell.rating <= 5
        assert cell.rule_id == f"{cell.structure.value}.{cell.dimension}"


@pytest.mark.gate("G6.3")
def test_a_qualitative_cell_cannot_exist_without_a_rule():
    """Prose that is not rule-derived must not be constructible."""
    from engine.structures.models import StructureKey
    from recommend.characteristics import Cell

    with pytest.raises(ValueError):
        Cell(
            structure=StructureKey.PARTNERSHIP_FLIP,
            dimension="execution_complexity",
            rating=3,
            reason="   ",
            rule_id="anything",
        )
    with pytest.raises(ValueError):
        Cell(
            structure=StructureKey.PARTNERSHIP_FLIP,
            dimension="execution_complexity",
            rating=9,
            reason="out of range",
            rule_id="anything",
        )


@pytest.mark.gate("G6.4")
def test_the_qualitative_matrix_has_no_gaps():
    """Ten dimensions for every structure. A silent gap reads as a blank cell."""
    from engine.structures.models import StructureKey
    from recommend.characteristics import DIMENSIONS, BY_STRUCTURE

    assert len(DIMENSIONS) == 10
    missing = []
    for key in StructureKey:
        cells = BY_STRUCTURE.get(key, {})
        for dimension in DIMENSIONS:
            if dimension.id not in cells:
                missing.append(f"{key.value}.{dimension.id}")
    assert not missing, "gaps in the matrix: " + ", ".join(missing)

    total = sum(len(v) for v in BY_STRUCTURE.values())
    assert total == len(StructureKey) * len(DIMENSIONS)


@pytest.mark.gate("G6.4")
def test_ratings_point_the_same_way_for_every_dimension():
    """Higher is better for the sponsor, everywhere, or the scores cannot add up."""
    from engine.structures.models import StructureKey
    from recommend.characteristics import cell

    # A direct transfer is the simplest structure in the set to execute and a
    # partnership flip the hardest, so the polarity is checkable.
    assert (
        cell(StructureKey.DIRECT_TRANSFER, "execution_complexity").rating
        > cell(StructureKey.PARTNERSHIP_FLIP, "execution_complexity").rating
    )
    # An equipment lease involves no tax credit, so it cannot suffer recapture.
    assert cell(StructureKey.EQUIPMENT_LEASE, "recapture_exposure").rating == 5


@pytest.mark.gate("G6.5")
def test_the_engine_overrides_the_gates_where_they_disagree():
    """A gate sees the deal's shape; the engine sees whether it can be built.

    A post-cliff solar project passes the flip and preferred-equity gates —
    neither is credit-dependent by definition — but with no credit the engine
    cannot size either. Rendering them would print uninitialised zeros as
    results, which is how a comparison table produces confident wrong numbers.
    """
    from compare.table import NotMeaningful

    table = _table(
        {
            "asset_type": "SOLAR_PLUS_STORAGE",
            "size": {"mwac": 430.0, "mwh": 340.0},
            "state": "TX",
            "contract": {"kind": "PPA", "tenor_years": 15},
            "cod": "2028-06",
        }
    )

    demoted = [
        e
        for e in table.recommendation.infeasible
        if any(v.gate_id == "engine-infeasible" for v in e.gates_failed)
    ]
    assert demoted, "the engine and the gates agreed on a deal where they should not"
    for entry in demoted:
        assert entry.structure not in table.structures
        verdict = next(
            v for v in entry.gates_failed if v.gate_id == "engine-infeasible"
        )
        assert verdict.fact.strip()

    # No zero stands in for a result.
    npv = next(r for r in table.quantitative if r.id == "sponsor_npv")
    for key in table.structures:
        value = npv.values[key.value]
        if not isinstance(value, NotMeaningful):
            assert value.value != 0.0, f"{key.value} reported an exact zero NPV"

    # The leader named in the rationale is one that survived.
    leader = table.recommendation.leader
    assert leader is not None and leader.structure in table.structures
    assert leader.structure.label.lower().split(",")[0] in table.recommendation.rationale.lower()


@pytest.mark.gate("G6.5")
def test_a_shortlist_that_destroys_value_says_so():
    table = _table(
        {
            "asset_type": "SOLAR_PLUS_STORAGE",
            "size": {"mwac": 430.0, "mwh": 340.0},
            "state": "TX",
            "contract": {"kind": "PPA", "tenor_years": 15},
            "cod": "2028-06",
        }
    )
    from compare.table import NotMeaningful

    npv = next(r for r in table.quantitative if r.id == "sponsor_npv")
    values = [
        v.value
        for v in npv.values.values()
        if not isinstance(v, NotMeaningful) and v.value is not None
    ]
    if values and max(values) < 0:
        assert table.value_warning
        assert "does not support a financing" in table.value_warning
    else:
        assert table.value_warning == ""
