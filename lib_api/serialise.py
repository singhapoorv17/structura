"""Engine objects -> the exact JSON in ``app/API_CONTRACT.md``.

Four rules are non-negotiable and each is asserted by ``tests/test_api_*.py``:

1. ``irr_is_meaningful`` comes from the engine's own guard
   (``StructureResult.sponsor_irr_is_meaningful``). When it is false the IRR is
   still emitted — the contract says so — carrying
   ``irr_not_meaningful_reason``. The UI leads with ``sponsor_npv`` instead.
2. **Every** warning reaches the response. Engine, tax, structure and reference
   deal warnings are concatenated, de-duplicated in first-seen order, and never
   filtered. A PLACEHOLDER warning that does not reach the screen is the exact
   failure mode SPEC §4.3 exists to prevent.
3. ``risks`` carry severity, and BLOCKING survives verbatim.
4. ``capital_account_breaches`` are first-class, not a footnote.

One documented divergence from the contract text: the contract enumerates
``severity: BLOCKING|HIGH|MEDIUM|LOW`` while the engine's
``RiskSeverity`` is ``BLOCKING|CAUTION|INFO``. ``severity`` carries the
contract's vocabulary so a strict client never sees an unknown value, and
``severity_engine`` carries the engine's own word so nothing is lost.

Non-finite floats (NaN, ±inf) can legitimately fall out of a ratio with a zero
denominator — an LLCR on a project with no debt, for example. JSON has no
representation for them and ``json.dumps`` emits bare ``NaN``, which is invalid
JSON and will throw in ``JSON.parse``. :func:`sanitise` replaces them with
``null`` and appends a warning naming the path, so the substitution is visible
rather than silent.
"""

from __future__ import annotations

import math
from dataclasses import fields, is_dataclass
from datetime import date
from enum import Enum
from typing import Any, Mapping, Sequence

from engine.reference_deals import ReferenceDeal
from engine.structures.models import RiskSeverity
from engine.structures.selector import StructureComparison
from engine.tax import LAW_VERIFIED_ON
from engine.tax.citations import get_all_citations, get_citation, unverified_citations
from engine.tax.enums import Confidence, Notice202542Status

__all__ = [
    "sanitise",
    "comparison_to_dict",
    "reference_deals_payload",
    "current_law_payload",
    "SEVERITY_TO_CONTRACT",
    "CONFIDENCE_TO_CONTRACT",
]

#: engine RiskSeverity -> the contract's vocabulary.
SEVERITY_TO_CONTRACT: Mapping[RiskSeverity, str] = {
    RiskSeverity.BLOCKING: "BLOCKING",
    RiskSeverity.CAUTION: "MEDIUM",
    RiskSeverity.INFO: "LOW",
}

#: engine Confidence -> the contract's ``HIGH|MEDIUM|PLACEHOLDER``.
CONFIDENCE_TO_CONTRACT: Mapping[Confidence, str] = {
    Confidence.VERIFIED: "HIGH",
    Confidence.PROVISIONAL: "MEDIUM",
    Confidence.PLACEHOLDER: "PLACEHOLDER",
}


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _num(value: Any) -> float | None:
    """A float the JSON encoder can emit, or ``None``."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None
    return out if math.isfinite(out) else None


def _text(value: Any) -> str | None:
    """Empty string means "nothing to say"; the contract wants ``null``."""
    if value is None:
        return None
    text = str(value)
    return text or None


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _plain(value: Any) -> Any:
    """Best-effort conversion of any engine object into JSON-safe data."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, Sequence):
        return [_plain(v) for v in value]
    return str(value)


def sanitise(payload: Any, *, path: str = "$", found: list[str] | None = None) -> Any:
    """Replace every non-finite float with ``None``, recording where.

    The API never emits ``NaN`` or ``Infinity``: both are invalid JSON and both
    crash a browser's ``JSON.parse``.
    """
    if found is None:
        found = []
    if isinstance(payload, float):
        if math.isfinite(payload):
            return payload
        found.append(path)
        return None
    if isinstance(payload, dict):
        return {
            k: sanitise(v, path=f"{path}.{k}", found=found) for k, v in payload.items()
        }
    if isinstance(payload, (list, tuple)):
        return [
            sanitise(v, path=f"{path}[{i}]", found=found)
            for i, v in enumerate(payload)
        ]
    return payload


