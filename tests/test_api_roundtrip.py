"""The inputs /api/reference-deals publishes must be valid /api/compare overrides.

This is the contract the UI depends on: it seeds its form from the published
inputs and posts them straight back as overrides. If the two schemas drift the
landing page breaks — or, worse, silently computes a different deal.

Both failures have actually happened:
  1. The UI seeded from a hand-written mock and posted those values to the live
     engine, so the page displayed an uncalibrated deal (29.71% sponsor IRR
     against the calibrated 14.85%).
  2. The fix for (1) published `technology` as the lowercase enum value while
     the validator requires the uppercase token, so every request 400'd.

Neither was caught by unit tests, because each half was individually correct.
Only the round-trip catches it.
"""

from __future__ import annotations

import pytest

from lib_api.service import run_compare, run_reference_deals


def _deals():
    return run_reference_deals()["deals"]


def test_every_reference_deal_publishes_its_inputs():
    deals = _deals()
    assert deals, "no reference deals published"
    for d in deals:
        assert "inputs" in d and d["inputs"], f"{d['key']} publishes no inputs"


@pytest.mark.parametrize("key", [d["key"] for d in _deals()])
def test_published_inputs_are_accepted_as_overrides(key):
    """Post the published inputs straight back, exactly as the UI does."""
    published = {d["key"]: d for d in _deals()}[key]["inputs"]
    result = run_compare({"deal_key": key, "overrides": published})
    body = result[1] if isinstance(result, tuple) else result
    assert "error" not in body, f"{key}: round-trip rejected — {body.get('error')}"
    assert body.get("ranked"), f"{key}: no ranked structures returned"


@pytest.mark.parametrize("key", [d["key"] for d in _deals()])
def test_round_trip_reproduces_the_calibrated_result(key):
    """Seeding from published inputs must give the SAME answer as the bare deal.

    This is the assertion that would have caught the uncalibrated landing page:
    if the published inputs are not the deal's real inputs, the two runs
    diverge.
    """
    bare = run_compare({"deal_key": key})
    bare = bare[1] if isinstance(bare, tuple) else bare

    published = {d["key"]: d for d in _deals()}[key]["inputs"]
    seeded = run_compare({"deal_key": key, "overrides": published})
    seeded = seeded[1] if isinstance(seeded, tuple) else seeded

    bare_top, seeded_top = bare["ranked"][0], seeded["ranked"][0]
    assert bare_top["key"] == seeded_top["key"], (
        f"{key}: seeding from published inputs changed the winner "
        f"({bare_top['key']} → {seeded_top['key']}) — the published inputs are "
        f"not the deal's real inputs"
    )

    a, b = bare_top.get("sponsor_after_tax_irr"), seeded_top.get("sponsor_after_tax_irr")
    if a is not None and b is not None:
        assert abs(a - b) < 1e-9, (
            f"{key}: winner IRR differs between the bare deal and the "
            f"published-inputs round-trip ({a:.6%} vs {b:.6%})"
        )


def test_technology_token_matches_the_validator_vocabulary():
    """Regression: the published token must be the UPPERCASE form."""
    allowed = {"STORAGE", "SOLAR", "WIND", "DATA_CENTER"}
    for d in _deals():
        tech = d["inputs"].get("technology")
        assert tech in allowed, (
            f"{d['key']}: technology '{tech}' is not one of {sorted(allowed)} — "
            "the override validator will reject it"
        )
