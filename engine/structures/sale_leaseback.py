"""Sale-leaseback.

Norton Rose Fulbright, *Cost of Capital: 2026 Outlook*, lists sale-leaseback as
one of the five live 2026 structures and records that it is **making a
comeback**.
It returns whenever tax equity is scarce or expensive, because it is the only
structure on the list that is effectively **100% financing**: the developer
sells the asset at fair market value and gets its whole cost back in cash at
closing.

The mechanics, and who ends up owning what
------------------------------------------
1. The sponsor builds the asset and **sells it at FMV** to an investor-lessor.
2. The lessor **leases it back** to the sponsor for a stated term.
3. The lessor is the tax owner: it takes the **investment credit** and the
   **depreciation**. The sponsor's only tax item is a **rent deduction**.
4. At expiry the sponsor may buy the asset back at a **fair market value**
   purchase option — and it must be FMV, because a bargain option is the
   classic fact pattern that recharacterises the whole thing as a financing.

**The sponsor no longer owns the tax attributes.** That is the defining
difference from every partnership structure here, and it is asserted directly
in the tests.

The 90-day window that makes or breaks it
------------------------------------------
Under **§50(d)(4)** (carrying forward former §48(b)), a sale and leaseback
completed **within three months** of the date the property was originally placed
in service lets the purchaser-lessor be treated as having placed the property in
service — which is what preserves the investment credit for the lessor. Outside
that window the credit is simply gone: the seller cannot claim it (it disposed
of the property) and the buyer cannot (it did not place it in service). Structura
models the window, and a sale outside it produces a **blocking** risk flag and a
materially higher rent, because the lessor has to earn its yield without a
credit.

The true-lease screen
---------------------
The lease must be a lease. **Rev. Proc. 2001-28** sets the IRS advance-ruling
guidelines: the lessor must have at least a **20% unconditional at-risk
investment**, the asset must have a **residual value of at least 20% of cost**
at expiry, and the lease term must not exceed **80% of the asset's useful
life**. These are ruling guidelines rather than substantive law — a lease that
fails one is not automatically a financing — so Structura runs them and reports
pass/fail rather than asserting a conclusion.

Rent is an output, not an input
-------------------------------
Level annual rent is **solved** with Brent's method so that the lessor earns its
target after-tax IRR on the purchase price, given the credit, the depreciation
and the residual. That is how a lessor actually quotes: it prices to a yield and
the rent falls out.

Declared simplifications (also in ``LIMITS_STRUCTURES.md``)
-----------------------------------------------------------
* The senior construction facility is assumed **repaid out of the sale proceeds
  at closing**, which is the normal outcome; no lessee-level back-leverage is
  modelled.
* Rent is **level**. Real leases are frequently stepped or seasonally shaped,
  and §467 rental-agreement rules (which can force accrual on a stepped lease)
  are not implemented.
* §110 / §162 rent deductibility is assumed; no §467 recharacterisation test is
  run.
* The lessee's purchase option is modelled as exercised at the assumed residual.
  No option-value analysis is performed.
"""

from __future__ import annotations

from dataclasses import dataclass

from scipy.optimize import brentq

from engine.metrics import irr
from engine.structures.defaults import (
    FLIP_SOLVE_MAX_ITER,
    PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR,
    PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT,
    SALE_LEASEBACK_ITC_WINDOW_MONTHS,
    TRUE_LEASE_MAX_TERM_PCT_OF_USEFUL_LIFE,
    TRUE_LEASE_MIN_LESSOR_AT_RISK_PCT,
    TRUE_LEASE_MIN_RESIDUAL_PCT,
)
from engine.structures.models import (
    RiskFlag,
    RiskSeverity,
    SaleLeasebackConfig,
    StructureContext,
    StructureKey,
    StructureResult,
    build_sources_and_uses,
    compute_cash_timing,
    effective_cost_of_capital,
    funding_risk_flags,
    irr_meaningfulness,
)

__all__ = ["TrueLeaseTests", "solve_level_rent", "run_sale_leaseback"]

_CITATIONS = (
    "section-50d4-sale-leaseback-window",
    "rev-proc-2001-28-true-lease",
    "section-50a-recapture",
    "section-50c3-itc-basis-reduction",
)

#: Absolute tolerance, in currency units, on the solved level rent.
_RENT_SOLVE_TOLERANCE = 1e-4


