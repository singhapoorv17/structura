"""G5 — screening, ranking, and an explanation made of this deal's own facts."""

from __future__ import annotations

import datetime as dt

import pytest

TODAY = dt.date(2026, 8, 8)

CREDIT_DEPENDENT = {"direct_transfer", "t_flip"}


def _recommend(spec_dict, priority=None):
    from intake import DealSpec, resolve
    from recommend import SponsorPriority, recommend

    resolution = resolve(DealSpec.from_dict(spec_dict), today=TODAY)
    return recommend(
        resolution,
        priority=priority or SponsorPriority.MAX_IRR,
        today=TODAY,
    )


@pytest.mark.gate("G5.1")
def test_every_canonical_deal_gets_a_sound_recommendation(canonical_spec):
    rec = _recommend(canonical_spec)

    leader = rec.leader
    assert leader is not None, f"{canonical_spec['key']}: nothing is feasible"
    assert leader.feasible

    # An equipment lease is for equipment, and only for equipment.
    is_equipment = canonical_spec["asset_type"] == "AI_COMPUTE"
    recommended = leader.structure.value
    if is_equipment:
        assert recommended == "equipment_lease"
    else:
        assert recommended != "equipment_lease"

    # A deal with no credit cannot be led by a structure that exists to
    # monetise one.
    no_credit = canonical_spec["asset_type"] in {
        "DATA_CENTRE",
        "AI_COMPUTE",
        "TRANSMISSION",
    }
    if no_credit:
        assert recommended not in CREDIT_DEPENDENT
        for entry in rec.feasible:
            assert entry.structure.value not in CREDIT_DEPENDENT

    # The rationale has to be about this project.
    assert rec.facts_used, "no facts from this deal were used"
    assert rec.facts_used[0] in rec.rationale


@pytest.mark.gate("G5.1")
def test_a_post_cliff_solar_project_cannot_be_led_by_a_credit_structure():
    """After the OBBBA deadline this is determinate, not a judgment call."""
    rec = _recommend(
        {
            "asset_type": "SOLAR",
            "size": {"mwac": 300.0},
            "state": "NM",
            "contract": {"kind": "PPA", "tenor_years": 20},
            "cod": "2029-06",
        }
    )
    assert rec.leader.structure.value not in CREDIT_DEPENDENT
    blocked = {e.structure.value for e in rec.infeasible}
    assert CREDIT_DEPENDENT <= blocked


@pytest.mark.gate("G5.2")
def test_every_infeasible_structure_carries_a_gate_id_and_a_fact(canonical_spec):
    rec = _recommend(canonical_spec)
    for entry in rec.infeasible:
        assert entry.gates_failed, f"{entry.structure.value} is blocked by nothing"
        for verdict in entry.gates_failed:
            assert verdict.gate_id, "a gate fired with no id"
            assert verdict.fact.strip(), f"{verdict.gate_id} gives no reason"
            assert verdict.source and verdict.source_url
            assert not verdict.passed
        assert entry.blocking_reason.strip()


@pytest.mark.gate("G5.3")
def test_the_sponsor_priority_changes_the_ranking_and_says_so(canonical_specs):
    from recommend import SponsorPriority

    moved = []
    for spec in canonical_specs:
        orders = {}
        for priority in SponsorPriority:
            rec = _recommend(spec, priority=priority)
            orders[priority] = tuple(e.structure.value for e in rec.feasible)
            assert priority.label in rec.rationale, (
                "the response does not say which objective drove the ranking"
            )
        if len(set(orders.values())) > 1:
            moved.append(spec["key"])

    assert moved, (
        "no canonical deal reorders under any objective, so the toggle does "
        "nothing"
    )


@pytest.mark.gate("G5.4")
def test_hard_gates_fire_outside_the_structure_modules():
    """A rule this consequential must not depend on one module remembering it."""
    from engine.structures.models import StructureKey
    from intake import DealSpec, resolve
    from recommend.gates import evaluate_gates

    resolution = resolve(
        DealSpec.from_dict(
            {
                "asset_type": "DATA_CENTRE",
                "size": {"it_mw": 250.0},
                "state": "VA",
                "contract": {"kind": "HYPERSCALE_LEASE", "tenor_years": 15},
                "cod": "2028-09",
            }
        ),
        today=TODAY,
    )
    gates = evaluate_gates(resolution, today=TODAY)

    for key in (StructureKey.DIRECT_TRANSFER, StructureKey.T_FLIP):
        failures = gates[key]
        assert failures, f"{key.value} survived a no-credit technology"
        assert any(v.gate_id == "no-credit-technology" for v in failures)


@pytest.mark.gate("G5.5")
def test_the_tax_equity_minimum_ticket_fires_with_its_citation():
    from comps.bands import BY_KEY
    from engine.structures.models import StructureKey
    from intake import DealSpec, resolve
    from recommend.gates import evaluate_gates

    band = BY_KEY["ticket.tax_equity_minimum"]
    small = resolve(
        DealSpec.from_dict(
            {
                "asset_type": "STORAGE",
                "size": {"mw": 20.0, "mwh": 40.0},
                "state": "CA",
                "contract": {"kind": "TOLLING", "tenor_years": 15},
                "cod": "2028-01",
                "capex": 40_000_000.0,
            }
        ),
        today=TODAY,
    )
    gates = evaluate_gates(small, today=TODAY)
    failures = gates[StructureKey.PARTNERSHIP_FLIP]
    verdict = next((v for v in failures if v.gate_id == "tax-equity-minimum-ticket"), None)
    assert verdict is not None, "a $40m deal cleared the tax equity minimum"
    assert verdict.source == band.source
    assert verdict.source_url == band.source_url
    assert f"${band.low / 1e6:,.0f}m" in verdict.fact

    # A deal comfortably above the threshold must not trip it.
    large = resolve(
        DealSpec.from_dict(
            {
                "asset_type": "STORAGE",
                "size": {"mw": 400.0, "mwh": 1600.0},
                "state": "CA",
                "contract": {"kind": "TOLLING", "tenor_years": 15},
                "cod": "2028-01",
                "capex": 600_000_000.0,
            }
        ),
        today=TODAY,
    )
    assert not [
        v
        for v in evaluate_gates(large, today=TODAY)[StructureKey.PARTNERSHIP_FLIP]
        if v.gate_id == "tax-equity-minimum-ticket"
    ]
