"""Record shape for the comparable-transactions corpus.

Two types live here and they are deliberately separate:

:class:`DealRecord`
    What a named transaction disclosed. Every cell is either a cited fact or an
    explicit "not disclosed". Nothing is inferred.
:class:`MarketBand`
    What the market prices for a shape of deal. Cited and dated, never attached
    to a named transaction.

Keeping them apart is the point. A reader who cannot tell which panel a number
came from cannot use either.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final, Iterator

from engine.provenance import Provenance, Provenanced, not_disclosed, stated

__all__ = [
    "LENGTH_CAPS",
    "ContractKind",
    "DealRecord",
    "MarketBand",
    "Technology",
    "Tranche",
    "cell_from_json",
]


#: Maximum stored length per string field. This is the structural guard against
#: keeping article bodies: the corpus stores extracted facts, and a fact does
#: not run to a paragraph. Exceeding a cap fails the acceptance suite.
LENGTH_CAPS: Final[dict[str, int]] = {
    "_default": 400,
    "headline": 200,
    "summary": 600,
}


class Technology(str, Enum):
    SOLAR = "SOLAR"
    SOLAR_PLUS_STORAGE = "SOLAR_PLUS_STORAGE"
    STORAGE = "STORAGE"
    WIND = "WIND"
    DATA_CENTRE = "DATA_CENTRE"
    AI_COMPUTE = "AI_COMPUTE"
    RNG = "RNG"
    GAS = "GAS"
    TRANSMISSION = "TRANSMISSION"
    PORTFOLIO = "PORTFOLIO"

    @property
    def family(self) -> str:
        """Technology family, for matching. Solar and solar+storage match."""
        if self in (Technology.SOLAR, Technology.SOLAR_PLUS_STORAGE):
            return "solar"
        if self in (Technology.DATA_CENTRE, Technology.AI_COMPUTE):
            return "digital"
        return self.value.lower()


class ContractKind(str, Enum):
    PPA = "PPA"
    TOLLING = "TOLLING"
    HEDGE = "HEDGE"
    HYPERSCALE_LEASE = "HYPERSCALE_LEASE"
    EQUIPMENT_LEASE = "EQUIPMENT_LEASE"
    MERCHANT = "MERCHANT"
    UNKNOWN = "UNKNOWN"


class TrancheKind(str, Enum):
    CONSTRUCTION_LOAN = "CONSTRUCTION_LOAN"
    CONSTRUCTION_TO_TERM = "CONSTRUCTION_TO_TERM"
    TERM_LOAN = "TERM_LOAN"
    TAX_EQUITY = "TAX_EQUITY"
    TAX_EQUITY_BRIDGE = "TAX_EQUITY_BRIDGE"
    TRANSFER_BRIDGE = "TRANSFER_BRIDGE"
    LETTER_OF_CREDIT = "LETTER_OF_CREDIT"
    REVOLVER = "REVOLVER"
    NOTES = "NOTES"
    PREFERRED = "PREFERRED"
    SPONSOR_EQUITY = "SPONSOR_EQUITY"


def cell_from_json(raw: Any, *, field_name: str) -> Provenanced:
    """Build a provenanced cell from its JSON form.

    A raw scalar is rejected outright. Every cell in the corpus declares where
    it came from, including when the answer is that the source did not say.
    """
    if not isinstance(raw, dict):
        raise ValueError(
            f"{field_name}: corpus cells must declare provenance, got {raw!r}"
        )
    provenance = Provenance(raw["provenance"])
    if provenance is Provenance.NOT_DISCLOSED:
        return not_disclosed(raw["reason"], unit=raw.get("unit", ""))
    if provenance is Provenance.STATED:
        return stated(
            raw["value"],
            source=raw["source"],
            source_url=raw.get("source_url"),
            source_date=_date(raw.get("source_date")),
            unit=raw.get("unit", ""),
            note=raw.get("note", ""),
            is_restatement=raw.get("is_restatement", False),
            echo_of=raw.get("echo_of"),
            source_date_unknown=raw.get("source_date_unknown", False),
        )
    raise ValueError(
        f"{field_name}: a deal record may only hold stated or not_disclosed "
        f"cells, got {provenance.value}. Market benchmarks belong in a "
        "MarketBand, not in a transaction."
    )


def _date(raw: str | None) -> dt.date | None:
    return dt.date.fromisoformat(raw) if raw else None


@dataclass(frozen=True, slots=True)
class Tranche:
    """One facility inside a financing."""

    name: str
    kind: TrancheKind
    amount: Provenanced
    pricing: Provenanced
    tenor_years: Provenanced
    note: str = ""

    def cells(self) -> Iterator[tuple[str, Provenanced]]:
        yield f"tranche[{self.name}].amount", self.amount
        yield f"tranche[{self.name}].pricing", self.pricing
        yield f"tranche[{self.name}].tenor_years", self.tenor_years


@dataclass(frozen=True, slots=True)
class DealRecord:
    """A named transaction, as far as public sources disclosed it."""

    key: str
    name: str
    technology: Technology
    sponsor: Provenanced
    total_quantum: Provenanced
    close_date: Provenanced
    cod: Provenanced
    location: Provenanced
    capacity: Provenanced
    contract_kind: ContractKind
    offtake: Provenanced
    lenders: tuple[str, ...]
    tranches: tuple[Tranche, ...]
    credit_route: Provenanced
    primary_source: str
    headline: str = ""
    summary: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    # -- introspection used by the acceptance suite ------------------------

    def provenanced_cells(self) -> Iterator[tuple[str, Provenanced]]:
        for name in (
            "sponsor",
            "total_quantum",
            "close_date",
            "cod",
            "location",
            "capacity",
            "offtake",
            "credit_route",
        ):
            yield name, getattr(self, name)
        for tranche in self.tranches:
            yield from tranche.cells()

    def flat_strings(self) -> Iterator[tuple[str, str]]:
        yield "headline", self.headline
        yield "summary", self.summary
        yield "name", self.name
        for name, cell in self.provenanced_cells():
            if isinstance(cell.value, str):
                yield name, cell.value
            if cell.note:
                yield f"{name}.note", cell.note
            if cell.reason:
                yield f"{name}.reason", cell.reason

    def capacity_mw(self) -> float | None:
        """Megawatts, parsed from the capacity string the source published.

        Sources write capacity as prose ("430 MWac solar with 340 MWh battery
        storage"), so the number has to be read back out. MWac is preferred
        over MWdc, and an energy-only figure returns nothing.
        """
        import re

        text = self.capacity.value
        if not isinstance(text, str):
            return None
        for pattern in (
            r"([\d,]+(?:\.\d+)?)\s*MWac",
            r"([\d,]+(?:\.\d+)?)\s*MW\b(?!h)",
            r"([\d,]+(?:\.\d+)?)\s*MWdc",
            r"([\d,]+(?:\.\d+)?)\s*GW\b",
        ):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                value = float(m.group(1).replace(",", ""))
                return value * 1000 if "GW" in pattern else value
        return None

    def disclosure_profile(self) -> dict[str, int]:
        """How much of this record is fact and how much the source withheld."""
        counts = {p.value: 0 for p in Provenance}
        for _, cell in self.provenanced_cells():
            counts[cell.provenance.value] += 1
        return counts


@dataclass(frozen=True, slots=True)
class MarketBand:
    """What the market prices for a shape of deal. Never deal-specific."""

    key: str
    label: str
    applies_to: tuple[str, ...]
    low: float
    high: float
    unit: str
    source: str
    source_url: str
    source_date: dt.date
    note: str = ""

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError(f"{self.key}: band inverted, {self.low} > {self.high}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "low": self.low,
            "high": self.high,
            "unit": self.unit,
            "source": self.source,
            "source_url": self.source_url,
            "source_date": self.source_date.isoformat(),
            "note": self.note,
        }
