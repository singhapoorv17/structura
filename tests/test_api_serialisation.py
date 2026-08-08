"""Serialisation: the frozen contract shape, and the four integrity guarantees.

These tests are the executable definition of the JSON response shape.
The four rules that cannot be traded away:

1. ``irr_is_meaningful`` comes from the engine's guard, and a false verdict
   still carries the rate plus its reason.
2. Every warning — engine, tax, structure, reference deal, API — reaches the
   response. PLACEHOLDER warnings in particular.
3. ``risks`` carry severity and BLOCKING survives.
4. ``capital_account_breaches`` are present.

Plus the one that makes the response usable at all: it must be valid JSON, so
no NaN and no Infinity, ever.
"""

from __future__ import annotations

import json
import math

import pytest

from engine.reference_deals import REFERENCE_DEALS
from engine.structures.models import RiskSeverity
from engine.tax.citations import get_all_citations
from engine.tax.enums import Confidence
from lib_api.serialise import (
    CONFIDENCE_TO_CONTRACT,
    SEVERITY_TO_CONTRACT,
    sanitise,
)
from lib_api.service import run_compare, run_current_law, run_reference_deals

DEAL_KEYS = tuple(REFERENCE_DEALS)

RANKED_FIELDS = {
    "rank",
    "key",
    "label",
    "feasible",
    "infeasible_reason",
    "sponsor_after_tax_irr",
    "irr_is_meaningful",
    "irr_not_meaningful_reason",
    "sponsor_npv",
    "effective_cost_of_capital",
    "sponsor_equity_required",
    "third_party_capital_raised",
    "total_capital_raised",
    "flip_year",
    "credit_transferred",
    "credit_retained",
    "cash_timing",
    "risks",
    "warnings",
}

TOP_LEVEL_FIELDS = {
    "deal",
    "headline",
    "law_verified_on",
    "ranked",
    "why_this_wins",
    "sources_and_uses",
    "debt",
    "tax",
    "capital_account_breaches",
    "warnings",
    "compute_ms",
}


@pytest.fixture(scope="module")
def responses():
    return {key: run_compare({"deal_key": key}) for key in DEAL_KEYS}


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", DEAL_KEYS)
def test_top_level_shape_matches_the_contract(responses, key):
    payload = responses[key]
    assert TOP_LEVEL_FIELDS <= set(payload)
    assert payload["deal"]["key"] == key
    assert payload["deal"]["capex"] == REFERENCE_DEALS[key].project.capex
    assert payload["law_verified_on"] == "2026-08-06"
    assert isinstance(payload["headline"], str) and payload["headline"]
    assert payload["compute_ms"] >= 0.0
    assert len(payload["ranked"]) == 5
    assert [r["rank"] for r in payload["ranked"]] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("key", DEAL_KEYS)
def test_ranked_entry_shape(responses, key):
    for entry in responses[key]["ranked"]:
        assert RANKED_FIELDS <= set(entry)
        assert isinstance(entry["feasible"], bool)
        assert isinstance(entry["irr_is_meaningful"], bool)
        assert isinstance(entry["label"], str) and entry["label"]
        if entry["feasible"]:
            assert entry["infeasible_reason"] is None
        else:
            assert entry["infeasible_reason"]
        timing = entry["cash_timing"]
        if timing is not None:
            assert set(timing) == {
                "cash_weighted_average_years",
                "share_by_year_5",
            }


@pytest.mark.parametrize("key", DEAL_KEYS)
def test_supporting_blocks_shape(responses, key):
    payload = responses[key]
    assert {
        "funding_requirement",
        "debt",
        "third_party_equity",
        "sponsor_equity",
        "post_cod_monetisation",
    } <= set(payload["sources_and_uses"])
    assert {
        "quantum",
        "gearing",
        "min_dscr",
        "binding_constraint",
        "llcr",
        "plcr",
    } <= set(payload["debt"])
    assert {
        "credit_section",
        "credit_rate",
        "credit_value",
        "eligibility_path",
        "feoc_pass",
        "adders",
        "warnings",
    } <= set(payload["tax"])
    why = payload["why_this_wins"]
    assert {
        "winner",
        "primary_metric",
        "winner_value",
        "runner_up",
        "runner_up_value",
        "margin",
        "drivers",
        "disqualified",
        "tie_breaks",
        "caveats",
    } <= set(why)
    assert why["primary_metric"] in {"sponsor_after_tax_irr", "sponsor_npv"}
    for driver in why["drivers"]:
        assert set(driver) == {
            "name",
            "unit",
            "winner_value",
            "runner_up_value",
            "delta",
            "higher_is_better",
            "note",
        }


def test_ranked_keys_are_the_five_structures(responses):
    for key in DEAL_KEYS:
        assert {r["key"] for r in responses[key]["ranked"]} == {
            "partnership_flip",
            "t_flip",
            "preferred_equity",
            "direct_transfer",
            "sale_leaseback",
        }


