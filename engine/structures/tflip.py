"""T-flip / hybrid — a partnership flip with a §6418 transfer bolted on.

Norton Rose Fulbright's *Cost of Capital: 2026 Outlook* (2026-01-29) and
Novogradac report that traditional tax equity in which the investor retains the
credits was ~30% of the market in 2024 and less in 2025; that *"most current
deals employ hybrid or preferred equity structures"*; and that T-flips appear
on **"pretty much every single transaction."**

The mechanic
------------
The partnership is a flip in every respect — capital accounts, DRO, outside
basis, minimum gain, the lot — except that some or all of the investment credit
is **sold for cash** under §6418 instead of being allocated to the tax-equity
investor. Everything else follows from that one change:

* The **§50(c)(3) basis reduction still applies.** §6418 transfers the credit,
  not the basis adjustment: the partnership's depreciable and §704(b) book
  basis fall by half the credit whether the credit is sold or kept. Getting
  this wrong overstates depreciation by 15% of capex on a 30% ITC deal.
* The tax-equity investor is now buying **depreciation and cash only**, so it
  takes longer to reach its target after-tax yield and **the flip point moves
  out**. :func:`run_tflip` computes that movement explicitly against an
  otherwise-identical pure flip, because it is the number that tells a sponsor
  what the transfer actually cost it.
* Transfer proceeds can be paid to the sponsor directly (the common case, and
  the default here) or contributed into the partnership. Paid to the sponsor
  they sit **outside** the capital accounts entirely.

The transfer leg is priced by :func:`engine.tax.model_transfer`, which enforces
the §70512(h) prohibition on transfers to a specified foreign entity. A blocked
transfer does not silently become a pure flip: it returns an infeasible result
naming the blocking rule.
"""

from __future__ import annotations

from dataclasses import replace

from engine.tax import model_transfer
from engine.structures.defaults import ITC_RECAPTURE_PERIOD_YEARS
from engine.structures.flip import run_flip, solve_flip_point
from engine.structures.models import (
    RiskFlag,
    RiskSeverity,
    StructureContext,
    StructureKey,
    StructureResult,
    TFlipConfig,
)

__all__ = ["run_tflip"]


def run_tflip(
    ctx: StructureContext, config: TFlipConfig | None = None
) -> StructureResult:
    """Run a hybrid flip-plus-transfer and report the flip-point interaction."""
    config = config or TFlipConfig()
    econ = ctx.economics
    face = econ.itc_amount
    warnings: list[str] = []
    risks: list[RiskFlag] = []

    if face <= 0.0:
        return StructureResult(
            key=StructureKey.T_FLIP,
            feasible=False,
            infeasible_reason=(
                "There is no credit to transfer, so there is no T-flip. "
                + (
                    ctx.tax.credit.disqualification_reason
                    or "The modelled credit is zero."
                )
            ),
            years=econ.years,
            warnings=tuple(econ.warnings),
            citation_ids=("section-6418-alive", "section-70512h-transfer-ban"),
        )

    transferred_face = face * config.transferred_credit_share
    retained = face - transferred_face

    # Price only the slice actually sold. ``model_transfer`` prices whatever
    # face value it is handed and applies the §70512(h) gate to it.
    sliced_credit = replace(ctx.tax.credit, credit_amount=transferred_face)
    transfer = model_transfer(
        ctx.tax_project,
        sliced_credit,
        price_per_dollar=config.price_per_dollar,
    )

    if not transfer.permitted and transferred_face > 0.0:
        return StructureResult(
            key=StructureKey.T_FLIP,
            feasible=False,
            infeasible_reason=(
                "The §6418 leg of the T-flip is blocked: " + transfer.blocked_reason
            ),
            years=econ.years,
            credit_transferred=0.0,
            credit_retained=face,
            risks=(
                RiskFlag(
                    code="transfer_blocked",
                    severity=RiskSeverity.BLOCKING,
                    summary="§6418 transfer prohibited",
                    detail=transfer.blocked_reason,
                    citation_ids=("section-70512h-transfer-ban",),
                ),
            ),
            warnings=tuple(econ.warnings),
            citation_ids=transfer.citation_ids,
        )

    # The comparison that gives the structure its meaning: the same partnership
    # with the credit kept inside it.
    pure_solve = solve_flip_point(
        ctx,
        config.flip,
        investor_commitment=config.flip.investor_commitment_for(
            face, econ.equity_at_cod
        ),
        credit_in_partnership=face,
    )

    result = run_flip(
        ctx,
        config.flip,
        key=StructureKey.T_FLIP,
        credit_in_partnership=retained,
        credit_transferred=transferred_face,
        transfer_net_proceeds=transfer.net_proceeds,
        transfer_year_index=config.settlement_year_index,
        proceeds_to_partnership=config.proceeds_to_partnership,
        extra_risks=risks,
        extra_warnings=warnings,
    )

    flip_delta = (
        result.flip_year - pure_solve.flip_year
        if result.flip_year is not None and pure_solve.solved
        else None
    )

    extra_risks = list(result.risks)
    extra_risks.append(
        RiskFlag(
            code="transfer_recapture_indemnity",
            severity=RiskSeverity.CAUTION,
            summary=(
                f"${transferred_face:,.0f} of credit sold at "
                f"{transfer.price_per_dollar:.2f} carries a "
                f"{ITC_RECAPTURE_PERIOD_YEARS}-year recapture indemnity"
            ),
            detail=(
                "Under §6418 the transferee bears an excessive-credit-transfer "
                "exposure and, in practice, recapture risk is passed back to "
                "the seller by indemnity and wrapped with credit insurance. "
                "That is why the transaction-cost default is non-zero rather "
                "than assumed away."
            ),
            citation_ids=(
                "excessive-credit-transfer-penalty",
                "section-50a-recapture",
            ),
        )
    )
    if flip_delta is not None and flip_delta > 0.0:
        extra_risks.append(
            RiskFlag(
                code="flip_point_deferred_by_transfer",
                severity=RiskSeverity.INFO,
                summary=(
                    f"Selling the credit pushes the flip out by "
                    f"{flip_delta:.2f} years"
                ),
                detail=(
                    f"With the credit retained the investor reaches its target "
                    f"in year {pure_solve.flip_year:.2f}; buying only "
                    f"depreciation and cash it needs until year "
                    f"{result.flip_year:.2f}. The sponsor has traded a later "
                    f"flip for ${transfer.net_proceeds:,.0f} of cash at "
                    f"settlement."
                ),
            )
        )

    detail = dict(result.detail)
    detail.update(
        {
            "credit_face": face,
            "credit_transferred": transferred_face,
            "credit_retained": retained,
            "transfer_price_per_dollar": transfer.price_per_dollar,
            "transfer_gross_proceeds": transfer.gross_proceeds,
            "transfer_transaction_costs": transfer.transaction_costs,
            "transfer_net_proceeds": transfer.net_proceeds,
            "transfer_effective_net_price": transfer.effective_net_price,
            "pure_flip_year": pure_solve.flip_year,
            "flip_year_deferred_by": flip_delta if flip_delta is not None else 0.0,
        }
    )

    return replace(
        result,
        risks=tuple(extra_risks),
        detail=detail,
        citation_ids=tuple(
            dict.fromkeys((*result.citation_ids, *transfer.citation_ids))
        ),
    )
