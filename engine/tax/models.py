"""Input and output data structures for the current-law tax engine.

Deliberately self-contained: this package imports nothing from the rest of
``engine`` (SPEC §6.4 makes ``engine/tax`` the current-law module, and keeping
it dependency-free means it can be lifted into the ``/current-law`` page, the
narrator, or a separate service without dragging the sculpting spine along).

All result types are frozen dataclasses carrying (a) the numbers, (b) an ordered
list of :class:`DeterminationStep` explaining how the numbers arose, and (c) the
ids of the citations that authorise each step. (b) and (c) exist because SPEC
§4.2 requires every output to be traceable and SPEC §6.6 has a narrator layer
that must never invent a reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Mapping

from engine.tax.constants import (
    DEFAULT_BONUS_RATE,
    PTC_CREDIT_PERIOD_YEARS,
)
from engine.tax.enums import (
    AdderType,
    BeginConstructionMethod,
    Confidence,
    CreditSection,
    CreditType,
    DepreciationMethod,
    EligibilityPath,
    ForeignEntityStatus,
    MacrMethod,
    Notice202542Status,
    PhaseDownApplication,
    Technology,
)

__all__ = [
    # enums re-exported so callers can `from engine.tax.models import Technology`
    "Technology",
    "CreditType",
    "CreditSection",
    "EligibilityPath",
    "BeginConstructionMethod",
    "Notice202542Status",
    "DepreciationMethod",
    "AdderType",
    "MacrMethod",
    "PhaseDownApplication",
    "ForeignEntityStatus",
    "Confidence",
    # inputs
    "ComponentCost",
    "MacrInputs",
    "ForeignEntityFlags",
    "TaxProject",
    "TaxScenario",
    # outputs
    "DeterminationStep",
    "BeginConstructionResult",
    "AdderResult",
    "FeocResult",
    "CreditResult",
    "DepreciationPeriod",
    "DepreciationSchedule",
    "TransferResult",
    "TaxResult",
]


# ---------------------------------------------------------------------------
# Explanation primitive
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DeterminationStep:
    """One link in the chain of reasoning from project facts to a tax outcome.

    The narrator (SPEC §6.6) renders these verbatim. It never computes and never
    overrides, so if a conclusion is not explained by a step here, it cannot be
    explained to the user at all.
    """

    label: str
    outcome: str
    detail: str
    citation_ids: tuple[str, ...] = ()

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"{self.label}: {self.outcome} - {self.detail}"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ComponentCost:
    """One line of the Material Assistance Cost Ratio cost build-up.

    ``pfe_attributable_cost`` is the portion of this component's total direct
    cost attributable to a *prohibited foreign entity* - i.e. the numerator of
    the part that must be excluded when computing the MACR.
    """

    name: str
    total_direct_cost: float
    pfe_attributable_cost: float = 0.0
    supplier_certification_obtained: bool = False

    def __post_init__(self) -> None:
        if self.total_direct_cost < 0:
            raise ValueError(f"{self.name}: total_direct_cost must be >= 0")
        if not 0.0 <= self.pfe_attributable_cost <= self.total_direct_cost:
            raise ValueError(
                f"{self.name}: pfe_attributable_cost must lie in "
                f"[0, total_direct_cost]"
            )


@dataclass(frozen=True, slots=True)
class MacrInputs:
    """Everything needed to compute or assert a Material Assistance Cost Ratio.

    Three routes are supported, mirroring IRS Notice 2026-15:

    * ``SUPPLIER_CERTIFICATION`` - build the ratio up from ``components``, each
      backed by a supplier certification;
    * ``DEFAULT_COST_TABLE`` - use DOE-derived default cost percentages (the
      tables ship as a documented placeholder structure);
    * ``INTERIM_SAFE_HARBOR`` - property acquired under a binding written
      contract predating the effective date;
    * ``USER_ASSERTED`` - the modeller simply states the ratio, which is what a
      screening analyst will do before diligence.
    """

    method: MacrMethod = MacrMethod.USER_ASSERTED
    asserted_ratio: float | None = None
    components: tuple[ComponentCost, ...] = ()
    interim_safe_harbor_elected: bool = False
    #: Free-text note explaining the basis of the ratio, echoed into the audit
    #: trail. Diligence teams live and die by this field.
    basis_note: str = ""

    def __post_init__(self) -> None:
        if self.asserted_ratio is not None and not 0.0 <= self.asserted_ratio <= 1.0:
            raise ValueError("asserted_ratio must lie in [0, 1]")
        if self.method is MacrMethod.USER_ASSERTED and self.asserted_ratio is None:
            raise ValueError(
                "MacrMethod.USER_ASSERTED requires asserted_ratio to be set"
            )
        if self.method is MacrMethod.SUPPLIER_CERTIFICATION and not self.components:
            raise ValueError(
                "MacrMethod.SUPPLIER_CERTIFICATION requires at least one component"
            )


@dataclass(frozen=True, slots=True)
class ForeignEntityFlags:
    """FEOC status of the parties. See OBBBA §70512 and I.R.C. §7701(a)(51)."""

    #: Status of the taxpayer claiming the credit.
    taxpayer_status: ForeignEntityStatus = ForeignEntityStatus.NONE
    #: Status of the proposed §6418 transferee, if any. §70512(h) bars a
    #: transfer to a SPECIFIED_FOREIGN_ENTITY.
    transferee_status: ForeignEntityStatus = ForeignEntityStatus.NONE
    #: Whether the project received material assistance from a prohibited
    #: foreign entity at all. If False the MACR test is trivially satisfied,
    #: but the flag must still be affirmatively made.
    received_material_assistance_from_pfe: bool = True


@dataclass(frozen=True, slots=True)
class TaxScenario:
    """Modelled legal/behavioural assumptions, separate from project facts.

    Separating this from :class:`TaxProject` is what makes SPEC §2.5 a
    *scenario* rather than a hard-coded assumption: the same project can be run
    against current law and against the appeal outcome.
    """

    #: The litigation fork. Default is current law as of 2026-08-06.
    notice_2025_42_status: Notice202542Status = Notice202542Status.VACATED
    #: How the non-wind/solar phase-down interacts with the bonus amounts.
    phase_down_application: PhaseDownApplication = PhaseDownApplication.ALL_CREDIT
    #: §168(k) bonus rate applied to the reduced basis.
    bonus_rate: float = DEFAULT_BONUS_RATE
    #: Recovery method for the depreciable basis.
    depreciation_method: DepreciationMethod = DepreciationMethod.MACRS_5

    def __post_init__(self) -> None:
        if not 0.0 <= self.bonus_rate <= 1.0:
            raise ValueError("bonus_rate must lie in [0, 1]")


@dataclass(frozen=True, slots=True)
class TaxProject:
    """The facts of one project, as a tax analyst would state them.

    Only the four fields without defaults are genuinely required; everything
    else has a defensible default so a screening run needs minimal input
    (SPEC §7 M1: "minimal required fields").
    """

    technology: Technology
    capacity_mw: float
    capex: float
    placed_in_service_date: date

    # -- credit election ---------------------------------------------------
    credit_type: CreditType = CreditType.ITC
    #: Basis eligible for the ITC. Defaults to capex; in practice interconnect
    #: and some soft costs are excluded, which the caller reflects here.
    eligible_basis: float | None = None
    #: Expected annual production, used for the §45Y production credit.
    annual_production_mwh: float = 0.0

    # -- begin construction ------------------------------------------------
    begin_construction_date: date | None = None
    begin_construction_method: BeginConstructionMethod = (
        BeginConstructionMethod.PHYSICAL_WORK_TEST
    )
    #: Fraction of total facility cost paid or incurred as at the claimed BOC
    #: date. Relevant only to the 5% cost safe harbor.
    cost_incurred_pct_at_boc: float = 0.0
    #: Whether physical work of a significant nature had commenced. Relevant
    #: only to the Physical Work Test, which has no bright-line threshold.
    physical_work_commenced: bool = False
    #: Free-text description of the physical work relied upon. Included in the
    #: audit trail because the test is facts-and-circumstances.
    physical_work_description: str = ""

    # -- labour ------------------------------------------------------------
    #: Prevailing wage and apprenticeship compliance - the 5x multiplier.
    is_pwa_compliant: bool = True

    # -- adders ------------------------------------------------------------
    #: Domestic cost ratio actually achieved, as a fraction.
    domestic_content_pct: float = 0.0
    #: Whether the taxpayer elects the Notice 2025-08 safe-harbor percentages
    #: instead of an actual cost build-up.
    domestic_content_safe_harbor_elected: bool = False
    #: Asserted energy community qualification. Structura does not run the
    #: census-tract test; see UNVERIFIED.md.
    energy_community: bool = False
    #: Which statutory category is relied upon, for the audit trail:
    #: "brownfield", "statistical_area", "coal_closure".
    energy_community_category: str = ""

    # -- FEOC --------------------------------------------------------------
    macr_inputs: MacrInputs | None = None
    foreign_entity_flags: ForeignEntityFlags = field(default_factory=ForeignEntityFlags)

    # -- taxpayer ----------------------------------------------------------
    #: First day of the taxable year in which the credit arises. Drives the
    #: §70512(h) effective-date test (calendar-year taxpayers first tested
    #: 2026-01-01).
    taxable_year_begin: date | None = None

    def __post_init__(self) -> None:
        if self.capacity_mw <= 0:
            raise ValueError("capacity_mw must be > 0")
        if self.capex < 0:
            raise ValueError("capex must be >= 0")
        if not 0.0 <= self.domestic_content_pct <= 1.0:
            raise ValueError("domestic_content_pct must lie in [0, 1]")
        if not 0.0 <= self.cost_incurred_pct_at_boc <= 1.0:
            raise ValueError("cost_incurred_pct_at_boc must lie in [0, 1]")
        if self.eligible_basis is not None and self.eligible_basis < 0:
            raise ValueError("eligible_basis must be >= 0")

    @property
    def itc_eligible_basis(self) -> float:
        """Basis the ITC percentage is applied to. Defaults to full capex."""
        return self.capex if self.eligible_basis is None else self.eligible_basis

    @property
    def credit_section(self) -> CreditSection:
        """The Code section under which the credit arises."""
        return (
            CreditSection.SEC_48E
            if self.credit_type is CreditType.ITC
            else CreditSection.SEC_45Y
        )

    @property
    def effective_taxable_year_begin(self) -> date:
        """Taxable year begin, defaulting to the calendar year of PIS."""
        if self.taxable_year_begin is not None:
            return self.taxable_year_begin
        return date(self.placed_in_service_date.year, 1, 1)

    def with_(self, **changes: object) -> "TaxProject":
        """Return a copy with fields replaced - convenience for scenario runs."""
        return replace(self, **changes)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BeginConstructionResult:
    """Whether construction was validly begun, and by which route."""

    established: bool
    method: BeginConstructionMethod
    method_available: bool
    notice_2025_42_status: Notice202542Status
    notice_2025_42_applies: bool
    begin_construction_date: date | None
    #: End of the fourth calendar year following the BOC year.
    continuity_deadline: date | None
    continuity_satisfied: bool
    reason: str
    steps: tuple[DeterminationStep, ...] = ()
    citation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AdderResult:
    """One bonus credit amount, granted or denied, with the reason."""

    adder: AdderType
    granted: bool
    #: Percentage points added to the ITC rate (0 if denied or if PTC).
    itc_percentage_points: float
    #: Multiplicative uplift on the PTC amount (0 if denied or if ITC).
    ptc_multiplier: float
    threshold: float | None
    achieved: float | None
    reason: str
    confidence: Confidence
    citation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FeocResult:
    """Material Assistance Cost Ratio pass/fail.

    A ``passes=False`` result is *disqualifying*, not advisory. See
    :mod:`engine.tax.feoc`.
    """

    applies: bool
    passes: bool
    macr: float | None
    threshold: float | None
    threshold_is_placeholder: bool
    method: MacrMethod | None
    applicable_year: int | None
    reason: str
    steps: tuple[DeterminationStep, ...] = ()
    citation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CreditResult:
    """The credit itself: rate, amount, and the whole chain of reasoning."""

    credit_type: CreditType
    credit_section: CreditSection
    eligible: bool
    path: EligibilityPath

    #: ITC: fraction of eligible basis. PTC: US$/kWh.
    base_rate: float
    pwa_applied: bool
    adders: tuple[AdderResult, ...]
    #: Rate after base + PWA + adders, before the phase-down haircut.
    gross_rate: float
    #: Fraction of the otherwise-allowable credit surviving the §48E(e)
    #: phase-down (1.0 where no phase-down applies).
    phase_down_pct: float
    #: Final rate after every adjustment.
    final_rate: float

    #: ITC: one-off credit in US$. PTC: total nominal credit over the ten-year
    #: period, undiscounted.
    credit_amount: float
    #: PTC only: credit per year of the credit period.
    annual_credit_amount: float = 0.0
    credit_period_years: int = PTC_CREDIT_PERIOD_YEARS

    disqualification_reason: str = ""
    steps: tuple[DeterminationStep, ...] = ()
    citation_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def explanation(self) -> str:
        """Plain-English narrative of why the result is what it is."""
        return "\n".join(str(s) for s in self.steps)


@dataclass(frozen=True, slots=True)
class DepreciationPeriod:
    """One tax year of cost recovery."""

    year: int
    opening_basis: float
    bonus_deduction: float
    recovery_deduction: float
    total_deduction: float
    closing_basis: float


@dataclass(frozen=True, slots=True)
class DepreciationSchedule:
    """Full period-by-period cost recovery, with the §50(c)(3) adjustment shown."""

    method: DepreciationMethod
    original_basis: float
    itc_amount: float
    basis_reduction: float
    depreciable_basis: float
    bonus_rate: float
    bonus_deduction: float
    periods: tuple[DepreciationPeriod, ...]
    citation_ids: tuple[str, ...] = ()

    @property
    def total_deductions(self) -> float:
        return sum(p.total_deduction for p in self.periods)

    @property
    def deductions_by_year(self) -> tuple[float, ...]:
        return tuple(p.total_deduction for p in self.periods)


@dataclass(frozen=True, slots=True)
class TransferResult:
    """Economics of a §6418 transfer, or the reason it is blocked."""

    permitted: bool
    credit_section: CreditSection
    credit_face_value: float
    price_per_dollar: float
    gross_proceeds: float
    transaction_costs: float
    net_proceeds: float
    #: Net proceeds as a fraction of face value - the number a sponsor quotes.
    effective_net_price: float
    #: Discount to face, i.e. 1 - effective_net_price.
    discount_to_face: float
    #: When cash is expected, relative to the credit year.
    settlement_date: date | None
    blocked_reason: str = ""
    steps: tuple[DeterminationStep, ...] = ()
    citation_ids: tuple[str, ...] = ()
    market_context: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TaxResult:
    """Everything :func:`engine.tax.compute_tax` determined about one project."""

    project: TaxProject
    scenario: TaxScenario
    begin_construction: BeginConstructionResult
    feoc: FeocResult
    credit: CreditResult
    depreciation: DepreciationSchedule
    transfer: TransferResult | None = None

    @property
    def steps(self) -> tuple[DeterminationStep, ...]:
        """The full audit trail, in the order a reviewer would read it."""
        out: list[DeterminationStep] = []
        out.extend(self.begin_construction.steps)
        out.extend(self.feoc.steps)
        out.extend(self.credit.steps)
        if self.transfer is not None:
            out.extend(self.transfer.steps)
        return tuple(out)

    @property
    def citation_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for group in (
            self.begin_construction.citation_ids,
            self.feoc.citation_ids,
            self.credit.citation_ids,
            self.depreciation.citation_ids,
            self.transfer.citation_ids if self.transfer else (),
        ):
            ids.extend(group)
        seen: dict[str, None] = {}
        for i in ids:
            seen.setdefault(i, None)
        return tuple(seen)
