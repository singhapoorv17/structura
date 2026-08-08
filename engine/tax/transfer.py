"""§6418 transferability and §6417 direct pay - alive, and dominant.

**Verified 2026-08-06.** Draft bills proposed sunsetting §6418. **The enacted
OBBBA preserved it whole, and §6417 elective payment is also intact.**

**Market shape (Crux).** Total credit monetisation reached **$63bn in 2025**.
The transfer market alone went **$32bn (2024) -> $42bn (2025), +48%**. Of ITC
gross value: **partnerships 57%, direct transfer 28%, preferred equity 15%**.
For PTCs, **more than 90% is direct transfer**, so a PTC deal starts from a
transfer assumption in the structure selector.

**Mechanics modelled**

* Face value of the credit, a clearing **price in cents on the dollar**, gross
  proceeds, transaction costs (broker fee, credit insurance, legal) and net
  proceeds.
* The **effective net price** - net proceeds over face - which is the number a
  sponsor actually quotes, and the **discount to face** that a comparison
  against tax equity has to beat.
* Settlement timing, because a credit earned at COD and paid for six months
  later is not worth its nominal price.

**The hard gate: §70512(h).** Transfer of a §45Q/45X/45Y/45Z/48E credit to a
**specified foreign entity** (§7701(a)(51)(B)) is **prohibited**, effective for
taxable years beginning after 2025-07-04 - first tested 2026-01-01 for a
calendar-year taxpayer. The test lives in :mod:`engine.tax.feoc` and is enforced
here: a blocked transfer returns ``permitted=False`` with zero proceeds, not a
priced transaction with a warning attached.

**Other §6418 mechanics worth knowing, implemented as documented constraints:**
the election is **one-time** (a transferee cannot re-transfer), consideration
must be **cash**, that cash is **neither taxable to the transferor nor
deductible by the transferee**, and an **excessive credit transfer** exposes the
transferee to the disallowed amount plus a **20% penalty** - which is why every
real transfer carries an indemnity or a credit insurance wrap, and why the
transaction-cost default is non-zero.
"""

from __future__ import annotations

from datetime import date

from engine.tax.constants import (
    DEFAULT_ITC_TRANSFER_PRICE,
    DEFAULT_PTC_TRANSFER_PRICE,
    DEFAULT_TRANSFER_TRANSACTION_COST_PCT,
    EXCESSIVE_CREDIT_TRANSFER_PENALTY_RATE,
    ITC_MARKET_MIX_2025,
    PTC_DIRECT_TRANSFER_SHARE_2025,
    TRANSFER_MARKET_SIZE_USD_BN,
)
from engine.tax.feoc import transfer_to_foreign_entity_prohibited
from engine.tax.models import (
    CreditResult,
    CreditSection,
    CreditType,
    DeterminationStep,
    ForeignEntityStatus,
    TaxProject,
    TransferResult,
)

__all__ = [
    "APPLICABLE_ENTITIES",
    "DIRECT_PAY_CITATION_ID",
    "default_transfer_price",
    "is_direct_pay_eligible",
    "model_transfer",
]

#: Authority for everything :func:`is_direct_pay_eligible` decides. Exposed as a
#: constant because the function returns a plain ``(bool, str)`` pair rather
#: than a result object, and the caller still needs to cite it.
DIRECT_PAY_CITATION_ID = "section-6417-direct-pay"

#: §6417(d)(1)(A) applicable entities, which may elect direct pay for the full
#: suite of credits. A taxable entity may elect §6417 only for §45Q, §45V and
#: §45X. Confidence.PROVISIONAL - see citations.py.
APPLICABLE_ENTITIES: tuple[str, ...] = (
    "tax_exempt_organization",
    "state_or_political_subdivision",
    "indian_tribal_government",
    "alaska_native_corporation",
    "tennessee_valley_authority",
    "rural_electric_cooperative",
    "us_territory_or_subdivision",
)

#: Credits a *taxable* entity may nonetheless monetise via §6417.
_TAXABLE_ENTITY_DIRECT_PAY_SECTIONS: frozenset[CreditSection] = frozenset(
    {CreditSection.SEC_45Q, CreditSection.SEC_45X}
)


