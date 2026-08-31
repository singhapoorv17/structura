"""The analysis service: a six-field deal in, the whole picture out.

One request runs the entire flow — resolve, match comparables, screen and rank
structures, compare them, break the economics out by party, and draw the
chart — because splitting it across calls would make the screens disagree with
each other whenever an input changed.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from chart import chart_for
from comps.matcher import match
from comps.schema import Technology
from compare import build_comparison
from intake import DealSpec, resolve
from parties import party_view
from recommend import SponsorPriority

__all__ = ["run_analyse", "run_chat", "run_library"]

MAX_COMPS = 6


def _spec(body: Any) -> DealSpec:
    if not isinstance(body, dict):
        raise ValueError("expected a JSON object")
    if not body.get("asset_type"):
        raise ValueError("asset_type is required")
    return DealSpec.from_dict(body)


def _priority(body: Any) -> SponsorPriority:
    raw = (body or {}).get("priority") or SponsorPriority.MAX_IRR.value
    try:
        return SponsorPriority(raw)
    except ValueError as exc:
        raise ValueError(
            f"unknown priority {raw!r}; expected one of "
            + ", ".join(p.value for p in SponsorPriority)
        ) from exc


def run_analyse(body: Any) -> dict:
    spec = _spec(body)
    priority = _priority(body)
    today = dt.date.today()

    resolution = resolve(spec, today=today)
    table = build_comparison(resolution, priority=priority, today=today)

    comps = match(
        technology=Technology(spec.asset_type),
        total_quantum=_capex(resolution),
        contract_kind=spec.contract.kind,
        state=spec.state or None,
        limit=MAX_COMPS,
    )

    parties = _parties(resolution, table, today)
    charts = {
        entry.structure.value: chart_for(entry.structure).to_svg()
        for entry in table.recommendation.ranked
        if entry.feasible
    }

    return {
        "deal": resolution.to_dict(),
        "comparables": comps.to_dict(),
        "comparison": table.to_dict(),
        "parties": parties,
        "charts": charts,
    }


def _capex(resolution) -> float | None:
    cell = resolution.inputs.get("capex")
    value = cell.value if cell else None
    return float(value) if isinstance(value, (int, float)) else None


def _parties(resolution, table, today) -> dict[str, Any]:
    """Per-party ledgers for each feasible structure that produced a result."""
    from compare.build import engine_inputs
    from engine.structures import compare_structures
    from engine.structures.models import PROJECT_STRUCTURES, StructureKey

    out: dict[str, Any] = {}

    # The lease carries every counterparty inside the model, so its ledgers are
    # the most complete set the tool produces. They were being discarded.
    from compare.lease import build_lease, build_securitised
    from engine.structures import run_equipment_lease

    for _key, _builder in (
        (StructureKey.EQUIPMENT_LEASE, build_lease),
        (StructureKey.SECURITISED_LEASE, build_securitised),
    ):
        if _key not in table.structures:
            continue
        config = _builder(resolution)
        if config is not None:
            try:
                result = run_equipment_lease(config)
                out[_key.value] = {
                    "structure": _key.value,
                    "total_capital": config.sources,
                    "ledgers": [
                        {
                            "party": entry.party,
                            "role": entry.role,
                            "years": list(range(len(entry.cashflow))),
                            "cashflow": list(entry.cashflow),
                            "trace": "EquipmentLeaseResult ledger",
                            "capital_account": None,
                            "outside_basis": None,
                            "components": {},
                            "metrics": _lease_party_metrics(entry, config),
                        }
                        for entry in result.ledgers
                    ],
                    "conservation": [
                        f"period {i}: {net:,.2f}"
                        for i, net in enumerate(result.reconciliation())
                        if abs(net) > 1e-3
                    ],
                    "guarantee": result.guarantee_asymmetry(),
                }
            except Exception:  # noqa: BLE001 - absent beats wrong
                pass

    renewable = [s for s in table.structures if s in PROJECT_STRUCTURES]
    if not renewable:
        return out

    project, debt, tax = engine_inputs(resolution)
    if tax is None:
        return out

    try:
        ranked = compare_structures(project, debt, tax).ranked
    except Exception:  # noqa: BLE001 - reported as absent, not as zeros
        return out

    for entry in ranked:
        if entry.result.key not in renewable or not entry.result.feasible:
            continue
        out[entry.result.key.value] = party_view(entry.result).to_dict()
    return out


def _lease_party_metrics(entry, config) -> dict[str, Any]:
    """Return metrics for one lease party, refusing a rate it cannot support."""
    from engine.metrics import irr as _irr

    invested = -sum(c for c in entry.cashflow if c < 0)
    returned = sum(c for c in entry.cashflow if c > 0)
    if invested <= 1e-6:
        return {
            "irr": None,
            "moic": None,
            "payback_year": None,
            "not_meaningful_reason": (
                "This party puts in no capital, so a rate has no base."
            ),
        }
    signs = [c for c in entry.cashflow if abs(c) > 1e-6]
    changes = sum(1 for a, b in zip(signs, signs[1:]) if a * b < 0)
    if signs and signs[0] > 0:
        return {
            "irr": None,
            "moic": round(returned / invested, 4),
            "payback_year": None,
            "not_meaningful_reason": (
                "The first period is a net inflow, so there is no investment "
                "for a rate to measure."
            ),
        }
    if changes > 1:
        return {
            "irr": None,
            "moic": round(returned / invested, 4),
            "payback_year": None,
            "not_meaningful_reason": (
                f"The cash flow changes sign {changes} times, so an IRR is not "
                "uniquely defined."
            ),
        }
    try:
        rate = _irr(list(entry.cashflow))
    except Exception:  # noqa: BLE001 - an unsolvable rate is a result
        rate = None
    return {
        "irr": rate,
        "moic": round(returned / invested, 4),
        "payback_year": None,
        "not_meaningful_reason": (
            ""
            if rate is not None
            else "No rate solves this cash flow, so none is reported."
        ),
    }


def run_chat(body: Any) -> dict:
    from chat import ask

    if not isinstance(body, dict):
        raise ValueError("expected a JSON object")
    spec = _spec(body.get("deal") or {})
    text = (body.get("message") or "").strip()
    turn = ask(spec, text, today=dt.date.today())
    payload = turn.to_dict()
    payload["deal"] = (turn.spec or spec).to_dict()
    return payload


def run_library() -> dict:
    """The corpus, for the transaction library screen."""
    from comps.corpus import load
    from comps.matcher import vintage

    records = []
    for record in load():
        records.append(
            {
                "key": record.key,
                "name": record.name,
                "technology": record.technology.value,
                "family": record.technology.family,
                "headline": record.headline,
                "summary": record.summary,
                "primary_source": record.primary_source,
                "vintage": vintage(record),
                "disclosure": record.disclosure_profile(),
                "lenders": list(record.lenders),
                "fields": {
                    name: cell.to_dict()
                    for name, cell in record.provenanced_cells()
                },
            }
        )
    records.sort(key=lambda r: (-(r["vintage"] or 0), r["name"]))
    return {"count": len(records), "deals": records}
