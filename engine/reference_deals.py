"""Calibrated reference deals — the demo set, and the calibration regression.

Why this module exists
----------------------
Structura's mechanics were verified long before its *inputs* were. A model can
be arithmetically perfect and still produce a number no practitioner will
believe: the shipped demo case produced a 163% sponsor IRR and reported more
third-party capital than the project cost to build. Neither was a solver bug.
Both were the consequence of an input set nobody had checked against how a deal
is actually financed.

This module is the answer to that. Each reference deal is a **complete, internally
consistent capital structure** — project, debt terms, tax facts, sponsor tax
profile and one config per structure — chosen so that:

* **Sources equal uses.** Senior debt plus third-party equity plus sponsor
  equity equals capex plus IDC plus fees plus funded reserves, exactly. Post-COD
  credit monetisation is reported separately and never counted as construction
  funding (see :class:`engine.structures.models.SourcesAndUses`).
* **The achieved minimum DSCR clears the published market floor** for the
  technology and revenue-risk profile (SPEC §2.7 / :data:`engine.defaults.MIN_DSCR`).
* **The sponsor's after-tax IRR lands in a defensible band.** Real sponsor
  equity IRRs in contracted US renewables and storage run roughly **8-15%
  levered after tax**. Every deal states the band it expects and
  ``tests/test_reference_deals.py`` asserts it.

Provenance rules, unchanged from the rest of the engine
-------------------------------------------------------
**Never fabricate a market number.** Every assumption below is an
:class:`Assumption` carrying its source and the date it was verified. Anything
not traceable to a public document is ``is_placeholder=True``, is listed by
:meth:`ReferenceDeal.placeholder_assumptions`, and surfaces as a warning on
every run. That covers, in particular:

* **Capex per kW and per kWh.** The ATB (SPEC §5.1) is the intended anchor and
  is a build-time data dependency this module does not carry; the figures here
  are round, plausible, labelled placeholders.
* **Revenue.** SPEC §5.1 is explicit that *"PPA prices: no free source
  exists"* — LevelTen's index is subscriber-only. Tolling rates, PPA prices and
  data-center rents are all placeholders. So is every operating cost.
* **Tax-equity, preferred and lease pricing**, which
  ``engine/structures/LIMITS_STRUCTURES.md`` §4 already records as unpublished.

What *is* sourced: the DSCR floors, the debt spreads, the ITC bridge advance
rates and the gearing convention (Norton Rose Fulbright, *Cost of Capital: 2026
Outlook*, 2026-01-29, via :mod:`engine.defaults`), and every tax rule, which
comes from :mod:`engine.tax` with its own citations.

The one calibration finding worth reading before the numbers
------------------------------------------------------------
**An ITC-eligible project cannot simultaneously carry maximum DSCR-sized senior
debt and monetise its credit.** A 30% §48E credit is not a return; it is a
*source*, and it displaces equity. Stack a 75% gearing cap on top of a 30% ITC
and the arithmetic gives 105% of cost before the sponsor writes a cheque — which
is exactly how the original demo produced sponsor equity of 6.5% of the stack
and a three-figure IRR. So every ITC reference deal here sets the senior gearing
cap so that **debt + third-party equity + sponsor equity = 100%**, and reports
the resulting minimum DSCR against the market floor rather than sizing to it.
The deals come out *gearing-bound with DSCR headroom*, which is the honest
result and is what the binding-constraint reporting exists to say. In the real
market the headroom is taken as **back-leverage at the sponsor holdco**, which
Structura does not model (``LIMITS_STRUCTURES.md``).

Usage
-----
::

    from engine.reference_deals import REFERENCE_DEALS, reference_deal

    deal = reference_deal("storage_bess_contracted")
    comparison = deal.compare()
    print(comparison.headline)
    for row in comparison.sources_and_uses_table():
        print(row["structure"], row["sources_total"], row["uses_total"])

Not advice. Illustrative modelling only (SPEC §4.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping

from engine import AmortizationStyle, DebtTerms, ProjectInputs
from engine.defaults import (
    MIN_DSCR,
    NRF_2026,
    RevenueContractType,
    Technology as EngineTechnology,
)
from engine.structures import (
    FlipConfig,
    FlipTrigger,
    PreferredConfig,
    SaleLeasebackConfig,
    SponsorTaxProfile,
    StructureConfigs,
    StructureContext,
    TFlipConfig,
    TransferConfig,
    build_context,
    compare_structures,
)
from engine.structures.selector import StructureComparison
from engine.tax import (
    DepreciationMethod,
    MacrInputs,
    MacrMethod,
    TaxProject,
    TaxScenario,
    Technology as TaxTechnology,
)

__all__ = [
    "REFERENCE_DEALS_VERIFIED_ON",
    "Assumption",
    "ExpectedOutcome",
    "ReferenceDeal",
    "REFERENCE_DEALS",
    "reference_deal",
    "reference_deal_keys",
]

#: Date the sourced assumptions in this module were last checked. The market
#: benchmarks come from :mod:`engine.defaults`, which carries its own date.
REFERENCE_DEALS_VERIFIED_ON: date = date(2026, 8, 6)

_NO_PUBLIC_SOURCE = (
    "PLACEHOLDER - no free public source. SPEC.md §5.1 records that no free "
    "source of PPA or offtake prices exists (LevelTen's index is "
    "subscriber-only); tax-equity, preferred and lease pricing is quoted deal "
    "by deal (LIMITS_STRUCTURES.md §4). Override before relying on any output."
)

_ATB_ANCHOR = (
    "PLACEHOLDER - round order-of-magnitude figure. The NLR Annual Technology "
    "Baseline 2024 v4.0.0 (SPEC.md §5.1, CC-BY 4.0, DOI 10.25984/2377191) is "
    "the intended anchor; this module carries no data dependency, so the figure "
    "is not read from it and is not a citation."
)

_STRUCTURA_CONVENTION = (
    "Structura modelling convention, derived from the sources-and-uses "
    "identity rather than from market data. Stated so it is auditable."
)


@dataclass(frozen=True, slots=True)
class Assumption:
    """One input, with the provenance that makes it auditable or a placeholder.

    Mirrors :class:`engine.defaults.Benchmark` deliberately: same discipline,
    same honesty, but scoped to a single deal rather than to the market.
    """

    name: str
    value: float | str
    unit: str
    source: str
    verified_on: date = REFERENCE_DEALS_VERIFIED_ON
    is_placeholder: bool = False
    note: str = ""

    def describe(self) -> str:
        flag = "PLACEHOLDER " if self.is_placeholder else ""
        return (
            f"{flag}{self.name} = {self.value} {self.unit} | {self.source} "
            f"| verified {self.verified_on.isoformat()}"
            + (f" | {self.note}" if self.note else "")
        )


@dataclass(frozen=True, slots=True)
class ExpectedOutcome:
    """The band each reference deal is calibrated to, asserted by the tests.

    Not a forecast and not a target the engine solves for — a **regression
    fence**. If a change to the engine moves a reference deal outside its band,
    either the change is wrong or the calibration needs revisiting, and either
    way somebody has to look.
    """

    #: Inclusive band for the **winning** structure's sponsor after-tax IRR,
    #: on the basis it was actually ranked on.
    winner_sponsor_irr: tuple[float, float] | None
    #: Inclusive envelope every feasible structure's *meaningful* IRR must sit
    #: inside. Wide on purpose: a structure that loses badly is a legitimate
    #: result, an impossible rate is not.
    all_meaningful_irr: tuple[float, float]
    #: Published DSCR floor the achieved minimum DSCR must clear.
    min_dscr_floor: float
    #: How many of the five structures should be feasible.
    feasible_structures: int
    #: Maximum tolerated §704(b) capital-account breach periods across all
    #: structures. Zero where the calibration eliminates them entirely.
    max_capital_account_breach_periods: int = 0


@dataclass(frozen=True, slots=True)
class ReferenceDeal:
    """One fully specified, calibrated deal, ready to run through the selector."""

    key: str
    name: str
    summary: str
    project: ProjectInputs
    debt_terms: DebtTerms
    tax_project: TaxProject
    tax_scenario: TaxScenario
    sponsor: SponsorTaxProfile
    configs: StructureConfigs
    assumptions: tuple[Assumption, ...]
    expected: ExpectedOutcome
    discount_rate: float = 0.10
    dscr_benchmark: str = ""
    calibration_note: str = ""

    def placeholder_assumptions(self) -> tuple[Assumption, ...]:
        return tuple(a for a in self.assumptions if a.is_placeholder)

    def placeholder_warning(self) -> str:
        names = ", ".join(a.name for a in self.placeholder_assumptions())
        return (
            f"PLACEHOLDER inputs in reference deal '{self.key}': {names}. "
            f"No free public source exists for offtake pricing, tax-equity "
            f"pricing or lease pricing; these are round, plausible stand-ins "
            f"and every output below inherits their uncertainty."
        )

    def build_context(self) -> StructureContext:
        return build_context(
            self.project,
            self.debt_terms,
            self.tax_project,
            tax_scenario=self.tax_scenario,
            sponsor=self.sponsor,
            discount_rate=self.discount_rate,
        )

    def compare(self, context: StructureContext | None = None) -> StructureComparison:
        """Run the five-structure comparison for this deal."""
        return compare_structures(
            self.project,
            self.debt_terms,
            self.tax_project,
            self.configs,
            tax_scenario=self.tax_scenario,
            sponsor=self.sponsor,
            discount_rate=self.discount_rate,
            context=context or self.build_context(),
        )


# ---------------------------------------------------------------------------
# Shared assumption text
# ---------------------------------------------------------------------------


def _dscr_assumption(
    technology: EngineTechnology, contract: RevenueContractType, value: float
) -> Assumption:
    bench = MIN_DSCR[(technology, contract)]
    return Assumption(
        name="target_dscr",
        value=value,
        unit="x",
        source=bench.source,
        verified_on=bench.verified_on,
        note=(
            f"Published range {bench.low}-{bench.high}x for "
            f"{technology.value}/{contract.value}. {bench.note}"
        ),
    )


def _spread_assumption(rate: float, note: str) -> Assumption:
    return Assumption(
        name="interest_rate",
        value=rate,
        unit="all-in nominal p.a.",
        source=NRF_2026 + "; SOFR is a labelled placeholder (engine.defaults)",
        note=note,
    )


_FLIP_DATE_ASSUMPTION = Assumption(
    name="flip_trigger",
    value="fixed_date, operating year 6",
    unit="",
    source=(
        "§50(a)(1): the investment credit vests 20% per full year, so a "
        "reduction of a partner's interest by more than one third inside five "
        "years recaptures the unvested balance."
    ),
    note=(
        "A yield-based flip on a 30-40% ITC deal solves to well inside year one "
        "- the credit alone repays the investor - and Structura flags that as a "
        "BLOCKING recapture risk. The market answer is a date, not a yield: "
        "these deals therefore flip on a fixed date past the recapture period, "
        "which SPEC §6.2 lists alongside the yield-based form."
    ),
)


# ---------------------------------------------------------------------------
# 1. Storage (BESS), contracted — lead with this (SPEC §2.1, §6.4)
# ---------------------------------------------------------------------------
# OBBBA left standalone storage untouched by the wind/solar cliff: full §48E on
# a begin-construction basis through 2033, then 75% (2034), 50% (2035), zero
# from 2036. That seven-year runway is why SPEC §6.4 says lead with storage.

_STORAGE_CAPEX = 140_000_000.0
_STORAGE_EQUITY_AT_COD = 80_875_518.0  # solved by the Phase 1 circularity

_storage_flip = FlipConfig(
    trigger=FlipTrigger.FIXED_DATE,
    fixed_flip_year=6.0,
    target_after_tax_irr=0.065,
    investor_commitment=53_000_000.0,
    pre_flip_te_cash=0.50,
    post_flip_te_cash=0.05,
    investor_dro_cap=20_000_000.0,
)

#: The T-flip investor buys **depreciation and cash only** — the credit is sold
#: under §6418 — so it writes a much smaller cheque, and it bears no share of
#: the §50(c)(3) basis reduction because §50(c)(5) allocates that adjustment in
#: the same ratio as the credit. Both facts are modelled explicitly rather than
#: inherited from the plain flip's config.
_storage_tflip_inner = FlipConfig(
    trigger=FlipTrigger.FIXED_DATE,
    fixed_flip_year=6.0,
    target_after_tax_irr=0.065,
    investor_commitment=15_000_000.0,
    pre_flip_te_cash=0.35,
    post_flip_te_cash=0.05,
    pre_flip_te_credit=0.0,
    post_flip_te_credit=0.05,
    # Twice the commitment. Large, and stated rather than tuned quietly: it is
    # what it takes to keep this investor's §704(b) capital account above its
    # floor in every period. A real LLC agreement would instead restrict the
    # distribution or carry a qualified income offset, neither of which
    # Structura models (LIMITS_STRUCTURES.md §1.5).
    investor_dro_cap=30_000_000.0,
)

STORAGE_BESS_CONTRACTED = ReferenceDeal(
    key="storage_bess_contracted",
    name="100 MW / 400 MWh BESS, contracted toll, post-OBBBA §48E",
    summary=(
        "A four-hour lithium-ion battery on a fifteen-year tolling agreement, "
        "placed in service 2027. Standalone storage keeps full §48E on a "
        "begin-construction basis to 2033 (OBBBA, SPEC §2.1), so unlike solar "
        "and wind this is forward pipeline rather than safe-harboured "
        "inventory - which is why SPEC §6.4 says lead the product with it."
    ),
    project=ProjectInputs(
        name="Reference BESS - 100 MW / 400 MWh, contracted",
        technology=EngineTechnology.STORAGE,
        capacity_mw=100.0,
        capex=_STORAGE_CAPEX,
        construction_months=18,
        cod_date=date(2027, 1, 1),
        opex_year1=3_000_000.0,
        opex_escalation=0.025,
        # Revenue is a tolling capacity payment, not an energy sale, so the
        # volume driver is set to unity and the whole payment carried on the
        # price line. A BESS on a toll is paid for availability.
        production_p50=1.0,
        degradation=0.0,
        contracted_price=15_500_000.0,
        contracted_share=1.0,
        contracted_escalation=0.02,
        contract_years=15.0,
        merchant_price=9_300_000.0,
        merchant_escalation=0.02,
        project_life_years=20.0,
        periods_per_year=1,
    ),
    debt_terms=DebtTerms(
        target_dscr=1.20,
        tenor_years=15.0,
        interest_rate=0.0575,
        amortization=AmortizationStyle.SCULPTED,
        max_gearing=0.45,
        tail_years=2.0,
        dsra_months=6.0,
    ),
    tax_project=TaxProject(
        technology=TaxTechnology.STORAGE,
        capacity_mw=100.0,
        capex=_STORAGE_CAPEX,
        placed_in_service_date=date(2027, 1, 1),
        begin_construction_date=date(2026, 3, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        macr_inputs=MacrInputs(
            method=MacrMethod.USER_ASSERTED, asserted_ratio=0.80
        ),
    ),
    tax_scenario=TaxScenario(
        bonus_rate=0.0, depreciation_method=DepreciationMethod.MACRS_5
    ),
    # A pure-play developer: no tax capacity of its own. That is the entire
    # reason the tax-equity and transfer markets exist ($63bn of credit
    # monetisation in 2025, SPEC §2.2) and it is what makes the five-structure
    # comparison a real question rather than an arithmetic exercise.
    sponsor=SponsorTaxProfile(
        tax_rate=0.21, can_use_credits=False, can_use_depreciation=False
    ),
    configs=StructureConfigs(
        flip=_storage_flip,
        t_flip=TFlipConfig(
            flip=_storage_tflip_inner,
            transferred_credit_share=1.0,
            settlement_year_index=0,
            # Market practice, and the reason for it is a modelling result:
            # §6418(b) excludes transfer proceeds from gross income, so paying
            # them into the partnership distributes cash with no matching book
            # allocation and drives the tax-equity capital account below its
            # floor for the rest of the deal. Selling at the holdco keeps the
            # proceeds outside the capital accounts entirely.
            proceeds_to_partnership=False,
        ),
        preferred=PreferredConfig(
            commitment=48_500_000.0,
            cash_priority_share=0.75,
            investor_dro_cap=25_000_000.0,
        ),
        transfer=TransferConfig(settlement_year_index=0),
        sale_leaseback=SaleLeasebackConfig(
            lease_term_years=15.0,
            asset_useful_life_years=20.0,
            months_after_placed_in_service=1,
        ),
    ),
    assumptions=(
        Assumption(
            name="capex",
            value=1_400.0,
            unit="US$ per kW (US$350/kWh on a 4-hour system)",
            source=_ATB_ANCHOR,
            is_placeholder=True,
        ),
        Assumption(
            name="contracted_revenue",
            value=15_500_000.0,
            unit="US$ per year, year 1 (≈US$12.9/kW-month)",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
            note=(
                "A tolling capacity payment. The original demo case carried "
                "revenue of 14% of capex, which no storage asset earns; this is "
                "11% of capex and rises with a 2% escalator."
            ),
        ),
        Assumption(
            name="opex",
            value=3_000_000.0,
            unit="US$ per year, year 1 (US$30/kW-year)",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
        ),
        _dscr_assumption(
            EngineTechnology.STORAGE, RevenueContractType.CONTRACTED, 1.20
        ),
        _spread_assumption(
            0.0575,
            "SOFR placeholder 4.00% + 175bps permanent (NRF publishes "
            "162.5-187.5bps; mid-point). Fully contracted, so no merchant adder.",
        ),
        Assumption(
            name="max_gearing",
            value=0.45,
            unit="debt / total project cost",
            source=_STRUCTURA_CONVENTION,
            note=(
                "Not the 75% credit-agreement cap. The §48E credit is a source, "
                "not a return: at 30% of capex it displaces equity, so senior "
                "debt is capped at 45% to leave the stack at exactly 100% once "
                "the tax-equity cheque and the sponsor's own equity are in. "
                "The achieved minimum DSCR is reported against the 1.20x market "
                "floor; the headroom would be taken as holdco back-leverage, "
                "which Structura does not model."
            ),
        ),
        _FLIP_DATE_ASSUMPTION,
        Assumption(
            name="tax_equity_commitment",
            value=53_000_000.0,
            unit="US$ (38% of capex)",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
            note=(
                "Sized so senior debt + tax equity + sponsor equity = 100% of "
                "the funding requirement, leaving the sponsor 19% of the stack."
            ),
        ),
        Assumption(
            name="t_flip_tax_equity_commitment",
            value=15_000_000.0,
            unit="US$",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
            note=(
                "Materially smaller than the plain-flip cheque because the "
                "T-flip investor buys depreciation and cash only - the credit "
                "is sold under §6418."
            ),
        ),
        Assumption(
            name="investor_dro_cap",
            value=20_000_000.0,
            unit="US$ (38% of the tax-equity commitment)",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
            note=(
                "A capped deficit restoration obligation. Zero is also market "
                "(the investor relies on its share of minimum gain instead); a "
                "capped DRO is used here because it is what keeps the §704(b) "
                "capital account above its floor in every period of this deal."
            ),
        ),
    ),
    expected=ExpectedOutcome(
        winner_sponsor_irr=(0.08, 0.16),
        all_meaningful_irr=(-0.05, 0.30),
        min_dscr_floor=1.20,
        feasible_structures=5,
        max_capital_account_breach_periods=0,
    ),
    dscr_benchmark="storage / contracted, 1.15-1.20x (NRF 2026, SPEC §2.7)",
    calibration_note=(
        "Gearing-bound at 45% with DSCR headroom over the 1.20x floor. The "
        "binding constraint is the capital stack, not the lender - which is "
        "what an ITC deal looks like once the credit is treated as a source."
    ),
)


# ---------------------------------------------------------------------------
# 2. Solar, safe-harboured — began construction before the 2026-07-04 cliff
# ---------------------------------------------------------------------------
# SPEC §2.1: wind and solar must have begun construction on or before
# 2026-07-04. That deadline passed 33 days before the spec was written, so the
# forward solar pipeline is safe-harboured inventory. This deal is on the right
# side of it and keeps the four-year continuity window.

_SOLAR_CAPEX = 180_000_000.0

_solar_flip = FlipConfig(
    trigger=FlipTrigger.FIXED_DATE,
    fixed_flip_year=6.0,
    target_after_tax_irr=0.065,
    investor_commitment=55_800_000.0,
    pre_flip_te_cash=0.50,
    post_flip_te_cash=0.05,
    investor_dro_cap=19_500_000.0,
)

_solar_tflip_inner = FlipConfig(
    trigger=FlipTrigger.FIXED_DATE,
    fixed_flip_year=6.0,
    target_after_tax_irr=0.065,
    investor_commitment=15_500_000.0,
    pre_flip_te_cash=0.35,
    post_flip_te_cash=0.05,
    pre_flip_te_credit=0.0,
    post_flip_te_credit=0.05,
    #: Twice the commitment - see the storage deal's note.
    investor_dro_cap=31_000_000.0,
)

SOLAR_SAFE_HARBOURED = ReferenceDeal(
    key="solar_safe_harboured",
    name="150 MWac solar PV, safe-harboured before the 2026-07-04 cliff",
    summary=(
        "A utility-scale PV project that began construction on 2026-03-01 - "
        "before the OBBBA begin-construction cliff of 2026-07-04 - and is "
        "placed in service in 2028, inside the four-year continuity window. A "
        "project that missed the cliff would have to be in service by "
        "2027-12-31 or receive nothing, and the selector's credit gate would "
        "disqualify both credit-dependent structures."
    ),
    project=ProjectInputs(
        name="Reference solar - 150 MWac, 20-year PPA, safe-harboured",
        technology=EngineTechnology.SOLAR,
        capacity_mw=150.0,
        capex=_SOLAR_CAPEX,
        construction_months=18,
        cod_date=date(2028, 1, 1),
        opex_year1=2_700_000.0,
        opex_escalation=0.025,
        production_p50=330_000.0,
        degradation=0.005,
        contracted_price=48.0,
        contracted_share=1.0,
        contracted_escalation=0.015,
        contract_years=20.0,
        merchant_price=28.8,
        merchant_escalation=0.015,
        project_life_years=30.0,
        periods_per_year=1,
    ),
    debt_terms=DebtTerms(
        target_dscr=1.30,
        tenor_years=18.0,
        interest_rate=0.0575,
        amortization=AmortizationStyle.SCULPTED,
        max_gearing=0.55,
        tail_years=2.0,
        dsra_months=6.0,
    ),
    tax_project=TaxProject(
        technology=TaxTechnology.SOLAR,
        capacity_mw=150.0,
        capex=_SOLAR_CAPEX,
        placed_in_service_date=date(2028, 1, 1),
        begin_construction_date=date(2026, 3, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        macr_inputs=MacrInputs(
            method=MacrMethod.USER_ASSERTED, asserted_ratio=0.80
        ),
    ),
    tax_scenario=TaxScenario(
        bonus_rate=0.0, depreciation_method=DepreciationMethod.MACRS_5
    ),
    sponsor=SponsorTaxProfile(
        tax_rate=0.21, can_use_credits=False, can_use_depreciation=False
    ),
    configs=StructureConfigs(
        flip=_solar_flip,
        t_flip=TFlipConfig(
            flip=_solar_tflip_inner,
            transferred_credit_share=1.0,
            settlement_year_index=0,
            proceeds_to_partnership=False,
        ),
        preferred=PreferredConfig(
            commitment=47_200_000.0,
            cash_priority_share=0.75,
            investor_dro_cap=25_800_000.0,
        ),
        transfer=TransferConfig(settlement_year_index=0),
        sale_leaseback=SaleLeasebackConfig(
            lease_term_years=20.0,
            asset_useful_life_years=30.0,
            months_after_placed_in_service=1,
        ),
    ),
    assumptions=(
        Assumption(
            name="capex",
            value=1_200.0,
            unit="US$ per kWac",
            source=_ATB_ANCHOR,
            is_placeholder=True,
        ),
        Assumption(
            name="production_p50",
            value=330_000.0,
            unit="MWh in year 1 (25.1% net capacity factor)",
            source=_ATB_ANCHOR,
            is_placeholder=True,
            note="Site-specific. PVWatts v8 at developer.nlr.gov is the free "
            "source; this module carries no network dependency.",
        ),
        Assumption(
            name="ppa_price",
            value=48.0,
            unit="US$/MWh, year 1, 1.5% escalator, 20-year term",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
            note=(
                "SPEC §5.1: no free source of PPA prices exists. Use ATB LCOE "
                "as the sanity anchor and enter a real price."
            ),
        ),
        Assumption(
            name="opex",
            value=2_700_000.0,
            unit="US$ per year, year 1 (US$18/kWac-year)",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
        ),
        _dscr_assumption(
            EngineTechnology.SOLAR, RevenueContractType.CONTRACTED, 1.30
        ),
        _spread_assumption(
            0.0575,
            "SOFR placeholder 4.00% + 175bps permanent. Fully contracted for "
            "20 of 30 years; the merchant tail sits outside the 18-year tenor.",
        ),
        Assumption(
            name="max_gearing",
            value=0.55,
            unit="debt / total project cost",
            source=_STRUCTURA_CONVENTION,
            note=(
                "Set so the stack closes at 100% with a 30% §48E credit "
                "monetised. See the storage deal's note - the reasoning is the "
                "same and it is the single most important calibration decision "
                "in this module."
            ),
        ),
        Assumption(
            name="begin_construction_date",
            value="2026-03-01",
            unit="",
            source=(
                "OBBBA (P.L. 119-21) as recorded at SPEC.md §2.1, verified "
                "2026-08-06: wind and solar must have begun construction on or "
                "before 2026-07-04."
            ),
            note=(
                "Established by physical work. The 5% cost safe harbor is also "
                "available today because *Oregon Environmental Council v. IRS*, "
                "No. 25-4400 (CKK) vacated Notice 2025-42 on 2026-06-06 - but "
                "an appeal is pending, so a deal relying on it should be run "
                "through the litigation scenario (SPEC §2.5)."
            ),
        ),
        _FLIP_DATE_ASSUMPTION,
        Assumption(
            name="tax_equity_commitment",
            value=55_800_000.0,
            unit="US$ (31% of capex)",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
        ),
    ),
    expected=ExpectedOutcome(
        winner_sponsor_irr=(0.07, 0.16),
        all_meaningful_irr=(-0.05, 0.30),
        min_dscr_floor=1.30,
        feasible_structures=5,
        max_capital_account_breach_periods=0,
    ),
    dscr_benchmark="solar / contracted, 1.25-1.30x (NRF 2026, SPEC §2.7)",
    calibration_note=(
        "Gearing-bound at 55% with DSCR headroom over the 1.30x floor, for the "
        "same reason as the storage deal: a 30% §48E credit is a source, not a "
        "return. The T-flip carries a deficit restoration obligation of twice "
        "the tax-equity commitment, which is what keeps every §704(b) capital "
        "account above its floor in the absence of a qualified income offset."
    ),
)


# ---------------------------------------------------------------------------
# 3. Data centre powered shell — the volume story, and no credit at all
# ---------------------------------------------------------------------------
# SPEC §2.7: >$200bn of data-centre project debt in 2025; Morgan Stanley
# projects $250-300bn of hyperscaler debt in 2026; NRF publishes DSCR of
# 1.05-1.15x and pricing of SOFR+250 to 425. SPEC §6.4 pairs it with storage as
# the technology to lead with.
#
# It is also the deal that shows the credit gate doing its job. A powered shell
# is not §48E property: there is no clean-electricity investment credit, so the
# §6418 transfer and the T-flip - which is *defined* by its transfer leg - are
# not structures at all here, and the selector says so with the rule attached.

_DC_CAPEX = 480_000_000.0

_dc_flip = FlipConfig(
    trigger=FlipTrigger.FIXED_DATE,
    fixed_flip_year=6.0,
    target_after_tax_irr=0.065,
    investor_commitment=67_100_000.0,
    pre_flip_te_cash=0.50,
    post_flip_te_cash=0.05,
    investor_dro_cap=26_800_000.0,
)

DATA_CENTER_POWERED_SHELL = ReferenceDeal(
    key="data_center_powered_shell",
    name="48 MW data-centre powered shell, 15-year hyperscaler lease",
    summary=(
        "A powered shell on a fifteen-year triple-net lease to an "
        "investment-grade hyperscaler. NRF publishes DSCR of 1.05-1.15x and "
        "pricing of SOFR+250 to 425 for the asset class (SPEC §2.7), which is "
        "materially more leverage and materially wider spreads than a "
        "contracted renewable. No §48E credit attaches to a shell, so the "
        "direct transfer and the T-flip are disqualified by the selector's "
        "credit gate - which is the point of running them anyway."
    ),
    project=ProjectInputs(
        name="Reference data centre - 48 MW powered shell",
        technology=EngineTechnology.DATA_CENTER,
        capacity_mw=48.0,
        capex=_DC_CAPEX,
        construction_months=24,
        cod_date=date(2028, 1, 1),
        opex_year1=6_000_000.0,
        opex_escalation=0.025,
        # Triple-net rent, so the volume driver is unity and the whole payment
        # sits on the price line, as for the BESS toll.
        production_p50=1.0,
        degradation=0.0,
        contracted_price=58_000_000.0,
        contracted_share=1.0,
        contracted_escalation=0.025,
        contract_years=15.0,
        merchant_price=40_600_000.0,
        merchant_escalation=0.02,
        project_life_years=25.0,
        periods_per_year=1,
    ),
    debt_terms=DebtTerms(
        target_dscr=1.15,
        tenor_years=15.0,
        interest_rate=0.07375,
        amortization=AmortizationStyle.SCULPTED,
        max_gearing=0.75,
        tail_years=2.0,
        dsra_months=6.0,
    ),
    # A powered shell is not clean-electricity property. ``eligible_basis=0``
    # is how that fact is expressed: the technology tag is inert once the
    # eligible basis is nil, and engine.tax carries no DATA_CENTER member
    # because no credit section reaches one.
    tax_project=TaxProject(
        technology=TaxTechnology.STORAGE,
        capacity_mw=48.0,
        capex=_DC_CAPEX,
        eligible_basis=0.0,
        placed_in_service_date=date(2028, 1, 1),
        begin_construction_date=date(2026, 1, 1),
        physical_work_commenced=True,
        is_pwa_compliant=True,
        macr_inputs=MacrInputs(
            method=MacrMethod.USER_ASSERTED, asserted_ratio=0.80
        ),
    ),
    # 39-year straight line, not MACRS-5: a building is not energy property.
    tax_scenario=TaxScenario(
        bonus_rate=0.0, depreciation_method=DepreciationMethod.SL_39
    ),
    # Unlike the developer sponsors above, a data-centre sponsor is normally a
    # taxpayer and can use its own depreciation. That single switch is what
    # makes the answer different, and it is why SponsorTaxProfile exists.
    sponsor=SponsorTaxProfile(
        tax_rate=0.21, can_use_credits=False, can_use_depreciation=True
    ),
    configs=StructureConfigs(
        flip=_dc_flip,
        t_flip=TFlipConfig(flip=_dc_flip, proceeds_to_partnership=False),
        preferred=PreferredConfig(
            commitment=60_400_000.0,
            cash_priority_share=0.60,
            investor_dro_cap=26_800_000.0,
            preferred_income_share=0.50,
            preferred_credit_share=0.50,
        ),
        transfer=TransferConfig(settlement_year_index=0),
        sale_leaseback=SaleLeasebackConfig(
            lease_term_years=20.0,
            asset_useful_life_years=25.0,
            months_after_placed_in_service=1,
        ),
    ),
    assumptions=(
        Assumption(
            name="capex",
            value=10_000.0,
            unit="US$ per kW of critical IT load",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
            note="Powered shell plus shell-and-core; excludes tenant fit-out.",
        ),
        Assumption(
            name="contracted_rent",
            value=58_000_000.0,
            unit="US$ per year, year 1 (≈US$101/kW-month), 2.5% escalator",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
        ),
        Assumption(
            name="opex",
            value=6_000_000.0,
            unit="US$ per year, year 1 (landlord-side only; lease is triple net)",
            source=_NO_PUBLIC_SOURCE,
            is_placeholder=True,
        ),
        _dscr_assumption(
            EngineTechnology.DATA_CENTER, RevenueContractType.CONTRACTED, 1.15
        ),
        _spread_assumption(
            0.07375,
            "SOFR placeholder 4.00% + 337.5bps, the mid-point of the "
            "SOFR+250-425 range NRF publishes for data centres (SPEC §2.7). "
            "Wider than any renewable in this library.",
        ),
        Assumption(
            name="max_gearing",
            value=0.75,
            unit="debt / total project cost",
            source=(
                "Customary non-recourse cap (engine.defaults.MAX_GEARING, "
                + NRF_2026
                + ")"
            ),
            note=(
                "Unlike the two credit deals, no ITC displaces equity here, so "
                "the ordinary 75% cap applies unmodified. The achieved minimum "
                "DSCR is reported against the 1.15x data-centre floor."
            ),
        ),
        Assumption(
            name="credit",
            value=0.0,
            unit="US$",
            source=(
                "§48E applies to qualified clean electricity facilities and "
                "energy storage technology. A powered shell is neither."
            ),
            note=(
                "Expressed as eligible_basis=0. The selector's credit gate then "
                "disqualifies the direct transfer and the T-flip, naming the "
                "reason - which is the correct answer, not a modelling gap."
            ),
        ),
        Assumption(
            name="depreciation",
            value="SL 39",
            unit="",
            source="§168(c): 39-year straight line for nonresidential real property.",
        ),
    ),
    expected=ExpectedOutcome(
        winner_sponsor_irr=(0.08, 0.18),
        all_meaningful_irr=(-0.05, 0.30),
        min_dscr_floor=1.15,
        feasible_structures=3,
        max_capital_account_breach_periods=0,
    ),
    dscr_benchmark=(
        "data centre / contracted, 1.05-1.15x (NRF 2026, SPEC §2.7); 1.05x is "
        "reserved for investment-grade hyperscaler portfolios"
    ),
    calibration_note=(
        "The only deal in the library where the ordinary 75% gearing cap "
        "applies unmodified, because there is no credit to displace equity. "
        "Two of the five structures are correctly disqualified."
    ),
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REFERENCE_DEALS: Mapping[str, ReferenceDeal] = {
    d.key: d
    for d in (
        STORAGE_BESS_CONTRACTED,
        SOLAR_SAFE_HARBOURED,
        DATA_CENTER_POWERED_SHELL,
    )
}


def reference_deal_keys() -> tuple[str, ...]:
    return tuple(REFERENCE_DEALS)


def reference_deal(key: str) -> ReferenceDeal:
    """Look up one reference deal, with a useful error if the key is wrong."""
    try:
        return REFERENCE_DEALS[key]
    except KeyError as exc:
        raise KeyError(
            f"No reference deal '{key}'. Available: "
            + ", ".join(reference_deal_keys())
        ) from exc