# ---------------------------------------------------------------------------
# /api/compare
# ---------------------------------------------------------------------------


def _risk(flag) -> dict:
    return {
        "code": flag.code,
        "severity": SEVERITY_TO_CONTRACT.get(flag.severity, "MEDIUM"),
        "severity_engine": _enum_value(flag.severity),
        "message": flag.summary,
        "detail": flag.detail,
        "citation_ids": list(flag.citation_ids),
    }


def _ranked_entry(entry) -> dict:
    r = entry.result
    timing = r.cash_timing
    return {
        "rank": entry.rank,
        "key": r.key.value,
        "label": r.label,
        "feasible": bool(r.feasible),
        "infeasible_reason": _text(r.infeasible_reason),
        "sponsor_after_tax_irr": _num(r.sponsor_after_tax_irr),
        # Straight from the engine's meaningfulness guard - never recomputed.
        "irr_is_meaningful": bool(r.sponsor_irr_is_meaningful),
        "irr_not_meaningful_reason": _text(r.sponsor_irr_not_meaningful_reason),
        "sponsor_npv": _num(r.sponsor_npv),
        "effective_cost_of_capital": _num(r.effective_cost_of_capital),
        "sponsor_equity_required": _num(r.sponsor_equity_required),
        "third_party_capital_raised": _num(r.third_party_capital_raised),
        "total_capital_raised": _num(r.total_capital_raised),
        "flip_year": _num(r.flip_year),
        "credit_transferred": _num(r.credit_transferred),
        "credit_retained": _num(r.credit_retained),
        "cash_timing": (
            None
            if timing is None
            else {
                "cash_weighted_average_years": _num(timing.weighted_average_years),
                "share_by_year_5": _num(timing.share_received_by_year_5),
            }
        ),
        "risks": [_risk(f) for f in r.risks],
        "warnings": list(r.warnings),
        "rank_basis": entry.rank_basis,
    }


def _why(comparison: StructureComparison) -> dict | None:
    why = comparison.why_this_wins
    if why is None:
        return None
    return {
        "winner": why.winner.value,
        "primary_metric": why.primary_metric,
        "winner_value": _num(why.winner_value),
        "runner_up": why.runner_up.value if why.runner_up is not None else None,
        "runner_up_value": _num(why.runner_up_value),
        "margin": _num(why.margin),
        "drivers": [
            {
                "name": d.name,
                "unit": d.unit,
                "winner_value": _num(d.winner_value),
                "runner_up_value": _num(d.runner_up_value),
                "delta": _num(d.delta),
                "higher_is_better": bool(d.higher_is_better),
                "note": d.note,
            }
            for d in why.drivers
        ],
        "disqualified": [
            {"key": key.value, "reason": reason} for key, reason in why.disqualified
        ],
        "tie_breaks": list(why.tie_breaks),
        "caveats": list(why.caveats),
    }


def _sources_and_uses(comparison: StructureComparison) -> dict:
    """The winner's funding statement, or the context's if nothing is feasible."""
    source = None
    for entry in comparison.ranked:
        if entry.result.feasible and entry.result.sources_and_uses is not None:
            source = entry.result
            break
    if source is None:
        econ = comparison.context.economics
        return {
            "funding_requirement": _num(econ.total_project_cost),
            "debt": _num(econ.debt_at_cod),
            "third_party_equity": 0.0,
            "sponsor_equity": _num(econ.equity_at_cod),
            "post_cod_monetisation": 0.0,
            "structure": None,
            "balances": None,
        }
    s = source.sources_and_uses
    return {
        "funding_requirement": _num(s.uses_total),
        "debt": _num(s.senior_debt),
        "third_party_equity": _num(s.third_party_equity),
        "sponsor_equity": _num(s.sponsor_equity),
        "post_cod_monetisation": _num(s.post_cod_monetisation),
        "structure": source.key.value,
        "balances": bool(s.balances),
    }


