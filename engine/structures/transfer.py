"""Direct transfer under §6418 — the credit sold for cents on the dollar.

**§6418 is alive.** Draft bills proposed sunsetting it; the enacted OBBBA
(P.L. 119-21) preserved it whole, and §6417 elective payment with it
(SPEC.md §2.2, verified 2026-08-06). Any model built on the assumption that
transferability died is modelling a bill that did not pass.

Market shape (Crux, quoted at SPEC §2.2): total credit monetisation **$63bn in
2025**; the transfer market alone **$32bn (2024) → $42bn (2025), +48%**. Of ITC
gross value, direct transfer took **28%**; for PTCs, **more than 90%**. That
last figure is the single most useful heuristic in the whole selector: a §45Y
deal should start from a transfer assumption and justify anything else.

Why it is structurally different from everything else here
----------------------------------------------------------
There is **no partner**. The sponsor keeps 100% of the project, sells only the
credit, and therefore has no capital account, no DRO, no minimum gain and no
§704(d) limitation to worry about. That simplicity is the product: a transfer
closes in weeks where a flip closes in months.

The cost of that simplicity is the other half of the trade:

* The sponsor **keeps the depreciation**. If it has no tax capacity, the
  depreciation is worth nothing and the transfer has monetised only part of the
  tax value. :attr:`SponsorTaxProfile.can_use_depreciation` decides this, and it
  is usually the deciding fact in the whole structure comparison.
* The sponsor sells at a **discount to face** — the price in cents on the dollar
  less transaction costs — and that discount is the entire cost of the capital.
* The **§70512(h)** prohibition on transferring §45Q/45X/45Y/45Z/48E credits to
  a specified foreign entity is a hard gate. A blocked transfer returns
  ``feasible=False`` naming the rule, never a priced transaction with a warning
  attached.
"""

from __future__ import annotations

from engine.metrics import irr
from engine.tax import model_transfer
from engine.tax.constants import DEFAULT_TRANSFER_TRANSACTION_COST_PCT
from engine.structures.models import (
    RiskFlag,
    RiskSeverity,
    StructureContext,
    StructureKey,
    StructureResult,
    TransferConfig,
    build_sources_and_uses,
    compute_cash_timing,
    effective_cost_of_capital,
    funding_risk_flags,
    irr_meaningfulness,
    recapture_risk_flag,
)

__all__ = ["run_transfer"]

_CITATIONS = (
    "section-6418-alive",
    "section-70512h-transfer-ban",
    "transfer-market-2025",
    "itc-transfer-pricing-default",
    "excessive-credit-transfer-penalty",
    "section-50a-recapture",
    "section-50c3-itc-basis-reduction",
)


