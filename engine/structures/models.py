"""Configs, shared context and result types for the five 2026 structures.

Self-contained by design: this module imports from :mod:`engine` and
:mod:`engine.tax` rather than duplicating anything either of them already owns.
The debt sculpt, the waterfall, the credit determination and the depreciation
schedule all arrive here as finished objects.

Why five structures and not one
-------------------------------
Norton Rose Fulbright's *Cost of Capital: 2026 Outlook* (2026-01-29) reports
that traditional tax equity in which the investor retains the credits
was **~30% of the market in 2024 and a smaller percentage in 2025**; **"most
current deals employ hybrid or preferred equity structures"**; and Jack Cargas
of BofA describes the position as *"it feels like there are now 31 different
flavors."* A model that offers only a 99/1 yield-based flip is describing a
minority of a shrinking segment.

The five live structures are therefore first-class citizens with a common
interface: partnership flip, T-flip (flip plus §6418 transfer), preferred equity
partnership, direct transfer, and sale-leaseback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from engine import (
    DebtTerms,
    FundingSolution,
    ProjectInputs,
    WaterfallResult,
    run_model,
)
from engine.tax import (
    CreditType,
    TaxProject,
    TaxResult,
    TaxScenario,
    compute_tax,
)
from engine.structures.defaults import (
    DE_MINIMIS_SPONSOR_EQUITY_SHARE,
    DE_MINIMIS_SPONSOR_PAYBACK_YEARS,
    FUNDING_RELATIVE_TOLERANCE,
    FUNDING_TOLERANCE,
    IMPLAUSIBLE_SPONSOR_IRR,
    ITC_RECAPTURE_PERIOD_YEARS,
    PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR,
    PLACEHOLDER_POST_FLIP_TE_ALLOCATION_SHARE,
    POST_FLIP_TE_CASH_SHARE,
    PLACEHOLDER_PREFERRED_RETURN,
    PLACEHOLDER_PREFERRED_TARGET_TERM_YEARS,
    PLACEHOLDER_PRE_FLIP_TE_ALLOCATION_SHARE,
    PLACEHOLDER_MAX_INVESTOR_SHARE_OF_EQUITY,
    PRE_FLIP_TE_CASH_SHARE,
    PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT,
    PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR,
    PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR,
)
from engine.metrics import irr
from engine.structures.partnership import PartnershipResult

__all__ = [
    "StructureKey",
    "FlipTrigger",
    "RiskSeverity",
    "RiskFlag",
    "SponsorTaxProfile",
    "ProjectEconomics",
    "StructureContext",
    "build_context",
    "FlipConfig",
    "TFlipConfig",
    "PreferredConfig",
    "TransferConfig",
    "SaleLeasebackConfig",
    "StructureConfigs",
    "CashTiming",
    "SourcesAndUses",
    "StructureResult",
    "build_project_economics",
    "build_sources_and_uses",
    "capital_account_risk_flags",
    "funding_risk_flags",
    "compute_cash_timing",
    "effective_cost_of_capital",
    "irr_meaningfulness",
    "partner_after_tax_flows",
    "recapture_risk_flag",
]


class StructureKey(str, Enum):
    """The five live 2026 capital structures (NRF, *Cost of Capital: 2026 Outlook*)."""

    PARTNERSHIP_FLIP = "partnership_flip"
    T_FLIP = "t_flip"
    PREFERRED_EQUITY = "preferred_equity"
    DIRECT_TRANSFER = "direct_transfer"
    SALE_LEASEBACK = "sale_leaseback"

    @property
    def label(self) -> str:
        return {
            StructureKey.PARTNERSHIP_FLIP: "Partnership flip",
            StructureKey.T_FLIP: "T-flip (hybrid flip + §6418 transfer)",
            StructureKey.PREFERRED_EQUITY: "Preferred equity partnership",
            StructureKey.DIRECT_TRANSFER: "Direct transfer (§6418)",
            StructureKey.SALE_LEASEBACK: "Sale-leaseback",
        }[self]

    @property
    def requires_credit(self) -> bool:
        """True where the structure has no economic purpose without a credit.

        A direct transfer with nothing to transfer is not a structure, and a
        T-flip is *defined* by the transfer leg. A plain flip, a preferred
        equity partnership and a sale-leaseback can still monetise accelerated
        depreciation, so they degrade rather than disappear.
        """
        return self in (StructureKey.DIRECT_TRANSFER, StructureKey.T_FLIP)


class FlipTrigger(str, Enum):
    """How a partnership flip flips.

    YIELD_BASED
        The sharing ratios flip when the tax investor's **after-tax IRR**
        reaches a target. The flip date is an *output*, solved numerically.
        This is the dominant form and the one that makes the structure hard to
        model: the investor's return depends on the flip date, which depends on
        the investor's return.
    FIXED_DATE
        The ratios flip on a stated date whatever the achieved yield. Simpler,
        and it moves the yield risk from the sponsor to the investor.
    """

    YIELD_BASED = "yield_based"
    FIXED_DATE = "fixed_date"


class RiskSeverity(str, Enum):
    INFO = "info"
    CAUTION = "caution"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class RiskFlag:
    """One structural risk, named the way a diligence memo names it."""

    code: str
    severity: RiskSeverity
    summary: str
    detail: str
    citation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SponsorTaxProfile:
    """What the sponsor can actually *use*, which decides the whole question.

    A sponsor with no tax appetite cannot use a credit or a depreciation
    deduction, which is the entire reason tax equity and the transfer market
    exist. ``can_use_credits`` False forces monetisation.
    """

    tax_rate: float = 0.21
    can_use_credits: bool = False
    can_use_depreciation: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.tax_rate < 1.0:
            raise ValueError("tax_rate must lie in [0, 1)")


# ---------------------------------------------------------------------------
# Shared project economics
# ---------------------------------------------------------------------------


def _annualise(series: Sequence[float], periods_per_year: int) -> tuple[float, ...]:
    """Collapse a model-period series into tax years by summation.

    Partnership tax is annual. The debt spine can run semi-annual or quarterly
    periods, so anything crossing into this package is summed into years. A
    trailing part-year is kept as a whole year, which is the correct treatment
    for a tax return and is declared in ``LIMITS_STRUCTURES.md``.
    """
    if periods_per_year == 1:
        return tuple(float(x) for x in series)
    out: list[float] = []
    for start in range(0, len(series), periods_per_year):
        out.append(float(sum(series[start : start + periods_per_year])))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class ProjectEconomics:
    """The annual project-level series every structure sits on top of.

    Identical for all five structures by construction — that is what makes the
    comparison in :mod:`engine.structures.selector` an apples-to-apples one.
    """

    years: tuple[int, ...]
    ebitda: tuple[float, ...]
    interest: tuple[float, ...]
    principal: tuple[float, ...]
    distributable_cash: tuple[float, ...]
    """Cash to equity out of the project waterfall, after senior debt service
    and reserves."""
    tax_depreciation: tuple[float, ...]
    book_depreciation: tuple[float, ...]
    debt_balance: tuple[float, ...]
    """Closing senior debt balance each year."""
    itc_amount: float
    itc_basis_reduction: float
    ptc_by_year: tuple[float, ...]
    credit_year_index: int
    capex: float
    total_project_cost: float
    debt_at_cod: float
    equity_at_cod: float
    #: Interest during construction, capitalised into total project cost.
    idc: float = 0.0
    #: Upfront and commitment fees, financed by the facility.
    fees: float = 0.0
    #: Funded reserves at COD (the initial DSRA).
    reserves: float = 0.0
    warnings: tuple[str, ...] = ()

    @property
    def n_years(self) -> int:
        return len(self.years)

    def taxable_income(self) -> tuple[float, ...]:
        """EBITDA less interest less tax depreciation, per year.

        The partnership's federal taxable income. Note that principal is not
        deductible and does not appear, which is precisely why a highly geared
        project throws off a large book loss in early years and a taxable gain
        later — the shape that makes a flip work at all.
        """
        return tuple(
            self.ebitda[i] - self.interest[i] - self.tax_depreciation[i]
            for i in range(self.n_years)
        )

    def book_income(self) -> tuple[float, ...]:
        """§704(b) book income: the same line on **book** depreciation."""
        return tuple(
            self.ebitda[i] - self.interest[i] - self.book_depreciation[i]
            for i in range(self.n_years)
        )

    def book_basis(self) -> tuple[float, ...]:
        """Closing §704(b) book basis of the property, year by year.

        Opens at capex, reduced by the §1.704-1(b)(2)(iv)(j) credit adjustment
        in the credit year and by book depreciation thereafter. It is the
        denominator of partnership minimum gain.
        """
        out: list[float] = []
        basis = self.capex
        for i in range(self.n_years):
            if i == self.credit_year_index:
                basis -= self.itc_basis_reduction
            basis = max(basis - self.book_depreciation[i], 0.0)
            out.append(basis)
        return tuple(out)


@dataclass(frozen=True, slots=True)
class StructureContext:
    """One resolved project, ready to be run through any structure."""

    project: ProjectInputs
    terms: DebtTerms
    tax_project: TaxProject
    tax_scenario: TaxScenario
    funding: FundingSolution
    waterfall: WaterfallResult
    tax: TaxResult
    economics: ProjectEconomics
    sponsor: SponsorTaxProfile
    discount_rate: float

    @property
    def credit_amount(self) -> float:
        return self.tax.credit.credit_amount

    @property
    def credit_is_zero(self) -> bool:
        return self.tax.credit.credit_amount <= 0.0


def build_context(
    project: ProjectInputs,
    terms: DebtTerms,
    tax_project: TaxProject,
    *,
    tax_scenario: TaxScenario | None = None,
    sponsor: SponsorTaxProfile | None = None,
    discount_rate: float = 0.10,
    lockup_dscr: float | None = None,
) -> StructureContext:
    """Run the debt spine and the tax engine once, and share the results.

    Every structure is then measured against **the same** sculpted debt, the
    same waterfall and the same credit determination. Running the debt sizing
    per structure would make the comparison meaningless, so it is deliberately
    done once here.
    """
    tax_scenario = tax_scenario or TaxScenario()
    sponsor = sponsor or SponsorTaxProfile()
    funding, waterfall, _returns = run_model(
        project, terms, lockup_dscr=lockup_dscr, discount_rate=discount_rate
    )
    tax = compute_tax(tax_project, tax_scenario)
    economics = build_project_economics(project, funding, waterfall, tax)
    return StructureContext(
        project=project,
        terms=terms,
        tax_project=tax_project,
        tax_scenario=tax_scenario,
        funding=funding,
        waterfall=waterfall,
        tax=tax,
        economics=economics,
        sponsor=sponsor,
        discount_rate=discount_rate,
    )


def build_project_economics(
    project: ProjectInputs,
    funding: FundingSolution,
    waterfall: WaterfallResult,
    tax: TaxResult,
) -> ProjectEconomics:
    """Assemble the annual series, aligning the tax and cash calendars.

    Alignment rule: operating year 1 is the calendar year of COD, and the
    depreciation schedule from :func:`engine.tax.build_schedule` is labelled
    with the placed-in-service year. Where those differ, the depreciation is
    shifted onto the operating calendar and a warning is recorded rather than
    silently dropped.
    """
    ppy = project.periods_per_year
    warnings: list[str] = []

    ebitda = _annualise(funding.cashflow.ebitda, ppy)
    n_years = len(ebitda)
    years = tuple(project.cod_date.year + i for i in range(n_years))

    interest = _annualise(waterfall.interest, ppy)
    principal = _annualise(
        tuple(
            waterfall.principal_scheduled[i] + waterfall.sweep_prepayment[i]
            for i in range(waterfall.n_periods)
        ),
        ppy,
    )
    distributable = _annualise(waterfall.distributions, ppy)
    balances = waterfall.closing_balance
    debt_balance = tuple(
        balances[min((i + 1) * ppy - 1, len(balances) - 1)] for i in range(n_years)
    )

    def _pad(series: tuple[float, ...]) -> tuple[float, ...]:
        if len(series) >= n_years:
            return series[:n_years]
        return series + tuple(0.0 for _ in range(n_years - len(series)))

    dep = tax.depreciation.deductions_by_year
    pis_year = tax.project.placed_in_service_date.year
    offset = pis_year - project.cod_date.year
    if offset != 0:
        warnings.append(
            f"Placed-in-service year {pis_year} differs from the COD year "
            f"{project.cod_date.year}; the depreciation schedule was shifted by "
            f"{offset} year(s) onto the operating calendar."
        )
    if offset > 0:
        dep = tuple(0.0 for _ in range(offset)) + dep
    elif offset < 0:
        dep = dep[-offset:]
    tax_depreciation = _pad(tuple(dep))
    dropped = sum(tuple(dep)[n_years:]) if len(dep) > n_years else 0.0
    if dropped > 0.0:
        warnings.append(
            f"${dropped:,.0f} of depreciation falls after the modelled project "
            f"life and is not deducted in this model."
        )

    itc_amount = (
        tax.credit.credit_amount
        if tax.credit.credit_type is CreditType.ITC
        else 0.0
    )
    ptc = [0.0] * n_years
    if tax.credit.credit_type is CreditType.PTC and tax.credit.eligible:
        for i in range(min(tax.credit.credit_period_years, n_years)):
            ptc[i] = tax.credit.annual_credit_amount

    credit_year_index = max(0, min(offset, n_years - 1))

    return ProjectEconomics(
        years=years,
        ebitda=ebitda,
        interest=interest,
        principal=principal,
        distributable_cash=distributable,
        tax_depreciation=tax_depreciation,
        # Absent a §704(c) layer, §1.704-1(b)(2)(iv)(g)(3) makes book
        # depreciation track tax depreciation exactly, because book value and
        # adjusted tax basis are the same number. The two series are kept
        # separate anyway so the distinction is structural, not assumed.
        book_depreciation=tax_depreciation,
        debt_balance=debt_balance,
        itc_amount=itc_amount,
        itc_basis_reduction=tax.depreciation.basis_reduction,
        ptc_by_year=tuple(ptc),
        credit_year_index=credit_year_index,
        capex=funding.construction.capex,
        total_project_cost=funding.construction.total_project_cost,
        debt_at_cod=funding.construction.debt_at_cod,
        equity_at_cod=funding.construction.equity_at_cod,
        idc=funding.construction.idc,
        fees=(
            funding.construction.upfront_fee + funding.construction.commitment_fee
        ),
        reserves=funding.construction.dsra_initial,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Per-structure configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FlipConfig:
    """Terms of a partnership flip.

    Sharing ratios are stated as the **tax-equity** share; the sponsor takes
    the complement. Income, loss, credit and cash are separate because they are
    separate in every real LLC agreement.
    """

    trigger: FlipTrigger = FlipTrigger.YIELD_BASED
    target_after_tax_irr: float = PLACEHOLDER_TE_TARGET_AFTER_TAX_IRR.value
    #: Used only when ``trigger`` is FIXED_DATE. Expressed in operating years
    #: from COD; 6.0 means the ratios flip at the end of operating year 6.
    fixed_flip_year: float = 6.0

    pre_flip_te_income: float = PLACEHOLDER_PRE_FLIP_TE_ALLOCATION_SHARE.value
    pre_flip_te_loss: float = PLACEHOLDER_PRE_FLIP_TE_ALLOCATION_SHARE.value
    pre_flip_te_credit: float = PLACEHOLDER_PRE_FLIP_TE_ALLOCATION_SHARE.value
    pre_flip_te_cash: float = PRE_FLIP_TE_CASH_SHARE.value

    post_flip_te_income: float = PLACEHOLDER_POST_FLIP_TE_ALLOCATION_SHARE.value
    post_flip_te_loss: float = PLACEHOLDER_POST_FLIP_TE_ALLOCATION_SHARE.value
    post_flip_te_credit: float = PLACEHOLDER_POST_FLIP_TE_ALLOCATION_SHARE.value
    post_flip_te_cash: float = POST_FLIP_TE_CASH_SHARE.value

    #: Tax-equity commitment. ``None`` derives it from the credit at the
    #: disclosed placeholder rate.
    investor_commitment: float | None = None
    investor_tax_rate: float = 0.21
    #: The investor's deficit restoration obligation, in dollars. Zero is the
    #: market norm: a tax-equity investor relies on its share of minimum gain
    #: instead, and that is exactly what caps its loss allocations.
    investor_dro_cap: float = 0.0
    #: Sponsors normally carry an unlimited DRO, which is what lets the
    #: reallocation mechanic land somewhere.
    sponsor_unlimited_dro: bool = True

    def __post_init__(self) -> None:
        for name in (
            "pre_flip_te_income",
            "pre_flip_te_loss",
            "pre_flip_te_credit",
            "pre_flip_te_cash",
            "post_flip_te_income",
            "post_flip_te_loss",
            "post_flip_te_credit",
            "post_flip_te_cash",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1]")
        if self.fixed_flip_year < 0.0:
            raise ValueError("fixed_flip_year must be >= 0")
        if self.investor_commitment is not None and self.investor_commitment < 0.0:
            raise ValueError("investor_commitment must be >= 0")

    def investor_commitment_for(self, itc_amount: float, equity: float) -> float:
        """Derive the tax-equity commitment when the caller has not stated one.

        ``itc x PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR``, capped at
        ``PLACEHOLDER_MAX_INVESTOR_SHARE_OF_EQUITY`` of the project's equity.
        A tax-equity investor pays more than the face of the credit because it
        also receives the accelerated depreciation and a slice of the cash —
        but the sponsor must be left with equity in the deal. Both constants
        are disclosed placeholders; state ``investor_commitment`` to bypass
        them entirely.
        """
        if self.investor_commitment is not None:
            return self.investor_commitment
        derived = itc_amount * PLACEHOLDER_TE_INVESTMENT_PER_CREDIT_DOLLAR.value
        ceiling = equity * PLACEHOLDER_MAX_INVESTOR_SHARE_OF_EQUITY.value
        return max(0.0, min(derived, ceiling))


@dataclass(frozen=True, slots=True)
class TFlipConfig:
    """A flip with a §6418 transfer bolted on — the near-universal structure.

    Novogradac reports T-flips on *"pretty much every single
    transaction."* The economics are a flip in which some or all of the credit
    is **sold for cash** rather than allocated to the tax-equity investor. The
    investor is then buying depreciation and cash, so it needs longer to reach
    its target yield: the flip point moves out. That interaction is the whole
    point of modelling this separately from a plain flip.
    """

    flip: FlipConfig = field(default_factory=FlipConfig)
    #: Fraction of the credit sold to a third party under §6418. The remainder
    #: is allocated inside the partnership on the credit sharing ratio.
    transferred_credit_share: float = 1.0
    #: Clearing price in cents on the dollar. ``None`` uses the
    #: ``engine.tax.transfer`` default for the credit type.
    price_per_dollar: float | None = None
    #: Year (index from COD) in which transfer proceeds settle.
    settlement_year_index: int = 0
    #: True pays the transfer proceeds into the partnership, where they are
    #: distributed on the cash sharing ratio. That is the default because the
    #: §6418 election is made by the entity that owns the facility, which in a
    #: T-flip is the partnership — so the cash lands inside it. Set False where
    #: the sponsor sells at the holdco level and keeps the proceeds outside the
    #: capital accounts entirely.
    proceeds_to_partnership: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.transferred_credit_share <= 1.0:
            raise ValueError("transferred_credit_share must lie in [0, 1]")
        if self.settlement_year_index < 0:
            raise ValueError("settlement_year_index must be >= 0")


@dataclass(frozen=True, slots=True)
class PreferredConfig:
    """Preferred equity partnership terms.

    Crux puts preferred equity at **15% of ITC gross value in
    2025**. Economically it sits between debt and the flip: the investor takes
    a stated return and a redemption right ahead of the sponsor's common, and
    normally also takes the tax attributes.
    """

    commitment: float | None = None
    preferred_return: float = PLACEHOLDER_PREFERRED_RETURN.value
    target_term_years: float = PLACEHOLDER_PREFERRED_TARGET_TERM_YEARS.value
    #: Share of distributable cash applied to the preferred (current return
    #: first, then redemption) before anything reaches the common.
    cash_priority_share: float = 1.0
    #: Share of income, loss and credits allocated to the preferred partner.
    preferred_income_share: float = 0.99
    preferred_credit_share: float = 0.99
    #: After redemption in full, the preferred's residual sharing ratio.
    post_redemption_income_share: float = 0.05
    post_redemption_cash_share: float = 0.05
    investor_tax_rate: float = 0.21
    investor_dro_cap: float = 0.0
    #: True compounds unpaid preferred return; False accrues it simple.
    compound_unpaid_return: bool = True

    def __post_init__(self) -> None:
        if self.preferred_return < 0.0:
            raise ValueError("preferred_return must be >= 0")
        if self.target_term_years <= 0.0:
            raise ValueError("target_term_years must be > 0")
        for name in (
            "cash_priority_share",
            "preferred_income_share",
            "preferred_credit_share",
            "post_redemption_income_share",
            "post_redemption_cash_share",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1]")


@dataclass(frozen=True, slots=True)
class TransferConfig:
    """Direct sale of the credit under §6418.

    28% of ITC gross value and **more than 90% of PTC value** in 2025 (Crux).
    The sponsor keeps the whole project and sells only the credit,
    so there is no partner, no capital account and no DRO — which is both the
    attraction and the limitation: depreciation stays with a sponsor who may
    not be able to use it.
    """

    price_per_dollar: float | None = None
    transaction_cost_pct: float | None = None
    settlement_year_index: int = 0
    #: True where the sponsor can actually use the depreciation it retains.
    #: Overrides :attr:`SponsorTaxProfile.can_use_depreciation` when set.
    sponsor_uses_depreciation: bool | None = None

    def __post_init__(self) -> None:
        if self.settlement_year_index < 0:
            raise ValueError("settlement_year_index must be >= 0")


@dataclass(frozen=True, slots=True)
class SaleLeasebackConfig:
    """Sale at fair market value followed by a lease back to the sponsor.

    NRF lists sale-leaseback among the five live structures and
    notes it is **making a comeback**. The seller-lessee gets cash equal to
    FMV; the purchaser-lessor takes the whole tax position — the investment
    credit and the depreciation — and the lessee's only tax item is a rent
    deduction. Rent is solved to the lessor's target after-tax yield.
    """

    #: Sale price. ``None`` sells at the modelled fair market value, taken as
    #: total project cost.
    sale_price: float | None = None
    lease_term_years: float = 20.0
    asset_useful_life_years: float | None = None
    lessor_target_after_tax_irr: float = (
        PLACEHOLDER_LESSOR_TARGET_AFTER_TAX_IRR.value
    )
    lessor_tax_rate: float = 0.21
    residual_value_pct: float = PLACEHOLDER_SALE_LEASEBACK_RESIDUAL_PCT.value
    #: True assumes the lessee exercises a fair-market-value purchase option at
    #: the end of the term, paying the residual value.
    purchase_option_exercised: bool = True
    #: Months between the original placed-in-service date and the sale. The
    #: §50(d)(4) three-month window is what preserves the credit for the
    #: lessor; outside it, the credit is lost to both parties.
    months_after_placed_in_service: int = 1

    def __post_init__(self) -> None:
        if self.lease_term_years <= 0.0:
            raise ValueError("lease_term_years must be > 0")
        if not 0.0 <= self.residual_value_pct <= 1.0:
            raise ValueError("residual_value_pct must lie in [0, 1]")
        if self.months_after_placed_in_service < 0:
            raise ValueError("months_after_placed_in_service must be >= 0")


@dataclass(frozen=True, slots=True)
class StructureConfigs:
    """One config per structure. Omit a structure to leave it out of the run."""

    flip: FlipConfig | None = field(default_factory=FlipConfig)
    t_flip: TFlipConfig | None = field(default_factory=TFlipConfig)
    preferred: PreferredConfig | None = field(default_factory=PreferredConfig)
    transfer: TransferConfig | None = field(default_factory=TransferConfig)
    sale_leaseback: SaleLeasebackConfig | None = field(
        default_factory=SaleLeasebackConfig
    )


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CashTiming:
    """When the sponsor actually gets its money.

    The metric that separates a transfer from a flip more sharply than IRR
    does: a transfer front-loads cash into year one, a flip defers it past the
    flip point. Two structures with the same IRR are not the same deal.
    """

    first_positive_year: int | None
    """Index (from COD) of the first year the sponsor is cash positive."""
    share_received_by_year_5: float
    share_received_by_year_10: float
    weighted_average_years: float
    """Cash-weighted average time to receipt, in years from COD."""
    payback_years: float | None


@dataclass(frozen=True, slots=True)
class SourcesAndUses:
    """Construction sources against the construction funding requirement.

    **The invariant this type exists to enforce: sources cannot exceed uses.**
    A capital stack is an identity, not a preference. Everything drawn at
    financial close — senior debt, third-party equity, sponsor equity — funds
    one number: capex plus interest during construction plus fees plus funded
    reserves. If a reported "capital raised" figure exceeds that number, the
    model is counting something that never funded the project.

    The line this type draws
    ------------------------
    A **§6418 credit sale settles after the property is placed in service** —
    the credit does not exist until then. Its proceeds therefore *cannot* be a
    source of construction funding. They are a post-COD monetisation: cash that
    reimburses capital already committed and is distributed, not capital that
    built the asset. Adding them to the construction stack inflates "third-party
    capital raised" by the whole net proceeds and produces the impossible
    result that sources exceed uses.

    The same reasoning applies to a **sale-leaseback**: the lessor's purchase
    price is paid *after* the asset exists and is used to repay the senior
    facility and return the sponsor's construction equity. It refinances the
    stack; it does not build it.

    Where a project genuinely funds construction against an expected credit it
    does so through an **ITC bridge loan** (NRF 2026: 98% advance at SOFR+150
    if covered, 75% at SOFR+225 if not). That is debt, and Structura does not
    model it — see ``LIMITS_STRUCTURES.md``.
    """

    #: Total funding requirement: capex + IDC + fees + funded reserves.
    uses_total: float
    capex: float
    idc: float
    fees: float
    reserves: float

    # --- construction sources ---------------------------------------------
    senior_debt: float
    third_party_equity: float
    """Tax-equity or preferred capital contributed at financial close."""
    credit_proceeds_at_cod: float
    """Credit monetisation proceeds that genuinely fund construction. Zero in
    every structure Structura currently models, and stated explicitly rather
    than omitted so that adding an ITC bridge later has somewhere to land."""
    sponsor_equity: float

    # --- outside the construction stack ------------------------------------
    post_cod_monetisation: float
    """Cash received from third parties **after** COD: §6418 transfer proceeds,
    or a sale-leaseback purchase price. Reimbursement, not funding."""
    post_cod_monetisation_note: str = ""

    @property
    def third_party_construction_capital(self) -> float:
        """Debt plus third-party equity plus any credit proceeds at COD."""
        return self.senior_debt + self.third_party_equity + self.credit_proceeds_at_cod

    @property
    def sources_total(self) -> float:
        return self.third_party_construction_capital + self.sponsor_equity

    @property
    def tolerance(self) -> float:
        return max(FUNDING_TOLERANCE, FUNDING_RELATIVE_TOLERANCE * abs(self.uses_total))

    @property
    def imbalance(self) -> float:
        """Sources less uses. Positive means the project is over-funded."""
        return self.sources_total - self.uses_total

    @property
    def balances(self) -> bool:
        return abs(self.imbalance) <= self.tolerance

    @property
    def oversubscribed(self) -> bool:
        """True where third-party capital alone exceeds the funding requirement.

        The commercially real case: a stated tax-equity or preferred commitment
        larger than the equity the project actually needs. The sponsor cannot
        contribute a negative amount, so the excess has nowhere to go — and a
        model that silently floors sponsor equity at zero reports a capital
        stack that no lender would fund.
        """
        return self.third_party_construction_capital > self.uses_total + self.tolerance

    def describe(self) -> str:
        return (
            f"uses ${self.uses_total:,.0f} = capex ${self.capex:,.0f} + IDC "
            f"${self.idc:,.0f} + fees ${self.fees:,.0f} + reserves "
            f"${self.reserves:,.0f}; sources ${self.sources_total:,.0f} = senior "
            f"debt ${self.senior_debt:,.0f} + third-party equity "
            f"${self.third_party_equity:,.0f} + credit proceeds at COD "
            f"${self.credit_proceeds_at_cod:,.0f} + sponsor equity "
            f"${self.sponsor_equity:,.0f}; post-COD monetisation "
            f"${self.post_cod_monetisation:,.0f} (excluded from sources)"
        )


def build_sources_and_uses(
    econ: ProjectEconomics,
    *,
    third_party_equity: float = 0.0,
    sponsor_equity: float | None = None,
    credit_proceeds_at_cod: float = 0.0,
    post_cod_monetisation: float = 0.0,
    post_cod_monetisation_note: str = "",
    senior_debt: float | None = None,
) -> SourcesAndUses:
    """Assemble the sources-and-uses statement for one structure.

    ``sponsor_equity`` defaults to the plug — the funding requirement less every
    other source — floored at zero. Where that floor bites, the resulting
    statement reports ``oversubscribed`` and does **not** silently balance.
    """
    debt = econ.debt_at_cod if senior_debt is None else senior_debt
    other = debt + third_party_equity + credit_proceeds_at_cod
    if sponsor_equity is None:
        sponsor_equity = max(econ.total_project_cost - other, 0.0)
    construction = econ.total_project_cost
    return SourcesAndUses(
        uses_total=construction,
        capex=econ.capex,
        idc=econ.idc,
        fees=econ.fees,
        reserves=econ.reserves,
        senior_debt=debt,
        third_party_equity=third_party_equity,
        credit_proceeds_at_cod=credit_proceeds_at_cod,
        sponsor_equity=sponsor_equity,
        post_cod_monetisation=post_cod_monetisation,
        post_cod_monetisation_note=post_cod_monetisation_note,
    )


def irr_meaningfulness(
    *,
    sponsor_after_tax_irr: float | None,
    sponsor_equity_required: float,
    funding_requirement: float,
    payback_years: float | None,
) -> tuple[bool, str]:
    """Decide whether a sponsor IRR describes the deal or describes its base.

    Returns ``(is_meaningful, reason)``. ``reason`` is empty when the rate is
    meaningful. The three tests, in the order a reviewer would apply them:

    1. **No rate exists** — no net sponsor investment, so no rate.
    2. **De minimis equity base** — sponsor equity below
       :data:`~engine.structures.defaults.DE_MINIMIS_SPONSOR_EQUITY_SHARE` of
       the funding requirement. IRR is a rate *on* an equity base; shrink the
       base and the rate stops being about the deal.
    3. **Immediate payback** — the whole net investment returns inside
       :data:`~engine.structures.defaults.DE_MINIMIS_SPONSOR_PAYBACK_YEARS`,
       so the annualised rate is dominated by the period convention.

    A fourth check is *reporting only*: a rate above
    :data:`~engine.structures.defaults.IMPLAUSIBLE_SPONSOR_IRR` is retained but
    labelled, because a project-finance sponsor IRR of that size is a signal
    about the inputs, not a result.
    """
    if sponsor_after_tax_irr is None:
        return False, (
            "No rate exists: the structure leaves the sponsor with no net "
            "investment, so there is nothing for a return to be a return on."
        )
    if funding_requirement > 0.0:
        share = sponsor_equity_required / funding_requirement
        if share < DE_MINIMIS_SPONSOR_EQUITY_SHARE:
            return False, (
                f"De minimis equity base: sponsor equity of "
                f"${sponsor_equity_required:,.0f} is {share:.1%} of the "
                f"${funding_requirement:,.0f} funding requirement, below the "
                f"{DE_MINIMIS_SPONSOR_EQUITY_SHARE:.0%} floor below which a "
                f"levered IRR measures the size of the denominator rather than "
                f"the economics of the deal. Ranked on sponsor NPV instead; "
                f"read the effective cost of capital alongside it."
            )
    if (
        payback_years is not None
        and payback_years <= DE_MINIMIS_SPONSOR_PAYBACK_YEARS
    ):
        return False, (
            f"Immediate payback: the sponsor recovers its entire net investment "
            f"in {payback_years:.2f} years, so the annualised rate is set by the "
            f"model's annual period convention rather than by the deal. Ranked "
            f"on sponsor NPV instead."
        )
    if sponsor_after_tax_irr > IMPLAUSIBLE_SPONSOR_IRR:
        return False, (
            f"Implausible for a project-finance structure: "
            f"{sponsor_after_tax_irr:.1%} against a market range of roughly "
            f"8-15% levered after tax for contracted US renewables and storage. "
            f"A rate this size is a denominator artefact or a double-counted "
            f"benefit; ranked on sponsor NPV instead and flagged for review."
        )
    return True, ""


@dataclass(frozen=True, slots=True)
class StructureResult:
    """The common interface every structure module returns.

    The selector consumes only these fields, which is what makes the five
    structures comparable at all.
    """

    key: StructureKey
    feasible: bool
    infeasible_reason: str = ""

    # --- headline metrics ---------------------------------------------------
    sponsor_after_tax_irr: float | None = None
    sponsor_npv: float = 0.0
    effective_cost_of_capital: float | None = None
    sponsor_equity_required: float = 0.0
    third_party_capital_raised: float = 0.0
    """Third-party **construction** capital: senior debt plus third-party
    equity contributed at financial close. Post-COD credit monetisation is
    reported separately in :attr:`post_cod_monetisation` and is deliberately
    *not* counted here — see :class:`SourcesAndUses`."""
    total_capital_raised: float = 0.0
    """Every source that funded construction, sponsor equity included. Equal to
    the funding requirement within tolerance unless the structure is
    over-subscribed, which :attr:`sources_and_uses` reports."""
    post_cod_monetisation: float = 0.0
    """Cash received from third parties after COD: §6418 transfer proceeds or a
    sale-leaseback purchase price. Reimbursement, not construction funding."""
    sources_and_uses: SourcesAndUses | None = None

    # --- headline-metric robustness ----------------------------------------
    sponsor_irr_is_meaningful: bool = True
    """False where the reported IRR is an artefact of a de minimis equity base,
    an immediate payback, or an absent net investment. The selector ranks such a
    structure on sponsor NPV and never leads with the rate."""
    sponsor_irr_not_meaningful_reason: str = ""

    # --- series -------------------------------------------------------------
    years: tuple[int, ...] = ()
    sponsor_cashflow: tuple[float, ...] = ()
    """After-tax sponsor cashflow, index 0 = COD (negative equity outflow)."""
    sponsor_cash_only: tuple[float, ...] = ()
    """Cash distributions and proceeds, before any tax effect."""
    third_party_cashflow: tuple[float, ...] = ()
    """Capital in at index 0, then everything paid or surrendered to the
    providers of that capital. Its IRR is the effective cost of capital."""
    cash_timing: CashTiming | None = None

    # --- structure-specific -------------------------------------------------
    flip_year: float | None = None
    flip_solved: bool | None = None
    investor_achieved_irr: float | None = None
    credit_transferred: float = 0.0
    credit_retained: float = 0.0
    transfer_net_proceeds: float = 0.0
    partnership: PartnershipResult | None = None
    detail: Mapping[str, float] = field(default_factory=dict)

    # --- explanation --------------------------------------------------------
    risks: tuple[RiskFlag, ...] = ()
    warnings: tuple[str, ...] = ()
    citation_ids: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return self.key.label


def funding_risk_flags(sources: SourcesAndUses) -> tuple[RiskFlag, ...]:
    """Flag a capital stack that does not add up.

    Two distinct failures, deliberately not merged:

    * **Over-subscribed** — third-party capital alone exceeds the funding
      requirement. Commercially real (an over-sized tax-equity or preferred
      commitment) and BLOCKING: the sponsor cannot contribute a negative
      amount, so the structure as drawn cannot be funded.
    * **Does not balance** — sources and uses differ for any other reason. That
      is a modelling failure, not a deal fact, and is reported as such.
    """
    out: list[RiskFlag] = []
    if sources.oversubscribed:
        excess = sources.third_party_construction_capital - sources.uses_total
        out.append(
            RiskFlag(
                code="funding_oversubscribed",
                severity=RiskSeverity.BLOCKING,
                summary=(
                    f"Third-party capital exceeds the funding requirement by "
                    f"${excess:,.0f}"
                ),
                detail=(
                    f"Senior debt plus third-party equity of "
                    f"${sources.third_party_construction_capital:,.0f} is more "
                    f"than the ${sources.uses_total:,.0f} the project needs to "
                    f"build. Sources cannot exceed uses: the sponsor cannot "
                    f"contribute a negative amount, so the stated commitment "
                    f"would have to be cut, the gearing reduced, or the excess "
                    f"distributed at closing - none of which this structure "
                    f"models. Reduce the stated commitment or the gearing cap."
                ),
            )
        )
    elif not sources.balances:
        out.append(
            RiskFlag(
                code="funding_does_not_balance",
                severity=RiskSeverity.BLOCKING,
                summary=(
                    f"Sources and uses differ by ${sources.imbalance:,.0f}"
                ),
                detail=(
                    "The capital stack is an identity. A residual of this size "
                    "means a source or a use is being counted twice or not at "
                    "all. " + sources.describe()
                ),
            )
        )
    return tuple(out)


def capital_account_risk_flags(
    partnership: PartnershipResult,
) -> tuple[RiskFlag, ...]:
    """Promote a §704(b) capital-account breach out of the warning list.

    A capital account below its floor for a run of periods is a structural
    result, not a rounding note, and it must reach a reader at the same level
    as the flip point and the recapture exposure. Severity escalates with
    persistence: a single period is a CAUTION, a sustained deficit is BLOCKING,
    because a partnership that distributes cash a no-DRO partner can never
    restore has an LLC agreement problem, not a modelling one.
    """
    out: list[RiskFlag] = []
    for breach in partnership.capital_account_breaches:
        severity = (
            RiskSeverity.BLOCKING if breach.n_periods > 1 else RiskSeverity.CAUTION
        )
        out.append(
            RiskFlag(
                code="capital_account_below_floor",
                severity=severity,
                summary=(
                    f"'{breach.partner}' §704(b) capital account below its floor "
                    f"in {breach.n_periods} period(s); worst breach "
                    f"${breach.worst_breach:,.0f} in {breach.worst_year}"
                ),
                detail=(
                    breach.describe()
                    + " No allocation caused this - the DRO-cap mechanic makes "
                    "that impossible and the integrity assertion would have "
                    "raised. It is caused by distributing cash to a partner "
                    "with no deficit restoration obligation beyond its share of "
                    "minimum gain. Treat the reported investor yield as "
                    "optimistic by the amount of the breach."
                ),
                citation_ids=(
                    "reg-1-704-1b2iid-alternate-economic-effect",
                    "reg-1-704-2-minimum-gain",
                ),
            )
        )
    return tuple(out)


def recapture_risk_flag(
    credit_amount: float, structure: StructureKey, *, party: str
) -> RiskFlag:
    """The §50(a) recapture flag every ITC structure carries.

    §50(a)(1): the investment credit vests 20% per full year. A disposition of
    the property — or, in a partnership, a reduction of a partner's interest by
    more than one third — inside the five-year period recaptures the unvested
    balance. It is the reason flip dates never fall inside year five and the
    reason transfer agreements carry recapture indemnities.
    """
    return RiskFlag(
        code="itc_recapture",
        severity=RiskSeverity.CAUTION,
        summary=(
            f"§50(a) recapture exposure of up to "
            f"${credit_amount:,.0f} for {ITC_RECAPTURE_PERIOD_YEARS} years"
        ),
        detail=(
            f"The investment credit vests at "
            f"{100 / ITC_RECAPTURE_PERIOD_YEARS:.0f}% per full year. Under the "
            f"{structure.label} structure the recapture sits with {party}. A "
            f"disposition of the property, or a reduction of a partner's "
            f"interest by more than one third, inside the five-year period "
            f"recaptures the unvested balance."
        ),
        citation_ids=("section-50a-recapture",),
    )


def compute_cash_timing(
    cashflow: Sequence[float], periods_per_year: int = 1
) -> CashTiming:
    """Summarise when positive sponsor cash arrives.

    ``cashflow[0]`` is the COD outflow, so timing is measured over the positive
    entries only — the question being answered is "when do I get paid", not
    "what is my net position".
    """
    positives = [(i, cf) for i, cf in enumerate(cashflow) if cf > 0.0]
    total = sum(cf for _, cf in positives)
    if total <= 0.0:
        return CashTiming(
            first_positive_year=None,
            share_received_by_year_5=0.0,
            share_received_by_year_10=0.0,
            weighted_average_years=0.0,
            payback_years=None,
        )
    first = positives[0][0]
    by5 = sum(cf for i, cf in positives if i <= 5) / total
    by10 = sum(cf for i, cf in positives if i <= 10) / total
    wal = sum(i * cf for i, cf in positives) / total / periods_per_year

    payback: float | None = None
    cumulative = 0.0
    previous = 0.0
    for i, cf in enumerate(cashflow):
        previous = cumulative
        cumulative += cf
        if cumulative >= 0.0 and i > 0:
            payback = (
                i / periods_per_year
                if cf == 0.0
                else (i - 1 + (-previous / cf)) / periods_per_year
            )
            break

    return CashTiming(
        first_positive_year=first,
        share_received_by_year_5=by5,
        share_received_by_year_10=by10,
        weighted_average_years=wal,
        payback_years=payback,
    )


def partner_after_tax_flows(
    partnership: PartnershipResult,
    name: str,
    *,
    tax_rate: float,
    can_use_credits: bool = True,
    can_use_losses: bool = True,
) -> tuple[float, ...]:
    """After-tax cashflow for one partner, year by year, excluding contributions.

    ``distribution - tax_rate x taxable income recognised + credits``.

    The two switches matter more than they look. A developer with no tax
    capacity gets nothing from an allocated credit and nothing from an
    allocated loss; that is the whole reason the tax-equity and transfer
    markets exist (Crux: $63bn of credit monetisation in 2025). Modelling
    a sponsor as if it could use attributes it cannot use is the single most
    common way to make a flip look worse than it is.
    """
    out: list[float] = []
    for period in partnership.periods:
        row = period.partner(name)
        taxable = row.taxable_income_recognised
        if taxable < 0.0 and not can_use_losses:
            tax_effect = 0.0
        else:
            tax_effect = -tax_rate * taxable
        credit = row.credit_allocated if can_use_credits else 0.0
        out.append(row.distributions + tax_effect + credit)
    return tuple(out)


def effective_cost_of_capital(third_party_cashflow: Sequence[float]) -> float | None:
    """IRR of the third-party capital series — the all-in cost of everything
    that is not sponsor equity.

    **Definition, stated precisely because the number is otherwise arguable.**
    The series is built from the project's side of the table:

    * **Inflows** — cash the project or sponsor *receives* from third parties:
      senior debt drawn, tax-equity or preferred contributions, §6418 transfer
      proceeds, sale-leaseback sale proceeds.
    * **Outflows** — everything paid *or surrendered* to those providers:
      senior debt service, investor cash distributions, preferred return and
      redemption, lease rent and any purchase-option payment, **plus the tax
      attributes given away**, valued at what the recipient realises from them
      (a credit at face; a loss at the recipient's marginal rate).

    Valuing surrendered attributes at the **recipient's** value, not the
    sponsor's, is deliberate: it makes the number comparable across structures
    regardless of the sponsor's own tax appetite, which is what the question
    "which structure gives me the lowest cost of capital" is actually asking.

    Returns ``None`` where the series never changes sign and no rate exists.
    """
    return irr(tuple(third_party_cashflow))