# ---------------------------------------------------------------------------
# Calibration survives the API layer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key,expected_irr",
    [
        ("storage_bess_contracted", 0.1485),
        ("solar_safe_harboured", 0.1172),
        ("data_center_powered_shell", 0.1510),
    ],
)
def test_calibrated_sponsor_irr_reaches_the_response(responses, key, expected_irr):
    """The API must not perturb the calibrated numbers by so much as a rounding."""
    winner = responses[key]["ranked"][0]
    assert winner["irr_is_meaningful"] is True
    assert winner["sponsor_after_tax_irr"] == pytest.approx(expected_irr, abs=5e-5)


# ---------------------------------------------------------------------------
# Rule 1 — the meaningfulness guard
# ---------------------------------------------------------------------------


def test_irr_not_meaningful_still_carries_the_rate_and_the_reason(responses):
    """Contract: the IRR is present but flagged, and the UI leads with NPV."""
    entries = [
        e
        for payload in responses.values()
        for e in payload["ranked"]
        if not e["irr_is_meaningful"]
    ]
    assert entries, "expected at least one non-meaningful IRR across the demo set"
    for entry in entries:
        assert entry["irr_not_meaningful_reason"]
        assert isinstance(entry["irr_not_meaningful_reason"], str)
        assert entry["sponsor_npv"] is not None


def test_meaningful_irr_has_no_reason(responses):
    for payload in responses.values():
        for entry in payload["ranked"]:
            if entry["irr_is_meaningful"]:
                assert entry["irr_not_meaningful_reason"] is None


def test_guard_is_the_engines_not_the_apis(responses):
    """Every flag is copied from the engine result, never recomputed here."""
    for key, payload in responses.items():
        comparison = REFERENCE_DEALS[key].compare()
        engine_flags = {
            r.result.key.value: r.result.sponsor_irr_is_meaningful
            for r in comparison.ranked
        }
        api_flags = {e["key"]: e["irr_is_meaningful"] for e in payload["ranked"]}
        assert api_flags == engine_flags


def test_headline_never_leads_with_a_meaningless_rate(responses):
    for payload in responses.values():
        winner = payload["ranked"][0]
        if winner["feasible"] and not winner["irr_is_meaningful"]:
            assert "NOT MEANINGFUL" in payload["headline"]
            assert payload["why_this_wins"]["primary_metric"] == "sponsor_npv"


# ---------------------------------------------------------------------------
# Rule 2 — no warning is ever swallowed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", DEAL_KEYS)
def test_every_engine_warning_reaches_the_response(responses, key):
    payload = responses[key]
    comparison = REFERENCE_DEALS[key].compare()
    emitted = set(payload["warnings"])
    for warning in comparison.warnings:
        assert warning in emitted
    for entry in comparison.ranked:
        for warning in entry.result.warnings:
            assert warning in emitted


@pytest.mark.parametrize("key", DEAL_KEYS)
def test_placeholder_warnings_survive(responses, key):
    payload = responses[key]
    assert any("PLACEHOLDER" in w for w in payload["warnings"])
    deal = REFERENCE_DEALS[key]
    if deal.placeholder_assumptions():
        assert deal.placeholder_warning() in payload["warnings"]


@pytest.mark.parametrize("key", DEAL_KEYS)
def test_per_structure_warnings_are_also_attached_to_their_structure(responses, key):
    comparison = REFERENCE_DEALS[key].compare()
    by_key = {e["key"]: e for e in responses[key]["ranked"]}
    for entry in comparison.ranked:
        assert by_key[entry.result.key.value]["warnings"] == list(
            entry.result.warnings
        )


def test_api_layer_warnings_are_added_not_substituted():
    payload = run_compare({"overrides": {"capex": 150_000_000, "nonsense": 1}})
    warnings = payload["warnings"]
    assert any("no 'deal_key' was supplied" in w for w in warnings)
    assert any("nonsense" in w for w in warnings)
    assert any("NOT re-solved" in w for w in warnings)
    assert any("PLACEHOLDER" in w for w in warnings)


def test_tax_block_carries_its_own_warnings(responses):
    for payload in responses.values():
        assert any("PLACEHOLDER" in w for w in payload["tax"]["warnings"])


# ---------------------------------------------------------------------------
# Rule 3 — risks and severity
# ---------------------------------------------------------------------------


def test_severity_map_covers_every_engine_severity():
    assert set(SEVERITY_TO_CONTRACT) == set(RiskSeverity)
    assert SEVERITY_TO_CONTRACT[RiskSeverity.BLOCKING] == "BLOCKING"
    assert set(SEVERITY_TO_CONTRACT.values()) <= {"BLOCKING", "HIGH", "MEDIUM", "LOW"}


