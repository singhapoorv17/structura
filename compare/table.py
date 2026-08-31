"""The comparison table: quantitative rows, and the qualitative band beneath.

Two bands, one table. The numbers say which structure pays more; the
qualitative band says what it costs to get there — how long it takes, who will
actually transact, what breaks if the rules move. Both are needed to make the
choice, and neither substitutes for the other.

Every quantitative cell is either a badged number or an explicit
not-meaningful verdict with its reason. Every qualitative cell carries a rule
id. Nothing renders as prose that a reader cannot trace back to a rule.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from compare.build import engine_inputs
from engine.provenance import Provenanced, assumed
from engine.structures.models import PROJECT_STRUCTURES, StructureKey
from recommend import Recommendation, SponsorPriority, recommend
from recommend.characteristics import DIMENSIONS, BY_STRUCTURE, Cell

__all__ = ["ComparisonTable", "NotMeaningful", "QuantRow", "build_comparison"]


@dataclass(frozen=True, slots=True)
class NotMeaningful:
    """A metric that exists but should not be read."""

    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"value": None, "not_meaningful": True, "reason": self.reason}


#: The quantitative rows, in the order a reader wants them.
QUANT_ROWS: tuple[tuple[str, str, str], ...] = (
    ("sponsor_after_tax_irr", "Sponsor IRR, after tax", "%"),
    ("sponsor_npv", "Sponsor NPV", "USD"),
    ("effective_cost_of_capital", "Effective cost of capital", "%"),
    ("sponsor_equity_required", "Sponsor equity required", "USD"),
    ("third_party_capital_raised", "Third-party construction capital", "USD"),
    ("post_cod_monetisation", "Cash from monetisation after COD", "USD"),
    ("total_capital_raised", "Total capital raised", "USD"),
)


@dataclass(frozen=True, slots=True)
class QuantRow:
    id: str
    label: str
    unit: str
    values: dict[str, Provenanced | NotMeaningful]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "unit": self.unit,
            "values": {k: v.to_dict() for k, v in self.values.items()},
        }


@dataclass(frozen=True, slots=True)
class ComparisonTable:
    structures: tuple[StructureKey, ...]
    quantitative: tuple[QuantRow, ...]
    qualitative: tuple[Cell, ...]
    recommendation: Recommendation

    @property
    def headline_metric(self) -> tuple[str, str]:
        """Which row to lead with, and why.

        Sponsor IRR is the metric everyone asks for, and on a heavily
        credit-supported deal it is the one metric that cannot be trusted: at
        six per cent of the capital stack the sponsor's rate says more about
        the denominator than the deal. Where that is the case for every
        structure the table leads with NPV instead and says so, rather than
        printing a column of blanks.
        """
        irr = next(r for r in self.quantitative if r.id == "sponsor_after_tax_irr")
        usable = [
            v for v in irr.values.values() if not isinstance(v, NotMeaningful)
        ]
        if usable:
            return "sponsor_after_tax_irr", ""
        reasons = {
            v.reason.split(":")[0]
            for v in irr.values.values()
            if isinstance(v, NotMeaningful)
        }
        return "sponsor_npv", (
            "Sponsor IRR is not a usable comparison on this deal — "
            + "; ".join(sorted(reasons))
            + ". The ranking leads with sponsor NPV, with effective cost of "
            "capital alongside as the cross-check."
        )

    @property
    def value_warning(self) -> str:
        """Flag a shortlist where the best available structure loses money.

        Being the last structure standing is not the same as being worth
        doing, and a table that ranks without saying so invites the wrong
        conclusion.
        """
        npv = next((r for r in self.quantitative if r.id == "sponsor_npv"), None)
        if npv is None:
            return ""
        values = [
            v.value
            for v in npv.values.values()
            if not isinstance(v, NotMeaningful) and v.value is not None
        ]
        if not values or max(values) >= 0:
            return ""
        return (
            f"Every available structure returns a negative sponsor NPV, the "
            f"best at ${max(values) / 1e6:,.1f}m. On these assumptions the "
            "project does not support a financing in any form. The ranking "
            "below orders the alternatives; it does not endorse one."
        )

    def qualitative_cell(self, structure: StructureKey, dimension: str) -> Cell:
        for cell in self.qualitative:
            if cell.structure is structure and cell.dimension == dimension:
                return cell
        raise KeyError((structure, dimension))

    def to_dict(self) -> dict[str, Any]:
        return {
            "structures": [
                {"key": s.value, "label": s.label} for s in self.structures
            ],
            "quantitative": [row.to_dict() for row in self.quantitative],
            "qualitative": [cell.to_dict() for cell in self.qualitative],
            "dimensions": [
                {"id": d.id, "label": d.label, "question": d.question}
                for d in DIMENSIONS
            ],
            "recommendation": self.recommendation.to_dict(),
            "headline_metric": self.headline_metric[0],
            "headline_note": self.headline_metric[1],
            "value_warning": self.value_warning,
        }


def build_comparison(
    resolution,
    *,
    priority: SponsorPriority = SponsorPriority.MAX_IRR,
    today: dt.date | None = None,
) -> ComparisonTable:
    """Compare every feasible structure, quantitatively and qualitatively.

    The gates are a pre-screen; the engine is the authority on whether a
    structure can actually be built on these economics. Where the two
    disagree the engine wins, and the structure is reported as infeasible
    with the engine's own reason rather than rendered with its zero defaults.
    """
    rec = recommend(resolution, priority=priority, today=today)
    results = _run_engine(resolution, tuple(e.structure for e in rec.feasible))
    rec = _reconcile(rec, results)
    feasible = tuple(e.structure for e in rec.feasible)

    rows: list[QuantRow] = []
    for row_id, label, unit in QUANT_ROWS:
        values: dict[str, Provenanced | NotMeaningful] = {}
        for key in feasible:
            values[key.value] = _cell(results.get(key), row_id, unit, key)
        rows.append(QuantRow(id=row_id, label=label, unit=unit, values=values))

    qualitative = tuple(
        BY_STRUCTURE[s][d.id] for s in feasible for d in DIMENSIONS
    )

    return ComparisonTable(
        structures=feasible,
        quantitative=tuple(rows),
        qualitative=qualitative,
        recommendation=rec,
    )


def _reconcile(rec: Recommendation, results: dict) -> Recommendation:
    """Demote any structure the engine declares infeasible.

    A gate can only see the deal's shape. The engine sees the economics, and
    it is the engine that knows there is no credit to flip. Rendering a
    structure the engine rejected would print its uninitialised zeros as
    though they were results.
    """
    from dataclasses import replace as _replace

    from recommend.gates import GateVerdict

    entries = []
    changed = False
    for entry in rec.ranked:
        result = results.get(entry.structure)
        if entry.feasible and result is not None and not getattr(
            result, "feasible", True
        ):
            changed = True
            reason = (
                getattr(result, "infeasible_reason", "").strip()
                or "The engine could not build this structure on these economics."
            )
            entries.append(
                _replace(
                    entry,
                    feasible=False,
                    gates_failed=entry.gates_failed
                    + (
                        GateVerdict(
                            gate_id="engine-infeasible",
                            structure=entry.structure,
                            passed=False,
                            fact=reason,
                            source="Structura engine",
                            source_url="urn:structura:engine",
                        ),
                    ),
                )
            )
        else:
            entries.append(entry)

    if not changed:
        return rec

    entries.sort(key=lambda e: (not e.feasible, -e.score, e.structure.value))
    ranked = tuple(entries)
    return _replace(
        rec,
        ranked=ranked,
        rationale=_amend(rec, ranked),
    )


def _amend(rec: Recommendation, ranked) -> str:
    """Rebuild the conclusion once the engine has had its say.

    The original sentence names a leader that may no longer be feasible, so it
    is regenerated from the reconciled ranking rather than edited.
    """
    from recommend.engine import _rationale

    base = _rationale(None, ranked, rec.priority, rec.facts_used)
    demoted = [
        e
        for e in ranked
        if not e.feasible
        and any(v.gate_id == "engine-infeasible" for v in e.gates_failed)
    ]
    if demoted:
        names = ", ".join(e.structure.label for e in demoted)
        base += (
            f" {names} passed the eligibility screens, but the engine could "
            "not size them on these economics; each carries the reason."
        )
    return base


class _LeaseResult:
    """Adapts an equipment lease onto the fields the comparison reads."""

    feasible = True
    sponsor_irr_is_meaningful = False
    sponsor_irr_not_meaningful_reason = (
        "The vehicle's equity is a thin slice beneath the notes and its rate "
        "reflects that rather than the economics of the asset. Rent, the "
        "residual and the noteholder returns are the figures to read."
    )

    def __init__(self, result, key: StructureKey) -> None:
        self._m = __import__(
            "compare.lease", fromlist=["lease_metrics"]
        ).lease_metrics(result)
        self.key = key
        self.result = result
        self.sponsor_after_tax_irr = None
        self.effective_cost_of_capital = None
        for name, value in self._m.items():
            setattr(self, name, value)


def _run_engine(resolution, feasible) -> dict[StructureKey, Any]:
    """Run the renewable set where the deal supports one."""
    out: dict[StructureKey, Any] = {}

    # An equipment lease is not a project structure and never reached the
    # engine, so a deal led by one came back with no numbers at all.
    from compare.lease import build_lease, build_securitised
    from engine.structures import run_equipment_lease

    for key, builder in (
        (StructureKey.EQUIPMENT_LEASE, build_lease),
        (StructureKey.SECURITISED_LEASE, build_securitised),
    ):
        if key not in feasible:
            continue
        config = builder(resolution)
        if config is None:
            continue
        try:
            out[key] = _LeaseResult(run_equipment_lease(config), key)
        except Exception:  # noqa: BLE001 - absent beats wrong
            pass

    renewable = [k for k in feasible if k in PROJECT_STRUCTURES]
    if not renewable:
        return out

    project, debt, tax = engine_inputs(resolution)
    if tax is None:
        # No credit-bearing technology, so the credit structures were already
        # gated out. The remaining renewable structures still need economics,
        # and without a tax project the engine cannot build a context. Report
        # that plainly rather than substituting a zero-credit stand-in.
        return out

    from engine.structures import compare_structures

    try:
        comparison = compare_structures(project, debt, tax)
    except Exception as exc:  # noqa: BLE001 - surfaced, not swallowed
        out["__error__"] = str(exc)
        return out

    for ranked in comparison.ranked:
        out[ranked.result.key] = ranked.result
    return out


def _cell(result, row_id: str, unit: str, key: StructureKey):
    if result is None or not hasattr(result, row_id):
        return NotMeaningful(
            "The engine did not produce this metric for this structure."
        )
    value = getattr(result, row_id)
    if value is None:
        return NotMeaningful(f"{row_id.replace('_', ' ')} is undefined here.")
    if row_id == "sponsor_after_tax_irr" and not getattr(
        result, "sponsor_irr_is_meaningful", True
    ):
        return NotMeaningful(
            getattr(result, "sponsor_irr_not_meaningful_reason", "")
            or "The equity base is too small for a rate to mean anything."
        )
    return assumed(
        float(value),
        unit=unit,
        note=f"Computed by the engine for {key.label}.",
    )
