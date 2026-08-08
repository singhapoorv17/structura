"""Turn six fields into a complete, badged model.

The user supplies asset type, size, state, contract, COD and (optionally)
capex. Everything else the engine needs is resolved here, and every resolved
value carries the class of evidence behind it:

* ``stated``    — the user typed it
* ``benchmark`` — a cited market figure, or a figure derived from comparable
  transactions with those transactions named
* ``assumed``   — a tool default with no external source

The capex default is the interesting one. Rather than a lab cost estimate, it
is derived from what comparable transactions actually raised per megawatt, with
the deals named. That is a financing total rather than a construction budget,
and the note says so.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field
from typing import Any

from comps import bands as bands_module
from comps.matcher import match
from comps.schema import Technology
from engine.provenance import (
    Provenanced,
    assumed,
    benchmark_value,
    confidence_header,
    stated,
)
from intake.premise import Advisory, check
from intake.spec import DealSpec

USER = "User input"

#: Technology-family fallbacks for total capital per megawatt, used only where
#: the corpus has no comparable transaction to derive one from. No public
#: source publishes these, so they are tool defaults and are badged as such.
FALLBACK_PER_MW: dict[str, float] = {
    "solar": 1_800_000.0,
    "storage": 1_400_000.0,
    "wind": 1_900_000.0,
    "digital": 9_000_000.0,
    "rng": 4_000_000.0,
}

#: Engine defaults that have no published market source.
CONSTRUCTION_MONTHS = {"solar": 18, "storage": 12, "wind": 24, "digital": 30}

#: Net capacity factor by technology family. Publicly reported fleet averages
#: vary by resource and region; these are tool defaults, not a sourced table,
#: and they are badged accordingly.
CAPACITY_FACTOR = {"solar": 0.26, "wind": 0.40, "digital": 0.85, "rng": 0.85}

#: Storage throughput assumptions: one full cycle a day at this round-trip
#: efficiency.
STORAGE_CYCLES_PER_YEAR = 365.0
STORAGE_ROUND_TRIP = 0.86

#: Operating cost, dollars per kW per year. Tool defaults.
OPEX_PER_KW_YEAR = {"solar": 18.0, "wind": 45.0, "storage": 12.0, "digital": 0.0, "rng": 90.0}

#: First-year contracted price. No free source publishes PPA, toll or lease
#: pricing, which is the single largest unsourced input in the model. Where the
#: user does not supply one these stand in, and they say so loudly.
CONTRACT_PRICE = {"solar": 45.0, "wind": 35.0, "rng": 25.0, "digital": 110.0}

#: Storage capacity payment, dollars per kW per month, converted to an implied
#: energy price over modelled throughput.
STORAGE_CAPACITY_PAYMENT_PER_KW_MONTH = 10.0

NO_PRICE_SOURCE = (
    "No free source publishes contract pricing, so this is a tool default "
    "rather than a market figure. It is the largest single assumption in the "
    "model: override it with the deal's own price."
)


@dataclass(frozen=True, slots=True)
class Resolution:
    """A complete model, with every input's evidence attached."""

    spec: DealSpec
    inputs: dict[str, Provenanced] = field(default_factory=dict)
    advisories: tuple[Advisory, ...] = ()
    comps_used: tuple[str, ...] = ()

    @property
    def confidence(self) -> dict[str, int]:
        return confidence_header(self.inputs)

    def unresolved(self) -> tuple[str, ...]:
        """Required inputs that came out with no value.

        A resolution with anything here is not a runnable model.
        """
        return tuple(
            name
            for name, cell in self.inputs.items()
            if cell.value is None
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "inputs": {k: v.to_dict() for k, v in self.inputs.items()},
            "advisories": [a.to_dict() for a in self.advisories],
            "comps_used": list(self.comps_used),
            "confidence": self.confidence,
        }


