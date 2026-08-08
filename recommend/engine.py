"""Rank the feasible structures, and say why in this deal's own terms.

Deterministic. No model call, no hidden weights: the priority the sponsor
selects picks which qualitative dimensions carry weight, the weights are
published here, and the rationale is assembled from facts about this project
rather than from generic prose about what a flip is.

The ranking this produces is structural. It says which structures suit this
sponsor's stated objective given what the deal is. The quantitative comparison
refines it, and where the two disagree the numbers win — the response says so
rather than presenting a structural ordering as if it were an IRR ranking.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from engine.structures.models import StructureKey
from recommend.characteristics import DIMENSIONS, BY_STRUCTURE, Cell
from recommend.gates import GateVerdict, SponsorPriority, evaluate_gates
from recommend.labels import asset_label, asset_phrase

__all__ = ["Recommendation", "RankedStructure", "recommend"]

#: Which dimensions matter under each objective, and how much. Published rather
#: than buried: a reader who disagrees with the weighting can see it and say so.
WEIGHTS: dict[SponsorPriority, dict[str, float]] = {
    SponsorPriority.MAX_IRR: {
        "optionality": 2.0,
        "covenant_burden": 1.0,
        "exit_flexibility": 1.5,
        "tax_law_sensitivity": 0.5,
    },
    SponsorPriority.MAX_NEAR_TERM_CASH: {
        "time_to_close": 2.5,
        "execution_complexity": 1.5,
        "counterparty_depth": 1.5,
    },
    SponsorPriority.MIN_EXECUTION_RISK: {
        "execution_complexity": 2.5,
        "documentation_burden": 1.5,
        "recapture_exposure": 2.0,
        "tax_law_sensitivity": 2.0,
        "counterparty_depth": 1.0,
    },
    SponsorPriority.MAX_PROCEEDS_AT_CLOSE: {
        "counterparty_depth": 2.0,
        "time_to_close": 2.0,
        "accounting_treatment": 1.0,
        "execution_complexity": 1.0,
    },
}


@dataclass(frozen=True, slots=True)
class RankedStructure:
    structure: StructureKey
    feasible: bool
    score: float
    gates_failed: tuple[GateVerdict, ...] = ()
    drivers: tuple[Cell, ...] = ()

    @property
    def blocking_reason(self) -> str:
        if self.feasible:
            return ""
        return " ".join(v.fact for v in self.gates_failed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "structure": self.structure.value,
            "label": self.structure.label,
            "feasible": self.feasible,
            "score": round(self.score, 3),
            "gates_failed": [v.to_dict() for v in self.gates_failed],
            "drivers": [c.to_dict() for c in self.drivers],
            "blocking_reason": self.blocking_reason,
        }


@dataclass(frozen=True, slots=True)
class Recommendation:
    priority: SponsorPriority
    ranked: tuple[RankedStructure, ...]
    rationale: str
    facts_used: tuple[str, ...] = field(default_factory=tuple)

    @property
    def leader(self) -> RankedStructure | None:
        for entry in self.ranked:
            if entry.feasible:
                return entry
        return None

    @property
    def feasible(self) -> tuple[RankedStructure, ...]:
        return tuple(e for e in self.ranked if e.feasible)

    @property
    def infeasible(self) -> tuple[RankedStructure, ...]:
        return tuple(e for e in self.ranked if not e.feasible)

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority": self.priority.value,
            "priority_label": self.priority.label,
            "ranked": [e.to_dict() for e in self.ranked],
            "rationale": self.rationale,
            "facts_used": list(self.facts_used),
        }


def recommend(
    resolution,
    *,
    priority: SponsorPriority = SponsorPriority.MAX_IRR,
    today: dt.date | None = None,
) -> Recommendation:
    """Screen, rank, and explain."""
    gates = evaluate_gates(resolution, today=today)
    weights = WEIGHTS[priority]

    entries: list[RankedStructure] = []
    for key, failures in gates.items():
        cells = BY_STRUCTURE.get(key, {})
        score = sum(cells[d].rating * w for d, w in weights.items() if d in cells)
        drivers = tuple(
            sorted(
                (cells[d] for d in weights if d in cells),
                key=lambda c: -c.rating * weights[c.dimension],
            )[:3]
        )
        entries.append(
            RankedStructure(
                structure=key,
                feasible=not failures,
                score=score,
                gates_failed=failures,
                drivers=drivers,
            )
        )

    entries.sort(key=lambda e: (not e.feasible, -e.score, e.structure.value))
    ranked = tuple(entries)
    facts = _facts(resolution)
    return Recommendation(
        priority=priority,
        ranked=ranked,
        rationale=_rationale(resolution, ranked, priority, facts),
        facts_used=facts,
    )


# ---------------------------------------------------------------------------


#: Structure names as they read inside a sentence. Lower-casing the display
#: label turns "SPV" into "spv", so the mid-sentence form is written out.
STRUCTURE_IN_SENTENCE: dict[StructureKey, str] = {
    StructureKey.PARTNERSHIP_FLIP: "a partnership flip",
    StructureKey.T_FLIP: "a T-flip, pairing a flip with a §6418 transfer",
    StructureKey.PREFERRED_EQUITY: "a preferred equity partnership",
    StructureKey.DIRECT_TRANSFER: "a direct §6418 credit transfer",
    StructureKey.SALE_LEASEBACK: "a sale-leaseback",
    StructureKey.EQUIPMENT_LEASE: (
        "an equipment lease through an owning SPV, with a residual value guarantee"
    ),
}


def _in_sentence(key: StructureKey) -> str:
    return STRUCTURE_IN_SENTENCE.get(key, key.label)


def _facts(resolution) -> tuple[str, ...]:
    """The project's own facts, phrased for use in a sentence."""
    spec = resolution.spec
    out: list[str] = []
    asset = asset_label(spec.asset_type)
    mw = spec.capacity_mw()
    if mw:
        out.append(f"a {mw:,.0f} MW {asset} project")
    else:
        out.append(asset_phrase(spec.asset_type).lower().replace("an ", "an ").replace("a ", "a ", 1))
    if spec.state:
        out.append(f"in {spec.state}")
    cell = resolution.inputs.get("capex")
    if cell is not None and isinstance(cell.value, (int, float)):
        out.append(f"at roughly ${cell.value / 1e6:,.0f}m of capital cost")
    cod = spec.cod_date()
    if cod:
        out.append(f"targeting commercial operation in {cod:%B %Y}")
    # Duration is only meaningful where the megawatt figure is the storage
    # inverter rating. On a solar-plus-storage project the quoted MWac is the
    # solar side, so dividing by it produces a duration the project does not
    # have.
    if spec.asset_type == "STORAGE":
        hours = spec.storage_hours()
        if hours:
            out.append(f"with {hours:.1f} hours of storage")
    elif spec.energy_mwh():
        out.append(f"paired with {spec.energy_mwh():,.0f} MWh of storage")
    return tuple(out)