def _debt_block(comparison: StructureComparison) -> dict:
    sizing = comparison.context.funding.sizing
    return {
        "quantum": _num(sizing.debt.debt_size),
        "gearing": _num(sizing.gearing),
        "min_dscr": _num(sizing.min_dscr),
        "binding_constraint": _enum_value(sizing.binding_constraint),
        "llcr": _num(sizing.llcr),
        "plcr": _num(sizing.plcr),
    }


def _tax_block(comparison: StructureComparison) -> dict:
    tax = comparison.context.tax
    credit = tax.credit
    warnings = [f"engine.tax: {w}" for w in credit.warnings]
    if tax.feoc.threshold_is_placeholder:
        warnings.append(
            "engine.tax: the Material Assistance Cost Ratio threshold applied "
            "to this project is a PLACEHOLDER - see engine/tax/UNVERIFIED.md "
            "item 1."
        )
    return {
        "credit_section": _enum_value(credit.credit_section),
        "credit_rate": _num(credit.final_rate),
        "credit_value": _num(credit.credit_amount),
        "eligibility_path": _enum_value(credit.path),
        "feoc_pass": bool(tax.feoc.passes),
        "adders": [
            _enum_value(a.adder) for a in credit.adders if a.granted
        ],
        "warnings": warnings,
        "eligible": bool(credit.eligible),
        "disqualification_reason": _text(credit.disqualification_reason),
        "begin_construction_established": bool(tax.begin_construction.established),
        "notice_2025_42_status": _enum_value(
            tax.scenario.notice_2025_42_status
        ),
    }


def _breach(structure_key, breach) -> dict:
    return {
        "structure": structure_key.value,
        "partner": _enum_value(getattr(breach, "partner", None)),
        "periods": _plain(getattr(breach, "periods", None)),
        "years": _plain(getattr(breach, "years", None)),
        "worst_breach": _num(getattr(breach, "worst_breach", None)),
        "worst_period": _plain(getattr(breach, "worst_period", None)),
        "worst_year": _plain(getattr(breach, "worst_year", None)),
        "cause": _text(getattr(breach, "cause", None)),
    }


def comparison_to_dict(
    comparison: StructureComparison,
    deal: ReferenceDeal,
    *,
    compute_ms: float,
    extra_warnings: Sequence[str] = (),
) -> dict:
    """Serialise a comparison into the frozen response shape.

    ``extra_warnings`` are the API-layer warnings (defaulted deal key, ignored
    override field, capital structure not re-solved). They lead the list because
    they change how everything below them should be read.
    """
    warnings: list[str] = []
    warnings.extend(extra_warnings)
    placeholders = deal.placeholder_assumptions()
    if placeholders:
        warnings.append(deal.placeholder_warning())
    # Engine, tax and per-structure warnings, exactly as the selector collected
    # them. Nothing is filtered.
    warnings.extend(comparison.warnings)
    for entry in comparison.ranked:
        warnings.extend(entry.result.warnings)
    for structure_key, detail in comparison.funding_failures:
        warnings.append(
            f"engine.structures[{structure_key.value}]: sources and uses do "
            f"not balance. {detail}"
        )

    payload = {
        "deal": {
            "key": deal.key,
            "name": deal.name,
            "summary": deal.summary,
            "capex": _num(deal.project.capex),
            "technology": _enum_value(deal.project.technology),
            "dscr_benchmark": deal.dscr_benchmark,
            "calibration_note": deal.calibration_note,
            "discount_rate": _num(deal.discount_rate),
        },
        "headline": comparison.headline,
        "law_verified_on": LAW_VERIFIED_ON.isoformat(),
        "ranked": [_ranked_entry(e) for e in comparison.ranked],
        "why_this_wins": _why(comparison),
        "sources_and_uses": _sources_and_uses(comparison),
        "debt": _debt_block(comparison),
        "tax": _tax_block(comparison),
        "capital_account_breaches": [
            _breach(k, b) for k, b in comparison.capital_account_breaches
        ],
        "warnings": list(dict.fromkeys(warnings)),
        "citation_ids": list(comparison.citation_ids),
        "compute_ms": round(float(compute_ms), 1),
    }

    found: list[str] = []
    payload = sanitise(payload, found=found)
    if found:
        payload["warnings"].append(
            "api: "
            + str(len(found))
            + " value(s) were not finite (a ratio with a zero denominator, "
            "typically an LLCR or PLCR on an unlevered case) and are reported "
            "as null rather than as invalid JSON: "
            + ", ".join(sorted(set(found))[:12])
        )
    return payload


