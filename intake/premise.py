"""Premise checks — things worth saying before a model runs.

A user who types an off-market assumption should be told so before they see
five structures priced off it. Every advisory carries a citation; an advisory
that cannot cite anything does not belong here.

Severity has three levels and they mean different things:

``blocking``
    The project as described cannot get the treatment it assumes. Running the
    model without changing something produces a number for a deal that does
    not exist.
``caution``
    The assumption is unusual rather than impossible. The model runs.
``note``
    Something favourable or clarifying the user may not have priced in.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from comps.bands import BY_KEY

Severity = Literal["blocking", "caution", "note"]

#: OBBBA (P.L. 119-21) begin-construction deadline for wind and solar.
BEGIN_CONSTRUCTION_DEADLINE = dt.date(2026, 7, 4)
#: Wind and solar that missed the deadline must be placed in service by this
#: date to keep the credit.
PLACED_IN_SERVICE_BACKSTOP = dt.date(2027, 12, 31)

OBBBA = "One Big Beautiful Bill Act (P.L. 119-21)"
OBBBA_URL = "https://www.congress.gov/bill/119th-congress/house-bill/1"

NRF_HEDGES = "Norton Rose Fulbright, 'Lending to hedged wind and solar projects'"
NRF_HEDGES_URL = (
    "https://www.projectfinance.law/publications/2020/february/"
    "lending-to-hedged-wind-and-solar-projects"
)


@dataclass(frozen=True, slots=True)
class Advisory:
    id: str
    severity: Severity
    message: str
    source: str
    source_url: str
    source_date: dt.date | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
            "source_url": self.source_url,
            "source_date": self.source_date.isoformat() if self.source_date else None,
        }


WIND_SOLAR = {"SOLAR", "SOLAR_PLUS_STORAGE", "WIND"}


def check(spec, *, today: dt.date | None = None) -> tuple[Advisory, ...]:
    """Run every premise check against a deal spec."""
    today = today or dt.date.today()
    out: list[Advisory] = []

    _begin_construction(spec, today, out)
    _ercot_hedges(spec, out)
    _ticket_size(spec, out)
    _storage_runway(spec, out)
    _merchant(spec, out)

    order = {"blocking": 0, "caution": 1, "note": 2}
    return tuple(sorted(out, key=lambda a: (order[a.severity], a.id)))


def _begin_construction(spec, today: dt.date, out: list[Advisory]) -> None:
    if spec.asset_type not in WIND_SOLAR:
        return
    if today <= BEGIN_CONSTRUCTION_DEADLINE:
        return
    cod = spec.cod_date()
    if cod is not None and cod <= PLACED_IN_SERVICE_BACKSTOP:
        out.append(
            Advisory(
                id="begin-construction-backstop",
                severity="caution",
                message=(
                    f"The begin-construction deadline of "
                    f"{BEGIN_CONSTRUCTION_DEADLINE:%-d %B %Y} has passed. This "
                    f"project keeps the credit only on the placed-in-service "
                    f"backstop, which requires commercial operation by "
                    f"{PLACED_IN_SERVICE_BACKSTOP:%-d %B %Y}. The stated COD of "
                    f"{cod:%B %Y} clears it, but there is no schedule slack."
                ),
                source=OBBBA,
                source_url=OBBBA_URL,
            )
        )
        return
    out.append(
        Advisory(
            id="begin-construction-cliff",
            severity="blocking",
            message=(
                f"Wind and solar had to begin construction by "
                f"{BEGIN_CONSTRUCTION_DEADLINE:%-d %B %Y}, or be placed in "
                f"service by {PLACED_IN_SERVICE_BACKSTOP:%-d %B %Y}, to qualify. "
                f"A project starting now with a "
                f"{'COD of ' + format(cod, '%B %Y') if cod else 'later COD'} "
                "meets neither test, so it has no §48E or §45Y credit. Model it "
                "with no credit, or evidence an earlier construction start."
            ),
            source=OBBBA,
            source_url=OBBBA_URL,
        )
    )


def _ercot_hedges(spec, out: list[Advisory]) -> None:
    if spec.state.upper() != "TX":
        return
    if spec.contract.kind != "PPA":
        return
    if (spec.contract.tenor_years or 0) < 10:
        return
    out.append(
        Advisory(
            id="ercot-hedge-market",
            severity="caution",
            message=(
                f"A {spec.contract.tenor_years:g}-year physical PPA is unusual "
                "in ERCOT. Roughly two-thirds of installed ERCOT capacity is "
                "contracted through bank hedges rather than PPAs, because PPA "
                "supply never kept pace with development. A hedge changes the "
                "revenue shape a lender will size against: fixed volume at a "
                "strike, with generation sold merchant alongside. Consider "
                "modelling a hedge, and note the source predates the current "
                "market."
            ),
            source=NRF_HEDGES,
            source_url=NRF_HEDGES_URL,
            source_date=dt.date(2020, 2, 1),
        )
    )


def _ticket_size(spec, out: list[Advisory]) -> None:
    if spec.capex is None:
        return
    floor = BY_KEY["ticket.lender_final_hold_floor"]
    if spec.capex < floor.low:
        out.append(
            Advisory(
                id="below-lender-hold-floor",
                severity="caution",
                message=(
                    f"At ${spec.capex / 1e6:,.0f}m this sits below the "
                    f"${floor.low / 1e6:,.0f}m final hold a project-finance "
                    "lender will typically justify. Expect a club of smaller "
                    "lenders, a green bank, or a portfolio facility rather than "
                    "a syndicated project financing."
                ),
                source=floor.source,
                source_url=floor.source_url,
                source_date=floor.source_date,
            )
        )
        return
    te = BY_KEY["ticket.tax_equity_minimum"]
    if spec.capex < te.low:
        out.append(
            Advisory(
                id="below-tax-equity-minimum",
                severity="caution",
                message=(
                    f"At ${spec.capex / 1e6:,.0f}m of capital cost, eligible "
                    f"basis is likely below the ${te.low / 1e6:,.0f}m minimum "
                    "ticket a tax equity investor will underwrite. A direct "
                    "credit transfer is the realistic monetisation route."
                ),
                source=te.source,
                source_url=te.source_url,
                source_date=te.source_date,
            )
        )


def _storage_runway(spec, out: list[Advisory]) -> None:
    if spec.asset_type != "STORAGE":
        return
    out.append(
        Advisory(
            id="storage-credit-runway",
            severity="note",
            message=(
                "Standalone storage keeps §48E on a begin-construction basis "
                "through 2033, so it is not exposed to the wind and solar "
                "deadline. That runway is the main reason storage structuring "
                "options are wider than solar's right now."
            ),
            source=OBBBA,
            source_url=OBBBA_URL,
        )
    )


def _merchant(spec, out: list[Advisory]) -> None:
    if spec.contract.kind != "MERCHANT":
        return
    out.append(
        Advisory(
            id="merchant-share-cap",
            severity="caution",
            message=(
                "Fully merchant revenue will not support a conventional "
                "project financing. Lenders cap merchant exposure at roughly "
                "25% to 40% of revenue and size the rest to a contracted "
                "profile at a materially higher coverage ratio."
            ),
            source="Norton Rose Fulbright, 'Cost of Capital: 2026 Outlook'",
            source_url=(
                "https://www.projectfinance.law/publications/"
                "cost-of-capital-2026-outlook"
            ),
            source_date=dt.date(2026, 1, 29),
        )
    )