def resolve(spec: DealSpec, *, today: dt.date | None = None) -> Resolution:
    """Fill in everything the user did not say, and record why."""
    tech = Technology(spec.asset_type)
    family = tech.family
    inputs: dict[str, Provenanced] = {}

    # -- what the user gave us ---------------------------------------------

    inputs["asset_type"] = _user(spec.asset_type)
    if spec.state:
        inputs["state"] = _user(spec.state)
    if spec.contract.kind and spec.contract.kind != "UNKNOWN":
        inputs["contract_kind"] = _user(spec.contract.kind)
    if spec.contract.tenor_years is not None:
        inputs["contract_tenor_years"] = _user(spec.contract.tenor_years, unit="years")
    if spec.contract.price is not None:
        inputs["contract_price"] = _user(spec.contract.price, unit="$/MWh")

    capacity_mw = spec.capacity_mw()
    if capacity_mw is not None:
        inputs["capacity_mw"] = _user(capacity_mw, unit="MW")
    if spec.energy_mwh() is not None:
        inputs["energy_mwh"] = _user(spec.energy_mwh(), unit="MWh")

    cod = spec.cod_date()
    if cod is not None:
        inputs["cod"] = _user(cod.isoformat())

    # -- capex, from comparable transactions where we have them ------------

    comps = match(technology=tech, state=spec.state or None, limit=8)
    per_mw, cited = _per_mw_from_comps(comps)

    if spec.capex is not None:
        inputs["capex"] = _user(spec.capex, unit="USD")
    elif capacity_mw is not None and per_mw is not None:
        inputs["capex"] = benchmark_value(
            capacity_mw * per_mw,
            source="Derived from comparable transactions: "
            + ", ".join(cited),
            source_date=dt.date.today(),
            unit="USD",
            note=(
                f"Median total capital of ${per_mw / 1e6:,.2f}m per MW across "
                f"{len(cited)} comparable financings. These are financing "
                "totals rather than construction budgets, so the figure "
                "includes fees, reserves and interest during construction."
            ),
        )
    elif capacity_mw is not None:
        fallback = FALLBACK_PER_MW.get(family)
        if fallback is not None:
            inputs["capex"] = assumed(
                capacity_mw * fallback,
                unit="USD",
                note=(
                    f"No comparable transaction in the corpus carries both a "
                    f"size and a quantum for {family}. This is a tool default "
                    f"of ${fallback / 1e6:,.2f}m per MW with no external source."
                ),
            )

    # -- debt terms, from the cited market bands ---------------------------

    dscr = _band(family, ("dscr.solar", "dscr.wind", "dscr.storage", "dscr.data_centre"))
    if dscr is not None:
        inputs["target_dscr"] = _from_band(dscr, dscr.high)

    term = bands_module.BY_KEY.get("spread.term")
    if term is not None and family in term.applies_to:
        inputs["debt_spread_bps"] = _from_band(term, (term.low + term.high) / 2)

    construction = bands_module.BY_KEY.get("spread.construction")
    if construction is not None and family in construction.applies_to:
        inputs["construction_spread_bps"] = _from_band(construction, construction.high)

    credit_price = _band(family, ("credit_price.itc_2026", "credit_price.ptc_2026"))
    if credit_price is not None:
        inputs["credit_price"] = _from_band(credit_price, credit_price.low)

    # -- production and revenue --------------------------------------------
    #
    # The engine will happily run on its own generic defaults, which are a
    # generator's, so a battery modelled without this step earns a solar
    # farm's revenue. Resolve it explicitly, and badge every part of it.

    if capacity_mw is not None:
        if family == "storage" and spec.energy_mwh():
            throughput = (
                spec.energy_mwh() * STORAGE_CYCLES_PER_YEAR * STORAGE_ROUND_TRIP
            )
            inputs["production_p50"] = assumed(
                throughput,
                unit="MWh per year",
                note=(
                    f"One full cycle a day at {STORAGE_ROUND_TRIP:.0%} round-trip "
                    "efficiency. Real dispatch depends on the toll."
                ),
            )
            if spec.contract.price is not None:
                inputs["contracted_price"] = _user(spec.contract.price, unit="$/MWh")
            else:
                annual_capacity_revenue = (
                    capacity_mw
                    * 1_000.0
                    * STORAGE_CAPACITY_PAYMENT_PER_KW_MONTH
                    * 12.0
                )
                inputs["contracted_price"] = assumed(
                    annual_capacity_revenue / throughput if throughput else 0.0,
                    unit="$/MWh",
                    note=(
                        f"Implied from a ${STORAGE_CAPACITY_PAYMENT_PER_KW_MONTH:,.0f}"
                        "/kW-month capacity payment spread over modelled "
                        f"throughput. {NO_PRICE_SOURCE}"
                    ),
                )
        else:
            factor = CAPACITY_FACTOR.get(family, 0.35)
            inputs["production_p50"] = assumed(
                capacity_mw * 8_760.0 * factor,
                unit="MWh per year",
                note=f"Net capacity factor of {factor:.0%}. No sourced table.",
            )
            if spec.contract.price is not None:
                inputs["contracted_price"] = _user(spec.contract.price, unit="$/MWh")
            else:
                inputs["contracted_price"] = assumed(
                    CONTRACT_PRICE.get(family, 50.0),
                    unit="$/MWh",
                    note=NO_PRICE_SOURCE,
                )

        inputs["opex_year1"] = assumed(
            capacity_mw * 1_000.0 * OPEX_PER_KW_YEAR.get(family, 25.0),
            unit="USD per year",
            note=(
                f"${OPEX_PER_KW_YEAR.get(family, 25.0):,.0f} per kW-year. "
                "Tool default, no sourced table."
            ),
        )

    # -- structural defaults with no published source ----------------------

    inputs["construction_months"] = assumed(
        CONSTRUCTION_MONTHS.get(family, 18),
        unit="months",
        note="Typical build duration for the technology. No published source.",
    )
    inputs["project_life_years"] = assumed(
        35 if family == "digital" else 25,
        unit="years",
        note="Modelling horizon. No published source.",
    )
    inputs["tenor_years"] = assumed(
        18.0, unit="years", note="Debt tenor. No published source; adjust to the deal."
    )

    return Resolution(
        spec=spec,
        inputs=inputs,
        advisories=check(spec, today=today),
        comps_used=tuple(cited),
    )