def run_transfer(
    ctx: StructureContext, config: TransferConfig | None = None
) -> StructureResult:
    """Sell the credit, keep the project, and price what that costs."""
    config = config or TransferConfig()
    econ = ctx.economics
    warnings: list[str] = [*econ.warnings]
    risks: list[RiskFlag] = []

    face = ctx.tax.credit.credit_amount
    transfer = model_transfer(
        ctx.tax_project,
        ctx.tax.credit,
        price_per_dollar=config.price_per_dollar,
        transaction_cost_pct=(
            DEFAULT_TRANSFER_TRANSACTION_COST_PCT
            if config.transaction_cost_pct is None
            else config.transaction_cost_pct
        ),
    )

    if not transfer.permitted:
        return StructureResult(
            key=StructureKey.DIRECT_TRANSFER,
            feasible=False,
            infeasible_reason=transfer.blocked_reason,
            years=econ.years,
            credit_retained=face,
            risks=(
                RiskFlag(
                    code="transfer_blocked",
                    severity=RiskSeverity.BLOCKING,
                    summary="§6418 transfer not available",
                    detail=transfer.blocked_reason,
                    citation_ids=(
                        "section-70512h-transfer-ban",
                        "section-6418-alive",
                    ),
                ),
            ),
            warnings=tuple(warnings),
            citation_ids=transfer.citation_ids,
        )

    uses_depreciation = (
        ctx.sponsor.can_use_depreciation
        if config.sponsor_uses_depreciation is None
        else config.sponsor_uses_depreciation
    )
    if not uses_depreciation:
        warnings.append(
            "The sponsor is modelled as unable to use the depreciation it "
            "retains, so the transfer monetises the credit only. That is the "
            "structural weakness of a direct transfer against a partnership."
        )

    taxable = econ.taxable_income()
    settlement = min(config.settlement_year_index, econ.n_years - 1)

    sponsor_flows: list[float] = []
    cash_only: list[float] = []
    for i in range(econ.n_years):
        cash = econ.distributable_cash[i]
        if i == settlement:
            cash += transfer.net_proceeds
        taxed = taxable[i]
        if taxed < 0.0 and not uses_depreciation:
            tax_effect = 0.0
        else:
            tax_effect = -ctx.sponsor.tax_rate * taxed
        sponsor_flows.append(cash + tax_effect)
        cash_only.append(cash)

    equity = econ.equity_at_cod
    sponsor_cashflow = (-equity, *sponsor_flows)
    sponsor_cash_series = (-equity, *cash_only)

    # Third-party capital: the senior facility plus the transfer proceeds. The
    # cost of the transfer leg is the discount - proceeds in, face surrendered -
    # both struck in the settlement year.
    debt_service = tuple(
        econ.interest[i] + econ.principal[i] for i in range(econ.n_years)
    )
    third_party = [econ.debt_at_cod]
    for i in range(econ.n_years):
        flow = -debt_service[i]
        if i == settlement:
            flow += transfer.net_proceeds - face
        third_party.append(flow)

    if face > 0.0:
        risks.append(
            recapture_risk_flag(
                face, StructureKey.DIRECT_TRANSFER, party="the transferee"
            )
        )
        risks.append(
            RiskFlag(
                code="excessive_credit_transfer",
                severity=RiskSeverity.CAUTION,
                summary=(
                    "§6418(g)(2) exposes the transferee to a 20% penalty on an "
                    "excessive credit transfer"
                ),
                detail=(
                    "That exposure is why every real transfer carries a seller "
                    "indemnity or a credit-insurance wrap, and why the "
                    f"transaction-cost assumption of "
                    f"{transfer.transaction_costs / face:.2%} of face is "
                    f"non-zero rather than assumed away."
                ),
                citation_ids=("excessive-credit-transfer-penalty",),
            )
        )
    else:
        risks.append(
            RiskFlag(
                code="no_credit_to_transfer",
                severity=RiskSeverity.BLOCKING,
                summary="There is no credit to sell",
                detail=(
                    ctx.tax.credit.disqualification_reason
                    or "The modelled credit is zero."
                ),
            )
        )

    if not uses_depreciation:
        risks.append(
            RiskFlag(
                code="depreciation_stranded",
                severity=RiskSeverity.CAUTION,
                summary=(
                    f"${sum(econ.tax_depreciation):,.0f} of depreciation is "
                    f"retained by a sponsor that cannot use it"
                ),
                detail=(
                    "A partnership structure would allocate those deductions to "
                    "an investor that can use them. Compare the flip and T-flip "
                    "results before concluding that a transfer is cheapest."
                ),
            )
        )

    # --- sources and uses --------------------------------------------------
    # There is no partner, so the sponsor funds the whole equity cheque. The
    # transfer proceeds arrive in the settlement year - after the property is
    # placed in service, because the credit does not exist before then - and
    # reimburse that cheque. They are not construction funding, and counting
    # them as such is what makes reported sources exceed uses.
    sources = build_sources_and_uses(
        econ,
        third_party_equity=0.0,
        sponsor_equity=equity,
        post_cod_monetisation=transfer.net_proceeds,
        post_cod_monetisation_note=(
            f"§6418 transfer proceeds of ${transfer.net_proceeds:,.0f} settle in "
            f"operating year {settlement + 1}, after the property is placed in "
            f"service. The sponsor funds ${equity:,.0f} of construction equity "
            f"and is reimbursed out of the sale; net equity at risk after "
            f"settlement is ${max(equity - transfer.net_proceeds, 0.0):,.0f}. "
            f"Funding construction against the expected credit would require an "
            f"ITC bridge loan (SPEC §2.7), which Structura does not model."
        ),
    )
    risks.extend(funding_risk_flags(sources))

    sponsor_irr = irr(sponsor_cashflow)
    timing = compute_cash_timing(sponsor_cashflow)
    meaningful, meaningful_reason = irr_meaningfulness(
        sponsor_after_tax_irr=sponsor_irr,
        sponsor_equity_required=equity,
        funding_requirement=sources.uses_total,
        payback_years=timing.payback_years,
    )

    feasible = face > 0.0
    return StructureResult(
        key=StructureKey.DIRECT_TRANSFER,
        feasible=feasible,
        infeasible_reason=(
            ""
            if feasible
            else (
                ctx.tax.credit.disqualification_reason
                or "There is no credit to transfer."
            )
        ),
        sponsor_after_tax_irr=sponsor_irr,
        sponsor_npv=sum(
            cf / (1.0 + ctx.discount_rate) ** i
            for i, cf in enumerate(sponsor_cashflow)
        ),
        effective_cost_of_capital=effective_cost_of_capital(third_party),
        sponsor_equity_required=equity,
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
        credit_transferred=face,
        credit_retained=0.0,
        transfer_net_proceeds=transfer.net_proceeds,
        detail={
            "credit_face": face,
            "price_per_dollar": transfer.price_per_dollar,
            "gross_proceeds": transfer.gross_proceeds,
            "transaction_costs": transfer.transaction_costs,
            "net_proceeds": transfer.net_proceeds,
            "effective_net_price": transfer.effective_net_price,
            "discount_to_face": transfer.discount_to_face,
            "settlement_year_index": float(settlement),
            "depreciation_retained": float(sum(econ.tax_depreciation)),
        },
        risks=tuple(risks),
        warnings=tuple(dict.fromkeys(warnings)),
        citation_ids=tuple(dict.fromkeys((*_CITATIONS, *transfer.citation_ids))),
    )
