"""Feasibility gates — the hard reasons a structure is off the table.

A gate is not a score. It answers one question with a yes or a no, names the
fact that decided it, and cites where that fact comes from. A structure that
fails a gate is shown to the reader with the reason attached rather than
quietly dropped, because "why can't I do a flip here" is usually the most
useful thing on the screen.

Gates run here rather than inside the structure modules on purpose. A rule
that matters this much should not depend on one module remembering to check
it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable

from comps.bands import BY_KEY
from engine.structures.models import PROJECT_STRUCTURES, StructureKey
from recommend.labels import asset_label, asset_phrase
from intake.premise import (
    BEGIN_CONSTRUCTION_DEADLINE,
    OBBBA,
    OBBBA_URL,
    PLACED_IN_SERVICE_BACKSTOP,
)

__all__ = ["Gate", "GateVerdict", "SponsorPriority", "evaluate_gates"]

EQUIPMENT_LEASE = StructureKey.EQUIPMENT_LEASE

#: Structures whose economics run through a tax equity investor. Below the
#: minimum ticket there is no counterparty, whatever the arithmetic says.
TAX_EQUITY_DEPENDENT = (
    StructureKey.PARTNERSHIP_FLIP,
    StructureKey.T_FLIP,
    StructureKey.PREFERRED_EQUITY,
)

#: Technologies that generate no §48E or §45Y credit at all.
NO_CREDIT_TECHNOLOGIES = {"DATA_CENTRE", "AI_COMPUTE", "TRANSMISSION", "GAS"}

#: Technologies financed as equipment bought by a vehicle rather than a plant
#: built by a sponsor.
EQUIPMENT_TECHNOLOGIES = {"AI_COMPUTE"}

WIND_SOLAR = {"SOLAR", "SOLAR_PLUS_STORAGE", "WIND"}


class SponsorPriority(str, Enum):
    """What the sponsor is optimising. It changes the ranking, and we say so."""

    MAX_IRR = "max_irr"
    MAX_NEAR_TERM_CASH = "max_near_term_cash"
    MIN_EXECUTION_RISK = "min_execution_risk"
    MAX_PROCEEDS_AT_CLOSE = "max_proceeds_at_close"

    @property
    def label(self) -> str:
        return {
            SponsorPriority.MAX_IRR: "maximise sponsor IRR",
            SponsorPriority.MAX_NEAR_TERM_CASH: "maximise near-term cash",
            SponsorPriority.MIN_EXECUTION_RISK: "minimise execution risk",
            SponsorPriority.MAX_PROCEEDS_AT_CLOSE: "maximise proceeds at close",
        }[self]


@dataclass(frozen=True, slots=True)
class GateVerdict:
    gate_id: str
    structure: StructureKey
    passed: bool
    fact: str
    source: str
    source_url: str
    source_date: dt.date | None = None

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id,
            "structure": self.structure.value,
            "passed": self.passed,
            "fact": self.fact,
            "source": self.source,
            "source_url": self.source_url,
            "source_date": self.source_date.isoformat() if self.source_date else None,
        }


@dataclass(frozen=True, slots=True)
class Gate:
    id: str
    label: str
    applies_to: tuple[StructureKey, ...]
    rule: Callable[..., tuple[bool, str] | None]


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def _no_credit_technology(resolution, today):
    asset = resolution.spec.asset_type
    if asset not in NO_CREDIT_TECHNOLOGIES:
        return None
    return False, (
        f"{asset_phrase(asset)} generates no §48E or §45Y credit, so there is "
        "nothing for a tax equity investor or a credit transferee to buy."
    )


def _begin_construction(resolution, today):
    spec = resolution.spec
    if spec.asset_type not in WIND_SOLAR:
        return None
    if today <= BEGIN_CONSTRUCTION_DEADLINE:
        return None
    cod = spec.cod_date()
    if cod is not None and cod <= PLACED_IN_SERVICE_BACKSTOP:
        return None
    return False, (
        f"Construction did not begin by {BEGIN_CONSTRUCTION_DEADLINE:%-d %B %Y} "
        f"and the stated COD of "
        f"{format(cod, '%B %Y') if cod else 'this project'} misses the "
        f"{PLACED_IN_SERVICE_BACKSTOP:%-d %B %Y} placed-in-service backstop, so "
        "the project has no credit to monetise."
    )


def _tax_equity_minimum(resolution, today):
    capex = _capex(resolution)
    if capex is None:
        return None
    band = BY_KEY["ticket.tax_equity_minimum"]
    if capex >= band.low:
        return None
    return False, (
        f"At ${capex / 1e6:,.0f}m of capital cost, eligible basis sits below "
        f"the ${band.low / 1e6:,.0f}m minimum ticket a tax equity investor "
        "will underwrite, so there is no counterparty for this structure at "
        "this size."
    )


def _equipment_only(resolution, today):
    asset = resolution.spec.asset_type
    if asset in EQUIPMENT_TECHNOLOGIES:
        return None
    return False, (
        "An equipment lease finances equipment bought by a third-party vehicle "
        f"and leased to an operator. {asset_phrase(asset)} is built by its "
        "sponsor, so the structure does not apply."
    )


def _project_structures_need_a_project(resolution, today):
    asset = resolution.spec.asset_type
    if asset not in EQUIPMENT_TECHNOLOGIES:
        return None
    return False, (
        "This is an equipment financing rather than a project financing. The "
        "renewable capital structures assume a sponsor-built plant with "
        "project-level debt, which this is not."
    )


GATES: tuple[Gate, ...] = (
    Gate(
        id="no-credit-technology",
        label="Technology generates a credit",
        applies_to=(
            StructureKey.DIRECT_TRANSFER,
            StructureKey.T_FLIP,
            StructureKey.PARTNERSHIP_FLIP,
            StructureKey.SALE_LEASEBACK,
        ),
        rule=_no_credit_technology,
    ),
    Gate(
        id="begin-construction",
        label="Credit survives the OBBBA deadline",
        applies_to=(StructureKey.DIRECT_TRANSFER, StructureKey.T_FLIP),
        rule=_begin_construction,
    ),
    Gate(
        id="tax-equity-minimum-ticket",
        label="Deal clears the tax equity minimum",
        applies_to=TAX_EQUITY_DEPENDENT,
        rule=_tax_equity_minimum,
    ),
    Gate(
        id="equipment-lease-applicability",
        label="Asset is leasable equipment",
        applies_to=(EQUIPMENT_LEASE,),
        rule=_equipment_only,
    ),
    Gate(
        id="project-structure-applicability",
        label="Asset is a sponsor-built project",
        applies_to=PROJECT_STRUCTURES,
        rule=_project_structures_need_a_project,
    ),
)

#: Where each gate's fact comes from.
SOURCES: dict[str, tuple[str, str, dt.date | None]] = {
    "no-credit-technology": (OBBBA, OBBBA_URL, None),
    "begin-construction": (OBBBA, OBBBA_URL, None),
    "tax-equity-minimum-ticket": (
        BY_KEY["ticket.tax_equity_minimum"].source,
        BY_KEY["ticket.tax_equity_minimum"].source_url,
        BY_KEY["ticket.tax_equity_minimum"].source_date,
    ),
    "equipment-lease-applicability": (
        "Structural: the vehicle buys the asset rather than the sponsor building it",
        "urn:structura:structural-rule",
        None,
    ),
    "project-structure-applicability": (
        "Structural: project structures assume a sponsor-built plant",
        "urn:structura:structural-rule",
        None,
    ),
}


def _capex(resolution) -> float | None:
    cell = resolution.inputs.get("capex")
    value = cell.value if cell is not None else None
    return float(value) if isinstance(value, (int, float)) else None


def evaluate_gates(
    resolution,
    *,
    structures: Iterable[StructureKey] | None = None,
    today: dt.date | None = None,
) -> dict[StructureKey, tuple[GateVerdict, ...]]:
    """Run every applicable gate against every structure.

    Returns the failures per structure. A structure with no entry passed
    everything.
    """
    today = today or dt.date.today()
    keys = tuple(structures) if structures else tuple(StructureKey)
    out: dict[StructureKey, list[GateVerdict]] = {k: [] for k in keys}

    for gate in GATES:
        verdict = gate.rule(resolution, today)
        if verdict is None:
            continue
        passed, fact = verdict
        if passed:
            continue
        source, url, date = SOURCES[gate.id]
        for key in gate.applies_to:
            if key not in out:
                continue
            out[key].append(
                GateVerdict(
                    gate_id=gate.id,
                    structure=key,
                    passed=False,
                    fact=fact,
                    source=source,
                    source_url=url,
                    source_date=date,
                )
            )

    return {k: tuple(v) for k, v in out.items()}
