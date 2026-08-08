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
    from engine.structures.models import PROJECT_STRUCTURES

    renewable = [s for s in table.structures if s in PROJECT_STRUCTURES]
    if not renewable:
        return {}

    project, debt, tax = engine_inputs(resolution)
    if tax is None:
        return {}

    try:
        ranked = compare_structures(project, debt, tax).ranked
    except Exception:  # noqa: BLE001 - reported as absent, not as zeros
        return {}

    out: dict[str, Any] = {}
    for entry in ranked:
        if entry.result.key not in renewable or not entry.result.feasible:
            continue
        out[entry.result.key.value] = party_view(entry.result).to_dict()
    return out


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