@dataclass(frozen=True, slots=True)
class TrueLeaseTests:
    """Rev. Proc. 2001-28 advance-ruling guidelines, run and reported."""

    lessor_at_risk_pct: float
    lessor_at_risk_passes: bool
    residual_pct: float
    residual_passes: bool
    term_pct_of_useful_life: float
    term_passes: bool

    @property
    def all_pass(self) -> bool:
        return (
            self.lessor_at_risk_passes
            and self.residual_passes
            and self.term_passes
        )

    def failures(self) -> tuple[str, ...]:
        out: list[str] = []
        if not self.lessor_at_risk_passes:
            out.append(
                f"lessor at-risk investment {self.lessor_at_risk_pct:.0%} is "
                f"below the {TRUE_LEASE_MIN_LESSOR_AT_RISK_PCT:.0%} guideline"
            )
        if not self.residual_passes:
            out.append(
                f"residual value {self.residual_pct:.0%} of cost is below the "
                f"{TRUE_LEASE_MIN_RESIDUAL_PCT:.0%} guideline"
            )
        if not self.term_passes:
            out.append(
                f"lease term is {self.term_pct_of_useful_life:.0%} of useful "
                f"life, above the "
                f"{TRUE_LEASE_MAX_TERM_PCT_OF_USEFUL_LIFE:.0%} guideline"
            )
        return tuple(out)


def _lessor_series(
    rent: float,
    *,
    sale_price: float,
    term_years: int,
    itc: float,
    depreciation: tuple[float, ...],
    residual: float,
    tax_rate: float,
) -> tuple[float, ...]:
    """The lessor's after-tax cashflow for a given level rent.

    Index 0 is closing: it pays the purchase price and books the investment
    credit. Each subsequent year it receives rent (taxable) and the tax value of
    its depreciation. The final year adds the residual — realised either through
    the lessee's purchase option or through a sale of the asset.
    """
    flows = [-sale_price + itc]
    for t in range(term_years):
        dep = depreciation[t] if t < len(depreciation) else 0.0
        flows.append(rent * (1.0 - tax_rate) + tax_rate * dep)
    flows[-1] += residual
    return tuple(flows)


def solve_level_rent(
    *,
    sale_price: float,
    term_years: int,
    itc: float,
    depreciation: tuple[float, ...],
    residual: float,
    tax_rate: float,
    target_irr: float,
) -> tuple[float, bool]:
    """Solve the level annual rent that gives the lessor its target yield.

    The lessor's IRR is strictly increasing in rent, so a bracket of
    ``[0, sale_price]`` — a rent equal to the whole purchase price every year
    would be an absurd yield — always contains the root when one exists.
    Returns ``(rent, solved)``; ``solved=False`` means the target is
    unreachable inside the bracket and the bracket end is returned rather than
    an extrapolation.
    """

    def f(rent: float) -> float:
        rate = irr(
            _lessor_series(
                rent,
                sale_price=sale_price,
                term_years=term_years,
                itc=itc,
                depreciation=depreciation,
                residual=residual,
                tax_rate=tax_rate,
            )
        )
        return -1.0 if rate is None else rate - target_irr

    lo, hi = 0.0, max(sale_price, 1.0)
    if f(lo) >= 0.0:
        return 0.0, True
    if f(hi) <= 0.0:
        return hi, False
    root = brentq(f, lo, hi, xtol=_RENT_SOLVE_TOLERANCE, maxiter=FLIP_SOLVE_MAX_ITER)
    return float(root), True