def default_transfer_price(credit_type: CreditType) -> float:
    """Default clearing price, cents on the dollar.

    ITC: 0.90, implied by the Norton Rose Fulbright ITC bridge quote ("75%
    advance, ~67.5% net at 90c"). PTC: a **placeholder** - no PTC clearing price is carried by
    the verified rulebook, and PTC strips price differently because they deliver
    over ten years. See ``UNVERIFIED.md``.
    """
    return (
        DEFAULT_ITC_TRANSFER_PRICE
        if credit_type is CreditType.ITC
        else DEFAULT_PTC_TRANSFER_PRICE
    )


def is_direct_pay_eligible(
    entity_type: str, credit_section: CreditSection
) -> tuple[bool, str]:
    """§6417 elective payment eligibility.

    Returns ``(eligible, reason)``. Applicable entities may elect direct pay
    generally; a taxable entity may elect it only for §45Q and §45X (and §45V,
    which Structura does not model).
    """
    if entity_type in APPLICABLE_ENTITIES:
        return (
            True,
            f"'{entity_type}' is an applicable entity under §6417(d)(1)(A) and "
            f"may elect a cash payment in lieu of the §{credit_section.value} "
            f"credit.",
        )
    if credit_section in _TAXABLE_ENTITY_DIRECT_PAY_SECTIONS:
        return (
            True,
            f"A taxable entity may elect §6417 elective payment for a "
            f"§{credit_section.value} credit.",
        )
    return (
        False,
        f"'{entity_type}' is not an applicable entity, and §6417 is not "
        f"available to a taxable entity for a §{credit_section.value} credit. "
        f"Monetise via a §6418 transfer or a partnership instead.",
    )


