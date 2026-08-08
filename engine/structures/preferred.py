"""Preferred equity partnership — priority return, redemption, then common.

**15% of ITC gross value in 2025** (Crux), and named by Norton Rose Fulbright,
*Cost of Capital: 2026 Outlook*, as one of the five live structures — with the
observation that *"most current deals employ hybrid or preferred equity
structures"*.

The structure sits between debt and a flip. A preferred investor contributes
capital, takes a **stated preferred return** on unreturned capital, is
**redeemed** ahead of the sponsor's common interest, and normally also takes the
tax attributes on a stated sharing ratio. Unlike a flip there is no yield-based
trigger: the investor's return is contractual, and the switch to the residual
sharing ratio happens when the preferred is redeemed in full.

Unlike debt, and this is the point, the preferred is **partnership equity**:
the allocations run through §704(b) capital accounts and are subject to the same
DRO cap and minimum-gain mechanics as a flip. That is why it is modelled here on
the same engine and not as a second debt tranche.

The cash waterfall inside the partnership
-----------------------------------------
Per year, out of the cash the project waterfall releases to equity:

1. **Current preferred return** on unreturned capital (compounding on unpaid
   amounts if elected — the market norm, because an unpaid preferred that does
   not compound is an interest-free loan to the sponsor).
2. **Redemption** of unreturned capital.
3. Everything else to the sponsor's common.

``cash_priority_share`` throttles how much of each year's cash the preferred can
reach, which is how a real deal keeps some cash flowing to the sponsor during
the preferred period.

Declared simplification
-----------------------
The preferred is modelled as a **partnership interest**, not as a redeemable
instrument that might be recharacterised as debt for tax purposes. Whether a
particular preferred is equity or disguised debt is a facts-and-circumstances
question Structura does not attempt; it is recorded in
``LIMITS_STRUCTURES.md``.
"""

from __future__ import annotations