@pytest.mark.parametrize("key", DEAL_KEYS)
def test_risks_carry_severity_and_blocking_survives(responses, key):
    payload = responses[key]
    comparison = REFERENCE_DEALS[key].compare()
    engine_blocking = {
        (r.result.key.value, f.code)
        for r in comparison.ranked
        for f in r.result.risks
        if f.severity is RiskSeverity.BLOCKING
    }
    api_blocking = {
        (e["key"], f["code"])
        for e in payload["ranked"]
        for f in e["risks"]
        if f["severity"] == "BLOCKING"
    }
    assert api_blocking == engine_blocking
    for entry in payload["ranked"]:
        for flag in entry["risks"]:
            assert flag["severity"] in {"BLOCKING", "HIGH", "MEDIUM", "LOW"}
            assert flag["code"] and flag["message"]


def test_the_data_centre_credit_gate_reaches_the_client(responses):
    """No §48E on a powered shell, so two structures must be disqualified."""
    payload = responses["data_center_powered_shell"]
    disqualified = {
        e["key"] for e in payload["ranked"] if not e["feasible"]
    }
    assert {"direct_transfer", "t_flip"} <= disqualified
    assert payload["tax"]["credit_value"] == 0.0
    reasons = {d["key"]: d["reason"] for d in payload["why_this_wins"]["disqualified"]}
    assert set(reasons) >= {"direct_transfer", "t_flip"}
    assert all(reasons.values())


# ---------------------------------------------------------------------------
# Rule 4 — capital account breaches
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", DEAL_KEYS)
def test_capital_account_breaches_field_is_always_present(responses, key):
    assert isinstance(responses[key]["capital_account_breaches"], list)


def test_capital_account_breaches_are_reported_when_they_occur():
    """An off-calibration override drives §704(b) accounts below their floor."""
    payload = run_compare(
        {
            "deal_key": "storage_bess_contracted",
            "overrides": {
                "capex": 200_000_000,
                "technology": "SOLAR",
                "begin_construction_date": "2026-08-01",
                "placed_in_service_date": "2029-01-01",
            },
        }
    )
    breaches = payload["capital_account_breaches"]
    assert breaches, "expected the off-calibration case to breach"
    for breach in breaches:
        assert breach["structure"]
        assert breach["partner"]
        assert breach["periods"]
        assert breach["cause"]
        assert breach["worst_breach"] is not None


# ---------------------------------------------------------------------------
# Valid JSON, always
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", DEAL_KEYS)
def test_response_is_strictly_valid_json(responses, key):
    text = json.dumps(responses[key], allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text
    json.loads(text)


def test_sanitise_removes_non_finite_floats_and_reports_the_path():
    found: list[str] = []
    cleaned = sanitise(
        {"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": -math.inf}, "e": 2.5},
        found=found,
    )
    assert cleaned == {"a": None, "b": [1.0, None], "c": {"d": None}, "e": 2.5}
    assert sorted(found) == ["$.a", "$.b[1]", "$.c.d"]
    json.dumps(cleaned, allow_nan=False)


def test_off_calibration_runs_are_still_valid_json():
    for overrides in (
        {"capex": 1_000.0},
        {"capex": 5e9},
        {"target_dscr": 5.0, "interest_rate": 0.5},
        {"interest_rate": 0.0, "tenor_years": 1.0},
        {"project_life_years": 50.0, "contract_years": 0.0},
        {"technology": "DATA_CENTER", "macr_ratio": 0.0},
        {"technology": "WIND", "begin_construction_date": "2026-12-31"},
    ):
        payload = run_compare({"overrides": overrides})
        json.dumps(payload, allow_nan=False)


# ---------------------------------------------------------------------------
# The two GET endpoints
# ---------------------------------------------------------------------------


def test_reference_deals_payload():
    payload = run_reference_deals()
    assert {d["key"] for d in payload["deals"]} == set(DEAL_KEYS)
    for deal in payload["deals"]:
        assert {"key", "name", "summary", "capex", "technology", "dscr_benchmark"} <= set(
            deal
        )
        assert deal["capex"] > 0
        assert deal["dscr_benchmark"]
    json.dumps(payload, allow_nan=False)


def test_current_law_payload():
    payload = run_current_law()
    assert payload["law_verified_on"] == "2026-08-06"
    assert len(payload["citations"]) == len(get_all_citations())
    for citation in payload["citations"]:
        assert {
            "id",
            "authority",
            "summary",
            "source",
            "verified_on",
            "confidence",
        } <= set(citation)
        assert citation["confidence"] in {"HIGH", "MEDIUM", "PLACEHOLDER"}
    # Honest gaps are a deliverable, not an apology.
    assert payload["unverified"]
    for item in payload["unverified"]:
        assert item["item"] and item["detail"] and item["impact"]
    litigation = payload["litigation"]
    assert litigation["case"].startswith("Oregon Environmental Council v. IRS")
    assert litigation["decided"] == "2026-06-06"
    assert litigation["toggle_values"] == ["vacated", "reinstated_on_appeal"]
    json.dumps(payload, allow_nan=False)


def test_confidence_map_covers_every_engine_level():
    assert set(CONFIDENCE_TO_CONTRACT) == set(Confidence)
    assert set(CONFIDENCE_TO_CONTRACT.values()) == {"HIGH", "MEDIUM", "PLACEHOLDER"}