def model_transfer(
    project: TaxProject,
    credit: CreditResult,
    *,
    price_per_dollar: float | None = None,
    transaction_cost_pct: float = DEFAULT_TRANSFER_TRANSACTION_COST_PCT,
    transferee_status: ForeignEntityStatus | None = None,
    settlement_date: date | None = None,
) -> TransferResult:
    """Price a §6418 transfer of the project's credit, or block it.

    Parameters
    ----------
    price_per_dollar
        Clearing price in cents on the dollar. Defaults to
        :func:`default_transfer_price`.
    transaction_cost_pct
        Broker fee + credit insurance + legal, as a fraction of **face value**.
        The default is a placeholder (see ``UNVERIFIED.md``); it is non-zero
        because the §6418(g)(2) 20% excessive-credit-transfer penalty makes an
        uninsured transfer commercially unusual.
    transferee_status
        FEOC status of the buyer. Defaults to
        ``project.foreign_entity_flags.transferee_status``.

    Returns
    -------
    TransferResult
        With ``permitted=False`` and zero proceeds where §70512(h) bites.
    """
    steps: list[DeterminationStep] = []
    citations = [
        "section-6418-alive",
        "section-70512h-transfer-ban",
        "transfer-market-2025",
    ]
    section = project.credit_section
    face = credit.credit_amount
    status = (
        transferee_status
        if transferee_status is not None
        else project.foreign_entity_flags.transferee_status
    )
    ty_begin = project.effective_taxable_year_begin

    market_context = {
        "transfer_market_usd_bn_2024": TRANSFER_MARKET_SIZE_USD_BN[2024],
        "transfer_market_usd_bn_2025": TRANSFER_MARKET_SIZE_USD_BN[2025],
        "itc_share_partnership": ITC_MARKET_MIX_2025["partnership"],
        "itc_share_direct_transfer": ITC_MARKET_MIX_2025["direct_transfer"],
        "itc_share_preferred_equity": ITC_MARKET_MIX_2025["preferred_equity"],
        "ptc_share_direct_transfer": PTC_DIRECT_TRANSFER_SHARE_2025,
        "excessive_transfer_penalty_rate": EXCESSIVE_CREDIT_TRANSFER_PENALTY_RATE,
    }

    steps.append(
        DeterminationStep(
            label="§6418 transferability",
            outcome="available",
            detail=(
                "OBBBA preserved §6418 intact; the transfer market grew from "
                f"${TRANSFER_MARKET_SIZE_USD_BN[2024]:.0f}bn in 2024 to "
                f"${TRANSFER_MARKET_SIZE_USD_BN[2025]:.0f}bn in 2025. "
                + (
                    f"More than {PTC_DIRECT_TRANSFER_SHARE_2025:.0%} of PTC "
                    "value moves by direct transfer, so a transfer is the "
                    "default assumption for a §45Y deal."
                    if project.credit_type is CreditType.PTC
                    else f"Direct transfer took "
                    f"{ITC_MARKET_MIX_2025['direct_transfer']:.0%} of ITC gross "
                    f"value in 2025 against "
                    f"{ITC_MARKET_MIX_2025['partnership']:.0%} for partnerships."
                )
            ),
            citation_ids=("section-6418-alive", "transfer-market-2025"),
        )
    )

    # --- §70512(h) hard gate ---------------------------------------------
    prohibited, feoc_reason = transfer_to_foreign_entity_prohibited(
        section, status, ty_begin
    )
    steps.append(
        DeterminationStep(
            label="§70512(h) specified foreign entity test",
            outcome="TRANSFER PROHIBITED" if prohibited else "no prohibition",
            detail=feoc_reason,
            citation_ids=("section-70512h-transfer-ban",),
        )
    )

    if prohibited:
        return TransferResult(
            permitted=False,
            credit_section=section,
            credit_face_value=face,
            price_per_dollar=0.0,
            gross_proceeds=0.0,
            transaction_costs=0.0,
            net_proceeds=0.0,
            effective_net_price=0.0,
            discount_to_face=1.0,
            settlement_date=settlement_date,
            blocked_reason=feoc_reason,
            steps=tuple(steps),
            citation_ids=tuple(dict.fromkeys(citations)),
            market_context=market_context,
        )

    if not credit.eligible or face <= 0.0:
        steps.append(
            DeterminationStep(
                label="Transfer economics",
                outcome="nothing to transfer",
                detail=(
                    "There is no credit to sell: "
                    + (credit.disqualification_reason or "the credit is zero.")
                ),
            )
        )
        return TransferResult(
            permitted=False,
            credit_section=section,
            credit_face_value=face,
            price_per_dollar=0.0,
            gross_proceeds=0.0,
            transaction_costs=0.0,
            net_proceeds=0.0,
            effective_net_price=0.0,
            discount_to_face=1.0,
            settlement_date=settlement_date,
            blocked_reason=credit.disqualification_reason or "Credit is zero.",
            steps=tuple(steps),
            citation_ids=tuple(dict.fromkeys(citations)),
            market_context=market_context,
        )

    # --- economics --------------------------------------------------------
    price = (
        price_per_dollar
        if price_per_dollar is not None
        else default_transfer_price(project.credit_type)
    )
    if not 0.0 <= price <= 1.0:
        raise ValueError("price_per_dollar must lie in [0, 1]")
    if not 0.0 <= transaction_cost_pct <= 1.0:
        raise ValueError("transaction_cost_pct must lie in [0, 1]")

    gross = face * price
    costs = face * transaction_cost_pct
    net = gross - costs
    effective = net / face
    citations.append("itc-transfer-pricing-default")
    citations.append("excessive-credit-transfer-penalty")

    steps.append(
        DeterminationStep(
            label="Transfer economics",
            outcome=(
                f"${face:,.0f} face at {price:.2f} = ${gross:,.0f} gross, "
                f"${net:,.0f} net ({effective:.1%} of face)"
            ),
            detail=(
                f"Transaction costs of {transaction_cost_pct:.1%} of face "
                f"(${costs:,.0f}) cover broker fee, credit insurance and legal. "
                f"The §6418(g)(2) excessive credit transfer penalty of "
                f"{EXCESSIVE_CREDIT_TRANSFER_PENALTY_RATE:.0%} sits with the "
                f"transferee, which is why the wrap is priced in rather than "
                f"assumed away."
            ),
            citation_ids=(
                "itc-transfer-pricing-default",
                "excessive-credit-transfer-penalty",
            ),
        )
    )

    return TransferResult(
        permitted=True,
        credit_section=section,
        credit_face_value=face,
        price_per_dollar=price,
        gross_proceeds=gross,
        transaction_costs=costs,
        net_proceeds=net,
        effective_net_price=effective,
        discount_to_face=1.0 - effective,
        settlement_date=settlement_date or project.placed_in_service_date,
        blocked_reason="",
        steps=tuple(steps),
        citation_ids=tuple(dict.fromkeys(citations)),
        market_context=market_context,
    )
