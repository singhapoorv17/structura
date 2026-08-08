"""What the user actually types.

Six fields. Everything else the model needs is resolved from market benchmarks
and from comparable transactions, and every resolved value says where it came
from.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["ContractSpec", "DealSpec"]


@dataclass(frozen=True, slots=True)
class ContractSpec:
    kind: str = "UNKNOWN"
    tenor_years: float | None = None
    #: $/MWh for an energy contract, $/kW-month for a capacity toll. Optional:
    #: no free source publishes PPA prices, so a blank stays blank.
    price: float | None = None


@dataclass(frozen=True, slots=True)
class DealSpec:
    """The six-field intake."""

    asset_type: str
    size: dict[str, float] = field(default_factory=dict)
    state: str = ""
    contract: ContractSpec = field(default_factory=ContractSpec)
    cod: str = ""
    capex: float | None = None
    name: str = ""

    # -- derived ------------------------------------------------------------

    def cod_date(self) -> dt.date | None:
        """First of the month for a ``YYYY-MM`` or ``YYYY-Qn`` string."""
        raw = (self.cod or "").strip()
        if not raw:
            return None
        m = re.fullmatch(r"(\d{4})-Q([1-4])", raw, re.IGNORECASE)
        if m:
            year, quarter = int(m.group(1)), int(m.group(2))
            return dt.date(year, quarter * 3 - 2, 1)
        m = re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", raw)
        if m:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
        m = re.fullmatch(r"(\d{4})", raw)
        if m:
            return dt.date(int(m.group(1)), 1, 1)
        return None

    def capacity_mw(self) -> float | None:
        """The megawatt figure the market would quote this project at."""
        for key in ("mwac", "mw", "it_mw", "mwdc"):
            if key in self.size:
                return float(self.size[key])
        return None

    def energy_mwh(self) -> float | None:
        return float(self.size["mwh"]) if "mwh" in self.size else None

    def storage_hours(self) -> float | None:
        mw, mwh = self.capacity_mw(), self.energy_mwh()
        if mw and mwh:
            return mwh / mw
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "asset_type": self.asset_type,
            "size": dict(self.size),
            "state": self.state,
            "contract": {
                "kind": self.contract.kind,
                "tenor_years": self.contract.tenor_years,
                "price": self.contract.price,
            },
            "cod": self.cod,
            "capex": self.capex,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DealSpec":
        contract = raw.get("contract") or {}
        return cls(
            asset_type=raw["asset_type"],
            size=dict(raw.get("size") or {}),
            state=raw.get("state", ""),
            contract=ContractSpec(
                kind=contract.get("kind", "UNKNOWN"),
                tenor_years=contract.get("tenor_years"),
                price=contract.get("price"),
            ),
            cod=raw.get("cod", ""),
            capex=raw.get("capex"),
            name=raw.get("name") or raw.get("key", ""),
        )