def _rationale(resolution, ranked, priority, facts) -> str:
    """Assemble the explanation from this deal, not from a template about flips."""
    leader = next((e for e in ranked if e.feasible), None)
    blocked = [e for e in ranked if not e.feasible]
    subject = " ".join(facts) if facts else "this project"

    if leader is None:
        reasons = "; ".join(sorted({e.blocking_reason for e in blocked}))
        return (
            f"No structure in the set is available for {subject}. {reasons}"
        )

    lines = [
        f"For {subject}, optimising to {priority.label}, the leading "
        f"structure is {_in_sentence(leader.structure)}."
    ]
    if leader.drivers:
        driver = leader.drivers[0]
        lines.append(driver.reason)

    runners = [e for e in ranked if e.feasible and e is not leader][:2]
    if runners:
        names = " and ".join(_in_sentence(e.structure) for e in runners)
        lines.append(f"{names} remain available and are compared alongside it.")

    if blocked:
        first = blocked[0]
        lines.append(
            f"{first.structure.label} is not available here: {first.blocking_reason}"
        )
        if len(blocked) > 1:
            lines.append(
                f"{len(blocked) - 1} further "
                f"{'structure is' if len(blocked) == 2 else 'structures are'} "
                "ruled out, each with the rule that blocked it."
            )

    lines.append(
        "This ordering is structural. The quantitative comparison refines it, "
        "and where the two disagree the numbers govern."
    )
    return " ".join(lines)
