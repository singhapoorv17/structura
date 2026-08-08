"""Partnership flip — yield-based and fixed-date — on real capital accounts.

The structure
-------------
A sponsor and a tax-equity investor form an LLC taxed as a partnership. Before
the **flip point** the investor takes the large share of income, loss, credits
and cash — classically 99%. After the flip point the ratios invert,
classically to 5/95, and the sponsor takes essentially all of the economics. In
a **yield-based** flip the flip happens when the investor's *after-tax IRR*
reaches a contracted target; in a **fixed-date** flip it happens on a stated
date regardless.

Cash is modelled as a **separate ratio** from income, loss and credits, because
it is separate in every real LLC agreement — a wind PTC deal commonly runs a
much lower pre-flip cash share than its 99% income share. That flexibility has
a consequence the solver has to police: if the pre-flip cash share is low enough
that the investor's after-tax flow turns *negative* once the first-year loss is
used up, the investor's cashflow series changes sign more than once and its IRR
is no longer unique. :func:`run_flip` counts the sign changes and warns.

Traditional tax equity of this kind was ~30% of the market in 2024 and less in
2025 (Norton Rose Fulbright, *Cost of Capital: 2026 Outlook*), so it is no
longer the default structure, but it remains the chassis on which the T-flip is
built.

Why the yield-based solve is genuinely circular
-----------------------------------------------
The investor's return depends on how long it holds 99% of the tax items, which
is the flip date; the flip date is defined as the moment the return reaches the
target. Structura resolves it the way the debt circularity is resolved in Phase
1 — numerically and deterministically, with Brent's method
(:func:`scipy.optimize.brentq`) on an explicit bracket.

To give Brent a continuous function to work on, the flip point is allowed to
fall **inside** a period: for flip point ``T`` and period ``p`` (zero-indexed),
the pre-flip weight is ``clamp(T - p, 0, 1)`` and that period's sharing ratios
are the weighted blend of the pre- and post-flip ratios. At integer ``T`` this
reduces exactly to a clean period boundary, and in between the investor's IRR
moves smoothly, so the root is well defined. Monotonicity — a later flip is
worth more to the investor — is asserted in the tests.

What makes this different from SAM's flip
-----------------------------------------
SAM applies the sharing ratios as fixed percentages of pre-computed cashflow;
a grep of its three finance modules returns zero hits for ``capital_account``,
``deficit_restoration``, ``outside_basis`` or ``suspended_loss``.
Here the ratios are fed into :func:`engine.structures.partnership.run_partnership`
and every allocation is tested against the investor's DRO cap. When the
investor's §704(b) capital account hits its floor, losses **reallocate to the
sponsor**, the investor's tax benefit stops, and the flip point moves out. That
is the behaviour a tax-equity investor actually underwrites, and it is not a
percentage split.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from scipy.optimize import brentq

from engine.metrics import irr
from engine.structures.defaults import (
    FLIP_SOLVE_MAX_ITER,
    FLIP_SOLVE_TOLERANCE,
    ITC_RECAPTURE_PERIOD_YEARS,
    PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR,
    PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR,
)
from engine.structures.models import (
    FlipTrigger,
    RiskFlag,
    RiskSeverity,
    StructureContext,
    StructureKey,
    StructureResult,
    build_sources_and_uses,
    capital_account_risk_flags,
    compute_cash_timing,
    effective_cost_of_capital,
    funding_risk_flags,
    irr_meaningfulness,
    partner_after_tax_flows,
    recapture_risk_flag,
)
from engine.structures.models import FlipConfig
from engine.structures.partnership import (
    PartnerRole,
    PartnerTerms,
    PartnershipResult,
    PeriodInputs,
    SharingRatios,
    run_partnership,
)

__all__ = [
    "SPONSOR",
    "TAX_EQUITY",
    "FlipSolve",
    "flip_sharing_ratios",
    "build_flip_partnership",
    "solve_flip_point",
    "run_flip",
]

#: Partner names used throughout the flip and T-flip structures.
SPONSOR = "sponsor"
TAX_EQUITY = "tax_equity"

_CITATIONS = (
    "reg-1-704-1b2iv-capital-accounts",
    "reg-1-704-1b2iid-alternate-economic-effect",
    "reg-1-704-2-minimum-gain",
    "section-704d-basis-limitation",
    "section-50a-recapture",
    "section-50c3-itc-basis-reduction",
    "rev-proc-2007-65-flip-guidelines",
)


@dataclass(frozen=True, slots=True)
class FlipSolve:
    """Outcome of the yield-based flip-point root find."""

    flip_year: float
    solved: bool
    achieved_investor_irr: float | None
    target_irr: float
    reason: str


def _blend(pre: float, post: float, weight: float) -> float:
    return weight * pre + (1.0 - weight) * post


def flip_sharing_ratios(
    config: FlipConfig, n_years: int, flip_year: float
) -> tuple[SharingRatios, ...]:
    """One :class:`SharingRatios` per year for a given flip point.

    ``flip_year`` is measured in operating years from COD. ``flip_year = 6``
    means years 1-6 (indices 0-5) are fully pre-flip and year 7 onwards is
    fully post-flip. Fractional values blend the two ratio sets within the year
    that straddles the flip, which is what makes the solve continuous.
    """
    out: list[SharingRatios] = []
    for p in range(n_years):
        w = min(max(flip_year - p, 0.0), 1.0)
        te_income = _blend(config.pre_flip_te_income, config.post_flip_te_income, w)
        te_loss = _blend(config.pre_flip_te_loss, config.post_flip_te_loss, w)
        te_credit = _blend(config.pre_flip_te_credit, config.post_flip_te_credit, w)
        te_cash = _blend(config.pre_flip_te_cash, config.post_flip_te_cash, w)
        out.append(
            SharingRatios(
                income={TAX_EQUITY: te_income, SPONSOR: 1.0 - te_income},
                loss={TAX_EQUITY: te_loss, SPONSOR: 1.0 - te_loss},
                credit={TAX_EQUITY: te_credit, SPONSOR: 1.0 - te_credit},
                cash={TAX_EQUITY: te_cash, SPONSOR: 1.0 - te_cash},
            )
        )
    return tuple(out)


def build_flip_partnership(
    ctx: StructureContext,
    config: FlipConfig,
    *,
    flip_year: float,
    investor_commitment: float,
    credit_in_partnership: float | None = None,
    extra_cash_by_year: Mapping[int, float] | None = None,
) -> PartnershipResult:
    """Run the §704(b) ledger for a flip at a given flip point.

    Parameters
    ----------
    credit_in_partnership
        Credit **retained** inside the partnership and allocated to the
        partners. ``None`` means the whole credit. A T-flip passes the retained
        remainder here after selling the rest under §6418.
    extra_cash_by_year
        Additional cash paid into the partnership in a given year — used by the
        T-flip when the transfer proceeds are contributed to the project rather
        than paid to the sponsor.

    The §50(c)(3) basis reduction is applied **whether or not the credit is
    transferred**: §6418 moves the credit, not the basis adjustment, so the
    partnership's depreciable and book basis fall by half the credit either way.
    """
    econ = ctx.economics
    n = econ.n_years
    partners = (
        PartnerTerms(
            name=SPONSOR,
            role=PartnerRole.SPONSOR,
            tax_rate=ctx.sponsor.tax_rate,
            unlimited_dro=config.sponsor_unlimited_dro,
            bears_residual_allocations=True,
        ),
        PartnerTerms(
            name=TAX_EQUITY,
            role=PartnerRole.TAX_EQUITY,
            tax_rate=config.investor_tax_rate,
            dro_cap=config.investor_dro_cap,
        ),
    )

    sponsor_commitment = max(econ.equity_at_cod - investor_commitment, 0.0)
    taxable = econ.taxable_income()
    book = econ.book_income()
    basis_series = econ.book_basis()
    credit_total = (
        econ.itc_amount if credit_in_partnership is None else credit_in_partnership
    )
    extra = dict(extra_cash_by_year or {})

    rows: list[PeriodInputs] = []
    for i in range(n):
        credit = econ.ptc_by_year[i]
        reduction = 0.0
        if i == econ.credit_year_index:
            credit += credit_total
            reduction = econ.itc_basis_reduction
        rows.append(
            PeriodInputs(
                period=i,
                year=econ.years[i],
                book_income=book[i],
                taxable_income=taxable[i],
                credit=credit,
                itc_basis_reduction=reduction,
                cash_available=econ.distributable_cash[i] + extra.get(i, 0.0),
                contributions=(
                    {SPONSOR: sponsor_commitment, TAX_EQUITY: investor_commitment}
                    if i == 0
                    else {}
                ),
                nonrecourse_liability=econ.debt_balance[i],
                book_basis=basis_series[i],
            )
        )

    return run_partnership(
        partners,
        rows,
        flip_sharing_ratios(config, n, flip_year),
        initial_book_basis=econ.capex,
        initial_nonrecourse_liability=econ.debt_at_cod,
    )


def investor_after_tax_series(
    partnership: PartnershipResult,
    *,
    investor_commitment: float,
    tax_rate: float,
    extra_investor_flows: Sequence[float] | None = None,
) -> tuple[float, ...]:
    """The investor's IRR series: commitment at t=0, after-tax flows thereafter.

    The investor funds at financial close and is paid in three currencies —
    cash distributions, the tax value of allocated losses, and credits. A
    tax-equity investor's yield is mostly the last two, which is exactly why a
    model that only splits cash cannot price one.
    """
    flows = partner_after_tax_flows(
        partnership, TAX_EQUITY, tax_rate=tax_rate
    )
    if extra_investor_flows is not None:
        flows = tuple(
            f + (extra_investor_flows[i] if i < len(extra_investor_flows) else 0.0)
            for i, f in enumerate(flows)
        )
    return (-investor_commitment, *flows)


def solve_flip_point(
    ctx: StructureContext,
    config: FlipConfig,
    *,
    investor_commitment: float,
    credit_in_partnership: float | None = None,
    extra_cash_by_year: Mapping[int, float] | None = None,
) -> FlipSolve:
    """Find the flip point at which the investor exactly hits its target yield.

    ``f(T) = investor_after_tax_IRR(T) - target`` is continuous and increasing
    in ``T`` (a later flip leaves the investor holding 99% of the tax items for
    longer). Brent's method is run on ``[0, n_years]``:

    * ``f(0) >= 0`` — the target is met even with an immediate flip, so the
      flip point is 0 and the sponsor should be negotiating a *higher* target.
    * ``f(n) <= 0`` — the target cannot be reached inside the modelled life.
      The solve reports ``solved=False`` and pins the flip at the end of the
      model rather than returning a number that does not exist. **It never
      extrapolates.**
    """
    target = config.target_after_tax_irr
    n = float(ctx.economics.n_years)

    if investor_commitment <= 0.0:
        return FlipSolve(
            flip_year=0.0,
            solved=False,
            achieved_investor_irr=None,
            target_irr=target,
            reason=(
                "No tax-equity commitment: there is nothing to flip. With no "
                "credit and no investment the structure is a single-owner deal."
            ),
        )

    def achieved(t: float) -> float | None:
        partnership = build_flip_partnership(
            ctx,
            config,
            flip_year=t,
            investor_commitment=investor_commitment,
            credit_in_partnership=credit_in_partnership,
            extra_cash_by_year=extra_cash_by_year,
        )
        return irr(
            investor_after_tax_series(
                partnership,
                investor_commitment=investor_commitment,
                tax_rate=config.investor_tax_rate,
            )
        )

    def f(t: float) -> float:
        rate = achieved(t)
        if rate is None:
            # No sign change in the investor's series: it never gets its money
            # back at any rate. Treat as arbitrarily far below target.
            return -1.0
        return rate - target

    f_lo = f(0.0)
    if f_lo >= 0.0:
        return FlipSolve(
            flip_year=0.0,
            solved=True,
            achieved_investor_irr=achieved(0.0),
            target_irr=target,
            reason=(
                "The investor clears its target yield even with an immediate "
                "flip; the flip point is the start of operations."
            ),
        )
    f_hi = f(n)
    if f_hi <= 0.0:
        return FlipSolve(
            flip_year=n,
            solved=False,
            achieved_investor_irr=achieved(n),
            target_irr=target,
            reason=(
                f"The investor cannot reach a {target:.2%} after-tax IRR before "
                f"the end of the modelled {int(n)}-year life even holding the "
                f"pre-flip ratios throughout. The deal does not clear at this "
                f"target and commitment; no flip date is reported."
            ),
        )

    root = brentq(f, 0.0, n, xtol=FLIP_SOLVE_TOLERANCE, maxiter=FLIP_SOLVE_MAX_ITER)
    return FlipSolve(
        flip_year=float(root),
        solved=True,
        achieved_investor_irr=achieved(float(root)),
        target_irr=target,
        reason=(
            f"Solved: the tax-equity investor reaches its {target:.2%} after-tax "
            f"IRR in operating year {root:.2f}, at which point the sharing "
            f"ratios flip."
        ),
    )


def run_flip(
    ctx: StructureContext,
    config: FlipConfig | None = None,
    *,
    key: StructureKey = StructureKey.PARTNERSHIP_FLIP,
    credit_in_partnership: float | None = None,
    credit_transferred: float = 0.0,
    transfer_net_proceeds: float = 0.0,
    transfer_year_index: int = 0,
    proceeds_to_partnership: bool = False,
    extra_risks: Sequence[RiskFlag] = (),
    extra_warnings: Sequence[str] = (),
) -> StructureResult:
    """Run a partnership flip end to end and return the common result shape.

    The T-flip in :mod:`engine.structures.tflip` calls straight through to this
    function with a reduced ``credit_in_partnership`` and the transfer leg
    supplied — a T-flip *is* a flip with a transfer bolted on, and the code says
    so rather than duplicating 200 lines.
    """
    config = config or FlipConfig()
    econ = ctx.economics
    warnings: list[str] = [*econ.warnings, *extra_warnings]
    risks: list[RiskFlag] = list(extra_risks)

    commitment = config.investor_commitment_for(econ.itc_amount, econ.equity_at_cod)
    if config.investor_commitment is None:
        warnings.append(
            "Tax-equity commitment was derived from the credit at "
            f"{PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR.value:.2f} per $1 of "
            "ITC. That ratio is a PLACEHOLDER - no public source prices tax "
            "equity. See LIMITS_STRUCTURES.md."
        )

    extra_cash = (
        {transfer_year_index: transfer_net_proceeds}
        if proceeds_to_partnership and transfer_net_proceeds > 0.0
        else None
    )

    if config.trigger is FlipTrigger.YIELD_BASED:
        solve = solve_flip_point(
            ctx,
            config,
            investor_commitment=commitment,
            credit_in_partnership=credit_in_partnership,
            extra_cash_by_year=extra_cash,
        )
        if config.target_after_tax_irr == PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR.value:
            warnings.append(
                "The target tax-equity after-tax IRR of "
                f"{PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR.value:.2%} is a "
                "PLACEHOLDER. It is the single most important input to a "
                "yield-based flip and no public source publishes it."
            )
    else:
        flip_year = min(config.fixed_flip_year, float(econ.n_years))
        partnership_probe = build_flip_partnership(
            ctx,
            config,
            flip_year=flip_year,
            investor_commitment=commitment,
            credit_in_partnership=credit_in_partnership,
            extra_cash_by_year=extra_cash,
        )
        solve = FlipSolve(
            flip_year=flip_year,
            solved=True,
            achieved_investor_irr=irr(
                investor_after_tax_series(
                    partnership_probe,
                    investor_commitment=commitment,
                    tax_rate=config.investor_tax_rate,
                )
            ),
            target_irr=config.target_after_tax_irr,
            reason=(
                f"Fixed-date flip in operating year {flip_year:.2f}. The yield "
                f"risk sits with the investor, not the sponsor."
            ),
        )

    if commitment <= 0.0:
        return StructureResult(
            key=key,
            feasible=False,
            infeasible_reason=solve.reason,
            years=econ.years,
            warnings=tuple(warnings),
            citation_ids=_CITATIONS,
        )

    partnership = build_flip_partnership(
        ctx,
        config,
        flip_year=solve.flip_year,
        investor_commitment=commitment,
        credit_in_partnership=credit_in_partnership,
        extra_cash_by_year=extra_cash,
    )
    warnings.extend(partnership.warnings)

    # Descartes' rule of signs: an IRR is unique only if the series changes
    # sign once. A pre-flip cash share too low to cover the tax on the
    # investor's income allocation produces a second sign change, and the
    # reported yield stops meaning what it appears to mean.
    investor_series = investor_after_tax_series(
        partnership,
        investor_commitment=commitment,
        tax_rate=config.investor_tax_rate,
    )
    sign_changes = sum(
        1
        for a, b in zip(investor_series, investor_series[1:])
        if a * b < 0.0
    )
    if sign_changes > 1:
        warnings.append(
            f"The tax-equity investor's after-tax cashflow changes sign "
            f"{sign_changes} times, so its IRR is not unique and the solved "
            f"flip point is only one of several roots. This happens when the "
            f"pre-flip cash share ({config.pre_flip_te_cash:.0%}) is too low to "
            f"cover the tax on the investor's income share "
            f"({config.pre_flip_te_income:.0%}). Raise the cash share or model "
            f"the flip on a fixed date."
        )

    sponsor_commitment = max(econ.equity_at_cod - commitment, 0.0)
    sponsor_flows = partner_after_tax_flows(
        partnership,
        SPONSOR,
        tax_rate=ctx.sponsor.tax_rate,
        can_use_credits=ctx.sponsor.can_use_credits,
        can_use_losses=ctx.sponsor.can_use_depreciation,
    )
    sponsor_cash_only = list(partnership.distributions(SPONSOR))

    # A §6418 transfer paid directly to the sponsor is sponsor cash, not
    # partnership cash, and lands outside the capital accounts.
    direct_proceeds = [0.0] * econ.n_years
    if transfer_net_proceeds > 0.0 and not proceeds_to_partnership:
        idx = min(transfer_year_index, econ.n_years - 1)
        direct_proceeds[idx] = transfer_net_proceeds

    sponsor_cashflow = (
        -sponsor_commitment,
        *(
            sponsor_flows[i] + direct_proceeds[i]
            for i in range(econ.n_years)
        ),
    )
    sponsor_cash_series = (
        -sponsor_commitment,
        *(sponsor_cash_only[i] + direct_proceeds[i] for i in range(econ.n_years)),
    )

    # --- effective cost of capital ---------------------------------------
    investor_flows = partner_after_tax_flows(
        partnership, TAX_EQUITY, tax_rate=config.investor_tax_rate
    )
    debt_service = tuple(
        econ.interest[i] + econ.principal[i] for i in range(econ.n_years)
    )
    third_party = [econ.debt_at_cod + commitment + transfer_net_proceeds]
    for i in range(econ.n_years):
        surrendered = 0.0
        if i == min(transfer_year_index, econ.n_years - 1):
            surrendered += credit_transferred
        third_party.append(-(debt_service[i] + investor_flows[i] + surrendered))

    sponsor_irr = irr(sponsor_cashflow)
    npv_rate = ctx.discount_rate
    sponsor_npv = sum(
        cf / (1.0 + npv_rate) ** i for i, cf in enumerate(sponsor_cashflow)
    )

    # --- sources and uses --------------------------------------------------
    # The tax-equity commitment funds construction. §6418 transfer proceeds do
    # not: the credit does not exist until the property is placed in service,
    # so a transfer settles post-PIS and reimburses capital already committed.
    # Counting it as construction funding is what makes sources exceed uses.
    sources = build_sources_and_uses(
        econ,
        third_party_equity=commitment,
        sponsor_equity=sponsor_commitment,
        post_cod_monetisation=transfer_net_proceeds,
        post_cod_monetisation_note=(
            (
                f"§6418 transfer proceeds of ${transfer_net_proceeds:,.0f} settle "
                f"in operating year {min(transfer_year_index, econ.n_years - 1) + 1}, "
                f"after the property is placed in service. They are "
                + (
                    "contributed to the partnership and distributed on the cash "
                    "sharing ratio"
                    if proceeds_to_partnership
                    else "paid to the sponsor outside the capital accounts"
                )
                + " - a reimbursement of committed capital, not a source of "
                "construction funding. Funding construction against an expected "
                "credit requires an ITC bridge loan, which Structura "
                "does not model."
            )
            if transfer_net_proceeds > 0.0
            else ""
        ),
    )
    risks.extend(funding_risk_flags(sources))
    risks.extend(capital_account_risk_flags(partnership))

    meaningful, meaningful_reason = irr_meaningfulness(
        sponsor_after_tax_irr=sponsor_irr,
        sponsor_equity_required=sponsor_commitment,
        funding_requirement=sources.uses_total,
        payback_years=compute_cash_timing(sponsor_cashflow).payback_years,
    )

    # --- risks -------------------------------------------------------------
    if econ.itc_amount > 0.0:
        risks.append(
            recapture_risk_flag(
                econ.itc_amount, key, party="the tax-equity investor"
            )
        )
        if solve.flip_year < ITC_RECAPTURE_PERIOD_YEARS:
            risks.append(
                RiskFlag(
                    code="flip_inside_recapture_period",
                    severity=RiskSeverity.BLOCKING,
                    summary=(
                        f"Flip point falls in year {solve.flip_year:.2f}, inside "
                        f"the {ITC_RECAPTURE_PERIOD_YEARS}-year §50(a) recapture "
                        f"period"
                    ),
                    detail=(
                        "A reduction of the investor's interest by more than one "
                        "third inside five years triggers recapture of the "
                        "unvested credit. Real flip dates are negotiated to land "
                        "after year five for exactly this reason; this result "
                        "should be treated as not executable as drawn."
                    ),
                    citation_ids=("section-50a-recapture",),
                )
            )

    te_floor_hits = sum(
        1
        for period in partnership.periods
        if period.partner(TAX_EQUITY).floor_binds
    )
    if te_floor_hits:
        risks.append(
            RiskFlag(
                code="dro_cap_reallocation",
                severity=RiskSeverity.CAUTION,
                summary=(
                    f"The investor's DRO cap bound in {te_floor_hits} of "
                    f"{econ.n_years} years"
                ),
                detail=(
                    "Losses that would have driven the investor's §704(b) "
                    "capital account below "
                    f"-(DRO {config.investor_dro_cap:,.0f} + its share of "
                    "partnership minimum gain) were reallocated to the sponsor. "
                    "The investor's tax benefit stops there, which pushes the "
                    "flip point out and is the mechanic SAM's percentage split "
                    "cannot represent."
                ),
                citation_ids=("reg-1-704-1b2iid-alternate-economic-effect",),
            )
        )

    suspended_final = partnership.suspended_losses(SPONSOR)[-1]
    if suspended_final > 0.0:
        risks.append(
            RiskFlag(
                code="suspended_losses_outstanding",
                severity=RiskSeverity.INFO,
                summary=(
                    f"${suspended_final:,.0f} of sponsor loss remains suspended "
                    f"under §704(d) at the end of the model"
                ),
                detail=(
                    "Losses in excess of outside basis are carried forward "
                    "indefinitely and freed as basis is restored. They are not "
                    "lost, but they are not deducted inside the modelled life "
                    "and therefore do not appear in the sponsor's IRR."
                ),
                citation_ids=("section-704d-basis-limitation",),
            )
        )

    if not solve.solved:
        risks.append(
            RiskFlag(
                code="flip_target_unreachable",
                severity=RiskSeverity.BLOCKING,
                summary="The investor's target yield is not reachable",
                detail=solve.reason,
            )
        )

    return StructureResult(
        key=key,
        feasible=solve.solved,
        infeasible_reason="" if solve.solved else solve.reason,
        sponsor_after_tax_irr=sponsor_irr,
        sponsor_npv=sponsor_npv,
        effective_cost_of_capital=effective_cost_of_capital(third_party),
        sponsor_equity_required=sponsor_commitment,
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
        cash_timing=compute_cash_timing(sponsor_cashflow),
        flip_year=solve.flip_year,
        flip_solved=solve.solved,
        investor_achieved_irr=solve.achieved_investor_irr,
        credit_transferred=credit_transferred,
        credit_retained=(
            econ.itc_amount if credit_in_partnership is None else credit_in_partnership
        ),
        transfer_net_proceeds=transfer_net_proceeds,
        partnership=partnership,
        detail={
            "investor_commitment": commitment,
            "investor_target_irr": config.target_after_tax_irr,
            "flip_year": solve.flip_year,
            "te_dro_cap": config.investor_dro_cap,
            "te_floor_binding_years": float(te_floor_hits),
            "sponsor_suspended_loss_final": suspended_final,
            "investor_final_capital_account": (
                partnership.capital_account(TAX_EQUITY)[-1]
            ),
            "sponsor_final_capital_account": (
                partnership.capital_account(SPONSOR)[-1]
            ),
        },
        risks=tuple(risks),
        warnings=tuple(dict.fromkeys(warnings)),
        citation_ids=_CITATIONS,
    )
