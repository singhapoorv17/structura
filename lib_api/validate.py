"""Request validation — types, ranges, and the guardrails that stop a DoS.

Two rules govern this module:

1. **Anything the caller can get wrong produces a 400 naming the field.** No
   silent coercion of a string into a float, no clamping a rate into range.
2. **Unknown override keys are a warning, not an error.** The frontend and the
   API are built in parallel against a frozen contract; rejecting an unexpected
   key would turn a cosmetic mismatch into a hard outage, while swallowing it
   silently would let a typo change nothing and look like it worked. So the key
   is ignored and the fact is carried into ``warnings`` where the contract
   guarantees it is displayed verbatim.

The range limits are deliberately wide. They exist to keep a hostile or
fat-fingered request from putting the solver into a thousand-period run inside a
300 s serverless function, not to express a view on what a sensible deal looks
like.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Mapping

from lib_api.errors import ApiError

__all__ = [
    "MAX_PROJECT_LIFE_YEARS",
    "MAX_PERIODS",
    "ALLOWED_OVERRIDES",
    "TECHNOLOGIES",
    "NOTICE_STATUSES",
    "parse_request",
    "ParsedRequest",
]

#: Hard ceilings. ``project_life_years`` x ``periods_per_year`` is the length of
#: every array the engine builds and the number of periods the sculpting solver
#: iterates, so it is the one input that turns a request into compute time.
MAX_PROJECT_LIFE_YEARS = 50.0
MAX_PERIODS = 200

#: US$5bn. Ten times the largest reference deal (a $480m data-centre shell) and
#: far above any single energy project this tool is aimed at — but chosen for a
#: second, harder reason. ``engine.structures.partnership`` asserts §704(b)
#: capital-account integrity against an **absolute** tolerance, and float64
#: rounding on a capital account of order 1e10 exceeds it. Above roughly $5bn
#: of capex the engine therefore raises its own integrity assertion, which is
#: the engine being right about its precision rather than wrong about the deal.
#: Capping here turns that into a clean 400 instead of a 500.
MAX_CAPEX = 5e9
MAX_CONSTRUCTION_MONTHS = 120

TECHNOLOGIES = ("STORAGE", "SOLAR", "WIND", "DATA_CENTER")
NOTICE_STATUSES = ("vacated", "reinstated_on_appeal")

#: name -> (kind, low, high). ``kind`` is one of "number", "int", "bool",
#: "date", "enum". Bounds are inclusive. This table IS the contract's override
#: block; adding a field here without adding it to ``build.py`` is caught by
#: ``tests/test_api_mapping.py``.
ALLOWED_OVERRIDES: Mapping[str, tuple] = {
    "capex": ("number", 1_000.0, MAX_CAPEX),
    "opex_year1": ("number", 0.0, MAX_CAPEX),
    "production_p50": ("number", 1e-9, 1e9),
    "contracted_price": ("number", 0.0, 1e9),
    "contract_years": ("number", 0.0, MAX_PROJECT_LIFE_YEARS),
    "project_life_years": ("number", 1.0, MAX_PROJECT_LIFE_YEARS),
    "target_dscr": ("number", 1.0, 5.0),
    "interest_rate": ("number", 0.0, 0.5),
    "tenor_years": ("number", 1.0, MAX_PROJECT_LIFE_YEARS),
    "technology": ("enum", TECHNOLOGIES, None),
    "begin_construction_date": ("date", date(2000, 1, 1), date(2100, 1, 1)),
    "placed_in_service_date": ("date", date(2000, 1, 1), date(2100, 1, 1)),
    "is_pwa_compliant": ("bool", None, None),
    "domestic_content_pct": ("number", 0.0, 1.0),
    "energy_community": ("bool", None, None),
    "macr_ratio": ("number", 0.0, 1.0),
    "bonus_rate": ("number", 0.0, 1.0),
    "notice_2025_42_status": ("enum", NOTICE_STATUSES, None),
}

#: Accepted alongside ``deal_key`` and ``overrides``. ``structure`` is
#: ``/api/export`` only; it is tolerated on ``/api/compare`` so a frontend can
#: post one body to both endpoints.
TOP_LEVEL_KEYS = ("deal_key", "overrides", "structure")

STRUCTURE_KEYS = (
    "partnership_flip",
    "t_flip",
    "preferred_equity",
    "direct_transfer",
    "sale_leaseback",
)


class ParsedRequest:
    """A validated request body. Plain object so it serialises trivially in logs."""

    __slots__ = ("deal_key", "overrides", "structure", "warnings")

    def __init__(
        self,
        deal_key: str | None,
        overrides: dict[str, Any],
        structure: str | None,
        warnings: list[str],
    ) -> None:
        self.deal_key = deal_key
        self.overrides = overrides
        self.structure = structure
        self.warnings = warnings

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"ParsedRequest(deal_key={self.deal_key!r}, "
            f"overrides={sorted(self.overrides)}, structure={self.structure!r})"
        )


def _number(name: str, raw: Any, low: float, high: float) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ApiError(
            f"'{name}' must be a number, got {type(raw).__name__}.", field=name
        )
    value = float(raw)
    if not math.isfinite(value):
        raise ApiError(f"'{name}' must be a finite number.", field=name)
    if value < low or value > high:
        raise ApiError(
            f"'{name}' must be between {low:g} and {high:g}, got {value:g}.",
            field=name,
        )
    return value


def _bool(name: str, raw: Any) -> bool:
    if not isinstance(raw, bool):
        raise ApiError(
            f"'{name}' must be true or false, got {type(raw).__name__}.", field=name
        )
    return raw


def _date(name: str, raw: Any, low: date, high: date) -> date:
    if not isinstance(raw, str):
        raise ApiError(
            f"'{name}' must be an ISO date string 'YYYY-MM-DD'.", field=name
        )
    try:
        value = date.fromisoformat(raw)
    except ValueError as exc:
        raise ApiError(
            f"'{name}' is not a valid ISO date 'YYYY-MM-DD': {raw!r}.", field=name
        ) from exc
    if value < low or value > high:
        raise ApiError(
            f"'{name}' must fall between {low.isoformat()} and {high.isoformat()}.",
            field=name,
        )
    return value


def _enum(name: str, raw: Any, allowed: tuple[str, ...]) -> str:
    if not isinstance(raw, str):
        raise ApiError(
            f"'{name}' must be one of {', '.join(allowed)}.", field=name
        )
    if raw not in allowed:
        raise ApiError(
            f"'{name}' must be one of {', '.join(allowed)}, got {raw!r}.",
            field=name,
        )
    return raw


def parse_request(body: Any, *, valid_deal_keys: tuple[str, ...]) -> ParsedRequest:
    """Validate a decoded JSON body against the frozen contract.

    Returns
    -------
    ParsedRequest
        ``overrides`` holds only recognised keys, already coerced to the right
        Python type. ``warnings`` holds anything the caller should see about how
        their request was interpreted.
    """
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise ApiError("Request body must be a JSON object.")

    warnings: list[str] = []

    for key in body:
        if key not in TOP_LEVEL_KEYS:
            warnings.append(
                f"api: ignored unknown top-level field '{key}'. The contract "
                f"accepts {', '.join(TOP_LEVEL_KEYS)}."
            )

    deal_key = body.get("deal_key")
    if deal_key is not None:
        if not isinstance(deal_key, str):
            raise ApiError("'deal_key' must be a string.", field="deal_key")
        if deal_key not in valid_deal_keys:
            raise ApiError(
                f"No reference deal '{deal_key}'. Available: "
                + ", ".join(valid_deal_keys),
                field="deal_key",
            )

    structure = body.get("structure")
    if structure is not None:
        structure = _enum("structure", structure, STRUCTURE_KEYS)

    raw_overrides = body.get("overrides")
    if raw_overrides is None:
        raw_overrides = {}
    if not isinstance(raw_overrides, dict):
        raise ApiError("'overrides' must be a JSON object.", field="overrides")

    overrides: dict[str, Any] = {}
    for name, raw in raw_overrides.items():
        spec = ALLOWED_OVERRIDES.get(name)
        if spec is None:
            warnings.append(
                f"api: ignored unknown override field '{name}'. It changed "
                f"nothing in the run below."
            )
            continue
        if raw is None:
            # An explicit null means "leave the base deal alone". Accepting it
            # lets a frontend send a fixed-shape object with empty inputs.
            continue
        kind, low, high = spec
        if kind == "number":
            overrides[name] = _number(name, raw, low, high)
        elif kind == "bool":
            overrides[name] = _bool(name, raw)
        elif kind == "date":
            overrides[name] = _date(name, raw, low, high)
        elif kind == "enum":
            overrides[name] = _enum(name, raw, low)
        else:  # pragma: no cover - table is closed
            raise ApiError(f"Unsupported override kind for '{name}'.", field=name)

    _cross_field_checks(overrides)
    return ParsedRequest(deal_key, overrides, structure, warnings)


def _cross_field_checks(overrides: Mapping[str, Any]) -> None:
    """The checks that need two fields at once. Still 400s, still named."""
    life = overrides.get("project_life_years")
    if life is not None:
        if life > MAX_PROJECT_LIFE_YEARS:  # pragma: no cover - range covers it
            raise ApiError(
                f"'project_life_years' is capped at {MAX_PROJECT_LIFE_YEARS:g}.",
                field="project_life_years",
            )
        contract_years = overrides.get("contract_years")
        if contract_years is not None and contract_years > life:
            raise ApiError(
                f"'contract_years' ({contract_years:g}) cannot exceed "
                f"'project_life_years' ({life:g}).",
                field="contract_years",
            )
        tenor = overrides.get("tenor_years")
        if tenor is not None and tenor > life:
            raise ApiError(
                f"'tenor_years' ({tenor:g}) cannot exceed 'project_life_years' "
                f"({life:g}).",
                field="tenor_years",
            )

    boc = overrides.get("begin_construction_date")
    pis = overrides.get("placed_in_service_date")
    if boc is not None and pis is not None and pis < boc:
        raise ApiError(
            "'placed_in_service_date' cannot precede "
            "'begin_construction_date'.",
            field="placed_in_service_date",
        )
