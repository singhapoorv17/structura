"""The API mapping layer: validation, guardrails and override application.

Nothing here starts a server. The endpoint modules are pure functions wrapped in
a thin HTTP shell (``tests/test_api_handlers.py`` covers the shell), so the
mapping is tested by calling it.
"""

from __future__ import annotations

from datetime import date

import pytest

from engine.defaults import Technology as EngineTechnology
from engine.tax import Technology as TaxTechnology
from engine.tax.enums import Notice202542Status
from lib_api.build import (
    DEFAULT_DEAL_KEY,
    TECHNOLOGY_MAP,
    apply_overrides,
    deal_keys,
    resolve_deal,
)
from lib_api.errors import ApiError
from lib_api.validate import (
    ALLOWED_OVERRIDES,
    MAX_PERIODS,
    MAX_PROJECT_LIFE_YEARS,
    parse_request,
)

KEYS = deal_keys()


def _parse(body):
    return parse_request(body, valid_deal_keys=KEYS)


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def test_empty_body_is_valid_and_defaults_the_deal():
    request = _parse({})
    assert request.deal_key is None
    assert request.overrides == {}
    deal, warnings = resolve_deal(request.deal_key)
    assert deal.key == DEFAULT_DEAL_KEY
    assert any("no 'deal_key' was supplied" in w for w in warnings)


def test_none_body_is_treated_as_empty():
    assert _parse(None).overrides == {}


@pytest.mark.parametrize("body", [[1, 2], "hello", 7, True])
def test_non_object_body_is_rejected(body):
    with pytest.raises(ApiError) as exc:
        _parse(body)
    assert exc.value.status == 400


def test_unknown_deal_key_names_the_field():
    with pytest.raises(ApiError) as exc:
        _parse({"deal_key": "not_a_deal"})
    assert exc.value.field == "deal_key"
    assert exc.value.status == 400


def test_unknown_override_is_a_warning_not_an_error():
    request = _parse({"overrides": {"moon_phase": 3}})
    assert request.overrides == {}
    assert any("moon_phase" in w for w in request.warnings)


def test_unknown_top_level_key_is_a_warning():
    request = _parse({"deal_key": KEYS[0], "colour": "blue"})
    assert any("colour" in w for w in request.warnings)


def test_explicit_null_override_leaves_the_base_deal_alone():
    assert _parse({"overrides": {"capex": None}}).overrides == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("capex", "lots"),
        ("capex", True),
        ("opex_year1", [1]),
        ("target_dscr", 0.5),
        ("interest_rate", 9.0),
        ("interest_rate", float("nan")),
        ("tenor_years", 0.0),
        ("domestic_content_pct", 1.5),
        ("macr_ratio", -0.1),
        ("bonus_rate", 2.0),
        ("technology", "FUSION"),
        ("technology", 3),
        ("notice_2025_42_status", "appealed"),
        ("is_pwa_compliant", "yes"),
        ("energy_community", 1),
        ("begin_construction_date", "01/03/2026"),
        ("begin_construction_date", 20260301),
        ("placed_in_service_date", "1066-10-14"),
        ("project_life_years", 500.0),
        ("production_p50", 0.0),
    ],
)
def test_bad_values_produce_a_400_naming_the_field(field, value):
    with pytest.raises(ApiError) as exc:
        _parse({"overrides": {field: value}})
    assert exc.value.status == 400
    assert exc.value.field == field
    assert field in exc.value.message


def test_contract_years_cannot_exceed_project_life():
    with pytest.raises(ApiError) as exc:
        _parse({"overrides": {"contract_years": 40, "project_life_years": 20}})
    assert exc.value.field == "contract_years"


def test_tenor_cannot_exceed_project_life():
    with pytest.raises(ApiError) as exc:
        _parse({"overrides": {"tenor_years": 30, "project_life_years": 20}})
    assert exc.value.field == "tenor_years"


def test_placed_in_service_cannot_precede_begin_construction():
    with pytest.raises(ApiError) as exc:
        _parse(
            {
                "overrides": {
                    "begin_construction_date": "2026-03-01",
                    "placed_in_service_date": "2025-01-01",
                }
            }
        )
    assert exc.value.field == "placed_in_service_date"


def test_structure_is_validated_against_the_five_keys():
    assert _parse({"structure": "t_flip"}).structure == "t_flip"
    with pytest.raises(ApiError) as exc:
        _parse({"structure": "yieldco"})
    assert exc.value.field == "structure"