# ---------------------------------------------------------------------------
# /api/reference-deals
# ---------------------------------------------------------------------------


def _deal_inputs(d: ReferenceDeal) -> dict:
    """The deal's ACTUAL calibrated inputs, in the /api/compare override schema.

    The UI seeds its form from this. Before this existed the frontend seeded
    from a hand-written mock, then posted those mock values as overrides to the
    live engine — so the landing page silently displayed an *uncalibrated*
    deal (a 29.71% sponsor IRR against the calibrated 14.85%). The form must be
    able to show the real numbers, so the API has to publish them.
    """
    p, t, tx = d.project, d.debt_terms, d.tax_project
    out = {
        "capex": _num(p.capex),
        "opex_year1": _num(p.opex_year1),
        "production_p50": _num(p.production_p50),
        "contracted_price": _num(p.contracted_price),
        "contract_years": _num(p.contract_years),
        "project_life_years": _num(p.project_life_years),
        "target_dscr": _num(t.target_dscr),
        "interest_rate": _num(t.interest_rate),
        "tenor_years": _num(t.tenor_years),
        "technology": _enum_value(tx.technology),
        "is_pwa_compliant": bool(getattr(tx, "is_pwa_compliant", False)),
    }
    for src, key in (
        ("begin_construction_date", "begin_construction_date"),
        ("placed_in_service_date", "placed_in_service_date"),
    ):
        v = getattr(tx, src, None)
        out[key] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def reference_deals_payload(deals: Mapping[str, ReferenceDeal]) -> dict:
    return {
        "deals": [
            {
                "key": d.key,
                "name": d.name,
                "summary": d.summary,
                "capex": _num(d.project.capex),
                "technology": _enum_value(d.project.technology),
                "dscr_benchmark": d.dscr_benchmark,
                "calibration_note": d.calibration_note,
                "placeholder_count": len(d.placeholder_assumptions()),
                "inputs": _deal_inputs(d),
            }
            for d in deals.values()
        ],
        "law_verified_on": LAW_VERIFIED_ON.isoformat(),
    }


# ---------------------------------------------------------------------------
# /api/current-law
# ---------------------------------------------------------------------------

#: The one live case in the rulebook. Every field is read off the citation of
#: the same name rather than restated here, so the page cannot drift from the
#: registry the engine actually applies.
_LITIGATION_CITATION_ID = "oregon-environmental-council-vacatur"


def current_law_payload() -> dict:
    citations = get_all_citations()
    case = get_citation(_LITIGATION_CITATION_ID)
    return {
        "law_verified_on": LAW_VERIFIED_ON.isoformat(),
        "citations": [
            {
                "id": c.id,
                "authority": c.authority,
                "title": c.title,
                "summary": c.plain_english,
                "source": c.source,
                "verified_on": c.verified_on.isoformat(),
                "confidence": CONFIDENCE_TO_CONTRACT[c.confidence],
                "confidence_engine": _enum_value(c.confidence),
                "module": c.module,
                "note": _text(c.note),
            }
            for c in citations
        ],
        "unverified": [
            {
                "id": c.id,
                "item": c.title,
                "detail": c.note or c.source,
                "impact": (
                    f"Applied by engine/tax/{c.module}.py under {c.authority}. "
                    f"Confidence {CONFIDENCE_TO_CONTRACT[c.confidence]}; every "
                    f"run that touches this rule carries a warning."
                ),
                "confidence": CONFIDENCE_TO_CONTRACT[c.confidence],
            }
            for c in unverified_citations()
        ],
        "litigation": {
            "case": "Oregon Environmental Council v. IRS, No. 25-4400 (CKK)",
            "decided": "2026-06-06",
            "effect": "Notice 2025-42 vacated in full; 5% safe harbor restored",
            "status": "appeal expected",
            "toggle_values": [s.value for s in Notice202542Status],
            "citation_id": case.id,
            "authority": case.authority,
            "note": case.note,
        },
    }
