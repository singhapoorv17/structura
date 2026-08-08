"""Lineage for every number the tool shows.

A reader deciding whether to put a figure in front of an investment committee
needs to know where it came from. Four classes cover everything this tool can
say about a number:

``stated``
    Taken from a cited public document. Requires a URL and a date.
``benchmark``
    Taken from the market-terms library. Requires a source and a date, and
    carries the published range where the source gave one.
``assumed``
    A tool default with no external source.
``not_disclosed``
    The document exists and does not say. Carries the reason and no value.

The fourth class matters as much as the first three. A release that omits the
tenor is a fact about the deal, and rendering it as a blank, a zero, or an
inference all misrepresent it.

:func:`to_wire` walks a response and refuses to serialise a bare number, so an
unbadged figure cannot reach a reader by omission.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Final

__all__ = [
    "Provenance",
    "Provenanced",
    "UnbadgedNumber",
    "assumed",
    "benchmark_value",
    "confidence_header",
    "not_disclosed",
    "stated",
    "to_wire",
]


class Provenance(str, Enum):
    """Where a number came from."""

    STATED = "stated"
    BENCHMARK = "benchmark"
    ASSUMED = "assumed"
    NOT_DISCLOSED = "not_disclosed"


class UnbadgedNumber(TypeError):
    """Raised when a bare number is about to be serialised.

    Carries the path to the offending leaf, because in a nested response the
    field name alone is rarely enough to find it.
    """

    def __init__(self, path: str, value: Any) -> None:
        super().__init__(
            f"unbadged number at {path or '<root>'}: {value!r}. "
            "Wrap it with stated(), benchmark_value(), assumed() or "
            "not_disclosed() before it reaches a reader."
        )
        self.path = path
        self.value = value


@dataclass(frozen=True, slots=True)
class Provenanced:
    """A value carried together with its lineage."""

    value: float | int | str | None
    provenance: Provenance
    unit: str = ""
    source: str | None = None
    source_url: str | None = None
    source_date: dt.date | None = None
    low: float | None = None
    high: float | None = None
    note: str = ""
    reason: str = ""
    #: True when the citation is a restatement of someone else's reporting
    #: rather than the reporting itself.
    is_restatement: bool = False
    #: Pointer to the primary source a restatement echoes.
    echo_of: str | None = None
    #: Set when the source is real and dated but the date was not captured.
    #: Saying so is required; inventing a plausible date is not an option, and
    #: a reader judging freshness needs to know which it is.
    source_date_unknown: bool = False

    def __post_init__(self) -> None:
        p = self.provenance
        if p is Provenance.STATED:
            if not self.source_url:
                raise ValueError("a stated value requires source_url")
            if self.source_date is None and not self.source_date_unknown:
                raise ValueError(
                    "a stated value requires source_date, or source_date_unknown "
                    "set explicitly"
                )
            if self.source_date is not None and self.source_date_unknown:
                raise ValueError("source_date and source_date_unknown conflict")
            if self.is_restatement and not self.echo_of:
                raise ValueError(
                    "a restatement must name the primary source it echoes"
                )
        elif p is Provenance.BENCHMARK:
            if not self.source:
                raise ValueError("a benchmark value requires a source")
            if self.source_date is None:
                raise ValueError("a benchmark value requires source_date")
        elif p is Provenance.NOT_DISCLOSED:
            if self.value is not None:
                raise ValueError("an undisclosed value cannot carry a value")
            if not self.reason:
                raise ValueError("an undisclosed value requires a reason")
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError(f"range inverted: {self.low} > {self.high}")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "value": self.value,
            "provenance": self.provenance.value,
        }
        if self.unit:
            out["unit"] = self.unit
        if self.source:
            out["source"] = self.source
        if self.source_url:
            out["source_url"] = self.source_url
        if self.source_date is not None:
            out["source_date"] = self.source_date.isoformat()
        elif self.source_date_unknown:
            out["source_date"] = None
            out["source_date_unknown"] = True
        if self.low is not None or self.high is not None:
            out["low"] = self.low
            out["high"] = self.high
        if self.note:
            out["note"] = self.note
        if self.reason:
            out["reason"] = self.reason
        if self.is_restatement:
            out["is_restatement"] = True
            out["echo_of"] = self.echo_of
        return out

    def with_note(self, note: str) -> "Provenanced":
        return replace(self, note=note)


# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------


def stated(
    value: float | int | str,
    *,
    source: str,
    source_url: str | None,
    source_date: dt.date | None,
    unit: str = "",
    note: str = "",
    is_restatement: bool = False,
    echo_of: str | None = None,
    source_date_unknown: bool = False,
) -> Provenanced:
    """A fact taken from a cited public document."""
    return Provenanced(
        value=value,
        provenance=Provenance.STATED,
        unit=unit,
        source=source,
        source_url=source_url,
        source_date=source_date,
        note=note,
        is_restatement=is_restatement,
        echo_of=echo_of,
        source_date_unknown=source_date_unknown,
    )


def benchmark_value(
    value: float,
    *,
    source: str,
    source_date: dt.date | None,
    low: float | None = None,
    high: float | None = None,
    unit: str = "",
    source_url: str | None = None,
    note: str = "",
) -> Provenanced:
    """A market-terms figure. Carries the published range where one exists."""
    return Provenanced(
        value=value,
        provenance=Provenance.BENCHMARK,
        unit=unit,
        source=source,
        source_url=source_url,
        source_date=source_date,
        low=low,
        high=high,
        note=note,
    )


def assumed(value: float | int | str, *, unit: str = "", note: str = "") -> Provenanced:
    """A tool default with no external source."""
    return Provenanced(
        value=value, provenance=Provenance.ASSUMED, unit=unit, note=note
    )


def not_disclosed(reason: str, *, unit: str = "") -> Provenanced:
    """The document exists and does not say."""
    return Provenanced(
        value=None, provenance=Provenance.NOT_DISCLOSED, unit=unit, reason=reason
    )


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

#: Scalars that may appear on the wire without a badge. Numbers are absent on
#: purpose; booleans are flags rather than quantities.
_BARE_OK: Final = (str, bool, type(None))


def to_wire(obj: Any, *, _path: str = "") -> Any:
    """Serialise a response, refusing any number that has no lineage.

    Raises
    ------
    UnbadgedNumber
        If a bare ``int`` or ``float`` sits at a leaf position anywhere in the
        structure.
    """
    if isinstance(obj, Provenanced):
        return obj.to_dict()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, _BARE_OK):
        return obj
    if isinstance(obj, Mapping):
        return {
            str(k): to_wire(v, _path=f"{_path}.{k}" if _path else str(k))
            for k, v in obj.items()
        }
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
        return [
            to_wire(v, _path=f"{_path}[{i}]") for i, v in enumerate(obj)
        ]
    if isinstance(obj, (int, float)):
        raise UnbadgedNumber(_path, obj)
    raise TypeError(f"cannot serialise {type(obj).__name__} at {_path or '<root>'}")


def confidence_header(obj: Any) -> dict[str, int]:
    """Count provenanced leaves by class.

    This is what a reader looks at first: how much of what they are seeing is
    fact, how much is market benchmark, and how much the tool made up.
    """
    counts = {p.value: 0 for p in Provenance}
    _count(obj, counts)
    counts["total"] = sum(counts.values())
    return counts


def _count(obj: Any, counts: dict[str, int]) -> None:
    if isinstance(obj, Provenanced):
        counts[obj.provenance.value] += 1
        return
    if isinstance(obj, Mapping):
        for v in obj.values():
            _count(v, counts)
        return
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
        for v in obj:
            _count(v, counts)
