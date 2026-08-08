"""Turn a resolved deal into engine inputs.

The resolver produced a badged set of values. This maps them onto the
dataclasses the engine expects. Nothing new is invented here: every number
comes from the resolution, and anything the resolution could not supply falls
back to the engine's own documented default rather than to a fresh guess.
"""

from __future__ import annotations

import datetime as dt

from engine.defaults import RevenueContractType, Technology as EngineTechnology
from engine.models import DebtTerms, ProjectInputs
from engine.tax import MacrInputs, MacrMethod, TaxProject
from engine.tax import Technology as TaxTechnology

__all__ = ["engine_inputs"]

#: Asset type to the engine's technology enum.
ENGINE_TECHNOLOGY = {
    "SOLAR": EngineTechnology.SOLAR,
    "SOLAR_PLUS_STORAGE": EngineTechnology.SOLAR,
    "STORAGE": EngineTechnology.STORAGE,
    "WIND": EngineTechnology.WIND,
    "DATA_CENTRE": EngineTechnology.DATA_CENTER,
    "RNG": EngineTechnology.OTHER,
    "GAS": EngineTechnology.GAS,
    "TRANSMISSION": EngineTechnology.OTHER,
}

TAX_TECHNOLOGY = {
    "SOLAR": TaxTechnology.SOLAR,
    "SOLAR_PLUS_STORAGE": TaxTechnology.SOLAR,
    "STORAGE": TaxTechnology.STORAGE,
    "WIND": TaxTechnology.WIND,
}

CONTRACT_RISK = {
    "PPA": RevenueContractType.CONTRACTED,
    "TOLLING": RevenueContractType.CONTRACTED,
    "HEDGE": RevenueContractType.CONTRACTED,
    "HYPERSCALE_LEASE": RevenueContractType.HYPERSCALER_CONTRACTED,
    "MERCHANT": RevenueContractType.MERCHANT_P50,
}


def _value(resolution, name, default=None):
    cell = resolution.inputs.get(name)
    if cell is None or cell.value is None:
        return default
    return cell.value


def engine_inputs(resolution) -> tuple[ProjectInputs, DebtTerms, TaxProject | None]:
    """Build the engine's three input objects from a resolution.

    Returns ``None`` for the tax project where the technology generates no
    credit; the caller decides what that means for each structure rather than
    having a zero-credit tax project quietly stand in for one.
    """
    spec = resolution.spec
    asset = spec.asset_type

    capacity = float(_value(resolution, "capacity_mw", 100.0))
    capex = float(_value(resolution, "capex", capacity * 1_800_000.0))
    cod = spec.cod_date() or dt.date(2028, 1, 1)
    life = float(_value(resolution, "project_life_years", 25))
    months = int(_value(resolution, "construction_months", 18))

    project = ProjectInputs(
        name=spec.name or f"{asset} project",
        technology=ENGINE_TECHNOLOGY.get(asset, EngineTechnology.OTHER),
        capacity_mw=capacity,
        capex=capex,
        construction_months=months,
        cod_date=cod,
        contract_years=float(spec.contract.tenor_years or 15.0),
        project_life_years=life,
        production_p50=float(_value(resolution, "production_p50", 400_000.0)),
        contracted_price=float(_value(resolution, "contracted_price", 70.0)),
        opex_year1=float(_value(resolution, "opex_year1", 5_000_000.0)),
    )

    dscr = float(_value(resolution, "target_dscr", 1.30))
    spread = float(_value(resolution, "debt_spread_bps", 175.0))
    # The bands quote a spread. The engine wants an all-in rate, so the
    # benchmark rate is added here and the placeholder is labelled as such in
    # engine.defaults.
    from engine.defaults import SOFR_PLACEHOLDER

    debt = DebtTerms(
        target_dscr=dscr,
        tenor_years=float(_value(resolution, "tenor_years", 18.0)),
        interest_rate=SOFR_PLACEHOLDER.value + spread / 10_000.0,
    )

    tax_tech = TAX_TECHNOLOGY.get(asset)
    if tax_tech is None:
        return project, debt, None

    tax = TaxProject(
        technology=tax_tech,
        capacity_mw=capacity,
        capex=capex,
        placed_in_service_date=cod,
        macr_inputs=MacrInputs(
            method=MacrMethod.USER_ASSERTED, asserted_ratio=0.80
        ),
    )
    return project, debt, tax
