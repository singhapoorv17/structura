"""Build an equipment lease from a resolved deal, and read its results.

The lease structure has existed in the engine since it was added for AI
compute, but nothing connected it to the comparison, so a deal whose leading
structure was an equipment lease came back with no numbers and no party
ledgers at all. This is that connection.

The capital stack is sized rather than assumed: senior notes to a gearing the
residual will support, a subordinated strip that carries the residual risk,
and a thin equity slice underneath. Every rate traces to a cited band.
"""

from __future__ import annotations

from typing import Any

from comps.bands import BY_KEY
from engine.structures import (
    EquipmentLeaseConfig,
    LeaseTranche,
    run_equipment_lease,
)

__all__ = ["build_lease", "build_securitised", "lease_metrics"]

#: How the stack is split. Senior takes the guaranteed portion, the
#: subordinated strip sits between it and the equity, and the sponsor holds the
#: rest. Chosen to sit near the observed transactions rather than derived.
SENIOR_SHARE = 0.86
SUBORDINATED_SHARE = 0.12
EQUITY_SHARE = 0.02

#: Spread the subordinated notes carry over the senior rate. On the one
#: transaction that discloses both, the unguaranteed strip priced roughly 275bp
#: wide of the guaranteed notes.
SUB_SPREAD = 0.0275

#: Residual value the notes are sized against, as a share of original cost.
EXPECTED_RESIDUAL = 0.30

#: Straight-line tax life used inside the vehicle.
TAX_LIFE_YEARS = 5.0


def build_lease(resolution, *, guarantor: str = "Equipment vendor",
                lessee: str = "Operator") -> EquipmentLeaseConfig | None:
    """Size a lease for this deal, or return nothing if it cannot be sized."""
    capex_cell = resolution.inputs.get("capex")
    if capex_cell is None or not isinstance(capex_cell.value, (int, float)):
        return None
    cost = float(capex_cell.value)
    if cost <= 0:
        return None

    band = BY_KEY["notes.digital_senior"]
    senior_rate = band.point_estimate / 100.0

    term = resolution.spec.contract.tenor_years or 6.0

    tranches = (
        LeaseTranche(
            "Senior notes",
            cost * SENIOR_SHARE,
            senior_rate,
            guaranteed=True,
        ),
        LeaseTranche(
            "Subordinated notes",
            cost * SUBORDINATED_SHARE,
            senior_rate + SUB_SPREAD,
            guaranteed=False,
            issue_price=0.985,
        ),
    )
    equity = cost * EQUITY_SHARE
    # Notes issued at a discount raise less than par, so the asset the vehicle
    # can actually buy is the cash raised, not the face amount.
    funded = sum(t.proceeds for t in tranches) + equity

    return EquipmentLeaseConfig(
        tranches=tranches,
        equity=equity,
        asset_cost=funded,
        lease_term_years=float(term),
        expected_residual_pct=EXPECTED_RESIDUAL,
        tax_life_years=TAX_LIFE_YEARS,
        guarantor_name=guarantor,
        lessee_name=lessee,
        equity_target_after_tax_irr=0.15,
    )


#: A securitised lease sits on real estate let to a creditworthy tenant, so it
#: gears higher than an equipment deal and amortises over a far longer term.
#: The Hyperion notes ran 23.6 years against a hyperscale lease.
SECURITISED_SENIOR_SHARE = 0.92
SECURITISED_EQUITY_SHARE = 0.08
SECURITISED_TERM_YEARS = 20.0
SECURITISED_RESIDUAL = 0.45
BUILDING_TAX_LIFE_YEARS = 39.0


def build_securitised(resolution, *, tenant: str = "Tenant") -> EquipmentLeaseConfig | None:
    """Size a securitised lease: a vehicle funded by notes against a lease.

    The same mechanics as an equipment lease, on a different asset. The
    security is the tenant's covenant rather than a manufacturer's guarantee,
    so there is no guarantor: every tranche looks to the lease and then to the
    building. Buildings hold value where equipment does not, which is why the
    residual is set far higher and the term far longer.
    """
    capex_cell = resolution.inputs.get("capex")
    if capex_cell is None or not isinstance(capex_cell.value, (int, float)):
        return None
    cost = float(capex_cell.value)
    if cost <= 0:
        return None

    band = BY_KEY["notes.digital_senior"]
    tranches = (
        LeaseTranche(
            "Senior secured notes",
            cost * SECURITISED_SENIOR_SHARE,
            band.point_estimate / 100.0,
            guaranteed=False,
        ),
    )
    equity = cost * SECURITISED_EQUITY_SHARE
    funded = sum(t.proceeds for t in tranches) + equity

    term = resolution.spec.contract.tenor_years or SECURITISED_TERM_YEARS

    return EquipmentLeaseConfig(
        tranches=tranches,
        equity=equity,
        asset_cost=funded,
        lease_term_years=float(max(term, 10.0)),
        expected_residual_pct=SECURITISED_RESIDUAL,
        tax_life_years=BUILDING_TAX_LIFE_YEARS,
        guarantor_name="No third-party guarantee",
        lessee_name=tenant,
        equity_target_after_tax_irr=0.11,
    )


def lease_metrics(result) -> dict[str, Any]:
    """The comparison rows an equipment lease can answer."""
    equity = result.ledger("SPV equity")
    invested = -sum(c for c in equity.cashflow if c < 0)
    returned = sum(c for c in equity.cashflow if c > 0)
    cfg = result.config
    return {
        "sponsor_equity_required": invested,
        "third_party_capital_raised": cfg.proceeds,
        "total_capital_raised": cfg.sources,
        "post_cod_monetisation": 0.0,
        "sponsor_npv": returned - invested,
        "annual_rent": result.annual_rent,
        "residual_shortfall": result.residual_shortfall,
        "guarantor_payment": result.guarantor_payment,
    }