from engine.metrics import irr
from engine.structures.defaults import (
    PLACEHOLDER_MAX_INVESTOR_SHARE_OF_EQUITY,
    PLACEHOLDER_PREFERRED_RETURN,
    PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR,
)
from engine.structures.models import (
    PreferredConfig,
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
from engine.structures.partnership import (
    PartnerRole,
    PartnerTerms,
    PeriodInputs,
    SharingRatios,
    run_partnership,
)

__all__ = ["SPONSOR", "PREFERRED", "preferred_cash_schedule", "run_preferred"]

SPONSOR = "sponsor"
PREFERRED = "preferred"

_CITATIONS = (
    "reg-1-704-1b2iv-capital-accounts",
    "reg-1-704-1b2iid-alternate-economic-effect",
    "section-704d-basis-limitation",
    "section-50a-recapture",
    "section-50c3-itc-basis-reduction",
    "transfer-market-2025",
)


def preferred_cash_schedule(
    config: PreferredConfig,
    commitment: float,
    distributable_cash: tuple[float, ...],
) -> tuple[
    tuple[float, ...], tuple[float, ...], tuple[float, ...], tuple[float, ...]
]:
    """Year-by-year preferred cash, split into return, redemption and balances.

    Returns ``(preferred_cash, return_paid, redemption, unreturned_capital)``.
    Unreturned capital is the **closing** balance for the year.
    """
    balance = commitment
    accrued = 0.0
    pref_cash: list[float] = []
    returns_paid: list[float] = []
    redemptions: list[float] = []
    balances: list[float] = []

    for cash in distributable_cash:
        base = balance + (accrued if config.compound_unpaid_return else 0.0)
        accrued += base * config.preferred_return

        available = max(cash, 0.0) * config.cash_priority_share
        pay_return = min(available, accrued)
        accrued -= pay_return
        available -= pay_return

        redeem = min(available, balance)
        balance -= redeem

        pref_cash.append(pay_return + redeem)
        returns_paid.append(pay_return)
        redemptions.append(redeem)
        balances.append(balance)

    return (
        tuple(pref_cash),
        tuple(returns_paid),
        tuple(redemptions),
        tuple(balances),
    )


def run_preferred(
    ctx: StructureContext, config: PreferredConfig | None = None
) -> StructureResult:
    """Run a preferred equity partnership end to end."""
    config = config or PreferredConfig()
    econ = ctx.economics
    warnings: list[str] = [*econ.warnings]
    risks: list[RiskFlag] = []

    commitment = config.commitment
    if commitment is None:
        commitment = max(
            0.0,
            min(
                econ.itc_amount * PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR.value,
                econ.equity_at_cod
                * PLACEHOLDER_MAX_INVESTOR_SHARE_OF_EQUITY.value,
            ),
        )
        warnings.append(
            "Preferred commitment was derived from the credit at "
            f"{PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR.value:.2f} per $1 of "
            "ITC. That ratio is a PLACEHOLDER; see LIMITS_STRUCTURES.md."
        )
    if config.preferred_return == PLACEHOLDER_PREFERRED_RETURN.value:
        warnings.append(
            f"The preferred return of {PLACEHOLDER_PREFERRED_RETURN.value:.2%} "
            "is a PLACEHOLDER. Crux reports preferred equity took 15% of ITC "
            "gross value in 2025 but publishes no coupon."
        )

    if commitment <= 0.0:
        return StructureResult(
            key=StructureKey.PREFERRED_EQUITY,
            feasible=False,
            infeasible_reason=(
                "No preferred commitment could be sized: with no credit and no "
                "stated commitment there is no preferred equity to raise."
            ),
            years=econ.years,
            warnings=tuple(warnings),
            citation_ids=_CITATIONS,
        )

    pref_cash, returns_paid, redemptions, balances = preferred_cash_schedule(
        config, commitment, econ.distributable_cash
    )

    partners = (
        PartnerTerms(
            name=SPONSOR,
            role=PartnerRole.SPONSOR,
            tax_rate=ctx.sponsor.tax_rate,
            unlimited_dro=True,
            bears_residual_allocations=True,
        ),
        PartnerTerms(
            name=PREFERRED,
            role=PartnerRole.PREFERRED,
            tax_rate=config.investor_tax_rate,
            dro_cap=config.investor_dro_cap,
        ),
    )

    taxable = econ.taxable_income()
    book = econ.book_income()
    basis_series = econ.book_basis()
    sponsor_commitment = max(econ.equity_at_cod - commitment, 0.0)

    rows: list[PeriodInputs] = []
    ratios: list[SharingRatios] = []
    for i in range(econ.n_years):
        credit = econ.ptc_by_year[i]
        reduction = 0.0
        if i == econ.credit_year_index:
            credit += econ.itc_amount
            reduction = econ.itc_basis_reduction
        rows.append(
            PeriodInputs(
                period=i,
                year=econ.years[i],
                book_income=book[i],
                taxable_income=taxable[i],
                credit=credit,
                itc_basis_reduction=reduction,
                cash_available=econ.distributable_cash[i],
                contributions=(
                    {SPONSOR: sponsor_commitment, PREFERRED: commitment}
                    if i == 0
                    else {}
                ),
                nonrecourse_liability=econ.debt_balance[i],
                book_basis=basis_series[i],
            )
        )
        # Tax items follow the preferred ratio while capital is outstanding and
        # drop to the residual ratio once it has been redeemed in full.
        outstanding = balances[i] > 0.0 or redemptions[i] > 0.0
        income_share = (
            config.preferred_income_share
            if outstanding
            else config.post_redemption_income_share
        )
        credit_share = (
            config.preferred_credit_share
            if outstanding
            else config.post_redemption_income_share
        )
        cash_total = econ.distributable_cash[i]
        if cash_total > 0.0:
            cash_share = min(pref_cash[i] / cash_total, 1.0)
        else:
            cash_share = (
                config.post_redemption_cash_share if not outstanding else 0.0
            )
        ratios.append(
            SharingRatios(
                income={PREFERRED: income_share, SPONSOR: 1.0 - income_share},
                loss={PREFERRED: income_share, SPONSOR: 1.0 - income_share},
                credit={PREFERRED: credit_share, SPONSOR: 1.0 - credit_share},
                cash={PREFERRED: cash_share, SPONSOR: 1.0 - cash_share},
            )
        )

    partnership = run_partnership(
        partners,
        rows,
        tuple(ratios),
        initial_book_basis=econ.capex,
        initial_nonrecourse_liability=econ.debt_at_cod,
    )
    warnings.extend(partnership.warnings)

    sponsor_flows = partner_after_tax_flows(
        partnership,
        SPONSOR,
        tax_rate=ctx.sponsor.tax_rate,
        can_use_credits=ctx.sponsor.can_use_credits,
        can_use_losses=ctx.sponsor.can_use_depreciation,
    )
    investor_flows = partner_after_tax_flows(
        partnership, PREFERRED, tax_rate=config.investor_tax_rate
    )

    sponsor_cashflow = (-sponsor_commitment, *sponsor_flows)
    sponsor_cash_series = (
        -sponsor_commitment,
        *partnership.distributions(SPONSOR),
    )

    debt_service = tuple(
        econ.interest[i] + econ.principal[i] for i in range(econ.n_years)
    )
    third_party = [econ.debt_at_cod + commitment]
    for i in range(econ.n_years):
        third_party.append(-(debt_service[i] + investor_flows[i]))

    redeemed_by_target = None
    target_index = int(round(config.target_term_years)) - 1
    if 0 <= target_index < econ.n_years:
        redeemed_by_target = balances[target_index] <= 0.0
        if not redeemed_by_target:
            risks.append(
                RiskFlag(
                    code="preferred_not_redeemed_on_time",
                    severity=RiskSeverity.CAUTION,
                    summary=(
                        f"${balances[target_index]:,.0f} of preferred capital "
                        f"is still outstanding at the {config.target_term_years:.0f}"
                        f"-year target"
                    ),
                    detail=(
                        "Project cash is not redeeming the preferred on the "
                        "contracted horizon. In a real deal this triggers a "
                        "coupon step-up, a cash sweep or a forced sale; none of "
                        "those is modelled, so the reported sponsor return is "
                        "optimistic."
                    ),
                )
            )
    if balances[-1] > 0.0:
        risks.append(
            RiskFlag(
                code="preferred_unredeemed_at_maturity",
                severity=RiskSeverity.BLOCKING,
                summary=(
                    f"${balances[-1]:,.0f} of preferred capital is never redeemed "
                    f"inside the modelled project life"
                ),
                detail=(
                    "The residual claim ranks ahead of the sponsor's common and "
                    "would have to be met from a refinancing or an asset sale, "
                    "neither of which is modelled."
                ),
            )
        )

    if econ.itc_amount > 0.0:
        risks.append(
            recapture_risk_flag(
                econ.itc_amount,
                StructureKey.PREFERRED_EQUITY,
                party="the preferred investor",
            )
        )

    pref_floor_hits = sum(
        1 for period in partnership.periods if period.partner(PREFERRED).floor_binds
    )
    if pref_floor_hits:
        risks.append(
            RiskFlag(
                code="dro_cap_reallocation",
                severity=RiskSeverity.CAUTION,
                summary=(
                    f"The preferred investor's DRO cap bound in "
                    f"{pref_floor_hits} of {econ.n_years} years"
                ),
                detail=(
                    "Losses beyond the investor's DRO plus its share of "
                    "partnership minimum gain were reallocated to the sponsor "
                    "under Treas. Reg. §1.704-1(b)(2)(ii)(d)."
                ),
                citation_ids=("reg-1-704-1b2iid-alternate-economic-effect",),
            )
        )

    sponsor_irr = irr(sponsor_cashflow)
    sponsor_npv = sum(
        cf / (1.0 + ctx.discount_rate) ** i for i, cf in enumerate(sponsor_cashflow)
    )

    # Preferred capital is contributed at financial close, so unlike a §6418
    # transfer it genuinely funds construction and belongs in the stack.
    sources = build_sources_and_uses(
        econ,
        third_party_equity=commitment,
        sponsor_equity=sponsor_commitment,
    )
    risks.extend(funding_risk_flags(sources))
    risks.extend(capital_account_risk_flags(partnership))

    timing = compute_cash_timing(sponsor_cashflow)
    meaningful, meaningful_reason = irr_meaningfulness(
        sponsor_after_tax_irr=sponsor_irr,
        sponsor_equity_required=sponsor_commitment,
        funding_requirement=sources.uses_total,
        payback_years=timing.payback_years,
    )

    return StructureResult(
        key=StructureKey.PREFERRED_EQUITY,
        feasible=True,
        sponsor_after_tax_irr=sponsor_irr,
        sponsor_npv=sponsor_npv,
        effective_cost_of_capital=effective_cost_of_capital(third_party),
        sponsor_equity_required=sponsor_commitment,
        third_party_capital_raised=sources.third_party_construction_capital,
        total_capital_raised=sources.sources_total,
        post_cod_monetisation=0.0,
        sources_and_uses=sources,
        sponsor_irr_is_meaningful=meaningful,
        sponsor_irr_not_meaningful_reason=meaningful_reason,
        years=econ.years,
        sponsor_cashflow=sponsor_cashflow,
        sponsor_cash_only=sponsor_cash_series,
        third_party_cashflow=tuple(third_party),
        cash_timing=timing,
        investor_achieved_irr=irr((-commitment, *investor_flows)),
        credit_retained=econ.itc_amount,
        partnership=partnership,
        detail={
            "preferred_commitment": commitment,
            "preferred_return": config.preferred_return,
            "preferred_return_paid_total": float(sum(returns_paid)),
            "preferred_redeemed_total": float(sum(redemptions)),
            "preferred_unreturned_final": balances[-1],
            "preferred_redemption_year": float(
                next(
                    (i + 1 for i, b in enumerate(balances) if b <= 0.0),
                    econ.n_years,
                )
            ),
            "preferred_floor_binding_years": float(pref_floor_hits),
        },
        risks=tuple(risks),
        warnings=tuple(dict.fromkeys(warnings)),
        citation_ids=_CITATIONS,
    )
