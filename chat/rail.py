"""Argue with the model.

The wizard creates a deal; this lets a user interrogate it. Every turn either
changes the deal and re-runs, or asks the model a question the model can
answer from what it computed. Nothing here generates prose about project
finance: a request it cannot turn into a model operation is refused, and says
what it would have needed.

That constraint is the design, not a limitation of it. A chat rail that can
answer without touching the model will eventually answer wrongly and
confidently, and the reader has no way to tell which kind of answer they got.

The parser is deterministic — patterns, not a language model. It handles the
mutations people actually make when pressure-testing a structure, and refuses
the rest out loud.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Callable

from intake.spec import ContractSpec, DealSpec

__all__ = ["Turn", "ask", "INTENTS"]


@dataclass(frozen=True, slots=True)
class Turn:
    """One exchange. Either the deal changed, or the model was queried."""

    understood: bool
    #: What changed on the deal, as field -> (before, after).
    delta: dict[str, tuple[Any, Any]]
    spec: DealSpec | None
    answer: str
    intent: str = ""
    #: Set when nothing could be done with the input.
    needed: str = ""

    @property
    def mutated(self) -> bool:
        return bool(self.delta)

    def to_dict(self) -> dict[str, Any]:
        return {
            "understood": self.understood,
            "intent": self.intent,
            "delta": {k: list(v) for k, v in self.delta.items()},
            "answer": self.answer,
            "needed": self.needed,
            "mutated": self.mutated,
        }


MONEY = r"\$?\s*([\d,]+(?:\.\d+)?)\s*(bn|billion|m|million|k)?"


def _money(match: re.Match, group: int = 1) -> float:
    value = float(match.group(group).replace(",", ""))
    scale = (match.group(group + 1) or "").lower()
    if scale in ("bn", "billion"):
        return value * 1e9
    if scale in ("m", "million"):
        return value * 1e6
    if scale == "k":
        return value * 1e3
    return value


def _set_contract(spec: DealSpec, **kwargs) -> DealSpec:
    return dataclasses.replace(
        spec, contract=dataclasses.replace(spec.contract, **kwargs)
    )


# -- intents ----------------------------------------------------------------
#
# Each is (id, pattern, apply). ``apply`` returns the new spec and a
# human-readable description of what it changed.


def _tenor(spec, m):
    years = float(m.group(1))
    return _set_contract(spec, tenor_years=years), (
        "contract_tenor_years",
        spec.contract.tenor_years,
        years,
    )


def _price(spec, m):
    price = float(m.group(1).replace(",", ""))
    return _set_contract(spec, price=price), (
        "contract_price",
        spec.contract.price,
        price,
    )


def _capex(spec, m):
    value = _money(m)
    return dataclasses.replace(spec, capex=value), ("capex", spec.capex, value)


def _cod(spec, m):
    return dataclasses.replace(spec, cod=m.group(1)), ("cod", spec.cod, m.group(1))


def _size(spec, m):
    unit = (m.group(2) or "mw").lower()
    key = {"mwac": "mwac", "mwdc": "mwdc", "mwh": "mwh", "mw": "mw"}[unit]
    value = float(m.group(1).replace(",", ""))
    size = dict(spec.size)
    before = size.get(key)
    size[key] = value
    return dataclasses.replace(spec, size=size), (f"size.{key}", before, value)


def _state(spec, m):
    state = m.group(1).upper()
    return dataclasses.replace(spec, state=state), ("state", spec.state, state)


def _contract_kind(spec, m):
    kind = {
        "ppa": "PPA",
        "toll": "TOLLING",
        "tolling": "TOLLING",
        "hedge": "HEDGE",
        "merchant": "MERCHANT",
        "lease": "HYPERSCALE_LEASE",
    }[m.group(1).lower()]
    return _set_contract(spec, kind=kind), (
        "contract_kind",
        spec.contract.kind,
        kind,
    )


INTENTS: tuple[tuple[str, str, Callable], ...] = (
    (
        "set-tenor",
        r"(?:tenor|ppa|contract|toll|offtake)\D{0,20}?(\d{1,2})\s*[- ]?years?",
        _tenor,
    ),
    ("set-tenor", r"(\d{1,2})\s*[- ]?year\s+(?:ppa|contract|toll|offtake)", _tenor),
    ("set-price", r"(?:price|at)\s*\$\s*([\d,]+(?:\.\d+)?)\s*(?:/|per\s+)?mwh", _price),
    ("set-capex", r"(?:capex|cost|capital cost)\D{0,12}?" + MONEY, _capex),
    ("set-cod", r"cod\D{0,12}?(\d{4}(?:-(?:\d{2}|Q[1-4]))?)", _cod),
    ("set-size", r"([\d,]+(?:\.\d+)?)\s*(mwac|mwdc|mwh|mw)\b", _size),
    ("set-state", r"\bin\s+([A-Z]{2})\b", _state),
    (
        "set-contract-kind",
        r"\b(?:as\s+a\s+|to\s+a\s+|switch\s+to\s+(?:a\s+)?)(ppa|toll|tolling|hedge|merchant|lease)\b",
        _contract_kind,
    ),
)

WHY_NOT = re.compile(
    r"why\s+(?:not|can'?t\s+(?:we|i)\s+(?:do|use))\s+(?:a\s+|the\s+)?([a-z \-]+)",
    re.IGNORECASE,
)

STRUCTURE_ALIASES = {
    "flip": "partnership_flip",
    "partnership flip": "partnership_flip",
    "t-flip": "t_flip",
    "tflip": "t_flip",
    "hybrid": "t_flip",
    "preferred": "preferred_equity",
    "preferred equity": "preferred_equity",
    "transfer": "direct_transfer",
    "direct transfer": "direct_transfer",
    "sale-leaseback": "sale_leaseback",
    "sale leaseback": "sale_leaseback",
    "leaseback": "sale_leaseback",
    "equipment lease": "equipment_lease",
    "lease": "equipment_lease",
}


def ask(spec: DealSpec, text: str, *, today: dt.date | None = None) -> Turn:
    """Interpret one turn against a deal."""
    lowered = text.strip().lower()
    if not lowered:
        return Turn(False, {}, None, "", needed="Nothing was asked.")

    # "Why not X" is answered from the gates, which are model output.
    why = WHY_NOT.search(lowered)
    if why:
        return _why_not(spec, why.group(1).strip(), today=today)

    for intent_id, pattern, apply in INTENTS:
        match = re.search(pattern, lowered, re.IGNORECASE)
        if not match:
            continue
        new_spec, (field, before, after) = apply(spec, match)
        if before == after:
            return Turn(
                True,
                {},
                new_spec,
                f"{field.replace('_', ' ')} is already {after}. Nothing re-ran.",
                intent=intent_id,
            )
        return Turn(
            understood=True,
            delta={field: (before, after)},
            spec=new_spec,
            answer=(
                f"{field.replace('_', ' ')} changed from "
                f"{_fmt(before)} to {_fmt(after)}. The model re-ran."
            ),
            intent=intent_id,
        )

    return Turn(
        understood=False,
        delta={},
        spec=None,
        answer="",
        needed=(
            "That did not map to a change in the deal. This rail only answers "
            "by re-running the model, so it needs an input to change — a "
            "tenor, a price, a capex, a COD, a size, a state, a contract type "
            "— or a question of the form 'why not <structure>'."
        ),
    )


def _why_not(spec: DealSpec, phrase: str, *, today) -> Turn:
    from engine.structures.models import StructureKey
    from intake import resolve
    from recommend.gates import evaluate_gates

    key = None
    for alias, value in sorted(
        STRUCTURE_ALIASES.items(), key=lambda kv: -len(kv[0])
    ):
        if alias in phrase:
            key = StructureKey(value)
            break
    if key is None:
        return Turn(
            False,
            {},
            None,
            "",
            intent="why-not",
            needed=f"'{phrase}' does not name a structure in the set.",
        )

    resolution = resolve(spec, today=today)
    failures = evaluate_gates(resolution, today=today).get(key, ())
    if not failures:
        return Turn(
            True,
            {},
            spec,
            f"{key.label} is available on this deal — it is in the comparison.",
            intent="why-not",
        )
    reasons = " ".join(v.fact for v in failures)
    cites = ", ".join(sorted({v.source for v in failures}))
    return Turn(
        understood=True,
        delta={},
        spec=spec,
        answer=f"{key.label} is blocked. {reasons} ({cites})",
        intent="why-not",
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "unset"
    if isinstance(value, float) and abs(value) >= 1e6:
        return f"${value / 1e6:,.0f}m"
    return str(value)
