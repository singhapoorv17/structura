"""Loading and validating the comparable-transactions corpus.

The corpus is JSON on disk so it can grow by ingest without a code change. The
loader is strict on purpose: a record that cannot declare where each of its
facts came from does not load at all.
"""

from __future__ import annotations

import functools
import json
import pathlib
from typing import Any, Iterator

from comps.schema import (
    ContractKind,
    DealRecord,
    Technology,
    Tranche,
    TrancheKind,
    cell_from_json,
)

DATA = pathlib.Path(__file__).resolve().parent / "data"


class CorpusError(ValueError):
    """A record failed validation. Carries the record key."""


@functools.lru_cache(maxsize=1)
def load() -> tuple[DealRecord, ...]:
    """Load and validate every record. Cached for the process lifetime."""
    records: list[DealRecord] = []
    seen: set[str] = set()
    for path in sorted(DATA.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for raw in payload["deals"]:
            record = _record(raw, path.name)
            if record.key in seen:
                raise CorpusError(f"duplicate record key: {record.key}")
            seen.add(record.key)
            records.append(record)
    return tuple(records)


def iter_records() -> Iterator[DealRecord]:
    yield from load()


def by_key(key: str) -> DealRecord:
    for record in load():
        if record.key == key:
            return record
    raise KeyError(key)


def _record(raw: dict[str, Any], filename: str) -> DealRecord:
    key = raw.get("key")
    if not key:
        raise CorpusError(f"{filename}: a record has no key")
    try:
        return DealRecord(
            key=key,
            name=raw["name"],
            technology=Technology(raw["technology"]),
            sponsor=cell_from_json(raw["sponsor"], field_name=f"{key}.sponsor"),
            total_quantum=cell_from_json(
                raw["total_quantum"], field_name=f"{key}.total_quantum"
            ),
            close_date=cell_from_json(
                raw["close_date"], field_name=f"{key}.close_date"
            ),
            cod=cell_from_json(raw["cod"], field_name=f"{key}.cod"),
            location=cell_from_json(raw["location"], field_name=f"{key}.location"),
            capacity=cell_from_json(raw["capacity"], field_name=f"{key}.capacity"),
            contract_kind=ContractKind(raw.get("contract_kind", "UNKNOWN")),
            offtake=cell_from_json(raw["offtake"], field_name=f"{key}.offtake"),
            lenders=tuple(raw.get("lenders", ())),
            tranches=tuple(
                _tranche(t, key, i) for i, t in enumerate(raw.get("tranches", ()))
            ),
            credit_route=cell_from_json(
                raw["credit_route"], field_name=f"{key}.credit_route"
            ),
            primary_source=raw["primary_source"],
            headline=raw.get("headline", ""),
            summary=raw.get("summary", ""),
            tags=tuple(raw.get("tags", ())),
        )
    except KeyError as exc:
        raise CorpusError(f"{key}: missing required field {exc}") from exc


def _tranche(raw: dict[str, Any], deal_key: str, index: int) -> Tranche:
    name = raw.get("name") or f"tranche-{index}"
    return Tranche(
        name=name,
        kind=TrancheKind(raw["kind"]),
        amount=cell_from_json(raw["amount"], field_name=f"{deal_key}.{name}.amount"),
        pricing=cell_from_json(raw["pricing"], field_name=f"{deal_key}.{name}.pricing"),
        tenor_years=cell_from_json(
            raw["tenor_years"], field_name=f"{deal_key}.{name}.tenor_years"
        ),
        note=raw.get("note", ""),
    )