# ---------------------------------------------------------------------------


def _user(value: Any, unit: str = "") -> Provenanced:
    return stated(
        value,
        source=USER,
        source_url="urn:structura:user-input",
        source_date=None,
        source_date_unknown=True,
        unit=unit,
        note="Supplied by the user.",
    )


def _band(family: str, keys: tuple[str, ...]):
    for key in keys:
        band = bands_module.BY_KEY.get(key)
        if band is not None and family in band.applies_to:
            return band
    return None


def _from_band(band, value: float) -> Provenanced:
    return benchmark_value(
        value,
        source=band.source,
        source_url=band.source_url,
        source_date=band.source_date,
        low=band.low,
        high=band.high,
        unit=band.unit,
        note=band.note,
    )


def _per_mw_from_comps(comps) -> tuple[float | None, list[str]]:
    """Median total capital per megawatt across the matched transactions.

    Only comps that disclosed both a quantum and a capacity can contribute,
    which is usually a minority of them. The names of the ones that did are
    returned so the resulting figure can be audited.
    """
    ratios: list[float] = []
    cited: list[str] = []
    for m in comps.matches:
        quantum = m.record.total_quantum.value
        mw = m.record.capacity_mw()
        if not isinstance(quantum, (int, float)) or not mw:
            continue
        ratios.append(float(quantum) / mw)
        cited.append(m.record.name)
    if not ratios:
        return None, []
    return statistics.median(ratios), cited
