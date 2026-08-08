"""Matching a project spec to the transactions we could verify.

The match is deterministic and explainable. Every returned comp carries the
reasons it matched and a coverage statement saying what the sources disclosed,
because a comp whose relevance the reader cannot audit is decoration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from comps import bands as bands_module
from comps.corpus import load
from comps.schema import DealRecord, MarketBand, Technology

#: Size bands, in USD of total quantum. A $140m storage deal and a $5bn
#: portfolio are not comparable however well the technology lines up.
SIZE_BANDS: tuple[tuple[float, float, str], ...] = (
    (0, 250_000_000, "sub-$250m"),
    (250_000_000, 1_000_000_000, "$250m-$1bn"),
    (1_000_000_000, 5_000_000_000, "$1bn-$5bn"),
    (5_000_000_000, float("inf"), "over $5bn"),
)


def size_band(amount: float | None) -> str | None:
    if amount is None:
        return None
    for low, high, label in SIZE_BANDS:
        if low <= amount < high:
            return label
    return None


#: OBBBA (P.L. 119-21) reset US renewable tax structuring. A financing that
#: closed before it is a record of a market that no longer exists, so it is
#: shown with a warning and ranked below current deals rather than hidden.
OBBBA_ENACTED = 2025


def vintage(record: DealRecord) -> int | None:
    """The year the transaction closed, or the year its source published."""
    for cell in (record.close_date, record.sponsor):
        value = cell.value
        if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
            return int(value[:4])
        if cell.source_date is not None:
            return cell.source_date.year
    return None


@dataclass(frozen=True, slots=True)
class Match:
    record: DealRecord
    score: int
    reasons: tuple[str, ...]

    def coverage(self) -> dict[str, int]:
        """What this comp actually disclosed, by provenance class."""
        return self.record.disclosure_profile()

    @property
    def vintage(self) -> int | None:
        return vintage(self.record)

    @property
    def vintage_warning(self) -> str | None:
        year = self.vintage
        if year is None:
            return "Vintage not established from the source recorded for this entry."
        if year < OBBBA_ENACTED:
            return (
                f"Closed in {year}, before OBBBA. Tax structuring, credit "
                "transfer pricing and begin-construction rules have changed "
                "since; treat the structure as historical."
            )
        return None


@dataclass(frozen=True, slots=True)
class CompsResult:
    """Two panels, kept apart on purpose."""

    matches: tuple[Match, ...]
    market_bands: tuple[MarketBand, ...]
    coverage_statement: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "deals": [
                {
                    "key": m.record.key,
                    "name": m.record.name,
                    "technology": m.record.technology.value,
                    "primary_source": m.record.primary_source,
                    "match_reasons": list(m.reasons),
                    "disclosure": m.coverage(),
                    "vintage": m.vintage,
                    "vintage_warning": m.vintage_warning,
                }
                for m in self.matches
            ],
            "market_bands": [b.to_dict() for b in self.market_bands],
            "coverage_statement": self.coverage_statement,
        }


def match(
    *,
    technology: Technology | str,
    total_quantum: float | None = None,
    contract_kind: str | None = None,
    state: str | None = None,
    limit: int = 6,
    corpus: Iterable[DealRecord] | None = None,
) -> CompsResult:
    """Return the closest verified transactions, plus the applicable bands."""
    tech = Technology(technology) if isinstance(technology, str) else technology
    family = tech.family
    records = list(corpus) if corpus is not None else list(load())

    band = size_band(total_quantum)
    scored: list[Match] = []
    for record in records:
        if record.technology.family != family:
            continue
        reasons = [f"same technology family ({family})"]
        score = 10
        if record.technology is tech:
            score += 5
            reasons.append(f"same technology ({tech.value})")
        if band and size_band(_amount(record)) == band:
            score += 4
            reasons.append(f"same size band ({band})")
        if contract_kind and record.contract_kind.value == contract_kind:
            score += 3
            reasons.append(f"same contract type ({contract_kind})")
        if state and isinstance(record.location.value, str):
            if state.upper() in record.location.value.upper():
                score += 2
                reasons.append(f"same market ({state})")
        year = vintage(record)
        if year is not None and year >= OBBBA_ENACTED:
            score += 6
            reasons.append(f"current vintage ({year})")
        scored.append(Match(record=record, score=score, reasons=tuple(reasons)))

    scored.sort(key=lambda m: (-m.score, m.record.key))
    top = tuple(scored[:limit])

    return CompsResult(
        matches=top,
        market_bands=bands_module.bands_for(family),
        coverage_statement=_coverage_statement(top, len(scored)),
    )


def _amount(record: DealRecord) -> float | None:
    value = record.total_quantum.value
    return float(value) if isinstance(value, (int, float)) else None


def _coverage_statement(matches: tuple[Match, ...], total: int) -> str:
    """State plainly what the reader is looking at.

    Naming the limits of the set is what makes the rest of it usable.
    """
    if not matches:
        return (
            "No transaction in the corpus matches this technology family. "
            "The market bands below still apply."
        )
    withheld = sum(m.coverage()["not_disclosed"] for m in matches)
    cells = sum(sum(m.coverage().values()) for m in matches)
    stale = [m for m in matches if m.vintage_warning]
    statement = (
        f"{len(matches)} of {total} matching transactions shown. "
        f"{cells - withheld} of {cells} fields were disclosed by the sources; "
        f"{withheld} were not. Pricing is rarely disclosed on any transaction, "
        "so spreads come from the market bands rather than from these deals."
    )
    if stale:
        statement += (
            f" {len(stale)} of these closed before OBBBA and are shown as "
            "historical structure rather than current market."
        )
    return statement