def test_every_contract_override_field_is_accepted():
    """The frozen contract's override block, field by field."""
    body = {
        "capex": 140_000_000,
        "opex_year1": 3_500_000,
        "production_p50": 200_000,
        "contracted_price": 95.0,
        "contract_years": 15,
        "project_life_years": 20,
        "target_dscr": 1.20,
        "interest_rate": 0.062,
        "tenor_years": 18,
        "technology": "STORAGE",
        "begin_construction_date": "2026-03-01",
        "placed_in_service_date": "2027-01-01",
        "is_pwa_compliant": True,
        "domestic_content_pct": 0.55,
        "energy_community": False,
        "macr_ratio": 0.80,
        "bonus_rate": 0.0,
        "notice_2025_42_status": "vacated",
    }
    assert set(body) == set(ALLOWED_OVERRIDES)
    request = _parse({"deal_key": "storage_bess_contracted", "overrides": body})
    assert set(request.overrides) == set(body)
    assert request.warnings == []


# ---------------------------------------------------------------------------
# Override application
# ---------------------------------------------------------------------------


def test_overrides_actually_reach_the_engine_inputs():
    deal, _ = resolve_deal("storage_bess_contracted")
    updated, warnings = apply_overrides(
        deal,
        _parse(
            {
                "overrides": {
                    "capex": 175_000_000,
                    "opex_year1": 4_100_000,
                    "production_p50": 2.0,
                    "contracted_price": 16_400_000,
                    "contract_years": 12,
                    "project_life_years": 22,
                    "target_dscr": 1.45,
                    "interest_rate": 0.0625,
                    "tenor_years": 14,
                    "is_pwa_compliant": False,
                    "domestic_content_pct": 0.6,
                    "energy_community": True,
                    "macr_ratio": 0.65,
                    "bonus_rate": 1.0,
                    "notice_2025_42_status": "reinstated_on_appeal",
                    "begin_construction_date": "2026-02-02",
                    "placed_in_service_date": "2027-06-01",
                }
            }
        ).overrides,
    )
    assert updated.project.capex == 175_000_000
    assert updated.tax_project.capex == 175_000_000
    assert updated.project.opex_year1 == 4_100_000
    assert updated.project.production_p50 == 2.0
    assert updated.project.contracted_price == 16_400_000
    assert updated.project.contract_years == 12
    assert updated.project.project_life_years == 22
    assert updated.debt_terms.target_dscr == 1.45
    assert updated.debt_terms.interest_rate == 0.0625
    assert updated.debt_terms.tenor_years == 14
    assert updated.tax_project.is_pwa_compliant is False
    assert updated.tax_project.domestic_content_pct == 0.6
    assert updated.tax_project.energy_community is True
    assert updated.tax_project.macr_inputs.asserted_ratio == 0.65
    assert updated.tax_scenario.bonus_rate == 1.0
    assert (
        updated.tax_scenario.notice_2025_42_status
        is Notice202542Status.REINSTATED_ON_APPEAL
    )
    assert updated.tax_project.begin_construction_date == date(2026, 2, 2)
    assert updated.tax_project.placed_in_service_date == date(2027, 6, 1)
    # COD and placed-in-service are the same event; both move together.
    assert updated.project.cod_date == date(2027, 6, 1)
    # The base deal is frozen and untouched.
    assert deal.project.capex == 140_000_000.0
    assert any("NOT re-solved" in w for w in warnings)


def test_no_overrides_returns_the_deal_unchanged_with_no_warnings():
    deal, _ = resolve_deal("solar_safe_harboured")
    updated, warnings = apply_overrides(deal, {})
    assert updated is deal
    assert warnings == []


@pytest.mark.parametrize("name,expected", sorted(TECHNOLOGY_MAP.items()))
def test_technology_override_maps_engine_and_tax_tags(name, expected):
    engine_tech, tax_tech, credit_eligible = expected
    deal, _ = resolve_deal("storage_bess_contracted")
    updated, warnings = apply_overrides(deal, {"technology": name})
    assert updated.project.technology is engine_tech
    assert updated.tax_project.technology is tax_tech
    if credit_eligible:
        assert updated.tax_project.eligible_basis is None
    else:
        # A powered shell is not §48E property. Expressed as a nil basis, not
        # as a missing technology tag.
        assert updated.tax_project.eligible_basis == 0.0
        assert any("credit gate" in w for w in warnings)
    assert isinstance(engine_tech, EngineTechnology)
    assert isinstance(tax_tech, TaxTechnology)


def test_period_guardrail_is_enforced():
    """The DoS fence: nobody gets to ask for a thousand-period run."""
    assert MAX_PROJECT_LIFE_YEARS * 1 <= MAX_PERIODS
    with pytest.raises(ApiError) as exc:
        _parse({"overrides": {"project_life_years": MAX_PROJECT_LIFE_YEARS + 1}})
    assert exc.value.field == "project_life_years"