def run_sale_leaseback(
    ctx: StructureContext, config: SaleLeasebackConfig | None = None
) -> StructureResult:
    """Run a sale-leaseback end to end."""
    config = config or SaleLeasebackConfig()
    econ = ctx.economics
    warnings: list[str] = [*econ.warnings]
    risks: list[RiskFlag] = []

    # FMV of the *asset*, which is its construction cost - not total project
    # cost, because IDC, fees and the DSRA are financing items the buyer does
    # not acquire.
    sale_price = config.sale_price if config.sale_price is not None else econ.capex
    term_years = int(min(round(config.lease_term_years), econ.n_years))
    if term_years <= 0:
        return StructureResult(
            key=StructureKey.SALE_LEASEBACK,
            feasible=False,
            infeasible_reason="Lease term rounds to zero years.",
            years=econ.years,
            warnings=tuple(warnings),
            citation_ids=_CITATIONS,
        )
    useful_life = (
        config.asset_useful_life_years
        if config.asset_useful_life_years is not None
        else ctx.project.project_life_years
    )
    residual = sale_price * config.residual_value_pct

    # --- §50(d)(4): the three-month window --------------------------------
    within_window = (
        config.months_after_placed_in_service <= SALE_LEASEBACK_ITC_WINDOW_MONTHS
    )
    itc_to_lessor = econ.itc_amount if within_window else 0.0
    if not within_window and econ.itc_amount > 0.0:
        risks.append(
            RiskFlag(
                code="sale_leaseback_outside_itc_window",
                severity=RiskSeverity.BLOCKING,
                summary=(
                    f"Sale closes {config.months_after_placed_in_service} months "
                    f"after placed in service, outside the "
                    f"{SALE_LEASEBACK_ITC_WINDOW_MONTHS}-month §50(d)(4) window"
                ),
                detail=(
                    f"The ${econ.itc_amount:,.0f} investment credit is lost to "
                    f"both parties: the seller disposed of the property and the "
                    f"purchaser did not place it in service. The lessor must "
                    f"earn its yield from rent and depreciation alone, so rent "
                    f"rises sharply."
                ),
                citation_ids=("section-50d4-sale-leaseback-window",),
            )
        )

    if config.lessor_target_after_tax_irr == (
        PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR.value
    ):
        warnings.append(
            "The lessor's target after-tax IRR of "
            f"{PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR.value:.2%} is a "
            "PLACEHOLDER; lease pricing is not published."
        )
    if config.residual_value_pct == PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT.value:
        warnings.append(
            "The assumed residual value of "
            f"{PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT.value:.0%} of cost is a "
            "PLACEHOLDER set at the Rev. Proc. 2001-28 guideline floor, not a "
            "forecast."
        )

    rent, rent_solved = solve_level_rent(
        sale_price=sale_price,
        term_years=term_years,
        itc=itc_to_lessor,
        depreciation=econ.tax_depreciation,
        residual=residual if config.purchase_option_exercised else 0.0,
        tax_rate=config.lessor_tax_rate,
        target_irr=config.lessor_target_after_tax_irr,
    )
    if not rent_solved:
        risks.append(
            RiskFlag(
                code="lease_rent_unsolvable",
                severity=RiskSeverity.BLOCKING,
                summary="No level rent gives the lessor its target yield",
                detail=(
                    "Even a rent equal to the purchase price every year does not "
                    "reach the target after-tax IRR. The lease is not financeable "
                    "on these assumptions."
                ),
            )
        )

    # --- Rev. Proc. 2001-28 screen ----------------------------------------
    lessor_at_risk_pct = 1.0 if sale_price > 0.0 else 0.0
    term_pct = term_years / useful_life if useful_life > 0 else 1.0
    tests = TrueLeaseTests(
        lessor_at_risk_pct=lessor_at_risk_pct,
        lessor_at_risk_passes=lessor_at_risk_pct
        >= TRUE_LEASE_MIN_LESSOR_AT_RISK_PCT,
        residual_pct=config.residual_value_pct,
        residual_passes=config.residual_value_pct >= TRUE_LEASE_MIN_RESIDUAL_PCT,
        term_pct_of_useful_life=term_pct,
        term_passes=term_pct <= TRUE_LEASE_MAX_TERM_PCT_OF_USEFUL_LIFE,
    )
    if not tests.all_pass:
        risks.append(
            RiskFlag(
                code="true_lease_guideline_failure",
                severity=RiskSeverity.CAUTION,
                summary=(
                    "The lease fails a Rev. Proc. 2001-28 advance-ruling "
                    "guideline"
                ),
                detail=(
                    "Failures: "
                    + "; ".join(tests.failures())
                    + ". These are ruling guidelines, not substantive law - but "
                    "failing one is the fact pattern that gets a lease "
                    "recharacterised as a secured financing, in which case the "
                    "lessor's credit and depreciation both fall away."
                ),
                citation_ids=("rev-proc-2001-28-true-lease",),
            )
        )

    # --- the sponsor as seller-lessee -------------------------------------
    # Construction equity is spent, the asset is sold, and the senior facility
    # is repaid out of the proceeds at closing.
    net_at_close = sale_price - econ.equity_at_cod - econ.debt_at_cod
    sponsor_flows: list[float] = []
    cash_only: list[float] = []
    for i in range(econ.n_years):
        rent_paid = rent if i < term_years else 0.0
        cash = econ.ebitda[i] - rent_paid
        if config.purchase_option_exercised and i == term_years - 1:
            cash -= residual
        taxable = econ.ebitda[i] - rent_paid
        tax_effect = -ctx.sponsor.tax_rate * taxable
        sponsor_flows.append(cash + tax_effect)
        cash_only.append(cash)

    sponsor_cashflow = (net_at_close, *sponsor_flows)
    sponsor_cash_series = (net_at_close, *cash_only)

    # Third-party capital: the lessor's purchase price in at closing, rent and
    # the purchase-option payment out, plus the tax attributes surrendered -
    # the credit at face and the depreciation at the lessor's marginal rate.
    third_party = [sale_price - itc_to_lessor]
    for i in range(econ.n_years):
        flow = -(rent if i < term_years else 0.0)
        dep = econ.tax_depreciation[i] if i < len(econ.tax_depreciation) else 0.0
        flow -= config.lessor_tax_rate * dep
        if config.purchase_option_exercised and i == term_years - 1:
            flow -= residual
        third_party.append(flow)

    sponsor_irr = irr(sponsor_cashflow)
    if sponsor_irr is None:
        warnings.append(
            "The sale proceeds return more than the sponsor's construction "
            "equity at closing, so the sponsor has no net investment and its "
            "IRR is undefined. Rank this structure on NPV and cash timing; a "
            "return on zero equity is not a return."
        )
        risks.append(
            RiskFlag(
                code="no_net_sponsor_equity",
                severity=RiskSeverity.INFO,
                summary="Sponsor has no net equity at risk after the sale",
                detail=(
                    "Sale-leaseback is effectively 100% financing, which is why "
                    "it returns when tax equity is scarce. IRR is not a "
                    "meaningful ranking metric against a structure that leaves "
                    "real equity in the deal."
                ),
            )
        )

    risks.append(
        RiskFlag(
            code="tax_attributes_transferred",
            severity=RiskSeverity.INFO,
            summary="The sponsor retains no tax attributes",
            detail=(
                f"The lessor is the tax owner and takes the "
                f"${itc_to_lessor:,.0f} investment credit and all "
                f"${sum(econ.tax_depreciation):,.0f} of depreciation. The "
                f"sponsor's only tax item is its rent deduction. Any §50(a) "
                f"recapture in the first five years also sits with the lessor."
            ),
            citation_ids=("section-50a-recapture",),
        )
    )

    # --- sources and uses --------------------------------------------------
    # The sponsor **builds** the asset before it sells it: construction is
    # funded by the senior facility and the sponsor's own equity, exactly as in
    # a single-owner deal. The lessor's purchase price arrives at closing of the
    # sale, after the asset exists, and is used to repay the facility and return
    # the construction equity. It refinances the stack; it does not fund it.
    # Counting it as construction capital would double-count the senior debt.
    sources = build_sources_and_uses(
        econ,
        third_party_equity=0.0,
        sponsor_equity=econ.equity_at_cod,
        post_cod_monetisation=sale_price,
        post_cod_monetisation_note=(
            f"The lessor pays ${sale_price:,.0f} at the sale, "
            f"{config.months_after_placed_in_service} month(s) after the property "
            f"was placed in service. Out of it the ${econ.debt_at_cod:,.0f} senior "
            f"facility is repaid and ${econ.equity_at_cod:,.0f} of construction "
            f"equity is returned, leaving the sponsor "
            f"${net_at_close:,.0f} net at closing. It is a refinancing of a "
            f"completed asset, not a source of construction funding."
        ),
    )
    risks.extend(funding_risk_flags(sources))

    timing = compute_cash_timing(sponsor_cashflow)
    meaningful, meaningful_reason = irr_meaningfulness(
        sponsor_after_tax_irr=sponsor_irr,
        sponsor_equity_required=max(-net_at_close, 0.0),
        funding_requirement=sources.uses_total,
        payback_years=timing.payback_years,
    )

    return StructureResult(
        key=StructureKey.SALE_LEASEBACK,
        feasible=rent_solved,
        infeasible_reason=(
            "" if rent_solved else "No level rent reaches the lessor's target yield."
        ),
        sponsor_after_tax_irr=sponsor_irr,
        sponsor_npv=sum(
            cf / (1.0 + ctx.discount_rate) ** i
            for i, cf in enumerate(sponsor_cashflow)
        ),
        effective_cost_of_capital=effective_cost_of_capital(third_party),
        sponsor_equity_required=max(-net_at_close, 0.0),
        third_party_capital_raised=sources.third_party_construction_capital,
        total_capital_raised=sources.sources_total,
        post_cod_monetisation=sources.post_cod_monetisation,
        sources_and_uses=sources,
        sponsor_irr_is_meaningful=meaningful,
        sponsor_irr_not_meaningful_reason=meaningful_reason,
        years=econ.years,
        sponsor_cashflow=sponsor_cashflow,
        sponsor_cash_only=sponsor_cash_series,
        third_party_cashflow=tuple(third_party),
        cash_timing=timing,
        credit_transferred=itc_to_lessor,
        credit_retained=0.0,
        detail={
            "sale_price": sale_price,
            "level_rent": rent,
            "lease_term_years": float(term_years),
            "residual_value": residual,
            "itc_to_lessor": itc_to_lessor,
            "net_cash_at_closing": net_at_close,
            "total_rent_paid": rent * term_years,
            "lessor_target_irr": config.lessor_target_after_tax_irr,
            "true_lease_term_pct_of_useful_life": term_pct,
            "true_lease_residual_pct": config.residual_value_pct,
            "within_50d4_window": 1.0 if within_window else 0.0,
        },
        risks=tuple(risks),
        warnings=tuple(dict.fromkeys(warnings)),
        citation_ids=_CITATIONS,
    )
